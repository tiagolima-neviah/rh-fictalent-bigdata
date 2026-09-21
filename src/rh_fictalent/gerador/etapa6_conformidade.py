"""Etapa 6 do gerador: conformidade e acesso (16 tabelas em `seguranca`, `treinamento` e `sst`).

É a última etapa, e a que responde "quem fez" e "estava em dia?":

- segurança: os cerca de 40 usuários internos ao longo do arco (os três nomes do caso e a
  retaguarda que cresce com a empresa, inclusive as contratações de 2026), o perfil de cada um
  com vigência, a matriz de permissão por módulo e a trilha de auditoria. A trilha não é ruído:
  cada CRIAR e EDITAR aponta para um registro que existe, no instante do carimbo dele, feito por
  alguém do setor e da filial que estava na casa naquele dia. As exportações crescem com a
  degradação: é o "exporta a planilha e cruza à mão" virando dado;
- treinamento: integração e normas regulamentadoras exigidas pela função, em turmas de segunda e
  quinta, com certificado que vence e reciclagem que atrasa quando a operação cede;
- SST: o exame admissional de todo contrato, o periódico de quem fica, o de retorno, o
  demissional quando a norma não dispensa, os programas legais por contrato de cliente, os
  riscos do posto (de onde vem o adicional da folha), os acidentes e a CAT.

O defeito do catálogo aqui é o SST-01, ASO vencido com a pessoa alocada. O gerador o conduz: a
cada periódico que vence, decide se o exame sai em dia ou atrasa, de modo que os dias alocados
sem ASO válido fechem o ano na proporção do catálogo (4% em 2024 e 2025, quase nada até 2022).

A etapa também fecha um ciclo do modelo: `ats.entrevista.usuario_id` nasce nulo na etapa 3,
porque o usuário só existe aqui. O preenchimento sai como retoque (`base["retoques"]`), gravado
na mesma transação, sem mexer no carimbo da entrevista.
"""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador import catalogos_conformidade as cc
from rh_fictalent.gerador import catalogos_financeiro as fin
from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, etapa3_pessoas, historia
from rh_fictalent.gerador.nucleo import FIM, INICIO, Tabelas, aleatorio, tabela
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.regua import Laudo, Medidas, Situacao, avaliar

HOJE = FIM.date()
ORDEM = (
    "seguranca.perfil",
    "seguranca.usuario",
    "seguranca.usuario_perfil",
    "seguranca.permissao",
    "treinamento.curso",
    "treinamento.curso_funcao",
    "treinamento.turma",
    "treinamento.turma_participante",
    "treinamento.certificado",
    "sst.tipo_exame",
    "sst.aso",
    "sst.programa_sst",
    "sst.risco_posto",
    "sst.acidente",
    "sst.cat",
    "seguranca.log_auditoria",
)
_mais_meses = etapa2_carteira._mais_meses
_registros = etapa2_carteira._registros
Evento = tuple[int, datetime, str, str, int | None, str, str | None, str | None]


@dataclass(frozen=True)
class Usuario:
    id: int
    nome: str
    login: str
    filial_id: int
    entrada: date
    saida: date | None
    papeis: tuple[tuple[date, str, str], ...]  # (desde, setor, cargo), em ordem

    def ativo_em(self, dia: date) -> bool:
        return self.entrada <= dia and (self.saida is None or dia <= self.saida)

    def papel_em(self, dia: date) -> tuple[str, str]:
        atual = self.papeis[0]
        for papel in self.papeis:
            if papel[0] <= dia:
                atual = papel
        return atual[1], atual[2]

    def segmentos(self) -> list[tuple[date, date, str, str]]:
        """(de, até, setor, cargo): um trecho por papel, até a saída ou o fim da história."""
        trechos = []
        for i, (desde, setor, cargo) in enumerate(self.papeis):
            proximo = (
                self.papeis[i + 1][0] - timedelta(days=1) if i + 1 < len(self.papeis) else None
            )
            trechos.append((desde, proximo or self.saida or HOJE, setor, cargo))
        return trechos


def _mes(dia: date) -> str:
    return f"{dia.year}-{dia.month:02d}"


def _dias_por_ano(de: date, ate: date) -> dict[int, int]:
    """Os dias do intervalo fechado [de, até], repartidos pelo ano em que caem."""
    dias: dict[int, int] = {}
    while de <= ate:
        fim_do_ano = min(ate, date(de.year, 12, 31))
        dias[de.year] = (fim_do_ano - de).days + 1
        de = fim_do_ano + timedelta(days=1)
    return dias


