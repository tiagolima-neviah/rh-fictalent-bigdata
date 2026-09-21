"""Etapa 2 do gerador: a carteira comercial, mês a mês, de 2018-01 a 2026-09.

Nada aqui é escrito por decreto. A cada mês a simulação decide: quem entra (sorteio em torno
do número de entradas do ano, com os meses de contrato novo pesando mais), quem renova, quem
sai (por mercado, na renovação; na pandemia, por redução; por serviço, meses depois de a
qualidade sentida passar do limite de cada cliente), quantos postos abrir ou fechar para a
carteira sustentar o headcount alvo do mês, e quantas reclamações a operação recebe.

A defasagem entre a queda de qualidade e a perda do contrato não é parâmetro: o cliente
formaliza a insatisfação (ADVERTENCIA) quando a média dos últimos seis meses passa do limite
dele, e só rompe na renovação seguinte (se ela estiver a pelo menos quatro meses) ou com
rescisão antecipada seis a nove meses depois.

Tabelas: 8 de `comercial`, mais os endereços e os centros de custo de contrato em `cadastro`
(continuando os ids da etapa 1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import fmean, median
from typing import Any

import numpy as np

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador import catalogos_comercial as com
from rh_fictalent.gerador import etapa1_cadastro, historia
from rh_fictalent.gerador.nucleo import FIM, INICIO, Tabelas, aleatorio, instante, tabela
from rh_fictalent.validacao import bandas, derivadas
from rh_fictalent.validacao.regua import Laudo, Medidas, Situacao, avaliar

# colunas que o gravador insere nulas e preenche depois (o ciclo centro_custo <-> contrato)
ADIADAS = {"cadastro.centro_custo": ["contrato_id"]}
POSICOES_PARA_CENTRO_DE_CUSTO = 30
FOLGA_DO_ALVO = 0.01  # a carteira só reage a desvio maior que 1% do alvo de posições
HOJE = FIM.date()
PARCELA_QUE_REAGE = 0.38  # clientes que rompem quando a qualidade sentida passa do limite
TOLERANCIA_MINIMA = 0.76  # o cliente mais sensível formaliza com a degradação em 0,76
MESES_DE_CASA_PARA_REAGIR = 6  # antes disso o cliente ainda não tem histórico para julgar
CHANCE_DE_SAIR_NA_RENOVACAO = 0.08  # por mercado, a cada renovação anual
CHANCE_EXTRA_NA_PRIMEIRA = 0.05  # cliente novo é mais frágil
CHANCE_EXTRA_EM_2020 = 0.12
RISCO_MENSAL_NA_PANDEMIA = 0.09  # clientes pequenos e médios, de março a junho de 2020


@dataclass
class Cliente:
    id: int
    porte: str
    setor: str
    base: int  # posições-base: o tamanho do cliente
    tolerancia: float  # quanto de degradação sentida ele aguenta antes de formalizar
    ancora: bool
    filial_id: int
    enderecos: list[int]
    principal: int = 0  # id do contrato com postos (ou do único, se for só R&S)
    cruzou: date | None = None
    saida: date | None = None
    motivo_saida: str | None = None
    fora: bool = False
    contratos: list[int] = field(default_factory=list)


class _Carteira:
    """O estado da simulação: as linhas já escritas e quem está vivo em cada mês."""

    def __init__(self, publicos: Path) -> None:
        self.rng = aleatorio("etapa2_carteira")
        self.mundo = etapa1_cadastro.gerar(publicos)
        self.clientes: dict[int, Cliente] = {}
        self.l_cliente: list[dict[str, Any]] = []
        self.l_contato: list[dict[str, Any]] = []
        self.l_contrato: list[dict[str, Any]] = []
        self.l_aditivo: list[dict[str, Any]] = []
        self.l_posto: list[dict[str, Any]] = []
        self.l_preco: list[dict[str, Any]] = []
        self.l_sla: list[dict[str, Any]] = []
        self.l_ocorrencia: list[dict[str, Any]] = []
        self.l_endereco: list[dict[str, Any]] = []
        self.l_centro: list[dict[str, Any]] = []
        self.id_endereco = len(self.mundo["cadastro.endereco"])
        self.id_centro = len(self.mundo["cadastro.centro_custo"])
        self.cnpjs: set[str] = set()
        self.saidas_no_mes: dict[str, int] = {}
        self.postos_do_contrato: dict[int, list[int]] = {}
        self.precos_do_posto: dict[int, list[int]] = {}
        self.fila_de_ocorrencias: list[tuple[date, dict[str, Any]]] = []
        self.reajustes_pendentes: list[tuple[int, date, float]] = []
        self.fim_do_mes = INICIO
        self.resto_reclamacoes = 0.0
        self.resto_elogios = 0.0

        municipios = self.mundo["cadastro.municipio"]
        regioes = self.mundo["cadastro.regiao"].set_index("id")["nome"].to_dict()
        self.municipios_da_regiao: dict[str, list[tuple[int, str, str]]] = {}
        for m in _registros(municipios):
            self.municipios_da_regiao.setdefault(regioes[m["regiao_id"]], []).append(
                (int(m["id"]), str(m["nome"]), str(m["uf"]))
            )
        self.ibge_do_municipio = {
            int(m["id"]): str(m["codigo_ibge"]) for m in _registros(municipios)
        }
        self.id_motivo = {
            (str(m["tipo"]), str(m["codigo"])): int(m["id"])
            for m in _registros(self.mundo["cadastro.motivo"])
        }
        self.id_escala = {
            str(e["codigo"]): int(e["id"]) for e in _registros(self.mundo["cadastro.escala"])
        }
        filiais = _registros(self.mundo["cadastro.filial"])
        self.id_filial = {str(f["codigo"]): int(f["id"]) for f in filiais}
        municipio_do_endereco = {
            int(e["id"]): int(e["municipio_id"])
            for e in _registros(self.mundo["cadastro.endereco"])
        }
        self.municipio_da_filial = {
            int(f["id"]): municipio_do_endereco[int(f["endereco_id"])] for f in filiais
        }
        self.pisos = self._indice_de_pisos()

    # ───────────────────────── utilidades ─────────────────────────
    def sortear(self, pesos: dict[str, float]) -> str:
        nomes = list(pesos)
        p = np.array([pesos[n] for n in nomes], dtype=float)
        return nomes[int(self.rng.choice(len(nomes), p=p / p.sum()))]

    def dia_util(self, primeiro: date, ultimo: date) -> date:
        dias = [
            primeiro + timedelta(days=i)
            for i in range((ultimo - primeiro).days + 1)
            if (primeiro + timedelta(days=i)).weekday() < 5
        ]
        return dias[int(self.rng.integers(len(dias)))] if dias else primeiro

    def momento(self, dia: date) -> datetime:
        quando = instante(dia, int(self.rng.integers(8, 18)), int(self.rng.integers(0, 60)))
        return min(quando, FIM)

    def carimbo(self, dia: date) -> dict[str, datetime]:
        quando = self.momento(dia)
        return {"criado_em": quando, "atualizado_em": quando}

    def _indice_de_pisos(self) -> dict[tuple[int, int], list[tuple[date, float, float]]]:
        """(município da convenção, função) -> [(início da vigência, piso, insalubridade)]."""
        municipio_da_convencao = {
            int(k["id"]): int(k["municipio_id"])
            for k in _registros(self.mundo["cadastro.convencao_coletiva"])
        }
        indice: dict[tuple[int, int], list[tuple[date, float, float]]] = {}
        for p in _registros(self.mundo["cadastro.piso_salarial"]):
            chave = (municipio_da_convencao[int(p["convencao_id"])], int(p["funcao_id"]))
            indice.setdefault(chave, []).append(
                (
                    p["vigencia_inicio"],
                    float(p["valor_piso"]),
                    float(p["adicional_insalubridade_pct"]),
                )
            )
        return indice

    def custo_do_posto(self, filial_id: int, funcao_id: int, dia: date) -> float:
        da_funcao = self.pisos[(self.municipio_da_filial[filial_id], funcao_id)]
        _, piso, insalubridade = [v for v in da_funcao if v[0] <= dia][-1]
        reajuste = math.prod(1 + r for ano, r in cat.REAJUSTES.items() if ano <= dia.year)
        beneficios = com.BENEFICIOS_EM_2017 * reajuste
        return piso * (1 + insalubridade) * (1 + com.ENCARGOS_SOBRE_O_PISO) + beneficios

    # ───────────────────────── leitura do estado ─────────────────────────
    def contrato(self, contrato_id: int) -> dict[str, Any]:
        return self.l_contrato[contrato_id - 1]

    def ativos(self) -> list[Cliente]:
        return [c for c in self.clientes.values() if not c.fora]

    def postos_abertos(
        self, referencia: date, contrato_id: int | None = None
    ) -> list[dict[str, Any]]:
        if contrato_id is None:
            universo = self.l_posto
        else:
            universo = [self.l_posto[i - 1] for i in self.postos_do_contrato.get(contrato_id, [])]
        return [p for p in universo if p["vigencia_fim"] is None or p["vigencia_fim"] >= referencia]

    def posicoes(self, referencia: date, tipo: str | None = None) -> int:
        return sum(
            p["quantidade"]
            for p in self.postos_abertos(referencia)
            if tipo is None or self.contrato(p["contrato_id"])["tipo_servico"] == tipo
        )

    # ───────────────────────── entradas ─────────────────────────
    def novo_endereco(self, municipio_id: int, tipo: str, dia: date) -> int:
        self.id_endereco += 1
        self.l_endereco.append(
            {
                "id": self.id_endereco,
                "logradouro": com.LOGRADOUROS[int(self.rng.integers(len(com.LOGRADOUROS)))],
                "numero": str(int(self.rng.integers(10, 4000))),
                "complemento": None,
                "bairro": com.BAIRROS[int(self.rng.integers(len(com.BAIRROS)))],
                "municipio_id": municipio_id,
                "cep": f"{int(self.rng.integers(10_000_000, 99_999_999))}",
                "tipo": tipo,
                **self.carimbo(dia),
            }
        )
        return self.id_endereco

    def novo_cnpj(self) -> str:
        while True:
            base = f"{int(self.rng.integers(10_000_000, 99_999_999))}0001"
            for pesos in (
                (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
                (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2),
            ):
                resto = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
                base += str(0 if resto < 2 else 11 - resto)
            if base not in self.cnpjs:
                self.cnpjs.add(base)
                return base

    def nome_de_empresa(self) -> str:
        silabas = int(self.rng.integers(2, 4))
        corpo = "".join(
            com.INICIOS[int(self.rng.integers(len(com.INICIOS)))]
            + com.VOGAIS[int(self.rng.integers(len(com.VOGAIS)))]
            for _ in range(silabas)
        )
        return (corpo + com.FINAIS[int(self.rng.integers(len(com.FINAIS)))]).capitalize()

    def filial_de(self, municipio: str, uf: str, dia: date) -> int:
        abertura = {f.codigo: f.dt_abertura for f in cat.FILIAIS}
        if uf == "MG" and dia >= abertura["EXT"]:
            return self.id_filial["EXT"]
        da_braganca = uf == "MG" or municipio in com.MUNICIPIOS_DA_FILIAL_DE_BRAGANCA
        if da_braganca and dia >= abertura["BRG"]:
            return self.id_filial["BRG"]
        return self.id_filial["ATB"]

    def entrar(self, dia: date, porte: str | None = None) -> None:
        ancora = porte is not None
        porte = porte or self.sortear({p: v[0] for p, v in com.PORTES.items()})
        setor = self.sortear({s: v[0] for s, v in com.SETORES.items()})
        regiao = "Região Bragantina" if ancora else self.sortear(com.REGIOES_DOS_CLIENTES)
        cidades = self.municipios_da_regiao[regiao]
        da_filial = {f.codigo_ibge for f in cat.FILIAIS}
        pesos = {
            str(i): (
                com.PESO_DA_CIDADE_DE_FILIAL if self.ibge_do_municipio[m[0]] in da_filial else 1.0
            )
            for i, m in enumerate(cidades)
        }
        municipio_id, municipio, uf = cidades[int(self.sortear(pesos))]
        _, base_min, base_max, *_ = com.PORTES[porte]

        cliente_id = len(self.l_cliente) + 1
        cadastro = dia - timedelta(days=int(self.rng.integers(5, 25)))
        cadastro = max(cadastro, INICIO)
        sede = self.novo_endereco(municipio_id, "CLIENTE", cadastro)
        locais = [sede]
        if porte in ("GRANDE", "MEDIA"):
            locais = [
                self.novo_endereco(municipio_id, "LOCAL_TRABALHO", cadastro)
                for _ in range(int(self.rng.integers(1, 3)))
            ]
        cliente = Cliente(
            id=cliente_id,
            porte=porte,
            setor=setor,
            base=int(self.rng.integers(base_min, base_max + 1)),
            tolerancia=(
                float(self.rng.uniform(TOLERANCIA_MINIMA, 1.0))
                if self.rng.random() < PARCELA_QUE_REAGE
                else math.inf
            ),
            ancora=ancora,
            filial_id=self.filial_de(municipio, uf, dia),
            enderecos=locais,
        )
        self.clientes[cliente_id] = cliente
        nome = self.nome_de_empresa()
        ramo = com.SETORES[setor][2][int(self.rng.integers(len(com.SETORES[setor][2])))]
        self.l_cliente.append(
            {
                "razao_social": f"{nome} {ramo} {'S.A.' if porte == 'GRANDE' else 'Ltda'}",
                "nome_fantasia": nome,
                "cnpj": self.novo_cnpj(),
                "porte": porte,
                "setor": setor,
                "municipio_id": municipio_id,
                "endereco_id": sede,
                "dt_primeiro_contrato": dia,
                "origem": "INDICACAO" if ancora else self.sortear(com.ORIGENS),
                "ativo": True,
                **self.carimbo(cadastro),
            }
        )
        for i in range(int(self.rng.integers(1, 4))):
            primeiro = com.NOMES[int(self.rng.integers(len(com.NOMES)))]
            ultimo = com.SOBRENOMES[int(self.rng.integers(len(com.SOBRENOMES)))]
            usuario = f"{primeiro}.{ultimo}".lower().encode("ascii", "ignore").decode()
            self.l_contato.append(
                {
                    "cliente_id": cliente_id,
                    "nome": f"{primeiro} {ultimo}",
                    "cargo": com.CARGOS_DE_CONTATO[
                        int(self.rng.integers(len(com.CARGOS_DE_CONTATO)))
                    ],
                    "email": f"{usuario}@{nome.lower()}.example",
                    "telefone": f"(11) 90000-{int(self.rng.integers(0, 10000)):04d}",
                    "fl_principal": i == 0,
                    **self.carimbo(cadastro),
                }
            )

        # no começo a empresa coloca gente efetiva (R&S); o temporário e a terceirização vêm depois
        so_recrutamento = (not ancora) and self.rng.random() < {2018: 0.35, 2019: 0.20}.get(
            dia.year, 0.10
        )
        if so_recrutamento:
            cliente.principal = self.novo_contrato(cliente, "RECRUTAMENTO", dia)
            return
        cliente.principal = self.novo_contrato(cliente, self.sortear(com.SETORES[setor][3]), dia)
        pacote = max(1, round(cliente.base * float(self.rng.uniform(0.4, 0.7))))
        _, _, _, _, posto_max, *_ = com.PORTES[porte]
        while pacote > 0:  # o cliente novo chega com os primeiros postos
            quantidade = min(pacote, int(self.rng.integers(1, posto_max + 1)))
            self.abrir_posto(cliente, cliente.principal, quantidade, dia.strftime("%Y-%m"))
            pacote -= quantidade
        if self.rng.random() < (0.5 if dia.year <= 2019 else 0.25):
            self.novo_contrato(cliente, "RECRUTAMENTO", dia)

    def novo_contrato(self, cliente: Cliente, tipo: str, inicio: date) -> int:
        contrato_id = len(self.l_contrato) + 1
        assinatura = max(inicio - timedelta(days=int(self.rng.integers(3, 16))), INICIO)
        sequencia = (
            sum(1 for k in self.l_contrato if k["dt_assinatura"].year == assinatura.year) + 1
        )
        self.l_contrato.append(
            {
                "numero": f"CT-{assinatura.year}-{sequencia:04d}",
                "cliente_id": cliente.id,
                "tipo_servico": tipo,
                "filial_id": cliente.filial_id,
                "centro_custo_id": cliente.filial_id,  # o centro de custo da filial tem o id dela
                "dt_assinatura": assinatura,
                "vigencia_inicio": inicio,
                "vigencia_fim": _mais_meses(inicio, 12) - timedelta(days=1),
                "prazo_pagamento_dias": 45 if cliente.porte == "GRANDE" else 28,
                "indice_reajuste": self.sortear(com.INDICES_DE_REAJUSTE),
                "garantia_reposicao_dias": 90 if tipo == "RECRUTAMENTO" else 0,
                "status": "ATIVO",
                "dt_encerramento": None,
                "motivo_encerramento_id": None,
                **self.carimbo(assinatura),
            }
        )
        cliente.contratos.append(contrato_id)
        penalidade = {"GRANDE": 0.05, "MEDIA": 0.03}.get(cliente.porte, 0.0)
        for indicador, meta, unidade in com.SLAS[tipo]:
            self.l_sla.append(
                {
                    "contrato_id": contrato_id,
                    "indicador": indicador,
                    "meta_valor": float(meta),
                    "unidade": unidade,
                    "penalidade_pct": penalidade,
                    **self.carimbo(assinatura),
                }
            )
        return contrato_id

    # ───────────────────────── postos e preços ─────────────────────────
    def abrir_posto(self, cliente: Cliente, contrato_id: int, quantidade: int, mes: str) -> None:
        primeiro, ultimo = historia.limites_do_mes(mes)
        k = self.contrato(contrato_id)
        # posto novo começa na primeira quinzena: o cliente quer o mês cheio (é o que o alvo supõe)
        quinzena = min(ultimo, date(primeiro.year, primeiro.month, 15))
        comeco = max(primeiro, k["vigencia_inicio"])
        inicio = self.dia_util(comeco, max(comeco, quinzena))
        familia = self.sortear(com.SETORES[cliente.setor][1])
        funcoes = {
            str(i): com.PESO_DO_NIVEL[f.nivel]
            for i, f in enumerate(cat.FUNCOES, start=1)
            if f.familia == familia
        }
        funcao_id = int(self.sortear(funcoes))
        turnos, escalas = com.JORNADAS[familia]
        fim: date | None = None
        numero = int(mes[5:])
        if k["tipo_servico"] == "TEMPORARIO" and numero >= 8:
            # reforço da temporada: a maioria encerra na última semana de dezembro (o CAGED
            # mostra o pico de desligamentos do setor em dezembro), o resto em janeiro
            ano = int(mes[:4])
            em_dezembro = numero < 12 and self.rng.random() < 0.60
            fim = (
                date(ano, 12, int(self.rng.integers(18, 32)))
                if em_dezembro
                else date(ano + 1, 1, int(self.rng.integers(2, 21)))
            )
        # o cliente pede o posto com antecedência, e a temporada é planejada mais cedo ainda
        antecedencia = int(self.rng.integers(10, 31) if fim else self.rng.integers(5, 16))
        if inicio.year >= 2026:
            antecedencia *= 3  # escaldado pela demora de 2025, o cliente passa a pedir bem antes
        criado = max(inicio - timedelta(days=antecedencia), k["dt_assinatura"])
        self.l_posto.append(
            {
                "contrato_id": contrato_id,
                "funcao_id": funcao_id,
                "quantidade": quantidade,
                "turno": self.sortear(turnos),
                "escala_id": self.id_escala[self.sortear(escalas)],
                "endereco_id": cliente.enderecos[int(self.rng.integers(len(cliente.enderecos)))],
                "vigencia_inicio": inicio,
                "vigencia_fim": fim,
                **self.carimbo(criado),
            }
        )
        self.postos_do_contrato.setdefault(contrato_id, []).append(len(self.l_posto))
        _, _, _, _, _, markup_min, markup_max = com.PORTES[cliente.porte]
        self.novo_preco(
            len(self.l_posto), float(self.rng.uniform(markup_min, markup_max)), inicio, criado
        )
        if self.posicoes_do_contrato(contrato_id, inicio) > POSICOES_PARA_CENTRO_DE_CUSTO:
            self.dar_centro_de_custo(contrato_id, inicio)

    def novo_preco(self, posto_id: int, markup: float, inicio: date, criado: date) -> None:
        posto = self.l_posto[posto_id - 1]
        k = self.contrato(posto["contrato_id"])
        mensal = round(self.custo_do_posto(k["filial_id"], posto["funcao_id"], inicio) * markup, 2)
        self.l_preco.append(
            {
                "posto_id": posto_id,
                "valor_mensal": mensal,
                "valor_hora": round(mensal / com.HORAS_NO_MES, 2),
                "markup_aplicado": round(markup, 4),
                "vigencia_inicio": inicio,
                "vigencia_fim": posto["vigencia_fim"],
                **self.carimbo(criado),
            }
        )
        self.precos_do_posto.setdefault(posto_id, []).append(len(self.l_preco))

    def posicoes_do_contrato(self, contrato_id: int, referencia: date) -> int:
        return sum(p["quantidade"] for p in self.postos_abertos(referencia, contrato_id))

    def dar_centro_de_custo(self, contrato_id: int, dia: date) -> None:
        k = self.contrato(contrato_id)
        if k["centro_custo_id"] != k["filial_id"]:
            return  # já tem o seu
        self.id_centro += 1
        cliente = self.l_cliente[k["cliente_id"] - 1]
        self.l_centro.append(
            {
                "id": self.id_centro,
                "codigo": f"CC-{k['numero']}",
                "nome": f"Contrato {k['numero']} · {cliente['nome_fantasia']}",
                "tipo": "CONTRATO",
                "filial_id": k["filial_id"],
                "contrato_id": contrato_id,
                **self.carimbo(dia),
            }
        )
        k["centro_custo_id"] = self.id_centro
        k["atualizado_em"] = self.l_centro[-1]["criado_em"]

    def fechar_posto(self, posto_id: int, dia: date) -> None:
        posto = self.l_posto[posto_id - 1]
        ultimo_preco = self.l_preco[self.precos_do_posto[posto_id][-1] - 1]
        dia = max(dia, ultimo_preco["vigencia_inicio"])
        posto["vigencia_fim"] = dia
        posto["atualizado_em"] = max(self.momento(dia), posto["criado_em"])
        for preco_id in self.precos_do_posto[posto_id]:
            preco = self.l_preco[preco_id - 1]
            if preco["vigencia_fim"] is None or preco["vigencia_fim"] > dia:
                preco["vigencia_fim"] = dia
                preco["atualizado_em"] = max(posto["atualizado_em"], preco["criado_em"])

    # ───────────────────────── renovação, reajuste e saída ─────────────────────────
    def aditivo(self, contrato_id: int, tipo: str, dia: date, **campos: Any) -> None:
        numero = sum(1 for a in self.l_aditivo if a["contrato_id"] == contrato_id) + 1
        self.l_aditivo.append(
            {
                "contrato_id": contrato_id,
                "numero": numero,
                "tipo": tipo,
                "dt_assinatura": dia,
                "vigencia_nova": campos.get("vigencia_nova"),
                "percentual_reajuste": campos.get("percentual_reajuste"),
                **self.carimbo(dia),
            }
        )

    def renovar(self, contrato_id: int, dia: date) -> None:
        k = self.contrato(contrato_id)
        aniversario = k["vigencia_fim"] + timedelta(days=1)
        k["vigencia_fim"] = _mais_meses(aniversario, 12) - timedelta(days=1)
        self.aditivo(contrato_id, "PRORROGACAO", dia, vigencia_nova=k["vigencia_fim"])
        k["atualizado_em"] = self.l_aditivo[-1]["criado_em"]
        if self.postos_abertos(aniversario, contrato_id):
            reajuste = cat.REAJUSTES.get(aniversario.year, 0.04)
            self.aditivo(contrato_id, "REAJUSTE", dia, percentual_reajuste=reajuste)
            self.reajustes_pendentes.append((contrato_id, aniversario, reajuste))

    def aplicar_reajustes(self, ultimo: date) -> None:
        """No aniversário do contrato, cada posto aberto ganha preço novo; o antigo se encerra."""
        vencidos = [r for r in self.reajustes_pendentes if r[1] <= ultimo]
        self.reajustes_pendentes = [r for r in self.reajustes_pendentes if r[1] > ultimo]
        for contrato_id, aniversario, _reajuste in vencidos:
            if self.contrato(contrato_id)["status"] != "ATIVO":
                continue
            for posto_id in self.postos_do_contrato.get(contrato_id, []):
                posto = self.l_posto[posto_id - 1]
                aberto = posto["vigencia_fim"] is None or posto["vigencia_fim"] >= aniversario
                if not aberto or posto["vigencia_inicio"] >= aniversario:
                    continue
                vigente = self.l_preco[self.precos_do_posto[posto_id][-1] - 1]
                vigente["vigencia_fim"] = aniversario - timedelta(days=1)
                vigente["atualizado_em"] = max(self.momento(aniversario), vigente["criado_em"])
                markup = float(vigente["markup_aplicado"])
                self.novo_preco(posto_id, markup, aniversario, aniversario)

    def ocorrencia(
        self,
        contrato_id: int,
        dia: date,
        tipo: str,
        texto: str,
        motivo: str | None,
        posto: int | None,
    ) -> None:
        if dia > HOJE:
            return
        linha = {
            "contrato_id": contrato_id,
            "posto_id": posto,
            "dt_ocorrencia": dia,
            "tipo": tipo,
            "descricao": texto,
            "motivo_id": self.id_motivo[("OCORRENCIA", motivo)] if motivo else None,
        }
        if dia > self.fim_do_mes:
            self.fila_de_ocorrencias.append((dia, linha))
        else:
            self.l_ocorrencia.append({**linha, **self.carimbo(dia)})

    def soltar_ocorrencias(self) -> None:
        prontas = [o for o in self.fila_de_ocorrencias if o[0] <= self.fim_do_mes]
        self.fila_de_ocorrencias = [o for o in self.fila_de_ocorrencias if o[0] > self.fim_do_mes]
        for dia, linha in sorted(prontas, key=lambda o: o[0]):
            self.l_ocorrencia.append({**linha, **self.carimbo(dia)})

    def agendar_saida(self, cliente: Cliente, dia: date, motivo: str) -> None:
        cliente.saida, cliente.motivo_saida = dia, motivo
        mes = dia.strftime("%Y-%m")
        self.saidas_no_mes[mes] = self.saidas_no_mes.get(mes, 0) + 1
        aviso = max(dia - timedelta(days=30), self.contrato(cliente.principal)["vigencia_inicio"])
        self.ocorrencia(cliente.principal, aviso, "AVISO_RESCISAO", com.TEXTO_DO_AVISO, None, None)

    def cabe_mais_uma_saida(self, mes: str) -> bool:
        livre = mes in historia.PANDEMIA or mes >= bandas.INICIO_DA_CRISE
        return livre or self.saidas_no_mes.get(mes, 0) < bandas.SAIDAS_MAXIMAS_NO_MES

    def sair(self, cliente: Cliente) -> None:
        dia, motivo = cliente.saida, cliente.motivo_saida
        if dia is None or motivo is None:
            raise RuntimeError("saída sem data ou motivo")
        quando = self.momento(dia)
        for contrato_id in cliente.contratos:
            k = self.contrato(contrato_id)
            if k["status"] == "ENCERRADO":
                continue
            k.update(
                status="ENCERRADO",
                dt_encerramento=dia,
                motivo_encerramento_id=self.id_motivo[("PERDA_CONTRATO", motivo)],
                atualizado_em=max(quando, k["criado_em"]),
            )
            for posto_id in self.postos_do_contrato.get(contrato_id, []):
                posto = self.l_posto[posto_id - 1]
                if posto["vigencia_fim"] is None or posto["vigencia_fim"] > dia:
                    self.fechar_posto(posto_id, max(dia, posto["vigencia_inicio"]))
        linha = self.l_cliente[cliente.id - 1]
        linha["ativo"], linha["atualizado_em"] = False, max(quando, linha["criado_em"])
        cliente.fora = True

    def qualidade_passou_do_limite(self, cliente: Cliente, mes: str) -> None:
        """O cliente formaliza a insatisfação e decide quando sai: daqui nasce a defasagem."""
        primeiro, ultimo = historia.limites_do_mes(mes)
        cliente.cruzou = self.dia_util(primeiro, ultimo)
        adverte = cliente.cruzou + timedelta(days=int(self.rng.integers(0, 15)))
        self.ocorrencia(
            cliente.principal,
            adverte,
            "ADVERTENCIA",
            com.TEXTO_DA_ADVERTENCIA,
            "ATRASO_REPOSICAO",
            None,
        )
        fim = self.contrato(cliente.principal)["vigencia_fim"]
        while (fim - cliente.cruzou).days < 120:
            fim = _mais_meses(fim + timedelta(days=1), 12) - timedelta(days=1)
        if (fim - cliente.cruzou).days > 300:  # renovação longe demais: rescisão antecipada
            fim = cliente.cruzou + timedelta(days=int(self.rng.integers(180, 271)))
        while not self.cabe_mais_uma_saida(fim.strftime("%Y-%m")):
            fim += timedelta(days=30)
        self.agendar_saida(cliente, fim, self.sortear(com.SAIDA_POR_SERVICO))

    # ───────────────────────── o mês ─────────────────────────
    def decidir_renovacoes(self, mes: str, seguinte: str | None) -> None:
        if seguinte is None:
            return
        primeiro, ultimo = historia.limites_do_mes(mes)
        inicio_seguinte, fim_seguinte = historia.limites_do_mes(seguinte)
        for cliente in self.ativos():
            for contrato_id in list(cliente.contratos):
                k = self.contrato(contrato_id)
                vence = k["vigencia_fim"]
                if k["status"] != "ATIVO" or not inicio_seguinte <= vence <= fim_seguinte:
                    continue
                if cliente.saida is not None:
                    if vence < cliente.saida:
                        self.renovar(contrato_id, self.dia_util(primeiro, ultimo))
                    continue
                if contrato_id != cliente.principal:
                    tem_postos = k["tipo_servico"] != "RECRUTAMENTO"
                    if tem_postos or self.rng.random() < 0.7:
                        self.renovar(contrato_id, self.dia_util(primeiro, ultimo))
                    else:  # o contrato de R&S acabou; o cliente segue com o principal
                        k.update(
                            status="ENCERRADO",
                            dt_encerramento=vence,
                            motivo_encerramento_id=self.id_motivo[
                                ("PERDA_CONTRATO", "FIM_PROJETO")
                            ],
                            atualizado_em=self.momento(min(vence, HOJE)),
                        )
                    continue
                primeira_renovacao = (vence - k["vigencia_inicio"]).days < 400
                chance = CHANCE_DE_SAIR_NA_RENOVACAO
                chance += CHANCE_EXTRA_NA_PRIMEIRA if primeira_renovacao else 0.0
                chance += CHANCE_EXTRA_EM_2020 if vence.year == 2020 else 0.0
                chance *= 0.3 if cliente.ancora else 1.0
                if cliente.ancora and vence.year == 2020:
                    chance = 0.0  # a empresa atravessa a pandemia sem perder cliente âncora
                cabe = self.cabe_mais_uma_saida(vence.strftime("%Y-%m"))
                if self.rng.random() < chance and cabe:
                    self.agendar_saida(cliente, vence, self.sortear(com.SAIDA_POR_MERCADO))
                else:
                    self.renovar(contrato_id, self.dia_util(primeiro, ultimo))

    def ajustar_postos(self, mes: str, alvo: float, alvo_suave: float) -> None:
        primeiro, ultimo = historia.limites_do_mes(mes)
        referencia = min(date(primeiro.year, primeiro.month, 15), ultimo)
        parcela = historia.PARCELA_TERCEIRIZACAO[primeiro.year]
        for tipo, alvo_do_tipo in (
            ("TERCEIRIZACAO", alvo_suave * parcela),
            ("TEMPORARIO", alvo - alvo_suave * parcela),
        ):
            falta = alvo_do_tipo - self.posicoes(referencia, tipo)
            if falta > max(1.0, FOLGA_DO_ALVO * alvo_do_tipo):
                self.abrir_ate(falta, tipo, mes, ultimo)
            elif -falta > max(1.0, FOLGA_DO_ALVO * alvo_do_tipo):
                self.fechar_ate(-falta, tipo, primeiro, referencia)

    def abrir_ate(self, falta: float, tipo: str, mes: str, ultimo: date) -> None:
        firmes = [
            c for c in self.ativos() if c.saida is None or c.saida > ultimo + timedelta(days=60)
        ]
        candidatos = [
            (c, k)
            for c in firmes
            for k in c.contratos
            if self.contrato(k)["tipo_servico"] == tipo and self.contrato(k)["status"] == "ATIVO"
        ]
        if not candidatos:
            # ninguém contrata este serviço ainda: o maior cliente ganha um segundo contrato
            com_postos = [
                c for c in firmes if self.contrato(c.principal)["tipo_servico"] != "RECRUTAMENTO"
            ]
            if not com_postos:
                return
            maior = max(com_postos, key=lambda c: (c.base, -c.id))
            primeiro, _ = historia.limites_do_mes(mes)
            inicio = self.dia_util(
                max(primeiro, self.contrato(maior.principal)["vigencia_inicio"]), ultimo
            )
            candidatos = [(maior, self.novo_contrato(maior, tipo, inicio))]
        pesos = {str(i): float(c.base) for i, (c, _) in enumerate(candidatos)}
        for _ in range(400):
            if falta < 1:
                break
            cliente, contrato_id = candidatos[int(self.sortear(pesos))]
            _, _, _, posto_min, posto_max, *_ = com.PORTES[cliente.porte]
            quantidade = min(int(self.rng.integers(posto_min, posto_max + 1)), math.ceil(falta))
            antes = self.posicoes_do_contrato(contrato_id, ultimo)
            self.abrir_posto(cliente, contrato_id, quantidade, mes)
            falta -= quantidade
            if antes >= 8 and quantidade >= 0.25 * antes and quantidade >= 5:
                inicio = self.l_posto[-1]["vigencia_inicio"]
                ja_tem = any(
                    a["contrato_id"] == contrato_id
                    and a["tipo"] == "ESCOPO"
                    and a["dt_assinatura"].strftime("%Y-%m") == mes
                    for a in self.l_aditivo
                )
                if not ja_tem:
                    self.aditivo(contrato_id, "ESCOPO", inicio)

    def fechar_ate(self, sobra: float, tipo: str, primeiro: date, referencia: date) -> None:
        abertos = [
            (i, p)
            for i, p in enumerate(self.l_posto, start=1)
            if (p["vigencia_fim"] is None or p["vigencia_fim"] >= referencia)
            and p["vigencia_inicio"] < primeiro
            and self.contrato(p["contrato_id"])["tipo_servico"] == tipo
        ]
        # primeiro o reforço de temporada que sobrou (tem fim marcado), depois o resto
        sorteio = [int(i) for i in self.rng.permutation(len(abertos))]
        ordem = sorted(sorteio, key=lambda i: abertos[i][1]["vigencia_fim"] is None)
        for posicao in ordem:
            if sobra < 1:
                break
            posto_id, posto = abertos[int(posicao)]
            if posto["quantidade"] > sobra * 1.5:
                continue  # fechar este posto inteiro passaria muito do ponto
            self.fechar_posto(posto_id, self.dia_util(primeiro, referencia))
            sobra -= posto["quantidade"]

    def registrar_ocorrencias(self, mes: str) -> None:
        primeiro, ultimo = historia.limites_do_mes(mes)
        referencia = min(date(primeiro.year, primeiro.month, 15), ultimo)
        fracao = _fracao_do_mes(mes)
        por_contrato: dict[int, int] = {}
        for posto in self.postos_abertos(referencia):
            if posto["vigencia_inicio"] <= ultimo:
                k = posto["contrato_id"]
                por_contrato[k] = por_contrato.get(k, 0) + posto["quantidade"]
        if not por_contrato:
            return
        total = sum(por_contrato.values())
        degradacao = historia.degradacao(mes)
        taxa = historia.referencia_do_ano("reclamacoes_100_postos", primeiro.year)
        self.resto_reclamacoes += taxa * total / 100 * fracao
        self.resto_elogios += 0.5 * (1 - 0.6 * degradacao) * total / 100 * fracao
        pesos = {
            str(k): q * (3.0 if self.clientes[self.contrato(k)["cliente_id"]].cruzou else 1.0)
            for k, q in por_contrato.items()
        }
        motivos = {
            codigo: saudavel + (degradado - saudavel) * degradacao
            for codigo, (saudavel, degradado, _) in com.RECLAMACOES.items()
        }
        while self.resto_reclamacoes >= 1:
            self.resto_reclamacoes -= 1
            contrato_id = int(self.sortear(pesos))
            motivo = self.sortear(motivos)
            postos = [
                i
                for i in self.postos_do_contrato[contrato_id]
                if self.l_posto[i - 1]["vigencia_inicio"] <= ultimo
                and (
                    self.l_posto[i - 1]["vigencia_fim"] is None
                    or self.l_posto[i - 1]["vigencia_fim"] >= referencia
                )
            ]
            no_posto = self.rng.random() < 0.7 and bool(postos)
            posto_id = postos[int(self.rng.integers(len(postos)))] if no_posto else None
            dia = self.dia_util(
                max(primeiro, self.contrato(contrato_id)["vigencia_inicio"]), ultimo
            )
            texto = com.RECLAMACOES[motivo][2]
            self.ocorrencia(contrato_id, dia, "RECLAMACAO", texto, motivo, posto_id)
        while self.resto_elogios >= 1:
            self.resto_elogios -= 1
            contrato_id = int(self.sortear({str(k): float(q) for k, q in por_contrato.items()}))
            dia = self.dia_util(
                max(primeiro, self.contrato(contrato_id)["vigencia_inicio"]), ultimo
            )
            self.ocorrencia(contrato_id, dia, "ELOGIO", com.TEXTO_DO_ELOGIO, "ELOGIO", None)


def _registros(quadro: Any) -> list[dict[str, Any]]:
    """As linhas de um DataFrame como dicionários de tipos nativos."""
    return [dict(linha) for linha in quadro.to_dict("records")]


def _mais_meses(dia: date, meses: int) -> date:
    total = dia.year * 12 + dia.month - 1 + meses
    ano, mes = divmod(total, 12)
    ultimo = (date(ano + (mes == 11), (mes + 1) % 12 + 1, 1) - timedelta(days=1)).day
    return date(ano, mes + 1, min(dia.day, ultimo))


def _fracao_do_mes(mes: str) -> float:
    """Quanto do mês a história cobre (só setembro de 2026 é parcial)."""
    primeiro, ultimo = historia.limites_do_mes(mes)
    cheio = (_mais_meses(date(primeiro.year, primeiro.month, 1), 1) - timedelta(days=1)).day
    return ((ultimo - date(primeiro.year, primeiro.month, 1)).days + 1) / cheio


def _entradas_do_mes(
    mes: str, ativos: int, alvo: dict[str, float], resto: float
) -> tuple[int, float]:
    """Quantos clientes entram no mês: o comercial fecha parte da distância até a meta de dois
    meses à frente, mais nos meses em que contrato novo costuma nascer, nunca em rajada."""
    if mes in historia.PANDEMIA:
        return 0, 0.0
    todos = list(alvo)
    adiante = todos[min(todos.index(mes) + 2, len(todos) - 1)]
    peso = historia.PESO_DO_MES_PARA_ENTRADA[int(mes[5:]) - 1] * _fracao_do_mes(mes)
    resto += max(0.0, historia.ESFORCO_COMERCIAL * (alvo[adiante] - ativos)) * peso
    crescimento_do_ano = alvo[
        f"{mes[:4]}-{min(12, FIM.month if mes[:4] == str(FIM.year) else 12):02d}"
    ]
    crescimento_do_ano -= alvo.get(f"{int(mes[:4]) - 1}-12", float(historia.FUNDADORES))
    teto = 3 if crescimento_do_ano >= 12 else 2
    entram = min(int(resto), teto)
    return entram, min(resto - entram, float(teto))


def simular(publicos: Path = etapa1_cadastro.PUBLICOS) -> _Carteira:
    carteira = _Carteira(publicos)
    alvo = historia.posicoes_alvo()
    clientes_alvo = historia.clientes_alvo()
    resto_de_entradas = 0.0
    todos = historia.meses()
    for indice, mes in enumerate(todos):
        primeiro, ultimo = historia.limites_do_mes(mes)
        carteira.fim_do_mes = ultimo
        carteira.soltar_ocorrencias()
        carteira.aplicar_reajustes(ultimo)
        for cliente in carteira.ativos():
            if cliente.saida is not None and cliente.saida <= ultimo:
                carteira.sair(cliente)
        media_de_seis_meses = fmean(
            historia.degradacao(m) for m in todos[max(0, indice - 5) : indice + 1]
        )
        for cliente in carteira.ativos():
            chegada = carteira.contrato(cliente.contratos[0])["vigencia_inicio"]
            de_casa = (primeiro - chegada).days >= 30 * MESES_DE_CASA_PARA_REAGIR
            sem_plano = de_casa and cliente.cruzou is None and cliente.saida is None
            if sem_plano and media_de_seis_meses >= cliente.tolerancia:
                carteira.qualidade_passou_do_limite(cliente, mes)
        if mes in historia.PANDEMIA:
            for cliente in carteira.ativos():
                pequeno = not cliente.ancora and cliente.porte in ("ME", "EPP", "MEDIA")
                if (
                    pequeno
                    and cliente.saida is None
                    and carteira.rng.random() < RISCO_MENSAL_NA_PANDEMIA
                ):
                    dia = carteira.dia_util(primeiro, ultimo)
                    carteira.agendar_saida(cliente, dia, carteira.sortear(com.SAIDA_NA_PANDEMIA))
                    carteira.sair(cliente)
        if indice == 0:
            entram = len(com.FUNDADORES)
        else:
            entram, resto_de_entradas = _entradas_do_mes(
                mes, len(carteira.ativos()), clientes_alvo, resto_de_entradas
            )
        for i in range(entram):
            fundador = com.FUNDADORES[i] if indice == 0 else None
            carteira.entrar(carteira.dia_util(primeiro, ultimo), fundador)
        carteira.decidir_renovacoes(mes, todos[indice + 1] if indice + 1 < len(todos) else None)
        janela = todos[max(0, indice - 6) : indice + 6]
        carteira.ajustar_postos(mes, alvo[mes], fmean(alvo[m] for m in janela))
        carteira.registrar_ocorrencias(mes)
    return carteira


def gerar(publicos: Path = etapa1_cadastro.PUBLICOS) -> Tabelas:
    c = simular(publicos)
    centros = [{k: v for k, v in linha.items() if k != "id"} for linha in c.l_centro]
    enderecos = [{k: v for k, v in linha.items() if k != "id"} for linha in c.l_endereco]
    tabelas: Tabelas = {
        "cadastro.endereco": _continuar(tabela(enderecos), len(c.mundo["cadastro.endereco"])),
        "cadastro.centro_custo": _continuar(tabela(centros), len(c.mundo["cadastro.centro_custo"])),
        "comercial.cliente": tabela(c.l_cliente),
        "comercial.cliente_contato": tabela(c.l_contato),
        "comercial.contrato": tabela(c.l_contrato),
        "comercial.contrato_aditivo": tabela(c.l_aditivo),
        "comercial.posto": tabela(c.l_posto),
        "comercial.posto_preco": tabela(c.l_preco),
        "comercial.sla_contrato": tabela(c.l_sla),
        "comercial.contrato_ocorrencia": tabela(c.l_ocorrencia),
    }
    conferir(tabelas, c.mundo)
    return tabelas


def _continuar(quadro: Any, ja_existem: int) -> Any:
    quadro["id"] = quadro["id"] + ja_existem
    return quadro


def medir(t: Tabelas) -> Medidas:
    """As medidas da régua que a carteira já permite tirar (as demais ficam pendentes)."""
    contratos = _registros(t["comercial.contrato"])
    clientes = _registros(t["comercial.cliente"])
    postos = _registros(t["comercial.posto"])
    ocorrencias = _registros(t["comercial.contrato_ocorrencia"])
    meses = historia.meses()

    ativos: dict[str, float] = {}
    for ano in bandas.ANOS:
        dia = min(date(ano, 12, 31), HOJE)
        vivos = {
            k["cliente_id"]
            for k in contratos
            if k["vigencia_inicio"] <= dia
            and (k["dt_encerramento"] is None or k["dt_encerramento"] > dia)
        }
        ativos[str(ano)] = float(len(vivos))

    primeira_vigencia: dict[int, date] = {}
    ultimo_encerramento: dict[int, date] = {}
    for k in contratos:
        cliente_id = int(k["cliente_id"])
        anterior = primeira_vigencia.get(cliente_id, k["vigencia_inicio"])
        primeira_vigencia[cliente_id] = min(anterior, k["vigencia_inicio"])
        if k["dt_encerramento"] is not None:
            ultimo = ultimo_encerramento.get(cliente_id, k["dt_encerramento"])
            ultimo_encerramento[cliente_id] = max(ultimo, k["dt_encerramento"])
    entradas = dict.fromkeys(meses, 0.0)
    for dia in primeira_vigencia.values():
        entradas[dia.strftime("%Y-%m")] += 1
    saidas = dict.fromkeys(meses, 0.0)
    for cliente in clientes:
        if not cliente["ativo"]:
            saidas[ultimo_encerramento[int(cliente["id"])].strftime("%Y-%m")] += 1

    reclamacoes: dict[str, float] = {}
    for ano in bandas.ANOS:
        posicoes_mes = 0.0
        for mes in (m for m in meses if int(m[:4]) == ano):
            primeiro, ultimo = historia.limites_do_mes(mes)
            referencia = min(date(primeiro.year, primeiro.month, 15), ultimo)
            abertas = sum(
                p["quantidade"]
                for p in postos
                if p["vigencia_inicio"] <= ultimo
                and (p["vigencia_fim"] is None or p["vigencia_fim"] >= referencia)
            )
            posicoes_mes += abertas * _fracao_do_mes(mes)
        do_ano = sum(
            1 for o in ocorrencias if o["tipo"] == "RECLAMACAO" and o["dt_ocorrencia"].year == ano
        )
        reclamacoes[str(ano)] = do_ano / (posicoes_mes / 100)

    primeira_advertencia: dict[int, date] = {}
    for o in ocorrencias:
        if o["tipo"] == "ADVERTENCIA":
            k_id = int(o["contrato_id"])
            anterior = primeira_advertencia.get(k_id, o["dt_ocorrencia"])
            primeira_advertencia[k_id] = min(anterior, o["dt_ocorrencia"])
    encerrado_em = {int(k["id"]): k["dt_encerramento"] for k in contratos}
    esperas = [
        (encerrado_em[k_id] - dia).days / 30.44
        for k_id, dia in primeira_advertencia.items()
        if encerrado_em[k_id] is not None
    ]

    medidas: dict[str, dict[str, float]] = {
        "clientes_ativos_fim_ano": ativos,
        "naturalidade": {
            "saidas_max_mes_fora_crise": derivadas.maximo_no_mes(
                saidas, derivadas.meses_de_crise(saidas)
            ),
            "entradas_max_mes": derivadas.maximo_no_mes(entradas),
            "entradas_concentracao_max": derivadas.concentracao_maxima(entradas),
        },
        "reclamacoes_100_postos": reclamacoes,
    }
    if esperas:
        medidas["defasagem_qualidade_perda"] = {"mediana_meses": float(median(esperas))}
    return medidas


def laudo_parcial(medidas: Medidas) -> Laudo:
    """A régua só nos checks cuja medida esta etapa entrega; o resto espera as próximas."""
    entregues = {(m, chave) for m, valores in medidas.items() for chave in valores}
    checks = [c for c in bandas.checks() if (c.medida, c.chave) in entregues]
    return avaliar(checks, medidas)


def conferir(t: Tabelas, mundo: Tabelas) -> None:
    """O aceite da etapa: chaves, vigências, preço vigente único e a régua parcial."""
    problemas: list[str] = []

    def exigir(condicao: bool, mensagem: str) -> None:
        if not condicao:
            problemas.append(mensagem)

    def ids(nome: str) -> set[int]:
        base = set(mundo[nome]["id"]) if nome in mundo else set()
        return base | (set(t[nome]["id"]) if nome in t else set())

    for filha, coluna, mae in (
        ("cadastro.endereco", "municipio_id", "cadastro.municipio"),
        ("cadastro.centro_custo", "filial_id", "cadastro.filial"),
        ("cadastro.centro_custo", "contrato_id", "comercial.contrato"),
        ("comercial.cliente", "municipio_id", "cadastro.municipio"),
        ("comercial.cliente", "endereco_id", "cadastro.endereco"),
        ("comercial.cliente_contato", "cliente_id", "comercial.cliente"),
        ("comercial.contrato", "cliente_id", "comercial.cliente"),
        ("comercial.contrato", "filial_id", "cadastro.filial"),
        ("comercial.contrato", "centro_custo_id", "cadastro.centro_custo"),
        ("comercial.contrato", "motivo_encerramento_id", "cadastro.motivo"),
        ("comercial.contrato_aditivo", "contrato_id", "comercial.contrato"),
        ("comercial.posto", "contrato_id", "comercial.contrato"),
        ("comercial.posto", "funcao_id", "cadastro.funcao"),
        ("comercial.posto", "escala_id", "cadastro.escala"),
        ("comercial.posto", "endereco_id", "cadastro.endereco"),
        ("comercial.posto_preco", "posto_id", "comercial.posto"),
        ("comercial.sla_contrato", "contrato_id", "comercial.contrato"),
        ("comercial.contrato_ocorrencia", "contrato_id", "comercial.contrato"),
        ("comercial.contrato_ocorrencia", "posto_id", "comercial.posto"),
        ("comercial.contrato_ocorrencia", "motivo_id", "cadastro.motivo"),
    ):
        usados = set(t[filha][coluna].dropna().astype(int))
        exigir(usados <= ids(mae), f"{filha}.{coluna} órfã: {sorted(usados - ids(mae))[:5]}")

    for nome, chave in (
        ("comercial.cliente", ["cnpj"]),
        ("comercial.contrato", ["numero"]),
        ("comercial.contrato_aditivo", ["contrato_id", "numero"]),
        ("comercial.sla_contrato", ["contrato_id", "indicador"]),
        ("cadastro.centro_custo", ["codigo"]),
    ):
        exigir(not t[nome].duplicated(chave).any(), f"{nome}: chave {chave} repetida")

    for nome, quadro in t.items():
        exigir(bool((quadro["atualizado_em"] >= quadro["criado_em"]).all()), f"{nome}: carimbo")
        exigir(bool((quadro["atualizado_em"] <= FIM).all()), f"{nome}: carimbo depois do fim")

    contratos = t["comercial.contrato"].set_index("id")
    postos = t["comercial.posto"]
    comeco = postos["contrato_id"].map(contratos["vigencia_inicio"])
    exigir(bool((postos["vigencia_inicio"] >= comeco).all()), "posto antes do contrato")
    exigir(bool((postos["vigencia_inicio"] <= HOJE).all()), "posto aberto no futuro")
    fechou = contratos["dt_encerramento"].to_dict()
    depois = [
        p.id
        for p in postos.itertuples(index=False)
        if fechou[p.contrato_id] is not None
        and (p.vigencia_fim is None or p.vigencia_fim > fechou[p.contrato_id])
    ]
    exigir(not depois, f"{len(depois)} postos abertos depois do encerramento do contrato")

    precos = t["comercial.posto_preco"].sort_values(["posto_id", "vigencia_inicio"])
    for posto_id, grupo in precos.groupby("posto_id"):
        fins = grupo["vigencia_fim"].tolist()
        inicios = grupo["vigencia_inicio"].tolist()
        emendado = all(
            f is not None and f + timedelta(days=1) == i
            for f, i in zip(fins[:-1], inicios[1:], strict=True)
        )
        exigir(emendado, f"posto {posto_id}: preços com buraco ou sobreposição")
    exigir(set(precos["posto_id"]) == set(postos["id"]), "posto sem preço")

    reprovados = laudo_parcial(medir(t)).com_situacao(Situacao.REPROVADO)
    for r in reprovados:
        problemas.append(f"régua {r.check.codigo}: {r.valor} fora de {r.check.banda}")
    if problemas:
        raise ValueError("etapa 2 reprovada:\n- " + "\n- ".join(problemas))
