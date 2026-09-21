"""Etapa 3 do gerador: o funil de colocação e as pessoas (9 tabelas de `ats`, 8 de `pessoas`).

O motor (etapa3_ocupacao) decide o que acontece com cada posição de cada posto: vagas que
abrem, fecham ou são canceladas, e vínculos que começam e terminam. Aqui isso vira linha:

- cada pedido vira requisição e vagas; cada vaga recebe candidatos (novos ou do banco da
  filial), que percorrem triagem, entrevista interna, encaminhamento, entrevista no cliente
  e aprovação, com data em cada passagem e o no-show de entrevista do ano;
- quem é aprovado numa vaga com posto vira colaborador (ou volta a ser: a mesma pessoa pode
  ter vários contratos de trabalho), com contrato, alocação, prorrogação, afastamentos e
  desligamento; vaga de recrutamento aprova e a pessoa vai para o quadro do cliente;
- a sujeira do catálogo entra na origem: candidato duplicado (CAD-01), CPF inválido (CAD-02),
  nascimento impossível (CAD-03), admissão registrada depois do fato (PES-01) e temporário
  além do prazo legal sem aditivo (PES-02, decidido no motor).

O gabarito (quem é duplicata de quem) sai junto de `gerar_com_gabarito`: é a resposta da
auditoria de qualidade, e não vai para a réplica.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador import catalogos_comercial as com
from rh_fictalent.gerador import catalogos_pessoas as cp
from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, historia
from rh_fictalent.gerador import etapa3_ocupacao as motor
from rh_fictalent.gerador.nucleo import FIM, INICIO, Tabelas, aleatorio
from rh_fictalent.validacao import bandas, derivadas
from rh_fictalent.validacao.regua import Laudo, Medidas, Situacao, avaliar

HOJE = FIM.date()
JORNADA = 10 * 3600.0  # o expediente, das 8h às 18h, em segundos
Linhas = list[tuple[Any, ...]]

COLUNAS = {
    "cadastro.endereco": (
        "id",
        "logradouro",
        "numero",
        "complemento",
        "bairro",
        "municipio_id",
        "cep",
        "tipo",
    ),
    "ats.fonte_candidato": ("id", "nome", "custo_medio"),
    "ats.etapa_funil": ("id", "codigo", "nome", "ordem"),
    "ats.requisicao": (
        "id",
        "numero",
        "cliente_id",
        "contrato_id",
        "posto_id",
        "quantidade",
        "dt_abertura",
        "dt_necessidade",
        "prioridade",
        "status",
        "motivo_cancelamento_id",
    ),
    "ats.vaga": (
        "id",
        "requisicao_id",
        "codigo",
        "titulo",
        "funcao_id",
        "filial_id",
        "quantidade_posicoes",
        "dt_abertura",
        "dt_fechamento",
        "status",
        "salario_previsto",
    ),
    "ats.candidato": (
        "id",
        "nome",
        "cpf",
        "dt_nascimento",
        "sexo",
        "municipio_id",
        "telefone",
        "email",
        "escolaridade",
        "fonte_id",
        "dt_cadastro",
    ),
    "ats.candidato_experiencia": (
        "id",
        "candidato_id",
        "empresa",
        "funcao_id",
        "dt_inicio",
        "dt_fim",
    ),
    "ats.candidatura": (
        "id",
        "vaga_id",
        "candidato_id",
        "dt_inscricao",
        "etapa_atual_id",
        "status",
        "dt_conclusao",
        "motivo_reprovacao_id",
    ),
    "ats.candidatura_etapa": (
        "id",
        "candidatura_id",
        "etapa_id",
        "dt_entrada",
        "dt_saida",
        "resultado",
        "motivo_id",
    ),
    "ats.entrevista": (
        "id",
        "candidatura_id",
        "tipo",
        "dt_agendada",
        "dt_realizada",
        "fl_compareceu",
        "usuario_id",
        "resultado",
    ),
    "pessoas.colaborador": (
        "id",
        "candidato_id",
        "matricula",
        "nome",
        "cpf",
        "dt_nascimento",
        "municipio_id",
        "endereco_id",
        "pis",
        "dt_admissao_primeira",
        "ativo",
    ),
    "pessoas.colaborador_documento": (
        "id",
        "colaborador_id",
        "tipo",
        "numero",
        "orgao",
        "dt_emissao",
    ),
    "pessoas.dependente": ("id", "colaborador_id", "nome", "parentesco", "dt_nascimento"),
    "pessoas.contrato_trabalho": (
        "id",
        "colaborador_id",
        "tipo",
        "funcao_id",
        "filial_id",
        "dt_admissao",
        "dt_prevista_termino",
        "dt_rescisao",
        "salario_base",
        "escala_id",
        "prazo_legal_dias",
        "status",
    ),
    "pessoas.contrato_trabalho_prorrogacao": (
        "id",
        "contrato_trabalho_id",
        "dt_assinatura",
        "dt_novo_termino",
        "dias_adicionais",
    ),
    "pessoas.alocacao": (
        "id",
        "colaborador_id",
        "contrato_trabalho_id",
        "posto_id",
        "dt_inicio",
        "dt_fim",
        "motivo_fim_id",
        "substituindo_alocacao_id",
    ),
    "pessoas.afastamento": (
        "id",
        "colaborador_id",
        "tipo",
        "dt_inicio",
        "dt_fim",
        "motivo_id",
        "cid_grupo",
    ),
    "pessoas.desligamento": (
        "id",
        "contrato_trabalho_id",
        "dt_desligamento",
        "tipo",
        "motivo_id",
        "dias_aviso_previo",
        "valor_rescisao",
        "dt_homologacao",
    ),
}
MOTIVO_DO_FIM_DA_ALOCACAO = {
    "TERMINO_CONTRATO": "FIM_CONTRATO",
    "PEDIDO_CLIENTE": "SUBSTITUICAO",
    "REDUCAO_QUADRO": "ENCERRAMENTO_POSTO",
}


def _digitos_verificadores(base: list[int], pesos: tuple[tuple[int, ...], ...]) -> list[int]:
    for linha in pesos:
        resto = sum(d * p for d, p in zip(base, linha, strict=True)) % 11
        base = [*base, 0 if resto < 2 else 11 - resto]
    return base


def cpf_valido(cpf: str | None) -> bool:
    if cpf is None or len(cpf) != 11 or not cpf.isdigit() or len(set(cpf)) == 1:
        return False
    pesos = (tuple(range(10, 1, -1)), tuple(range(11, 1, -1)))
    return _digitos_verificadores([int(d) for d in cpf[:9]], pesos) == [int(d) for d in cpf]


class _Construtor:
    def __init__(self, publicos: Path) -> None:
        self.rng = aleatorio("etapa3_pessoas")
        self.mundo = etapa1_cadastro.gerar(publicos)
        self.carteira = etapa2_carteira.gerar(publicos)
        r = etapa2_carteira._registros
        self.contratos = {int(k["id"]): k for k in r(self.carteira["comercial.contrato"])}
        self.postos = {int(p["id"]): p for p in r(self.carteira["comercial.posto"])}
        self.clientes = {int(c["id"]): c for c in r(self.carteira["comercial.cliente"])}
        self.funcoes = {i: f for i, f in enumerate(cat.FUNCOES, start=1)}
        self.id_motivo = {
            (str(m["tipo"]), str(m["codigo"])): int(m["id"])
            for m in r(self.mundo["cadastro.motivo"])
        }
        feriados = [
            f["data"] for f in r(self.mundo["cadastro.feriado"]) if f["abrangencia"] == "NACIONAL"
        ]
        self.calendario = motor.Calendario(feriados)
        # o eixo do horário comercial: os dias úteis da história, das 8h às 18h
        todos = [INICIO + timedelta(days=i) for i in range((HOJE - INICIO).days + 15)]
        folgas = set(feriados)
        self.dia_util = [d.weekday() < 5 and d not in folgas for d in todos]
        self.dias_uteis = [d for d, util in zip(todos, self.dia_util, strict=True) if util]
        self.uteis_antes = [0]
        for util in self.dia_util:
            self.uteis_antes.append(self.uteis_antes[-1] + util)

        # piso por (município da convenção da filial, função), como na etapa 2
        municipio_da_convencao = {
            int(k["id"]): int(k["municipio_id"])
            for k in r(self.mundo["cadastro.convencao_coletiva"])
        }
        self.pisos: dict[tuple[int, int], tuple[list[date], list[float]]] = {}
        for p in r(self.mundo["cadastro.piso_salarial"]):
            chave = (municipio_da_convencao[int(p["convencao_id"])], int(p["funcao_id"]))
            inicios, valores = self.pisos.setdefault(chave, ([], []))
            inicios.append(p["vigencia_inicio"])
            valores.append(float(p["valor_piso"]))
        municipio_do_endereco = {
            int(e["id"]): int(e["municipio_id"]) for e in r(self.mundo["cadastro.endereco"])
        }
        self.municipio_da_filial = {
            int(f["id"]): municipio_do_endereco[int(f["endereco_id"])]
            for f in r(self.mundo["cadastro.filial"])
        }
        # de onde vêm os candidatos de cada filial: os municípios da região dela, a cidade pesa mais
        regiao_do_municipio = {
            int(m["id"]): int(m["regiao_id"]) for m in r(self.mundo["cadastro.municipio"])
        }
        self.municipios_da_filial: dict[int, tuple[list[int], np.ndarray[Any, Any]]] = {}
        for filial_id, sede in self.municipio_da_filial.items():
            da_regiao = [
                m for m, reg in regiao_do_municipio.items() if reg == regiao_do_municipio[sede]
            ]
            pesos = np.array([12.0 if m == sede else 1.0 for m in da_regiao])
            self.municipios_da_filial[filial_id] = (da_regiao, pesos / pesos.sum())

        postos = r(self.carteira["comercial.posto"])
        self.vagas, self.vinculos = motor.simular(postos, self.contratos, feriados)
        funcoes_do_cliente = {
            cliente_id: [
                i for i, f in self.funcoes.items() if f.familia in com.SETORES[str(c["setor"])][1]
            ]
            for cliente_id, c in self.clientes.items()
        }
        deslocamento = len(self.vagas)
        self.vagas += motor.vagas_de_recrutamento(self.contratos, funcoes_do_cliente, feriados)
        self.vinculos_da_vaga: dict[int, list[motor.Vinculo]] = {}
        for v in self.vinculos:
            self.vinculos_da_vaga.setdefault(v.vaga, []).append(v)
        self.primeira_de_recrutamento = deslocamento

        self.linhas: dict[str, Linhas] = {nome: [] for nome in COLUNAS}
        self.carimbos: dict[str, list[tuple[datetime, datetime]]] = {nome: [] for nome in COLUNAS}
        self.relogio = 0
        self.pessoas: list[dict[str, Any]] = []
        self.banco: dict[int, list[int]] = {f: [] for f in self.municipio_da_filial}
        self.cpfs: set[str] = set()
        self.duplicata_de: dict[int, int] = {}  # candidato_id -> candidato_id original (gabarito)
        self.pessoa_do_vinculo: dict[int, int] = {}
        self.ja_existiam = {
            nome: len(self.mundo[nome]) + len(self.carteira[nome])
            for nome in ("cadastro.endereco",)
        }

    # ───────────────────────── utilidades ─────────────────────────
    def momento(self, dia: date) -> datetime:
        """Um horário comercial determinístico para o dia (barato: sem sorteio)."""
        self.relogio += 1
        hora, minuto = 8 + (self.relogio * 7919) % 10, (self.relogio * 104729) % 60
        return min(datetime.combine(dia, time(hora, minuto)), FIM)

    def linha(
        self,
        tabela: str,
        valores: tuple[Any, ...],
        criado: datetime,
        atualizado: datetime | None = None,
    ) -> int:
        novo_id = len(self.linhas[tabela]) + 1 + self.ja_existiam.get(tabela, 0)
        self.linhas[tabela].append((novo_id, *valores))
        criado = min(criado, FIM)
        self.carimbos[tabela].append((criado, max(criado, min(atualizado or criado, FIM))))
        return novo_id

    def piso(self, filial_id: int, funcao_id: int, dia: date) -> float:
        inicios, valores = self.pisos[(self.municipio_da_filial[filial_id], funcao_id)]
        return valores[max(0, bisect_right(inicios, dia) - 1)]

    def novo_cpf(self, valido: bool = True) -> str:
        pesos = (tuple(range(10, 1, -1)), tuple(range(11, 1, -1)))
        while True:
            digitos = _digitos_verificadores(
                [int(d) for d in self.rng.integers(0, 10, size=9)], pesos
            )
            if not valido:
                digitos[-1] = (digitos[-1] + 1 + int(self.rng.integers(0, 8))) % 10
            cpf = "".join(map(str, digitos))
            if cpf not in self.cpfs and len(set(cpf)) > 1:
                self.cpfs.add(cpf)
                return cpf

    def novo_pis(self) -> str:
        base = [int(d) for d in self.rng.integers(0, 10, size=10)]
        resto = sum(d * p for d, p in zip(base, (3, 2, 9, 8, 7, 6, 5, 4, 3, 2), strict=True)) % 11
        return "".join(map(str, [*base, 0 if resto < 2 else 11 - resto]))

    # ───────────────────────── catálogos do funil ─────────────────────────
    def catalogos(self) -> None:
        entrada = datetime.combine(INICIO, time(8, 0))
        for nome, custo, _ in cp.FONTES:
            self.linha("ats.fonte_candidato", (nome, custo), entrada)
        for codigo, nome, ordem in cp.ETAPAS:
            self.linha("ats.etapa_funil", (codigo, nome, ordem), entrada)

    # ───────────────────────── candidatos ─────────────────────────
    def nova_pessoa(self, filial_id: int, dia: date, limpa: bool = False) -> int:
        """Cadastra um candidato. Com sujeira de origem, a não ser que `limpa` (quem vai ser
        contratado precisa de CPF válido e idade possível). Devolve o índice da pessoa."""
        sorteio = self.rng.random(8)
        if not limpa and self.banco[filial_id] and sorteio[0] < cp.CHANCE_DE_DUPLICADO:
            return self.duplicar(filial_id, dia)
        feminino = sorteio[1] < 0.42
        nomes = cp.NOMES_F if feminino else cp.NOMES_M
        partes = [
            nomes[int(self.rng.integers(len(nomes)))],
            cp.SOBRENOMES[int(self.rng.integers(len(cp.SOBRENOMES)))],
            cp.SOBRENOMES[int(self.rng.integers(len(cp.SOBRENOMES)))],
        ]
        idade = int(self.rng.triangular(18, 27, 58))
        elegivel = True
        if not limpa and sorteio[2] < cp.CHANCE_DE_NASCIMENTO_IMPOSSIVEL:
            idade, elegivel = (
                (
                    int(self.rng.integers(2, 13))
                    if sorteio[3] < 0.5
                    else int(self.rng.integers(95, 120))
                ),
                False,
            )
        nascimento = date(
            dia.year - idade, int(self.rng.integers(1, 13)), int(self.rng.integers(1, 29))
        )
        cpf_ok = limpa or sorteio[4] >= cp.CHANCE_DE_CPF_INVALIDO
        municipios, pesos = self.municipios_da_filial[filial_id]
        pessoa: dict[str, Any] = {
            "nome": " ".join(partes),
            "cpf": self.novo_cpf(cpf_ok),
            "nascimento": nascimento,
            "sexo": "F" if feminino else ("M" if sorteio[5] < 0.97 else "N"),
            "municipio_id": municipios[int(self.rng.choice(len(municipios), p=pesos))],
            "filial_id": filial_id,
            "elegivel": elegivel and cpf_ok,
            "colaborador_id": None,
            "ocupacoes": [],
        }
        return self.cadastrar(pessoa, dia, com_email=sorteio[6] < 0.7)

    def duplicar(self, filial_id: int, dia: date) -> int:
        """CAD-01: a mesma pessoa cadastrada de novo, com outra grafia e às vezes outro CPF."""
        banco = self.banco[filial_id]
        original = self.pessoas[banco[int(self.rng.integers(len(banco)))]]
        for _ in range(5):  # a cópia parte de um cadastro original, não de outra cópia
            if original["candidato_id"] not in self.duplicata_de:
                break
            original = self.pessoas[banco[int(self.rng.integers(len(banco)))]]
        partes = str(original["nome"]).split()
        jeito = int(self.rng.integers(4))
        if jeito == 0:
            nome = f"{partes[0]} {partes[-1]}"  # sem o sobrenome do meio
        elif jeito == 1:
            nome = f"{partes[0]} {partes[1][0]}. {partes[-1]}"  # sobrenome do meio abreviado
        elif jeito == 2:
            nome = " ".join(partes).upper()
        else:
            nome = _sem_acento(" ".join(partes))
        if nome == original["nome"]:  # nome sem acento: a grafia diferente é a versão curta
            nome = f"{partes[0]} {partes[-1]}".upper()
        sorteio = float(self.rng.random())
        # o mesmo CPF na maioria; às vezes em branco, às vezes outro número (outro documento)
        cpf = original["cpf"] if sorteio < 0.7 else (None if sorteio < 0.85 else self.novo_cpf())
        copia = {
            **original,
            "nome": nome,
            "cpf": cpf,
            "elegivel": False,
            "colaborador_id": None,
            "ocupacoes": [],
        }
        indice = self.cadastrar(copia, dia, com_email=False)
        self.duplicata_de[self.pessoas[indice]["candidato_id"]] = int(original["candidato_id"])
        return indice

    def cadastrar(self, pessoa: dict[str, Any], dia: date, com_email: bool) -> int:
        fonte = int(self.rng.choice(len(cp.FONTES), p=[f[2] for f in cp.FONTES])) + 1
        escolaridade = cp.ESCOLARIDADES[
            int(self.rng.choice(4, p=[e[1] for e in cp.ESCOLARIDADES]))
        ][0]
        usuario = _sem_acento(str(pessoa["nome"]).lower()).replace(" ", ".").replace("..", ".")
        numero = len(self.linhas["ats.candidato"]) + 1
        quando = self.momento(dia)
        pessoa["candidato_id"] = self.linha(
            "ats.candidato",
            (
                pessoa["nome"],
                pessoa["cpf"],
                pessoa["nascimento"],
                pessoa["sexo"],
                pessoa["municipio_id"],
                f"(11) 90000-{numero % 10000:04d}",
                f"{usuario}.{numero}@email.example" if com_email else None,
                escolaridade,
                fonte,
                dia,
            ),
            quando,
        )
        for _ in range(int(self.rng.poisson(1.2))):
            inicio = dia - timedelta(days=int(self.rng.integers(200, 3000)))
            fim = inicio + timedelta(days=int(self.rng.integers(60, 900)))
            self.linha(
                "ats.candidato_experiencia",
                (
                    pessoa["candidato_id"],
                    cp.EMPRESAS_ANTERIORES[int(self.rng.integers(len(cp.EMPRESAS_ANTERIORES)))],
                    int(self.rng.integers(1, len(cat.FUNCOES) + 1))
                    if self.rng.random() < 0.6
                    else None,
                    inicio,
                    fim if fim < dia else None,
                ),
                quando,
            )
        self.pessoas.append(pessoa)
        self.banco[int(pessoa["filial_id"])].append(len(self.pessoas) - 1)
        return len(self.pessoas) - 1

    def livre(self, pessoa: dict[str, Any], inicio: date, fim: date | None) -> bool:
        ate = fim or date.max
        return all(ate < a or inicio > (b or date.max) for a, b in pessoa["ocupacoes"])

    def candidatos_da_vaga(
        self, vaga: motor.Vaga, filial_id: int, contratados: list[motor.Vinculo], extras: int
    ) -> tuple[list[int], list[int]]:
        """(índices dos aprovados, índices dos demais). Os aprovados estão livres no período."""
        banco = self.banco[filial_id]
        escolhidos: set[int] = set()
        aprovados: list[int] = []
        aprovacoes = max(vaga.posicoes if vaga.situacao == "PREENCHIDA" else 0, len(contratados))
        for i in range(aprovacoes):
            vinculo = contratados[i] if i < len(contratados) else None
            inicio = vinculo.inicio if vinculo else (vaga.fechamento or vaga.abertura)
            fim = vinculo.fim if vinculo else inicio
            achado = None
            for _ in range(8):
                if len(banco) < 20 or self.rng.random() < cp.CHANCE_DE_CANDIDATO_NOVO:
                    break
                indice = banco[-1 - int(self.rng.integers(min(len(banco), cp.MEMORIA_DO_BANCO)))]
                pessoa = self.pessoas[indice]
                if (
                    indice not in escolhidos
                    and pessoa["elegivel"]
                    and self.livre(pessoa, vaga.abertura, fim)
                ):
                    achado = indice
                    break
            if achado is None:
                achado = self.nova_pessoa(filial_id, vaga.abertura, limpa=True)
            escolhidos.add(achado)
            aprovados.append(achado)
            if vinculo is not None:
                self.pessoas[achado]["ocupacoes"].append((inicio, fim))
        demais: list[int] = []
        for _ in range(extras):
            if len(banco) < 20 or self.rng.random() < cp.CHANCE_DE_CANDIDATO_NOVO:
                indice = self.nova_pessoa(filial_id, vaga.abertura)
            else:
                indice = banco[-1 - int(self.rng.integers(min(len(banco), cp.MEMORIA_DO_BANCO)))]
                if indice in escolhidos or not self.livre(
                    self.pessoas[indice], vaga.abertura, vaga.abertura
                ):
                    continue
            escolhidos.add(indice)
            demais.append(indice)
        return aprovados, demais

    # ───────────────────────── requisições, vagas e funil ─────────────────────────
    def funil(self) -> None:
        ordem = sorted(range(len(self.vagas)), key=lambda i: (self.vagas[i].abertura, i))
        requisicao_do_posto: dict[int, int] = {}
        vagas_da_requisicao: dict[int, list[motor.Vaga]] = {}
        sequencia: dict[int, int] = {}
        for antigo in ordem:
            vaga = self.vagas[antigo]
            contrato = self.contratos[vaga.contrato_id]
            ano = vaga.abertura.year
            inicial = vaga.posto_id is not None and not vaga.reposicao
            requisicao_id = requisicao_do_posto.get(vaga.posto_id or 0) if inicial else None
            if requisicao_id is None:
                sequencia[ano] = sequencia.get(ano, 0) + 1
                quantidade = (
                    self.postos[vaga.posto_id]["quantidade"]
                    if inicial and vaga.posto_id
                    else vaga.posicoes
                )
                folga = (vaga.necessidade - vaga.conhecida).days
                prioridade = (
                    "URGENTE"
                    if folga <= 2
                    else "ALTA"
                    if folga <= 7
                    else "NORMAL"
                    if folga <= 25
                    else "BAIXA"
                )
                requisicao_id = self.linha(
                    "ats.requisicao",
                    (
                        f"RQ-{ano}-{sequencia[ano]:05d}",
                        int(contrato["cliente_id"]),
                        vaga.contrato_id,
                        vaga.posto_id,
                        quantidade,
                        min(vaga.conhecida, vaga.abertura),
                        vaga.necessidade,
                        prioridade,
                        "ABERTA",
                        None,
                    ),
                    self.momento(min(vaga.conhecida, vaga.abertura)),
                )
                if inicial and vaga.posto_id:
                    requisicao_do_posto[vaga.posto_id] = requisicao_id
            vagas_da_requisicao.setdefault(requisicao_id, []).append(vaga)
            self.uma_vaga(antigo, vaga, requisicao_id, int(contrato["filial_id"]))
        self.fechar_requisicoes(vagas_da_requisicao)

    def fechar_requisicoes(self, vagas_da_requisicao: dict[int, list[motor.Vaga]]) -> None:
        linhas, carimbos = self.linhas["ats.requisicao"], self.carimbos["ats.requisicao"]
        for requisicao_id, vagas in vagas_da_requisicao.items():
            situacoes = {v.situacao for v in vagas}
            if "ABERTA" in situacoes:
                status, motivo = "EM_ATENDIMENTO", None
            elif situacoes == {"CANCELADA"}:
                status = "CANCELADA"
                motivo = self.id_motivo[("CANCELAMENTO_VAGA", str(vagas[0].motivo_cancelamento))]
            else:
                status, motivo = "ATENDIDA", None
            linha = linhas[requisicao_id - 1]
            linhas[requisicao_id - 1] = (*linha[:9], status, motivo)
            fechamentos = [v.fechamento for v in vagas if v.fechamento]
            if fechamentos and status != "EM_ATENDIMENTO":
                criado, _ = carimbos[requisicao_id - 1]
                carimbos[requisicao_id - 1] = (criado, max(criado, self.momento(max(fechamentos))))

    def uma_vaga(self, antigo: int, vaga: motor.Vaga, requisicao_id: int, filial_id: int) -> None:
        funcao = self.funcoes[vaga.funcao_id]
        cliente = self.clientes[int(self.contratos[vaga.contrato_id]["cliente_id"])]
        aberta = vaga.situacao == "ABERTA"
        status = (
            ("EM_TRIAGEM" if (HOJE - vaga.abertura).days >= 2 else "ABERTA")
            if aberta
            else vaga.situacao
        )
        numero = len(self.linhas["ats.vaga"]) + 1
        criado = self.momento(vaga.abertura)
        vaga_id = self.linha(
            "ats.vaga",
            (
                requisicao_id,
                f"VG-{vaga.abertura.year}-{numero:06d}",
                f"{funcao.nome} · {cliente['nome_fantasia']}"[:120],
                vaga.funcao_id,
                filial_id,
                vaga.posicoes,
                vaga.abertura,
                vaga.fechamento,
                status,
                round(self.piso(filial_id, vaga.funcao_id, vaga.abertura), 2),
            ),
            criado,
            self.momento(vaga.fechamento) if vaga.fechamento else None,
        )
        contratados = sorted(self.vinculos_da_vaga.get(antigo, []), key=lambda v: v.inicio)
        media = cp.CANDIDATOS_POR_VAGA[vaga.tipo_servico] * vaga.posicoes**0.6
        extras = max(2, int(self.rng.poisson(media)))
        aprovados, demais = self.candidatos_da_vaga(vaga, filial_id, contratados, extras)
        for vinculo, indice in zip(contratados, aprovados, strict=False):
            self.pessoa_do_vinculo[id(vinculo)] = indice
        fim_da_vaga = vaga.fechamento or HOJE
        janela = max(1, (fim_da_vaga - vaga.abertura).days)
        for indice in aprovados:
            self.candidatura(vaga_id, vaga, indice, janela, fim_da_vaga, aprovado=True)
        for indice in demais:
            self.candidatura(vaga_id, vaga, indice, janela, fim_da_vaga, aprovado=False)

    def no_eixo(self, t: datetime, fim: bool = False) -> float:
        """O instante em segundos de expediente desde o começo da história."""
        d = (t.date() - INICIO).days
        if not self.dia_util[d]:  # fim de semana ou feriado: o expediente vizinho
            return self.uteis_antes[d] * JORNADA - (1.0 if fim else 0.0)
        segundos = (t - datetime.combine(t.date(), time(8, 0))).total_seconds()
        return self.uteis_antes[d] * JORNADA + min(max(segundos, 0.0), JORNADA - 1.0)

    def horario_comercial(
        self, abertura: datetime, limite: datetime
    ) -> Callable[[datetime], datetime]:
        """O funil é simulado em tempo corrido; quem trabalha nele tem expediente. Devolve a função
        que leva cada instante entre a abertura da vaga e o limite dela para o horário comercial
        (segunda a sexta, 8h às 18h, fora de feriado), sem inverter a ordem de nada e sem sair
        da janela da vaga."""
        a, b = self.no_eixo(abertura), self.no_eixo(limite, fim=True)
        total = (limite - abertura).total_seconds()

        def ajustar(t: datetime) -> datetime:
            parte = min(max((t - abertura).total_seconds() / total, 0.0), 1.0) if total > 0 else 0.0
            x = a + parte * max(b - a, 0.0)
            n = min(int(x // JORNADA), len(self.dias_uteis) - 1)
            abre = datetime.combine(self.dias_uteis[n], time(8, 0))
            return abre + timedelta(seconds=x - n * JORNADA)

        return ajustar

    def candidatura(
        self,
        vaga_id: int,
        vaga: motor.Vaga,
        indice: int,
        janela: int,
        fim_da_vaga: date,
        aprovado: bool,
    ) -> None:
        pessoa = self.pessoas[indice]
        u = self.rng.random(12)
        ano = vaga.abertura.year
        no_show = (
            historia.referencia_do_ano("no_show_entrevista", ano) * FATOR_DO_NO_SHOW_DE_ENTREVISTA
        )
        com_cliente = u[0] < cp.ENTREVISTA_NO_CLIENTE[vaga.tipo_servico]
        limite = datetime.combine(fim_da_vaga, time(17, 30))
        inscricao = datetime.combine(vaga.abertura, time(8, 0)) + timedelta(
            days=float(u[1]) * janela * (0.35 if aprovado else 0.8), hours=float(u[2]) * 9
        )
        inscricao = min(inscricao, limite - timedelta(hours=2))
        comercial = self.horario_comercial(datetime.combine(vaga.abertura, time(8, 0)), limite)
        # o caminho: lista de (etapa, resultado, motivo); quem é aprovado passa por tudo
        caminho: list[tuple[int, str, str | None]] = []
        entrevistas: dict[int, bool] = {}  # etapa -> compareceu
        conclusao, motivo_final = "APROVADA", None
        if aprovado:
            etapas = [1, 2, 3, 4, 5] if com_cliente else [1, 2, 3, 5]
            caminho = [(e, "APROVADO", None) for e in etapas]
            entrevistas = dict.fromkeys([e for e in etapas if e in (2, 4)], True)
        else:
            conclusao, motivo_final, caminho, entrevistas = self.caminho_de_quem_nao_entra(
                u, no_show, com_cliente
            )

        # as datas: cada etapa começa quando a anterior termina
        aberta = vaga.situacao == "ABERTA"
        passo = (limite - inscricao) / (len(caminho) + 0.5) if aprovado else None
        entrada = inscricao
        etapa_atual = caminho[0][0]
        candidatura_id = len(self.linhas["ats.candidatura"]) + 1
        linhas_de_etapa: list[tuple[tuple[Any, ...], datetime, datetime]] = []
        interrompida = False
        for n, (etapa, resultado, motivo) in enumerate(caminho):
            duracao = (
                passo if passo is not None else timedelta(days=0.3 + float(u[3 + n % 6]) * 2.5)
            )
            saida = entrada + duracao
            ultima = n == len(caminho) - 1
            if aprovado and ultima:
                saida = limite
            if resultado == "PENDENTE" or (saida > limite and not aprovado):
                # a vaga acabou (fechou, foi cancelada, a história parou) com a pessoa no caminho
                interrompida = True
                chegou = comercial(entrada)
                linhas_de_etapa.append(
                    ((candidatura_id, etapa, chegou, None, "PENDENTE", None), chegou, chegou)
                )
                etapa_atual = etapa
                break
            if etapa in entrevistas:
                agendada = comercial(entrada + (saida - entrada) * 0.8)
                compareceu = entrevistas[etapa]
                self.linha(
                    "ats.entrevista",
                    (
                        candidatura_id,
                        "INTERNA" if etapa == 2 else "CLIENTE",
                        agendada,
                        agendada if compareceu else None,
                        compareceu,
                        None,
                        ("APROVADO" if resultado == "APROVADO" else "REPROVADO")
                        if compareceu
                        else "NAO_COMPARECEU",
                    ),
                    comercial(entrada),
                    comercial(saida),
                )
            motivo_id = self.id_motivo[("REPROVACAO", motivo)] if motivo else None
            chegou, saiu = comercial(entrada), comercial(saida)
            linhas_de_etapa.append(
                ((candidatura_id, etapa, chegou, saiu, resultado, motivo_id), chegou, saiu)
            )
            etapa_atual, entrada = etapa, saida
        if interrompida:
            conclusao, motivo_final = ("EM_ANDAMENTO" if aberta else "CANCELADA"), None
            fim_da_candidatura: datetime | None = None if aberta else limite
        else:
            fim_da_candidatura = entrada
        inscricao = comercial(inscricao)
        fim_da_candidatura = comercial(fim_da_candidatura) if fim_da_candidatura else None
        self.linha(
            "ats.candidatura",
            (
                vaga_id,
                pessoa["candidato_id"],
                inscricao.date(),
                etapa_atual,
                conclusao,
                fim_da_candidatura.date() if fim_da_candidatura else None,
                self.id_motivo[("REPROVACAO", motivo_final)] if motivo_final else None,
            ),
            inscricao,
            fim_da_candidatura,
        )
        for valores, criado, atualizado in linhas_de_etapa:
            self.linha("ats.candidatura_etapa", valores, criado, atualizado)

    def caminho_de_quem_nao_entra(
        self, u: np.ndarray[Any, Any], no_show: float, com_cliente: bool
    ) -> tuple[str, str | None, list[tuple[int, str, str | None]], dict[int, bool]]:
        caminho: list[tuple[int, str, str | None]] = []
        entrevistas: dict[int, bool] = {}
        if u[3] >= cp.PASSA_DA_TRIAGEM:
            motivo = _escolher(cp.REPROVACAO_NA_TRIAGEM, float(u[4]))
            return "REPROVADA", motivo, [(1, "REPROVADO", motivo)], entrevistas
        caminho.append((1, "APROVADO", None))
        if u[5] < no_show:
            entrevistas[2] = False
            return "REPROVADA", "NO_SHOW", [*caminho, (2, "REPROVADO", "NO_SHOW")], entrevistas
        entrevistas[2] = True
        if u[6] < cp.DESISTE_NA_ENTREVISTA_INTERNA:
            return (
                "DESISTENCIA",
                "DESISTENCIA",
                [*caminho, (2, "DESISTIU", "DESISTENCIA")],
                entrevistas,
            )
        if u[6] >= cp.DESISTE_NA_ENTREVISTA_INTERNA + cp.PASSA_DA_ENTREVISTA_INTERNA:
            motivo = _escolher(cp.REPROVACAO_NA_ENTREVISTA, float(u[7]))
            return "REPROVADA", motivo, [*caminho, (2, "REPROVADO", motivo)], entrevistas
        caminho.append((2, "APROVADO", None))
        if u[8] >= cp.PASSA_DO_ENCAMINHAMENTO:
            motivo = _escolher(cp.REPROVACAO_NO_ENCAMINHAMENTO, float(u[9]))
            return "REPROVADA", motivo, [*caminho, (3, "REPROVADO", motivo)], entrevistas
        caminho.append((3, "APROVADO", None))
        if com_cliente:
            if u[10] < no_show * cp.FATOR_DO_NO_SHOW_NO_CLIENTE:
                entrevistas[4] = False
                return "REPROVADA", "NO_SHOW", [*caminho, (4, "REPROVADO", "NO_SHOW")], entrevistas
            entrevistas[4] = True
            if u[11] >= cp.PASSA_DA_ENTREVISTA_NO_CLIENTE:
                return "REPROVADA", "CLIENTE", [*caminho, (4, "REPROVADO", "CLIENTE")], entrevistas
            caminho.append((4, "APROVADO", None))
        # chegou ao fim, mas a posição ficou com outra pessoa: fica pendente até a vaga fechar
        return "CANCELADA", None, [*caminho, (5, "PENDENTE", None)], entrevistas

    # ───────────────────────── pessoas ─────────────────────────
    def admitir(self) -> None:
        ordem = sorted(self.vinculos, key=lambda v: (v.inicio, v.posto_id, v.posicao))
        ultima_alocacao: dict[tuple[int, int], int] = {}
        contratos_da_pessoa: dict[int, list[tuple[date | None, datetime]]] = {}
        for vinculo in ordem:
            indice = self.pessoa_do_vinculo[id(vinculo)]
            pessoa = self.pessoas[indice]
            posto = self.postos[vinculo.posto_id]
            filial_id = int(self.contratos[int(posto["contrato_id"])]["filial_id"])
            ano = vinculo.inicio.year
            retroativa = self.rng.random() < cp.ADMISSAO_RETROATIVA.get(
                ano, cp.ADMISSAO_RETROATIVA_DEPOIS
            )
            atraso = int(self.rng.integers(3, 31)) if retroativa else -int(self.rng.integers(1, 6))
            registro = self.momento(min(max(vinculo.inicio + timedelta(days=atraso), INICIO), HOJE))
            if pessoa["colaborador_id"] is None:
                self.novo_colaborador(pessoa, vinculo.inicio, registro)
            colaborador_id = int(pessoa["colaborador_id"])
            temporario = vinculo.tipo_servico == "TEMPORARIO"
            encerrado = vinculo.fim is not None
            saida = self.momento(vinculo.fim) if vinculo.fim else None
            prorrogacao = self.momento(vinculo.prorrogado_em) if vinculo.prorrogado_em else None
            contrato_id = self.linha(
                "pessoas.contrato_trabalho",
                (
                    colaborador_id,
                    "TEMPORARIO" if temporario else "TERCEIRIZADO",
                    vinculo.funcao_id,
                    filial_id,
                    vinculo.inicio,
                    vinculo.novo_termino or vinculo.prevista,
                    vinculo.fim,
                    round(
                        self.piso(filial_id, vinculo.funcao_id, vinculo.inicio)
                        * (1 + float(self.rng.random()) * 0.08),
                        2,
                    ),
                    int(posto["escala_id"]),
                    (motor.PRAZO_PRORROGADO if vinculo.novo_termino else motor.PRAZO_TEMPORARIO)
                    if temporario
                    else None,
                    "ENCERRADO" if encerrado else "ATIVO",
                ),
                registro,
                saida or prorrogacao,
            )
            contratos_da_pessoa.setdefault(indice, []).append((vinculo.fim, saida or registro))
            if vinculo.prorrogado_em and vinculo.novo_termino and prorrogacao:
                self.linha(
                    "pessoas.contrato_trabalho_prorrogacao",
                    (
                        contrato_id,
                        vinculo.prorrogado_em,
                        vinculo.novo_termino,
                        motor.PRAZO_PRORROGADO - motor.PRAZO_TEMPORARIO,
                    ),
                    prorrogacao,
                )
            chave = (vinculo.posto_id, vinculo.posicao)
            motivo_fim = None
            if encerrado:
                codigo = (
                    "NO_SHOW_PRIMEIRO_DIA"
                    if vinculo.no_show
                    else MOTIVO_DO_FIM_DA_ALOCACAO.get(str(vinculo.motivo), "FIM_CONTRATO")
                )
                motivo_fim = self.id_motivo[("FIM_ALOCACAO", codigo)]
            ultima_alocacao[chave] = self.linha(
                "pessoas.alocacao",
                (
                    colaborador_id,
                    contrato_id,
                    vinculo.posto_id,
                    vinculo.inicio,
                    vinculo.fim,
                    motivo_fim,
                    ultima_alocacao.get(chave),
                ),
                registro,
                saida,
            )
            if encerrado and vinculo.fim and saida:
                self.desligar(contrato_id, vinculo, filial_id, saida)
            self.afastar(colaborador_id, vinculo, pessoa)
        self.situacao_dos_colaboradores(contratos_da_pessoa)

    def novo_colaborador(self, pessoa: dict[str, Any], admissao: date, registro: datetime) -> None:
        self.ja_existiam.setdefault("cadastro.endereco", 0)
        endereco_id = self.linha(
            "cadastro.endereco",
            (
                com.LOGRADOUROS[int(self.rng.integers(len(com.LOGRADOUROS)))],
                str(int(self.rng.integers(10, 2500))),
                None,
                com.BAIRROS[int(self.rng.integers(len(com.BAIRROS)))],
                pessoa["municipio_id"],
                f"{int(self.rng.integers(10_000_000, 99_999_999))}",
                "COLABORADOR",
            ),
            registro,
        )
        numero = len(self.linhas["pessoas.colaborador"]) + 1
        pessoa["colaborador_id"] = self.linha(
            "pessoas.colaborador",
            (
                pessoa["candidato_id"],
                f"F{numero:06d}",
                pessoa["nome"],
                pessoa["cpf"],
                pessoa["nascimento"],
                pessoa["municipio_id"],
                endereco_id,
                self.novo_pis(),
                admissao,
                True,
            ),
            registro,
        )
        for tipo, orgao in cp.DOCUMENTOS:
            emissao = admissao - timedelta(days=int(self.rng.integers(200, 5000)))
            self.linha(
                "pessoas.colaborador_documento",
                (
                    pessoa["colaborador_id"],
                    tipo,
                    f"{int(self.rng.integers(10**7, 10**9))}",
                    orgao,
                    emissao,
                ),
                registro,
            )
        for _ in range(int(self.rng.poisson(0.7))):
            parentesco = _escolher(dict(cp.PARENTESCOS), float(self.rng.random()))
            idade = (
                int(self.rng.integers(0, 17))
                if parentesco in ("FILHO", "ENTEADO")
                else int(self.rng.integers(25, 70))
            )
            nomes = cp.NOMES_F if self.rng.random() < 0.5 else cp.NOMES_M
            sobrenome = str(pessoa["nome"]).split()[-1]
            self.linha(
                "pessoas.dependente",
                (
                    pessoa["colaborador_id"],
                    f"{nomes[int(self.rng.integers(len(nomes)))]} {sobrenome}",
                    parentesco,
                    date(
                        max(1940, admissao.year - idade),
                        int(self.rng.integers(1, 13)),
                        int(self.rng.integers(1, 29)),
                    ),
                ),
                registro,
            )

    def desligar(
        self, contrato_id: int, vinculo: motor.Vinculo, filial_id: int, saida: datetime
    ) -> None:
        if vinculo.fim is None:
            return
        dias = (vinculo.fim - vinculo.inicio).days + 1
        salario = self.piso(filial_id, vinculo.funcao_id, vinculo.inicio)
        proporcional = salario * min(dias, 365) / 365
        rescisao = proporcional * (2 + 1 / 3)  # 13º e férias com um terço, proporcionais
        aviso = 0
        if (
            vinculo.tipo_desligamento == "INVOLUNTARIO"
            and vinculo.tipo_servico != "TEMPORARIO"
            and dias > 90
        ):
            aviso, rescisao = 30, rescisao + salario + 0.4 * 0.08 * salario * dias / 30
        if vinculo.no_show or vinculo.motivo in ("ABANDONO", "JUSTA_CAUSA"):
            rescisao = salario * min(dias, 30) / 30 if not vinculo.no_show else 0.0
        homologacao = vinculo.fim + timedelta(days=int(self.rng.integers(1, 11)))
        self.linha(
            "pessoas.desligamento",
            (
                contrato_id,
                vinculo.fim,
                vinculo.tipo_desligamento,
                self.id_motivo[("DESLIGAMENTO", str(vinculo.motivo))],
                aviso,
                round(rescisao, 2),
                homologacao if homologacao <= HOJE else None,
            ),
            saida,
            self.momento(homologacao) if homologacao <= HOJE else None,
        )

    def afastar(self, colaborador_id: int, vinculo: motor.Vinculo, pessoa: dict[str, Any]) -> None:
        fim = vinculo.fim or HOJE
        dias = (fim - vinculo.inicio).days
        if dias < 30:
            return
        for _ in range(int(self.rng.poisson(cp.AFASTAMENTOS_POR_ANO_DE_CASA * dias / 365))):
            tipo, motivo, minimo, maximo, cid, _ = cp.AFASTAMENTOS[
                int(self.rng.choice(len(cp.AFASTAMENTOS), p=[a[5] for a in cp.AFASTAMENTOS]))
            ]
            if motivo == "MATERNIDADE" and pessoa["sexo"] != "F":
                continue
            inicio = vinculo.inicio + timedelta(days=int(self.rng.integers(10, dias)))
            retorno = inicio + timedelta(days=int(self.rng.integers(minimo, maximo + 1)))
            aberto = retorno > fim
            if aberto and vinculo.fim is not None:
                retorno, aberto = vinculo.fim, False
            self.linha(
                "pessoas.afastamento",
                (
                    colaborador_id,
                    tipo,
                    inicio,
                    None if aberto else retorno,
                    self.id_motivo[("AFASTAMENTO", motivo)],
                    cid,
                ),
                self.momento(inicio),
                None if aberto else self.momento(retorno),
            )

    def situacao_dos_colaboradores(
        self, contratos_da_pessoa: dict[int, list[tuple[date | None, datetime]]]
    ) -> None:
        linhas, carimbos = self.linhas["pessoas.colaborador"], self.carimbos["pessoas.colaborador"]
        for indice, contratos in contratos_da_pessoa.items():
            posicao = int(self.pessoas[indice]["colaborador_id"]) - 1
            ativo = any(fim is None for fim, _ in contratos)
            linhas[posicao] = (*linhas[posicao][:-1], ativo)
            criado, _ = carimbos[posicao]
            carimbos[posicao] = (criado, max(criado, max(quando for _, quando in contratos)))

    # ───────────────────────── saída ─────────────────────────
    def tabelas(self) -> Tabelas:
        prontas: Tabelas = {}
        for nome, colunas in COLUNAS.items():
            quadro = pd.DataFrame(self.linhas[nome], columns=list(colunas), dtype=object)
            quadro["criado_em"] = pd.Series([c for c, _ in self.carimbos[nome]], dtype=object)
            quadro["atualizado_em"] = pd.Series([a for _, a in self.carimbos[nome]], dtype=object)
            prontas[nome] = quadro
        return prontas


FATOR_DO_NO_SHOW_DE_ENTREVISTA = 1.26  # parte das entrevistas é no cliente, onde se falta menos


def _sem_acento(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _escolher(pesos: dict[str, float], u: float) -> str:
    acumulado, total = 0.0, sum(pesos.values())
    for nome, peso in pesos.items():
        acumulado += peso / total
        if u < acumulado:
            return nome
    return next(reversed(pesos))


def gerar_com_gabarito(publicos: Path = etapa1_cadastro.PUBLICOS) -> tuple[Tabelas, dict[str, Any]]:
    construtor = _Construtor(publicos)
    construtor.catalogos()
    construtor.funil()
    construtor.admitir()
    tabelas = construtor.tabelas()
    gabarito = {
        "duplicata_de": construtor.duplicata_de,
        "carteira": construtor.carteira,
        "mundo": construtor.mundo,
    }
    return tabelas, gabarito


def gerar(publicos: Path = etapa1_cadastro.PUBLICOS) -> Tabelas:
    tabelas, gabarito = gerar_com_gabarito(publicos)
    conferir(tabelas, gabarito)
    return tabelas


def _serie_diaria(inicios: list[date], fins: list[date | None]) -> np.ndarray[Any, Any]:
    dia0 = date(INICIO.year, 1, 1)
    n = (HOJE - dia0).days + 1
    delta = np.zeros(n + 1)
    for inicio, fim in zip(inicios, fins, strict=True):
        a, b = (inicio - dia0).days, ((fim or HOJE) - dia0).days + 1
        if a < n:
            delta[a] += 1
            delta[min(n, max(a, b))] -= 1
    return np.cumsum(delta)[:n]


def medir(t: Tabelas, gabarito: dict[str, Any]) -> Medidas:
    """As medidas da régua que o funil e as pessoas permitem tirar, somadas às da carteira."""
    r = etapa2_carteira._registros
    carteira: Tabelas = gabarito["carteira"]
    medidas = {k: dict(v) for k, v in etapa2_carteira.medir(carteira).items()}
    dia0 = date(INICIO.year, 1, 1)
    dias = [dia0 + timedelta(days=i) for i in range((HOJE - dia0).days + 1)]
    ano_de = np.array([d.year for d in dias])
    mes_de = np.array([d.month for d in dias])

    alocacoes = [
        a for a in r(t["pessoas.alocacao"]) if a["dt_fim"] is None or a["dt_fim"] > a["dt_inicio"]
    ]
    headcount = _serie_diaria([a["dt_inicio"] for a in alocacoes], [a["dt_fim"] for a in alocacoes])
    postos = r(carteira["comercial.posto"])
    posicoes = np.zeros(len(dias))
    for p in postos:
        serie = _serie_diaria([p["vigencia_inicio"]], [min(p["vigencia_fim"] or HOJE, HOJE)])
        posicoes += serie * p["quantidade"]
    medidas["headcount_medio"] = {str(a): float(headcount[ano_de == a].mean()) for a in bandas.ANOS}
    medidas["headcount_pico"] = {
        str(a): float(
            headcount[(ano_de == a) & (mes_de == (FIM.month if a == FIM.year else 12))].mean()
        )
        for a in bandas.ANOS
    }
    medidas["posto_descoberto_dias"] = {
        str(a): 30.4 * (1 - float(headcount[ano_de == a].sum() / posicoes[ano_de == a].sum()))
        for a in bandas.ANOS
    }
    mensal = {
        m: float(headcount[(ano_de == int(m[:4])) & (mes_de == int(m[5:]))].mean())
        for m in historia.meses()
    }
    medidas["naturalidade"]["headcount_desvio_maximo"] = derivadas.desvio_maximo_da_media_movel(
        mensal
    )

    vagas = r(t["ats.vaga"])
    requisicoes = {int(q["id"]): q for q in r(t["ats.requisicao"])}
    contratos = {int(k["id"]): k for k in r(carteira["comercial.contrato"])}
    tipo_da_vaga = {
        int(v["id"]): str(
            contratos[int(requisicoes[int(v["requisicao_id"])]["contrato_id"])]["tipo_servico"]
        )
        for v in vagas
    }
    calendario = motor.Calendario(
        [
            f["data"]
            for f in r(gabarito["mundo"]["cadastro.feriado"])
            if f["abrangencia"] == "NACIONAL"
        ]
    )
    medidas["vagas_abertas"] = {
        str(a): float(sum(1 for v in vagas if v["dt_abertura"].year == a)) for a in bandas.ANOS
    }
    for medida, tipos in (
        ("ttf_temporario_mediana", ("TEMPORARIO",)),
        ("ttf_rs_mediana", ("RECRUTAMENTO",)),
    ):
        medidas[medida] = {}
        for a in bandas.ANOS:
            tempos = [
                calendario.contar(v["dt_abertura"], v["dt_fechamento"])
                for v in vagas
                if v["status"] == "PREENCHIDA"
                and v["dt_abertura"].year == a
                and tipo_da_vaga[int(v["id"])] in tipos
            ]
            if tempos:
                medidas[medida][str(a)] = float(median(tempos))
    medidas["fill_rate"] = {}
    for a in bandas.ANOS:
        encerradas = [
            v
            for v in vagas
            if v["dt_abertura"].year == a and v["status"] in ("PREENCHIDA", "CANCELADA")
        ]
        pedidas = sum(v["quantidade_posicoes"] for v in encerradas)
        if pedidas:
            preenchidas = sum(
                v["quantidade_posicoes"] for v in encerradas if v["status"] == "PREENCHIDA"
            )
            medidas["fill_rate"][str(a)] = preenchidas / pedidas

    entrevistas = r(t["ats.entrevista"])
    medidas["no_show_entrevista"] = {}
    for a in bandas.ANOS:
        do_ano = [e for e in entrevistas if e["dt_agendada"].year == a]
        if do_ano:
            medidas["no_show_entrevista"][str(a)] = sum(
                1 for e in do_ano if e["fl_compareceu"] is False
            ) / len(do_ano)

    contratos_de_trabalho = r(t["pessoas.contrato_trabalho"])
    desligamento = {int(d["contrato_trabalho_id"]): d for d in r(t["pessoas.desligamento"])}
    no_show_id = next(
        int(m["id"])
        for m in r(gabarito["mundo"]["cadastro.motivo"])
        if m["codigo"] == "NO_SHOW_PRIMEIRO_DIA"
    )
    todas_as_alocacoes = r(t["pessoas.alocacao"])
    medidas["no_show_primeiro_dia"], medidas["turnover_90d"] = {}, {}
    for a in bandas.ANOS:
        do_ano = [x for x in todas_as_alocacoes if x["dt_inicio"].year == a]
        admitidos = [k for k in contratos_de_trabalho if k["dt_admissao"].year == a]
        if not do_ano or not admitidos:
            continue
        medidas["no_show_primeiro_dia"][str(a)] = sum(
            1 for x in do_ano if x["motivo_fim_id"] == no_show_id
        ) / len(do_ano)
        cedo = 0
        for k in admitidos:
            d = desligamento.get(int(k["id"]))
            if (
                d
                and d["tipo"] in ("VOLUNTARIO", "INVOLUNTARIO")
                and (d["dt_desligamento"] - k["dt_admissao"]).days <= 90
            ):
                cedo += 1
        medidas["turnover_90d"][str(a)] = cedo / len(admitidos)

    # sazonalidade contra o CAGED, na mesma janela da referência (2023 a 2025)
    admissoes = dict.fromkeys(historia.meses(), 0.0)
    desligamentos = dict.fromkeys(historia.meses(), 0.0)
    for k in contratos_de_trabalho:
        admissoes[k["dt_admissao"].strftime("%Y-%m")] += 1
        if k["dt_rescisao"] is not None:
            desligamentos[k["dt_rescisao"].strftime("%Y-%m")] += 1
    janela = {m for m in admissoes if "2023" <= m[:4] <= "2025"}
    medidas["sazonalidade_admissoes"] = derivadas.sazonalidade_contra_caged(
        {m: v for m, v in admissoes.items() if m in janela}
    )
    medidas["sazonalidade_desligamentos"] = derivadas.sazonalidade_contra_caged(
        {m: v for m, v in desligamentos.items() if m in janela}, "indice_desligamentos"
    )

    # mix de 2024: pessoas em atendimento (alocados por tipo; efetivados por R&S na garantia)
    em_2024 = ano_de == 2024
    tipo_do_posto = {
        int(p["id"]): str(contratos[int(p["contrato_id"])]["tipo_servico"]) for p in postos
    }
    por_tipo = {}
    for tipo in ("TEMPORARIO", "TERCEIRIZACAO"):
        do_tipo = [x for x in alocacoes if tipo_do_posto[int(x["posto_id"])] == tipo]
        por_tipo[tipo] = float(
            _serie_diaria([x["dt_inicio"] for x in do_tipo], [x["dt_fim"] for x in do_tipo])[
                em_2024
            ].mean()
        )
    efetivados = [
        v
        for v in vagas
        if v["status"] == "PREENCHIDA" and tipo_da_vaga[int(v["id"])] == "RECRUTAMENTO"
    ]
    garantia: np.ndarray[Any, Any] = np.zeros(len(dias))
    for v in efetivados:
        fim = min(v["dt_fechamento"] + timedelta(days=89), HOJE)
        garantia += _serie_diaria([v["dt_fechamento"]], [fim]) * v["quantidade_posicoes"]
    por_tipo["RS_EFETIVO"] = float(garantia[em_2024].mean())
    total = sum(por_tipo.values())
    medidas["mix_servico_2024"] = {tipo: valor / total for tipo, valor in por_tipo.items()}

    medidas["linhas_tabela"] = {
        nome: float(len(t[nome]))
        for nome in ("ats.candidatura_etapa", "ats.candidatura", "ats.candidato")
    }

    # coerência interna que esta etapa já permite conferir
    vigencia = {int(k["id"]): (k["dt_admissao"], k["dt_rescisao"]) for k in contratos_de_trabalho}
    fora_do_contrato = 0
    for x in todas_as_alocacoes:
        admissao, rescisao = vigencia[int(x["contrato_trabalho_id"])]
        fim = x["dt_fim"] or HOJE
        if x["dt_inicio"] < admissao or (rescisao is not None and fim > rescisao):
            fora_do_contrato += 1
    excesso = 0
    quantidade = {int(p["id"]): int(p["quantidade"]) for p in postos}
    por_posto: dict[int, list[tuple[date, int]]] = {}
    for x in alocacoes:
        eventos = por_posto.setdefault(int(x["posto_id"]), [])
        eventos.append((x["dt_inicio"], 1))
        eventos.append(((x["dt_fim"] or HOJE) + timedelta(days=1), -1))
    for posto_id, eventos in por_posto.items():
        ocupados = 0
        for _, passo in sorted(eventos):
            ocupados += passo
            if ocupados > quantidade[posto_id]:
                excesso += 1
                break
    medidas["violacoes"] = {"C-01": float(fora_do_contrato), "C-05": float(excesso)}

    # a sujeira na medida certa
    candidatos = r(t["ats.candidato"])
    sujeira: dict[str, float] = {
        "CAD-01": len(gabarito["duplicata_de"]) / len(candidatos),
        "CAD-02": sum(1 for c in candidatos if c["cpf"] is not None and not cpf_valido(c["cpf"]))
        / len(candidatos),
        "CAD-03": sum(
            1
            for c in candidatos
            if not 14 <= (c["dt_cadastro"].year - c["dt_nascimento"].year) <= 90
        )
        / len(candidatos),
    }
    criado_em = t["pessoas.contrato_trabalho"]["criado_em"].tolist()
    retro: dict[str, list[int]] = {"ate_2022": [0, 0], "desde_2024": [0, 0]}
    for k, criado in zip(contratos_de_trabalho, criado_em, strict=True):
        chave = (
            "ate_2022"
            if k["dt_admissao"].year <= 2022
            else "desde_2024"
            if k["dt_admissao"].year >= 2024
            else None
        )
        if chave:
            retro[chave][0] += criado.date() > k["dt_admissao"]
            retro[chave][1] += 1
    for chave, (sim, todos) in retro.items():
        sujeira[f"PES-01/{chave}"] = sim / max(1, todos)
    prorrogados = {
        int(p["contrato_trabalho_id"]) for p in r(t["pessoas.contrato_trabalho_prorrogacao"])
    }
    temporarios = [k for k in contratos_de_trabalho if k["tipo"] == "TEMPORARIO"]
    irregulares = []
    for k in temporarios:
        dias_de_casa = ((k["dt_rescisao"] or HOJE) - k["dt_admissao"]).days + 1
        limite = motor.PRAZO_PRORROGADO if int(k["id"]) in prorrogados else motor.PRAZO_TEMPORARIO
        if dias_de_casa > limite:
            irregulares.append(k)
    sujeira["PES-02"] = len(irregulares) / len(temporarios)
    sujeira["PES-02/parcela_desde_2023"] = sum(
        1
        for k in irregulares
        if (k["dt_admissao"] + timedelta(days=motor.PRAZO_TEMPORARIO)).year >= 2023
    ) / max(1, len(irregulares))
    medidas["sujeira"] = sujeira
    return medidas


def laudo_parcial(medidas: Medidas) -> Laudo:
    entregues = {(m, chave) for m, valores in medidas.items() for chave in valores}
    return avaliar([c for c in bandas.checks() if (c.medida, c.chave) in entregues], medidas)


def conferir(t: Tabelas, gabarito: dict[str, Any]) -> None:
    """O aceite da etapa: chaves, unicidade, datas dentro da história e a régua parcial."""
    problemas: list[str] = []
    referencia = {**gabarito["mundo"], **gabarito["carteira"]}

    def ids(nome: str) -> set[int]:
        juntos: set[int] = set()
        for fonte in (gabarito["mundo"], gabarito["carteira"], t):
            if nome in fonte:
                juntos |= set(fonte[nome]["id"])
        return juntos

    for filha, coluna, mae in (
        ("ats.requisicao", "cliente_id", "comercial.cliente"),
        ("ats.requisicao", "contrato_id", "comercial.contrato"),
        ("ats.requisicao", "posto_id", "comercial.posto"),
        ("ats.requisicao", "motivo_cancelamento_id", "cadastro.motivo"),
        ("ats.vaga", "requisicao_id", "ats.requisicao"),
        ("ats.vaga", "funcao_id", "cadastro.funcao"),
        ("ats.candidato", "municipio_id", "cadastro.municipio"),
        ("ats.candidato", "fonte_id", "ats.fonte_candidato"),
        ("ats.candidato_experiencia", "candidato_id", "ats.candidato"),
        ("ats.candidatura", "vaga_id", "ats.vaga"),
        ("ats.candidatura", "candidato_id", "ats.candidato"),
        ("ats.candidatura", "etapa_atual_id", "ats.etapa_funil"),
        ("ats.candidatura_etapa", "candidatura_id", "ats.candidatura"),
        ("ats.entrevista", "candidatura_id", "ats.candidatura"),
        ("pessoas.colaborador", "candidato_id", "ats.candidato"),
        ("pessoas.colaborador", "endereco_id", "cadastro.endereco"),
        ("pessoas.contrato_trabalho", "colaborador_id", "pessoas.colaborador"),
        ("pessoas.contrato_trabalho", "escala_id", "cadastro.escala"),
        ("pessoas.alocacao", "contrato_trabalho_id", "pessoas.contrato_trabalho"),
        ("pessoas.alocacao", "posto_id", "comercial.posto"),
        ("pessoas.alocacao", "substituindo_alocacao_id", "pessoas.alocacao"),
        ("pessoas.desligamento", "contrato_trabalho_id", "pessoas.contrato_trabalho"),
        ("pessoas.afastamento", "colaborador_id", "pessoas.colaborador"),
        ("pessoas.dependente", "colaborador_id", "pessoas.colaborador"),
    ):
        usados = set(t[filha][coluna].dropna().astype(int))
        orfaos = usados - ids(mae)
        if orfaos:
            problemas.append(f"{filha}.{coluna} órfã: {sorted(orfaos)[:5]}")
    for nome, chave in (
        ("pessoas.colaborador", ["matricula"]),
        ("pessoas.colaborador", ["cpf"]),
        ("pessoas.colaborador", ["candidato_id"]),
        ("pessoas.desligamento", ["contrato_trabalho_id"]),
        ("ats.requisicao", ["numero"]),
        ("ats.vaga", ["codigo"]),
    ):
        if t[nome].duplicated(chave).any():
            problemas.append(f"{nome}: chave {chave} repetida")
    for nome, quadro in t.items():
        if not (quadro["atualizado_em"] >= quadro["criado_em"]).all():
            problemas.append(f"{nome}: atualizado antes de criado")
        if not (quadro["atualizado_em"] <= FIM).all():
            problemas.append(f"{nome}: carimbo depois do fim da história")
    primeiro_endereco = len(referencia["cadastro.endereco"]) and (
        len(gabarito["mundo"]["cadastro.endereco"])
        + len(gabarito["carteira"]["cadastro.endereco"])
        + 1
    )
    if (
        len(t["cadastro.endereco"])
        and int(t["cadastro.endereco"]["id"].iloc[0]) != primeiro_endereco
    ):
        problemas.append("cadastro.endereco não continua os ids das etapas anteriores")
    for r_ in laudo_parcial(medir(t, gabarito)).com_situacao(Situacao.REPROVADO):
        problemas.append(f"régua {r_.check.codigo}: {r_.valor} fora de {r_.check.banda}")
    if problemas:
        raise ValueError("etapa 3 reprovada:\n- " + "\n- ".join(problemas))