class _Conformidade:
    def __init__(self, t3: Tabelas, gabarito: dict[str, Any]) -> None:
        self.rng = aleatorio("etapa6_conformidade")
        self.relogio = 0
        self.t3 = t3
        self.mundo: Tabelas = gabarito["mundo"]
        self.carteira: Tabelas = gabarito["carteira"]
        r = _registros
        self.feriados = {
            f["data"] for f in r(self.mundo["cadastro.feriado"]) if f["abrangencia"] == "NACIONAL"
        }
        filiais = r(self.mundo["cadastro.filial"])
        self.id_da_filial = {f["codigo"]: int(f["id"]) for f in filiais}
        self.codigo_da_filial = {int(f["id"]): f["codigo"] for f in filiais}
        por_codigo = {f.codigo: f for f in cat.FUNCOES}
        self.funcao = {
            int(f["id"]): por_codigo[f["codigo"]] for f in r(self.mundo["cadastro.funcao"])
        }
        self.id_da_funcao = {f.codigo: i for i, f in self.funcao.items()}
        self.id_fornecedor = {razao: i for i, (razao, _) in enumerate(fin.FORNECEDORES, start=1)}
        self.reajuste = {
            a: float(np.prod([1 + v for k, v in cat.REAJUSTES.items() if 2018 < k <= a]))
            for a in bandas.ANOS
        }
        self.degradacao = {m: historia.degradacao(m) for m in historia.meses()}

        self.contratos_de_trabalho = sorted(
            r(t3["pessoas.contrato_trabalho"]), key=lambda k: (k["dt_admissao"], k["id"])
        )
        self.colaborador_criado = {
            int(c["id"]): c["criado_em"] for c in r(t3["pessoas.colaborador"])
        }
        self.alocacoes = r(t3["pessoas.alocacao"])
        self.alocacoes_de: dict[int, list[dict[str, Any]]] = {}
        for a in self.alocacoes:
            self.alocacoes_de.setdefault(int(a["colaborador_id"]), []).append(a)
        self.afastamentos_de: dict[int, list[dict[str, Any]]] = {}
        for f in r(t3["pessoas.afastamento"]):
            self.afastamentos_de.setdefault(int(f["colaborador_id"]), []).append(f)
        self.postos = {int(p["id"]): p for p in r(self.carteira["comercial.posto"])}
        self.contratos = {int(k["id"]): k for k in r(self.carteira["comercial.contrato"])}
        self.dias_alocados = dict.fromkeys(bandas.ANOS, 0)
        entra_e_sai = np.zeros((HOJE - INICIO).days + 2)
        for a in self.alocacoes:
            for ano, dias in _dias_por_ano(a["dt_inicio"], a["dt_fim"] or HOJE).items():
                self.dias_alocados[ano] += dias
            entra_e_sai[(a["dt_inicio"] - INICIO).days] += 1
            entra_e_sai[((a["dt_fim"] or HOJE) - INICIO).days + 1] -= 1
        self.alocados_no_dia = np.cumsum(entra_e_sai)

        self.usuarios = self._usuarios()
        self._quem: dict[tuple[str, int, date], list[Usuario]] = {}
        self.eventos: list[Evento] = []
        self.linhas: dict[str, list[dict[str, Any]]] = {}

    # ───────────────────────── calendário e relógio ─────────────────────────
    def util(self, dia: date, passo: int = 1) -> date:
        while dia.weekday() >= 5 or dia in self.feriados:
            dia += timedelta(days=passo)
        return dia

    def mais_dias_uteis(self, dia: date, quantos: int) -> date:
        for _ in range(quantos):
            dia = self.util(dia + timedelta(days=1))
        return dia

    def dia_de_turma(self, a_partir: date, semanal: bool) -> date:
        """Turma curta abre segunda e quinta; curso de mais de um dia, só na segunda."""
        dias = (0,) if semanal else (0, 3)
        while a_partir.weekday() not in dias or a_partir in self.feriados:
            a_partir += timedelta(days=1)
        return a_partir

    def carimbo(self, dia: date, inicio: int = 8, horas: int = 10) -> datetime:
        """Um horário comercial determinístico para o dia (barato: sem sorteio)."""
        self.relogio += 1
        hora, minuto = inicio + (self.relogio * 7919) % horas, (self.relogio * 104729) % 60
        return min(datetime.combine(max(dia, INICIO), time(hora, minuto)), FIM)

    def ceder(self, dia: date) -> float:
        return self.degradacao.get(_mes(dia), 0.0)

    # ───────────────────────── quem usa o sistema ─────────────────────────
    def _usuarios(self) -> list[Usuario]:
        usuarios = []
        for i, (nome, setor, cargo, filial, entrada, saida) in enumerate(cc.USUARIOS, start=1):
            papeis = [(entrada, setor, cargo)]
            papeis += [(d, s, c) for n, d, s, c in cc.PROMOCOES if n == nome]
            partes = etapa3_pessoas._sem_acento(nome.lower()).split()
            usuarios.append(
                Usuario(
                    i,
                    nome,
                    f"{partes[0]}.{partes[-1]}",
                    self.id_da_filial[filial],
                    entrada,
                    saida,
                    tuple(sorted(papeis)),
                )
            )
        return usuarios

    def quem(self, setor: str, filial_id: int, dia: date, chave: int) -> Usuario:
        """Quem do setor registrou aquilo naquele dia: a assistente da filial, senão a de outra
        filial, senão a coordenação; setor que ainda não existe é coberto por outro."""
        dia = min(max(dia, INICIO), HOJE)
        lista = self._quem.get((setor, filial_id, dia))
        if lista is None:
            lista = self._quem[(setor, filial_id, dia)] = self._candidatos(setor, filial_id, dia)
        return lista[chave % len(lista)]

    def _candidatos(self, setor: str, filial_id: int, dia: date) -> list[Usuario]:
        ativos = [(u, *u.papel_em(dia)) for u in self.usuarios if u.ativo_em(dia)]
        while True:
            do_setor = [(u, cargo) for u, s, cargo in ativos if s == setor]
            base = [u for u, cargo in do_setor if cargo not in ("COORDENADOR", "GERENTE", "SOCIO")]
            for lista in (
                [u for u in base if u.filial_id == filial_id],
                base,
                [u for u, _ in do_setor],
            ):
                if lista:
                    return lista
            setor = cc.COBERTURA_DO_SETOR[setor]

    def coordena(self, setor: str, filial_id: int, dia: date, chave: int) -> Usuario:
        dia = min(max(dia, INICIO), HOJE)
        for u in self.usuarios:
            if u.ativo_em(dia) and u.papel_em(dia) == (setor, "COORDENADOR"):
                return u
        return self.quem(setor, filial_id, dia, chave)

    def seguranca(self) -> None:
        agora = self.carimbo(INICIO, 8, 1)
        entrada = {"criado_em": agora, "atualizado_em": agora}
        self.linhas["seguranca.perfil"] = [
            {"codigo": codigo, "nome": nome, **entrada} for codigo, nome in cc.PERFIS
        ]
        id_perfil = {codigo: i for i, (codigo, _) in enumerate(cc.PERFIS, start=1)}
        self.linhas["seguranca.permissao"] = [
            {
                "perfil_id": id_perfil[perfil],
                "modulo": modulo,
                "acao": acao,
                "fl_permitido": acao in cc.PODE[perfil].get(modulo, ()),
                **entrada,
            }
            for perfil, _ in cc.PERFIS
            for modulo in cc.MODULOS
            for acao in cc.ACOES
        ]
        vinculos = []
        for u in self.usuarios:
            for de, ate, _, cargo in u.segmentos():
                encerrado = ate if (ate != HOJE or u.saida == HOJE) else None
                criado = self.carimbo(de, 8, 2)
                vinculos.append(
                    {
                        "usuario_id": u.id,
                        "perfil_id": id_perfil[cargo],
                        "filial_id": u.filial_id if cargo == "ASSISTENTE" else None,
                        "vigencia_inicio": de,
                        "vigencia_fim": encerrado,
                        "criado_em": criado,
                        "atualizado_em": self.carimbo(encerrado, 17, 1) if encerrado else criado,
                    }
                )
        self.linhas["seguranca.usuario_perfil"] = sorted(
            vinculos, key=lambda v: (v["vigencia_inicio"], v["usuario_id"])
        )

    def acessos(self) -> None:
        """LOGIN de cada dia útil e as exportações de planilha, que crescem com a degradação."""
        dia0 = np.datetime64(INICIO, "D")
        todos = dia0 + np.arange((HOJE - INICIO).days + 1)
        semana = (todos.astype("int64") + 3) % 7  # 1970-01-01 foi quinta: 0 = segunda
        uteis = todos[
            (semana < 5) & ~np.isin(todos, np.array(sorted(self.feriados), dtype="datetime64[D]"))
        ]
        ceder = np.array([self.ceder(d) for d in uteis.astype(object)])
        limite = np.datetime64(FIM, "s")
        for u in self.usuarios:
            for de, ate, setor, cargo in u.segmentos():
                no_trecho = (uteis >= np.datetime64(de, "D")) & (uteis <= np.datetime64(ate, "D"))
                dias, cede = uteis[no_trecho], ceder[no_trecho]
                chance = cc.CHANCE_DE_LOGIN_NO_DIA.get(cargo, cc.CHANCE_DE_LOGIN_PADRAO)
                veio = self.rng.random(len(dias)) < chance
                segundos = self.rng.integers(7 * 3600 + 1800, 9 * 3600 + 1800, size=len(dias))
                logins = dias.astype("datetime64[s]") + segundos.astype("timedelta64[s]")
                logins = logins[veio & (logins <= limite)]
                for quando in logins.astype("datetime64[us]").tolist():
                    self.eventos.append(
                        (u.id, quando, "seguranca", "usuario", u.id, "LOGIN", None, None)
                    )
                base, soma = cc.EXPORTACOES_POR_DIA[cargo]
                vezes = self.rng.poisson(base + soma * cede) * veio
                exporta = np.repeat(dias, vezes).astype("datetime64[s]")
                segundos = self.rng.integers(9 * 3600 + 1800, 17 * 3600 + 1800, size=len(exporta))
                alvos = self.rng.integers(0, len(cc.EXPORTA[setor]), size=len(exporta))
                linhas = self.rng.integers(40, 6000, size=len(exporta))
                momentos = exporta + segundos.astype("timedelta64[s]")
                no_prazo = momentos <= limite
                momentos = momentos[no_prazo].astype("datetime64[us]")
                alvos, linhas = alvos[no_prazo], linhas[no_prazo]
                for quando, alvo, n in zip(
                    momentos.tolist(), alvos.tolist(), linhas.tolist(), strict=True
                ):
                    modulo, nome = cc.EXPORTA[setor][alvo]
                    detalhe = json.dumps({"formato": "xlsx", "linhas": n})
                    self.eventos.append(
                        (u.id, quando, modulo, nome, None, "EXPORTAR", None, detalhe)
                    )

    def trilha_dos_registros(self) -> None:
        """CRIAR no carimbo de criação e EDITAR no de atualização dos registros que gente digita."""
        r = _registros
        filial_do_contrato = {int(k["id"]): int(k["filial_id"]) for k in self.contratos_de_trabalho}

        def registrar(
            nome: str, linhas: list[dict[str, Any]], setor: str, filial: Any, mudou: Any = None
        ) -> None:
            modulo, tabela_ = nome.split(".")
            for linha in linhas:
                rid, criado = int(linha["id"]), linha["criado_em"]
                quem = self.quem(setor, filial(linha), criado.date(), rid)
                self.eventos.append((quem.id, criado, modulo, tabela_, rid, "CRIAR", None, None))
                troca = mudou(linha) if mudou and linha["atualizado_em"] > criado else None
                if troca:
                    quem = self.quem(setor, filial(linha), linha["atualizado_em"].date(), rid + 1)
                    antes, depois = (json.dumps(x, ensure_ascii=False) for x in troca)
                    self.eventos.append(
                        (
                            quem.id,
                            linha["atualizado_em"],
                            modulo,
                            tabela_,
                            rid,
                            "EDITAR",
                            antes,
                            depois,
                        )
                    )

        def fechou(linha: dict[str, Any], campo: str, aberto: str) -> Any:
            if linha[campo] is None:
                return None
            return {"status": aberto}, {"status": linha["status"], campo: linha[campo].isoformat()}

        registrar(
            "ats.vaga",
            r(self.t3["ats.vaga"]),
            "RECRUTAMENTO",
            lambda v: int(v["filial_id"]),
            lambda v: fechou(v, "dt_fechamento", "ABERTA"),
        )
        registrar(
            "pessoas.contrato_trabalho",
            self.contratos_de_trabalho,
            "DP",
            lambda k: int(k["filial_id"]),
            lambda k: fechou(k, "dt_rescisao", "ATIVO"),
        )
        registrar(
            "pessoas.desligamento",
            r(self.t3["pessoas.desligamento"]),
            "DP",
            lambda d: filial_do_contrato[int(d["contrato_trabalho_id"])],
        )
        registrar(
            "comercial.cliente",
            r(self.carteira["comercial.cliente"]),
            "COMERCIAL",
            lambda c: 0,
            lambda c: None if c["ativo"] else ({"ativo": True}, {"ativo": False}),
        )
        registrar(
            "comercial.contrato",
            list(self.contratos.values()),
            "COMERCIAL",
            lambda k: int(k["filial_id"]),
            lambda k: fechou(k, "dt_encerramento", "ATIVO"),
        )

    def entrevistadores(self) -> pd.DataFrame:
        """Quem conduziu cada entrevista: a assistente de recrutamento da filial da vaga na
        interna; na do cliente, a coordenação, que é quem acompanha o candidato."""
        entrevistas = self.t3["ats.entrevista"][["id", "candidatura_id", "tipo", "dt_agendada"]]
        vagas = self.t3["ats.vaga"][["id", "filial_id"]].rename(columns={"id": "vaga_id"})
        candidaturas = self.t3["ats.candidatura"][["id", "vaga_id"]].rename(
            columns={"id": "candidatura_id"}
        )
        juntas = entrevistas.merge(candidaturas, on="candidatura_id").merge(vagas, on="vaga_id")
        usuarios = []
        for e in _registros(juntas):
            escolha = self.coordena if e["tipo"] == "CLIENTE" else self.quem
            dia, chave = e["dt_agendada"].date(), int(e["candidatura_id"])
            usuarios.append(escolha("RECRUTAMENTO", int(e["filial_id"]), dia, chave).id)
        return pd.DataFrame({"id": juntas["id"].astype(int), "usuario_id": usuarios})

    def fechar_seguranca(self) -> None:
        ultimo: dict[int, datetime] = {}
        for usuario_id, quando, *_, acao, _a, _n in self.eventos:
            if acao == "LOGIN" and quando > ultimo.get(usuario_id, datetime.min):
                ultimo[usuario_id] = quando
        usuarios = []
        for u in self.usuarios:
            criado = self.carimbo(u.entrada, 8, 1)
            saiu = self.carimbo(u.saida, 18, 1) if u.saida else None
            usuarios.append(
                {
                    "login": u.login,
                    "nome": u.nome,
                    "email": f"{u.login}@{cc.DOMINIO_DE_EMAIL}",
                    "colaborador_id": None,  # a retaguarda não está em pessoas.colaborador
                    "filial_id": u.filial_id,
                    "ativo": u.saida is None,
                    "dt_criacao": u.entrada,
                    "ultimo_acesso": ultimo.get(u.id),
                    "criado_em": criado,
                    "atualizado_em": max(x for x in (criado, saiu, ultimo.get(u.id)) if x),
                }
            )
        self.linhas["seguranca.usuario"] = usuarios
        self.eventos.sort(key=lambda e: (e[1], e[0], e[5]))
        colunas = (
            "usuario_id",
            "dt_evento",
            "modulo",
            "tabela",
            "registro_id",
            "acao",
            "valor_anterior",
            "valor_novo",
        )
        self.linhas["seguranca.log_auditoria"] = [
            {**dict(zip(colunas, e, strict=True)), "criado_em": e[1], "atualizado_em": e[1]}
            for e in self.eventos
        ]

    # ───────────────────────── treinamento ─────────────────────────
    def treinamento(self) -> None:
        agora = self.carimbo(INICIO, 8, 1)
        entrada = {"criado_em": agora, "atualizado_em": agora}
        self.curso = {c[0]: (i, *c[1:]) for i, c in enumerate(cc.CURSOS, start=1)}
        self.linhas["treinamento.curso"] = [
            {
                "codigo": codigo,
                "nome": nome,
                "tipo": tipo,
                "carga_horaria": carga,
                "validade_meses": validade,
                **entrada,
            }
            for codigo, nome, tipo, carga, validade, _, _ in cc.CURSOS
        ]
        exigencias: list[tuple[str, str, bool]] = [("INTEGRA", f.codigo, True) for f in cat.FUNCOES]
        exigencias += [
            ("NR06", f.codigo, True) for f in cat.FUNCOES if f.familia in cc.FAMILIAS_COM_EPI
        ]
        exigencias += [(c, f, o) for c, funcoes in cc.CURSO_DA_FUNCAO.items() for f, o in funcoes]
        self.linhas["treinamento.curso_funcao"] = [
            {
                "curso_id": self.curso[curso][0],
                "funcao_id": self.id_da_funcao[funcao],
                "fl_obrigatorio": obrigatorio,
                **entrada,
            }
            for curso, funcao, obrigatorio in exigencias
        ]
        obrigatorios: dict[str, list[str]] = {}
        self.opcionais: dict[str, list[str]] = {}
        for curso, funcao, obrigatorio in exigencias:
            (obrigatorios if obrigatorio else self.opcionais).setdefault(funcao, []).append(curso)

        # (curso, filial, dia, cliente) -> [(colaborador, presença, aprovado, nota)]
        self.turmas: dict[tuple[str, int, date, int], list[tuple[int, float, bool, float | None]]]
        self.turmas = {}
        self.na_turma: set[tuple[str, int, date, int]] = set()
        self.cobertura: dict[tuple[int, str], date] = {}
        for k in self.contratos_de_trabalho:
            colaborador, filial = int(k["colaborador_id"]), int(k["filial_id"])
            admissao, fim = k["dt_admissao"], k["dt_rescisao"] or HOJE
            for curso in obrigatorios[self.funcao[int(k["funcao_id"])].codigo]:
                vale = self.cobertura.get((colaborador, curso))
                if vale is None or vale < admissao + timedelta(days=30):
                    vale = self.cursar(colaborador, filial, curso, admissao, fim)
                while vale is not None and vale < fim:  # vence com a pessoa ainda na casa
                    cede, sorteio = self.ceder(vale), float(self.rng.random())
                    esquecida = cc.RECICLAGEM_ESQUECIDA_NA_CRISE * cede
                    atrasada = cc.RECICLAGEM_ATRASADA + cc.RECICLAGEM_ATRASADA_NA_CRISE * cede
                    if sorteio < esquecida:
                        break
                    if sorteio < esquecida + atrasada:
                        quando = vale + timedelta(days=int(self.rng.integers(15, 151)))
                    else:
                        quando = max(
                            admissao, vale - timedelta(days=int(self.rng.integers(10, 41)))
                        )
                    vale = self.cursar(colaborador, filial, curso, quando, fim)
        self.vender_turmas()
        self.materializar_turmas()

    def termino(self, curso: str, dia: date) -> date:
        return self.mais_dias_uteis(dia, math.ceil(self.curso[curso][3] / 8) - 1)

    def cursar(
        self, colaborador: int, filial: int, curso: str, a_partir: date, fim: date
    ) -> date | None:
        """Matricula na próxima turma; devolve até quando o certificado vale (None: não tirou)."""
        _, _, tipo, carga, validade, _, _ = self.curso[curso]
        for _ in range(3):  # quem reprova volta na semana seguinte
            dia = self.dia_de_turma(a_partir, semanal=carga > 8)
            termino = self.termino(curso, dia)
            if termino > min(fim, HOJE):
                return None
            if (curso, filial, dia, colaborador) in self.na_turma:
                a_partir = dia + timedelta(days=1)
                continue
            self.na_turma.add((curso, filial, dia, colaborador))
            presenca = (
                100.0
                if carga <= 8 or self.rng.random() < 0.8
                else float(self.rng.integers(70, 100))
            )
            nota = None
            if tipo != "COMPORTAMENTAL":
                reprova = self.rng.random() < cc.CHANCE_DE_REPROVAR
                nota = round(
                    float(self.rng.uniform(3.0, 5.9) if reprova else self.rng.uniform(6.0, 10.0)), 1
                )
            aprovado = presenca >= 75 and (nota is None or nota >= 6)
            self.turmas.setdefault((curso, filial, dia, 0), []).append(
                (colaborador, presenca, aprovado, nota)
            )
            if aprovado:
                vale = _mais_meses(termino, validade) if validade else date.max
                volta = termino + timedelta(days=cc.INTEGRACAO_VALE_POR_DIAS)
                self.cobertura[(colaborador, curso)] = volta if curso == "INTEGRA" else vale
                return vale
            a_partir = dia + timedelta(days=7)
        return None

    def vender_turmas(self) -> None:
        """Treinamento vendido ao cliente: os cursos opcionais, para quem está alocado nele."""
        for ano in bandas.ANOS:
            referencia = date(ano, 5, 15)
            no_cliente: dict[tuple[int, int], dict[str, list[tuple[int, date]]]] = {}
            for a in self.alocacoes:
                if not a["dt_inicio"] <= referencia <= (a["dt_fim"] or HOJE):
                    continue
                posto = self.postos[int(a["posto_id"])]
                contrato = self.contratos[int(posto["contrato_id"])]
                chave = (int(contrato["cliente_id"]), int(contrato["filial_id"]))
                for curso in self.opcionais.get(self.funcao[int(posto["funcao_id"])].codigo, []):
                    no_cliente.setdefault(chave, {}).setdefault(curso, []).append(
                        (int(a["colaborador_id"]), a["dt_fim"] or HOJE)
                    )
            for (cliente, filial), por_curso in sorted(no_cliente.items()):
                curso, alocados = max(por_curso.items(), key=lambda par: (len(par[1]), par[0]))
                comprou = self.rng.random() < cc.CHANCE_DE_TREINAMENTO_VENDIDO
                dia = self.util(referencia + timedelta(days=int(self.rng.integers(0, 120))))
                termino = self.termino(curso, dia)
                pessoas = sorted({c for c, ate in alocados if ate >= termino})
                if not comprou or len(pessoas) < cc.MINIMO_PARA_VENDER or termino > HOJE:
                    continue
                for colaborador in pessoas[:20]:
                    faltou = self.rng.random() < 0.06
                    self.turmas.setdefault((curso, filial, dia, cliente), []).append(
                        (colaborador, 50.0 if faltou else 100.0, not faltou, None)
                    )

    def materializar_turmas(self) -> None:
        turmas: list[dict[str, Any]] = []
        participantes: list[dict[str, Any]] = []
        certificados: list[dict[str, Any]] = []
        ordem = sorted(self.turmas, key=lambda c: (c[2], c[1], self.curso[c[0]][0], c[3]))
        for curso, filial, dia, cliente in ordem:
            curso_id, _, _, _, validade, comprado, custo = self.curso[curso]
            termino = self.termino(curso, dia)
            inscritos = self.turmas[(curso, filial, dia, cliente)]
            for i in range(0, len(inscritos), cc.LOTACAO_DA_TURMA):
                lote = inscritos[i : i + cc.LOTACAO_DA_TURMA]
                instrutor = (
                    cc.INSTRUTORES_DO_FORNECEDOR[(curso_id + dia.toordinal()) % 3]
                    if comprado
                    else self.quem("SST", filial, dia, dia.toordinal()).nome
                )
                marcada = self.carimbo(dia - timedelta(days=7))
                encerrada = max(marcada, self.carimbo(termino, 16, 2))
                turmas.append(
                    {
                        "curso_id": curso_id,
                        "filial_id": filial,
                        "cliente_id": cliente or None,
                        "dt_inicio": dia,
                        "dt_fim": termino,
                        "instrutor": instrutor,
                        "custo_total": round(custo * len(lote) * self.reajuste[dia.year], 2),
                        "fornecedor_id": self.id_fornecedor[cc.FORNECEDOR_DE_TREINAMENTO]
                        if comprado
                        else None,
                        "criado_em": marcada,
                        "atualizado_em": encerrada,
                    }
                )
                for colaborador, presenca, aprovado, nota in lote:
                    inscrito = max(marcada, self.colaborador_criado[colaborador])
                    lancado = max(inscrito, encerrada)
                    participantes.append(
                        {
                            "turma_id": len(turmas),
                            "colaborador_id": colaborador,
                            "presenca_pct": presenca,
                            "fl_aprovado": aprovado,
                            "nota": nota,
                            "criado_em": inscrito,
                            "atualizado_em": lancado,
                        }
                    )
                    if aprovado:
                        certificados.append(
                            {
                                "turma_participante_id": len(participantes),
                                "numero": f"CERT-{termino.year}-{len(certificados) + 1:06d}",
                                "dt_emissao": termino,
                                "dt_validade": _mais_meses(termino, validade) if validade else None,
                                "criado_em": lancado,
                                "atualizado_em": lancado,
                            }
                        )
        self.linhas["treinamento.turma"] = turmas
        self.linhas["treinamento.turma_participante"] = participantes
        self.linhas["treinamento.certificado"] = certificados

    # ───────────────────────── sst: exames ─────────────────────────
    def exames(self) -> None:
        entrada = self.carimbo(INICIO, 8, 1)
        self.linhas["sst.tipo_exame"] = [
            {"codigo": c, "periodicidade_meses": p, "criado_em": entrada, "atualizado_em": entrada}
            for c, p in cc.TIPOS_DE_EXAME
        ]
        id_tipo = {c: i for i, (c, _) in enumerate(cc.TIPOS_DE_EXAME, start=1)}
        exames: list[
            tuple[date, int, str, date | None, int]
        ] = []  # dia, colaborador, tipo, validade, filial
        vencido = dict.fromkeys(bandas.ANOS, 0.0)
        abertos: list[date] = []  # quando fecha cada buraco aberto (ASO vencido, pessoa alocada)
        self.periodicos = {ano: [0, 0] for ano in bandas.ANOS}  # [em dia, atrasados]
        estado: dict[int, dict[str, Any]] = {}
        fila: list[tuple[date, int]] = []

        def renovar(k: dict[str, Any], tipo: str, dia: date) -> None:
            validade = _mais_meses(dia, cc.VALIDADE_DO_ASO_MESES)
            exames.append((dia, k["colaborador"], tipo, validade, k["filial"]))
            k["ultimo"] = dia
            heapq.heappush(fila, (validade, k["id"]))

        for contrato in self.contratos_de_trabalho:
            admissao, fim = contrato["dt_admissao"], contrato["dt_rescisao"] or HOJE
            funcao = self.funcao[int(contrato["funcao_id"])]
            k = estado[int(contrato["id"])] = {
                "id": int(contrato["id"]),
                "colaborador": int(contrato["colaborador_id"]),
                "filial": int(contrato["filial_id"]),
                "fim": fim,
                "encerrado": contrato["dt_rescisao"] is not None,
                "risco_alto": funcao.insalubre or funcao.periculosidade,
                "retornos": [],
            }
            for f in self.afastamentos_de.get(k["colaborador"], []):
                longo = (
                    f["dt_fim"]
                    and (f["dt_fim"] - f["dt_inicio"]).days + 1 >= cc.RETORNO_A_PARTIR_DE_DIAS
                )
                if longo and admissao <= f["dt_inicio"] and f["dt_fim"] < fim:
                    volta = self.util(f["dt_fim"] + timedelta(days=1))
                    if volta <= fim:
                        k["retornos"].append(volta)
                        validade = _mais_meses(volta, cc.VALIDADE_DO_ASO_MESES)
                        exames.append((volta, k["colaborador"], "RETORNO", validade, k["filial"]))
            antes = admissao - timedelta(days=int(self.rng.integers(1, 8)))
            renovar(k, "ADMISSIONAL", self.util(antes, -1))

        while fila:  # em ordem de vencimento, para o controle do ano enxergar o que já acumulou
            vence, contrato_id = heapq.heappop(fila)
            k = estado[contrato_id]
            if vence >= k["fim"]:
                continue  # o contrato acaba antes de o exame vencer
            no_caminho = [x for x in k["retornos"] if k["ultimo"] < x <= vence]
            if no_caminho:  # o exame de retorno renovou a validade
                k["ultimo"] = max(no_caminho)
                heapq.heappush(
                    fila, (_mais_meses(k["ultimo"], cc.VALIDADE_DO_ASO_MESES), contrato_id)
                )
                continue
            while abertos and abertos[0] <= vence:
                heapq.heappop(abertos)
            tolerado = cc.ASO_VENCIDO[vence.year] * self.alocados_no_dia[(vence - INICIO).days]
            if len(abertos) >= tolerado:  # em dia: o exame sai antes de vencer
                dia = self.util(vence - timedelta(days=int(self.rng.integers(5, 31))), -1)
                renovar(k, "PERIODICO", max(dia, k["ultimo"] + timedelta(days=1)))
                self.periodicos[vence.year][0] += 1
                continue
            self.periodicos[vence.year][1] += 1
            crise = vence.year >= cc.ANO_EM_QUE_O_PERIODICO_PASSA_A_SER_ESQUECIDO
            esquecido = crise and self.rng.random() < cc.CHANCE_DE_ESQUECER_O_PERIODICO
            atraso = int(self.rng.integers(15, 121) if crise else self.rng.integers(5, 41))
            exame = None if esquecido else self.util(vence + timedelta(days=atraso))
            retorno = min((x for x in k["retornos"] if x > vence), default=None)
            if retorno and (exame is None or retorno <= exame):
                fecha, exame = retorno, None
            else:
                fecha, retorno = exame, None
            if fecha is None or fecha > k["fim"]:  # ninguém renovou: vencido até sair (ou até hoje)
                fecha, exame, retorno = k["fim"] + timedelta(days=1), None, None
            heapq.heappush(abertos, fecha)
            for ano, dias in _dias_por_ano(
                vence + timedelta(days=1), fecha - timedelta(days=1)
            ).items():
                vencido[ano] += dias
            if exame:
                renovar(k, "PERIODICO", exame)
            elif retorno:
                k["ultimo"] = retorno
                heapq.heappush(fila, (_mais_meses(retorno, cc.VALIDADE_DO_ASO_MESES), contrato_id))

        for k in estado.values():  # o demissional, quando o último exame já não dispensa
            k["ultimo"] = max([k["ultimo"], *k["retornos"]])
            if (
                k["encerrado"]
                and (k["fim"] - k["ultimo"]).days > cc.DISPENSA_DO_DEMISSIONAL[k["risco_alto"]]
            ):
                dia = min(self.util(k["fim"] + timedelta(days=int(self.rng.integers(0, 5)))), HOJE)
                exames.append((dia, k["colaborador"], "DEMISSIONAL", None, k["filial"]))

        self.aso_conduzido = {a: vencido[a] / self.dias_alocados[a] for a in bandas.ANOS}
        ordem_do_tipo = {c: i for i, (c, _) in enumerate(cc.TIPOS_DE_EXAME)}
        exames.sort(key=lambda e: (e[0], e[1], ordem_do_tipo[e[2]]))
        asos = []
        for dia, colaborador, tipo, vale_ate, filial in exames:
            clinica = cc.CLINICAS[self.codigo_da_filial[filial]]
            medicos = cc.MEDICOS[clinica]
            restricao = self.rng.random() < cc.APTO_COM_RESTRICAO[tipo]
            criado = max(
                self.carimbo(dia, 10, 7),
                self.colaborador_criado[colaborador] + timedelta(minutes=5),
            )
            asos.append(
                {
                    "colaborador_id": colaborador,
                    "tipo_exame_id": id_tipo[tipo],
                    "dt_exame": dia,
                    "dt_validade": vale_ate,
                    "resultado": "APTO_RESTRICAO" if restricao else "APTO",
                    "medico_crm": medicos[(colaborador + dia.toordinal()) % len(medicos)],
                    "fornecedor_id": self.id_fornecedor[clinica],
                    "criado_em": min(criado, FIM),
                    "atualizado_em": min(criado, FIM),
                }
            )
        self.linhas["sst.aso"] = asos

    # ───────────────────────── sst: programas, riscos, acidentes ─────────────────────────
    def programas_e_riscos(self) -> None:
        postos_do_contrato: dict[int, list[dict[str, Any]]] = {}
        for p in self.postos.values():
            postos_do_contrato.setdefault(int(p["contrato_id"]), []).append(p)
        programas: list[tuple[date, int, str, date, str, int]] = []
        for contrato_id, postos in sorted(postos_do_contrato.items()):
            contrato = self.contratos[contrato_id]
            fim = contrato["dt_encerramento"] or HOJE
            risco_alto = any(
                self.funcao[int(p["funcao_id"])].insalubre
                or self.funcao[int(p["funcao_id"])].periculosidade
                for p in postos
            )
            for tipo, meses, responsavel in cc.PROGRAMAS:
                if tipo == "LTCAT" and not risco_alto:
                    continue
                antes = contrato["vigencia_inicio"] - timedelta(days=int(self.rng.integers(5, 21)))
                feito = max(INICIO, self.util(antes, -1))
                while True:
                    validade = _mais_meses(feito, meses)
                    programas.append(
                        (
                            feito,
                            contrato_id,
                            tipo,
                            validade,
                            responsavel,
                            int(contrato["cliente_id"]),
                        )
                    )
                    if validade >= fim:
                        break
                    chance = cc.PROGRAMA_ATRASADO + cc.PROGRAMA_ATRASADO_NA_CRISE * self.ceder(
                        validade
                    )
                    if self.rng.random() < chance:
                        feito = self.util(
                            validade + timedelta(days=int(self.rng.integers(20, 151)))
                        )
                    else:
                        feito = self.util(
                            validade - timedelta(days=int(self.rng.integers(5, 26))), -1
                        )
                    if feito > fim:
                        break  # venceu e ninguém refez até o contrato acabar (ou até hoje)
        programas.sort(key=lambda p: (p[0], p[1], p[2]))
        linhas: list[dict[str, Any]] = []
        pgr_do_contrato: dict[int, list[tuple[date, int, datetime]]] = {}
        for feito, contrato_id, tipo, validade, responsavel, cliente in programas:
            criado = self.carimbo(feito)
            linhas.append(
                {
                    "tipo": tipo,
                    "cliente_id": cliente,
                    "contrato_id": contrato_id,
                    "dt_elaboracao": feito,
                    "dt_validade": validade,
                    "responsavel": responsavel,
                    "criado_em": criado,
                    "atualizado_em": criado,
                }
            )
            if tipo == "PGR":
                pgr_do_contrato.setdefault(contrato_id, []).append((feito, len(linhas), criado))
        self.linhas["sst.programa_sst"] = linhas

        riscos = []
        for posto_id, posto in sorted(self.postos.items()):
            funcao = self.funcao[int(posto["funcao_id"])]
            pgrs = pgr_do_contrato[int(posto["contrato_id"])]
            vigentes = [p for p in pgrs if p[0] <= posto["vigencia_inicio"]] or pgrs[:1]
            _, programa_id, criado_do_programa = vigentes[-1]
            agentes = [(a, g, False, False) for a, g in cc.RISCOS_DA_FAMILIA[funcao.familia]]
            agentes += list(cc.RISCOS_DA_FUNCAO.get(funcao.codigo, ()))
            criado = max(posto["criado_em"], criado_do_programa)
            for agente, grau, insalubre, periculosidade in agentes:
                riscos.append(
                    {
                        "posto_id": posto_id,
                        "programa_sst_id": programa_id,
                        "agente_risco": agente,
                        "grau": grau,
                        "insalubridade_pct": cat.ADICIONAL_DE_INSALUBRIDADE if insalubre else 0.0,
                        "fl_periculosidade": periculosidade,
                        "criado_em": criado,
                        "atualizado_em": criado,
                    }
                )
        self.linhas["sst.risco_posto"] = riscos

    def acidentes(self) -> None:
        def alocacao_em(colaborador: int, dia: date) -> int | None:
            for a in self.alocacoes_de.get(colaborador, []):
                if a["dt_inicio"] <= dia <= (a["dt_fim"] or HOJE):
                    return int(a["id"])
            return None

        # (dia, colaborador, alocação, dias de afastamento, afastamento, volta)
        ocorridos: list[tuple[date, int, int | None, int, int | None, date | None]] = []
        for afastamentos in self.afastamentos_de.values():
            for f in afastamentos:
                if f["tipo"] == "ACIDENTE":
                    dias = ((f["dt_fim"] or HOJE) - f["dt_inicio"]).days + 1
                    colaborador = int(f["colaborador_id"])
                    ocorridos.append(
                        (
                            f["dt_inicio"],
                            colaborador,
                            alocacao_em(colaborador, f["dt_inicio"]),
                            dias,
                            int(f["id"]),
                            f["dt_fim"],
                        )
                    )
        for a in self.alocacoes:  # os sem afastamento: susto, curativo e volta ao trabalho
            dias = ((a["dt_fim"] or HOJE) - a["dt_inicio"]).days + 1
            meio = a["dt_inicio"] + timedelta(days=dias // 2)
            esperado = dias / 365 * cc.ACIDENTES_SEM_AFASTAMENTO_POR_ANO * (1 + self.ceder(meio))
            if self.rng.random() < esperado:
                dia = a["dt_inicio"] + timedelta(days=int(self.rng.integers(0, dias)))
                ocorridos.append((dia, int(a["colaborador_id"]), int(a["id"]), 0, None, None))
        ocorridos.sort(key=lambda o: (o[0], o[1]))
        acidentes, cats = [], []
        for dia, colaborador, alocacao, dias, afastamento, volta in ocorridos:
            criado = self.carimbo(dia)
            gravidade = next(g for limite, g in cc.GRAVIDADE_POR_DIAS if dias <= limite)
            acidentes.append(
                {
                    "colaborador_id": colaborador,
                    "alocacao_id": alocacao,
                    "dt_acidente": dia,
                    "tipo": "TRAJETO" if self.rng.random() < cc.CHANCE_DE_TRAJETO else "TIPICO",
                    "gravidade": gravidade,
                    "dias_afastamento": dias,
                    "afastamento_id": afastamento,
                    "criado_em": criado,
                    "atualizado_em": max(criado, self.carimbo(volta, 14, 3)) if volta else criado,
                }
            )
            atrasa = self.rng.random() < cc.CAT_ATRASADA + cc.CAT_ATRASADA_NA_CRISE * self.ceder(
                dia
            )
            espera = int(self.rng.integers(3, 13)) if atrasa else 1
            emissoes = [("INICIAL", self.util(dia + timedelta(days=espera)))]
            if dias >= cc.REABERTURA_A_PARTIR_DE_DIAS:
                depois = dia + timedelta(days=int(self.rng.integers(30, 46)))
                emissoes.append(("REABERTURA", self.util(depois)))
            cats += [
                (emissao, len(acidentes), tipo) for tipo, emissao in emissoes if emissao <= HOJE
            ]
        cats.sort()
        self.linhas["sst.acidente"] = acidentes
        self.linhas["sst.cat"] = []
        for emissao, acidente_id, tipo in cats:
            criado = self.carimbo(emissao)
            self.linhas["sst.cat"].append(
                {
                    "acidente_id": acidente_id,
                    "numero": f"CAT-{emissao.year}-{len(self.linhas['sst.cat']) + 1:05d}",
                    "dt_emissao": emissao,
                    "tipo_cat": tipo,
                    "criado_em": criado,
                    "atualizado_em": criado,
                }
            )


def montar(t3: Tabelas, gabarito: dict[str, Any]) -> tuple[Tabelas, dict[str, Any]]:
    """A etapa sobre uma etapa 3 já gerada (os testes reaproveitam a base)."""
    c = _Conformidade(t3, gabarito)
    c.seguranca()
    c.treinamento()
    c.exames()
    c.programas_e_riscos()
    c.acidentes()
    c.acessos()
    c.trilha_dos_registros()
    c.fechar_seguranca()
    base = {
        "etapa3": t3,
        "carteira": c.carteira,
        "mundo": c.mundo,
        "usuarios": c.usuarios,
        "aso_conduzido": c.aso_conduzido,
        "periodicos": c.periodicos,
        "retoques": {"ats.entrevista": c.entrevistadores()},
    }
    return {nome: tabela(c.linhas[nome]) for nome in ORDEM}, base


def gerar_com_base(publicos: Path = etapa1_cadastro.PUBLICOS) -> tuple[Tabelas, dict[str, Any]]:
    return montar(*etapa3_pessoas.gerar_com_gabarito(publicos))


def gerar(publicos: Path = etapa1_cadastro.PUBLICOS) -> Tabelas:
    tabelas, base = gerar_com_base(publicos)
    conferir(tabelas, base)
    return tabelas


def aso_vencido(asos: list[dict[str, Any]], alocacoes: list[dict[str, Any]]) -> dict[int, float]:
    """SST-01 por ano: no último dia de cada mês, a parte dos alocados sem ASO válido (exame
    feito e ainda dentro da validade); o ano é a média dos seus meses."""
    validos: dict[int, list[tuple[date, date]]] = {}
    for a in asos:
        if a["dt_validade"] is not None:
            validos.setdefault(int(a["colaborador_id"]), []).append(
                (a["dt_exame"], a["dt_validade"])
            )
    alocados: dict[date, int] = {}
    vencidos: dict[date, int] = {}
    for a in alocacoes:
        dia = _mais_meses(a["dt_inicio"].replace(day=1), 1) - timedelta(days=1)
        while dia <= (a["dt_fim"] or HOJE):
            if dia >= a["dt_inicio"]:
                em_dia = any(e <= dia <= v for e, v in validos.get(int(a["colaborador_id"]), ()))
                alocados[dia] = alocados.get(dia, 0) + 1
                vencidos[dia] = vencidos.get(dia, 0) + (not em_dia)
            dia = _mais_meses(dia.replace(day=1), 2) - timedelta(days=1)
    por_ano: dict[int, list[float]] = {}
    for dia, quantos in alocados.items():
        por_ano.setdefault(dia.year, []).append(vencidos[dia] / quantos)
    return {ano: sum(partes) / len(partes) for ano, partes in sorted(por_ano.items())}


def medir(t: Tabelas, base: dict[str, Any]) -> Medidas:
    vencido = aso_vencido(_registros(t["sst.aso"]), _registros(base["etapa3"]["pessoas.alocacao"]))
    return {
        "sujeira": {f"SST-01/{ano}": vencido[ano] for ano in (2024, 2025)},
        "linhas_tabela": {"sst.aso": float(len(t["sst.aso"]))},
    }


def laudo_parcial(medidas: Medidas) -> Laudo:
    entregues = {(m, chave) for m, valores in medidas.items() for chave in valores}
    return avaliar([c for c in bandas.checks() if (c.medida, c.chave) in entregues], medidas)


def conferir(t: Tabelas, base: dict[str, Any]) -> None:
    problemas: list[str] = []
    t3, carteira, mundo = base["etapa3"], base["carteira"], base["mundo"]
    for filha, coluna, mae in (
        ("seguranca.usuario", "filial_id", mundo["cadastro.filial"]),
        ("seguranca.usuario_perfil", "usuario_id", t["seguranca.usuario"]),
        ("seguranca.usuario_perfil", "perfil_id", t["seguranca.perfil"]),
        ("seguranca.permissao", "perfil_id", t["seguranca.perfil"]),
        ("seguranca.log_auditoria", "usuario_id", t["seguranca.usuario"]),
        ("treinamento.curso_funcao", "curso_id", t["treinamento.curso"]),
        ("treinamento.curso_funcao", "funcao_id", mundo["cadastro.funcao"]),
        ("treinamento.turma", "curso_id", t["treinamento.curso"]),
        ("treinamento.turma", "cliente_id", carteira["comercial.cliente"]),
        ("treinamento.turma_participante", "turma_id", t["treinamento.turma"]),
        ("treinamento.turma_participante", "colaborador_id", t3["pessoas.colaborador"]),
        ("treinamento.certificado", "turma_participante_id", t["treinamento.turma_participante"]),
        ("sst.aso", "colaborador_id", t3["pessoas.colaborador"]),
        ("sst.aso", "tipo_exame_id", t["sst.tipo_exame"]),
        ("sst.programa_sst", "contrato_id", carteira["comercial.contrato"]),
        ("sst.risco_posto", "posto_id", carteira["comercial.posto"]),
        ("sst.risco_posto", "programa_sst_id", t["sst.programa_sst"]),
        ("sst.acidente", "alocacao_id", t3["pessoas.alocacao"]),
        ("sst.acidente", "afastamento_id", t3["pessoas.afastamento"]),
        ("sst.cat", "acidente_id", t["sst.acidente"]),
    ):
        if not set(t[filha][coluna].dropna().astype(int)) <= set(mae["id"]):
            problemas.append(f"{filha}.{coluna} órfã")
    for nome, colunas in (
        ("seguranca.usuario", ["login"]),
        ("treinamento.turma_participante", ["turma_id", "colaborador_id"]),
        ("treinamento.certificado", ["numero"]),
        ("sst.cat", ["numero"]),
    ):
        if t[nome].duplicated(colunas).any():
            problemas.append(f"{nome}: {colunas} repetido")
    for nome, quadro in t.items():
        if (
            not (quadro["atualizado_em"] >= quadro["criado_em"]).all()
            or not (quadro["atualizado_em"] <= FIM).all()
        ):
            problemas.append(f"{nome}: carimbo fora de ordem ou depois do fim da história")
    retoque = base["retoques"]["ats.entrevista"]
    if len(retoque) != len(t3["ats.entrevista"]) or retoque["usuario_id"].isna().any():
        problemas.append("entrevista sem entrevistador")
    for r_ in laudo_parcial(medir(t, base)).com_situacao(Situacao.REPROVADO):
        problemas.append(f"régua {r_.check.codigo}: {r_.valor} fora de {r_.check.banda}")
    if problemas:
        raise ValueError("etapa 6 reprovada:\n- " + "\n- ".join(problemas))
