"""Etapa 5 do gerador: o financeiro (10 tabelas de `financeiro`) e a planilha gerencial em Excel.

A receita nasce da medição: cada posto ocupado no mês vira item de fatura (a mensalidade do
posto pela parte do mês coberta, mais horas extras, menos faltas), e cada colocação de R&S
vira honorário. A fatura gera um título a receber, que o cliente paga em dia, com atraso, ou
não paga (a inadimplência cresce com a crise, concentrada em quem está de saída). O que sai
vira título a pagar: a folha e os encargos da etapa 4, os benefícios, os impostos apurados no
lucro presumido, os exames admissionais e a retaguarda.

Duas coisas aqui são contrato do caso:

- a empresa nunca fecha um ano no vermelho. O custo direto e os impostos saem da operação; a
  despesa da retaguarda (equipe interna, aluguel, sistemas) é o que fecha a conta na margem
  líquida do ano, e ela tem de sair positiva e plausível, senão a etapa reprova;
- o consolidado gerencial (a planilha que a gerente-geral monta à mão) bate com a operação
  até 2021 e diverge cada vez mais a partir de 2022 (GER-01). Ele vai para a réplica, como a
  planilha carregada no sistema, e para arquivos Excel, que são a fonte de arquivo do pipeline.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador import catalogos_financeiro as fin
from rh_fictalent.gerador import catalogos_folha as cf
from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, etapa4_ponto_folha
from rh_fictalent.gerador.nucleo import FIM, INICIO, Tabelas, aleatorio, tabela
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.regua import Laudo, Medidas, Situacao, avaliar

HOJE = FIM.date()
PLANILHAS = Path("dados/gerencial")
ORDEM = (
    "financeiro.regime_tributario",
    "financeiro.tributo",
    "financeiro.aliquota",
    "financeiro.fornecedor",
    "financeiro.fatura",
    "financeiro.fatura_item",
    "financeiro.titulo_receber",
    "financeiro.titulo_pagar",
    "financeiro.imposto_apurado",
    "financeiro.consolidado_gerencial",
)


def _mes(dia: date) -> date:
    return dia.replace(day=1)


def _mes_seguinte(competencia: date, dia: int = 1) -> date:
    proximo = (competencia.replace(day=28) + timedelta(days=4)).replace(day=1)
    return proximo.replace(day=dia)


def _dia_util(dia: date) -> date:
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


def _fim_do_mes(competencia: date) -> date:
    return _mes_seguinte(competencia) - timedelta(days=1)


def _momento(dia: date, hora: int = 9) -> datetime:
    return min(datetime.combine(dia, time(hora, 0)), FIM)


class _Financeiro:
    def __init__(self, publicos: Path, fracao: float) -> None:
        self.rng = aleatorio("etapa5_financeiro")
        self.fracao = fracao
        self.titulos_lancados: list[dict[str, Any]] = []
        self.despesa_da_retaguarda: dict[int, float] = {}
        self.real: dict[tuple[date, int], tuple[int, float]] = {}
        self.t4, self.base = etapa4_ponto_folha.gerar_com_base(publicos, fracao)
        r = etapa2_carteira._registros
        self.t3: Tabelas = self.base["etapa3"]
        carteira: Tabelas = self.base["carteira"]
        self.contratos = {int(k["id"]): k for k in r(carteira["comercial.contrato"])}
        self.clientes = {int(c["id"]): c for c in r(carteira["comercial.cliente"])}
        self.postos = {int(p["id"]): p for p in r(carteira["comercial.posto"])}
        self.alocacoes = {int(a["id"]): a for a in r(self.t3["pessoas.alocacao"])}
        self.precos: dict[int, list[tuple[date, float, float]]] = {}
        for p in r(carteira["comercial.posto_preco"]):
            vigencia = (p["vigencia_inicio"], float(p["valor_mensal"]), float(p["valor_hora"]))
            self.precos.setdefault(int(p["posto_id"]), []).append(vigencia)
        mundo: Tabelas = self.base["mundo"]
        self.filiais = {int(f["id"]): f for f in r(mundo["cadastro.filial"])}
        endereco = {int(e["id"]): int(e["municipio_id"]) for e in r(mundo["cadastro.endereco"])}
        self.municipio_da_filial = {
            i: endereco[int(f["endereco_id"])] for i, f in self.filiais.items()
        }
        centros = r(mundo["cadastro.centro_custo"])
        self.centro_da_filial = {
            int(c["filial_id"]): int(c["id"]) for c in centros if c["tipo"] == "FILIAL"
        }
        self.centro_da_retaguarda = next(int(c["id"]) for c in centros if c["tipo"] == "RETAGUARDA")
        self.ultima = _mes(HOJE) - timedelta(days=1)  # a última competência fechada é o mês passado
        self.ultima = _mes(self.ultima)
        self.reajuste = {
            a: float(np.prod([1 + v for k, v in cat.REAJUSTES.items() if 2018 < k <= a]))
            for a in bandas.ANOS
        }

    # ───────────────────────── catálogos ─────────────────────────
    def catalogos(self) -> Tabelas:
        entrada = {"criado_em": _momento(INICIO, 8), "atualizado_em": _momento(INICIO, 8)}
        regime = [
            {
                "regime": "LUCRO_PRESUMIDO",
                "vigencia_inicio": date(2018, 1, 1),
                "vigencia_fim": None,
                **entrada,
            }
        ]
        tributos = [
            {"codigo": c, "descricao": d, "esfera": e, **entrada} for c, d, e, _, _ in fin.TRIBUTOS
        ]
        self.id_tributo = {c: i for i, (c, *_) in enumerate(fin.TRIBUTOS, start=1)}
        aliquotas = []
        for filial_id, aliquota in fin.ISS_DA_FILIAL.items():
            aliquotas.append(
                {
                    "tributo_id": self.id_tributo["ISS"],
                    "municipio_id": self.municipio_da_filial[self.id_da_filial(filial_id)],
                    "aliquota": aliquota,
                    "base_presumida_pct": None,
                    "vigencia_inicio": date(2018, 1, 1),
                    "vigencia_fim": None,
                    **entrada,
                }
            )
        for codigo, _, _, federal, presumida in fin.TRIBUTOS:
            if codigo != "ISS":
                aliquotas.append(
                    {
                        "tributo_id": self.id_tributo[codigo],
                        "municipio_id": None,
                        "aliquota": federal,
                        "base_presumida_pct": presumida,
                        "vigencia_inicio": date(2018, 1, 1),
                        "vigencia_fim": None,
                        **entrada,
                    }
                )
        fornecedores = []
        for i, (razao, tipo) in enumerate(fin.FORNECEDORES, start=1):
            base_do_cnpj = f"{90_000_000 + i * 7919:08d}0001"
            fornecedores.append(
                {"razao_social": razao, "cnpj": _cnpj(base_do_cnpj), "tipo": tipo, **entrada}
            )
        self.id_fornecedor = {razao: i for i, (razao, _) in enumerate(fin.FORNECEDORES, start=1)}
        return {
            "financeiro.regime_tributario": tabela(regime),
            "financeiro.tributo": tabela(tributos),
            "financeiro.aliquota": tabela(aliquotas),
            "financeiro.fornecedor": tabela(fornecedores),
        }

    def id_da_filial(self, codigo: str) -> int:
        return next(i for i, f in self.filiais.items() if f["codigo"] == codigo)

    # ───────────────────────── receita ─────────────────────────
    def medicao(self) -> pd.DataFrame:
        """Por alocação e competência: dias de contrato, dias trabalhados, faltas e horas extras."""
        ap = self.t4["ponto.apontamento"]
        quadro = pd.DataFrame(
            {
                "aloc": ap["alocacao_id"].to_numpy(),
                "competencia": ap["data"].to_numpy().astype("datetime64[M]"),
                "trabalhados": (ap["status"] == "NORMAL").to_numpy().astype(int),
                "faltas": (ap["status"] == "FALTA").to_numpy().astype(int),
                "extras": ap["horas_extras"].to_numpy(),
            }
        )
        return quadro.groupby(["aloc", "competencia"], sort=True).sum().reset_index()

    def preco(self, posto_id: int, dia: date) -> tuple[float, float]:
        vigentes = [v for v in self.precos[posto_id] if v[0] <= dia]
        _, mensal, hora = vigentes[-1] if vigentes else self.precos[posto_id][0]
        return mensal, hora

    def faturas(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Uma fatura por contrato e competência; nos contratos com posto, um item por posto."""
        itens: dict[tuple[date, int, int], dict[str, float]] = {}
        for linha in self.medicao().to_dict("records"):
            competencia = pd.Timestamp(linha["competencia"]).date()
            if competencia > self.ultima:
                continue
            a = self.alocacoes[int(linha["aloc"])]
            posto_id = int(a["posto_id"])
            fim_do_mes = _fim_do_mes(competencia)
            coberto = (
                min(a["dt_fim"] or fim_do_mes, fim_do_mes) - max(a["dt_inicio"], competencia)
            ).days + 1
            mensal, hora = self.preco(posto_id, fim_do_mes)
            chave = (competencia, int(self.postos[posto_id]["contrato_id"]), posto_id)
            item = itens.setdefault(
                chave,
                {"trabalhados": 0, "faltas": 0, "postos": 0.0, "extras": 0.0, "descontos": 0.0},
            )
            item["trabalhados"] += int(linha["trabalhados"])
            item["faltas"] += int(linha["faltas"])
            item["postos"] += mensal * min(1.0, coberto / fim_do_mes.day)
            item["extras"] += float(linha["extras"]) * hora * fin.FATOR_DA_HORA_EXTRA
            item["descontos"] += int(linha["faltas"]) * mensal / 30
        honorarios = self.honorarios_de_recrutamento()

        por_fatura: dict[tuple[date, int], list[tuple[int, dict[str, float]]]] = {}
        for (competencia, contrato_id, posto_id), item in itens.items():
            por_fatura.setdefault((competencia, contrato_id), []).append((posto_id, item))
        for do_honorario in honorarios:
            por_fatura.setdefault(do_honorario, [])
        faturas: list[dict[str, Any]] = []
        linhas_de_item: list[dict[str, Any]] = []
        sequencia: dict[int, int] = {}
        for competencia, contrato_id in sorted(por_fatura, key=lambda c: (c[0], c[1])):
            contrato = self.contratos[contrato_id]
            emissao = _dia_util(_mes_seguinte(competencia))
            bruto = honorarios.get((competencia, contrato_id), 0.0)
            fatura_id = len(faturas) + 1
            for posto_id, item in sorted(por_fatura[(competencia, contrato_id)]):
                total = round(item["postos"] + item["extras"] - item["descontos"], 2)
                linhas_de_item.append(
                    {
                        "fatura_id": fatura_id,
                        "posto_id": posto_id,
                        "qtd_dias_trabalhados": item["trabalhados"],
                        "qtd_faltas": item["faltas"],
                        "valor_postos": round(item["postos"], 2),
                        "valor_horas_extras": round(item["extras"], 2),
                        "valor_descontos": round(item["descontos"], 2),
                        "valor_total": total,
                        "criado_em": _momento(emissao),
                        "atualizado_em": _momento(emissao),
                    }
                )
                bruto += total
            bruto = round(bruto, 2)
            filial = self.filiais[int(contrato["filial_id"])]
            retido = fin.ISS_DA_FILIAL[str(filial["codigo"])] + fin.PIS + fin.COFINS
            impostos = round(bruto * retido, 2)
            sequencia[emissao.year] = sequencia.get(emissao.year, 0) + 1
            faturas.append(
                {
                    "numero": f"NF-{emissao.year}-{sequencia[emissao.year]:06d}",
                    "cliente_id": int(contrato["cliente_id"]),
                    "contrato_id": contrato_id,
                    "competencia": competencia,
                    "dt_emissao": emissao,
                    "valor_bruto": bruto,
                    "valor_impostos": impostos,
                    "valor_liquido": round(bruto - impostos, 2),
                    "status": "EMITIDA",
                    "criado_em": _momento(emissao),
                    "atualizado_em": _momento(emissao),
                }
            )
        return faturas, linhas_de_item

    def honorarios_de_recrutamento(self) -> dict[tuple[date, int], float]:
        """R&S: de 1,0 a 1,5 salário por pessoa colocada, faturado no mês em que a vaga fecha."""
        r = etapa2_carteira._registros
        requisicao = {int(q["id"]): int(q["contrato_id"]) for q in r(self.t3["ats.requisicao"])}
        honorarios: dict[tuple[date, int], float] = {}
        passo = max(1, round(1 / self.fracao))
        for v in r(self.t3["ats.vaga"]):
            contrato_id = requisicao[int(v["requisicao_id"])]
            if (
                v["status"] != "PREENCHIDA"
                or self.contratos[contrato_id]["tipo_servico"] != "RECRUTAMENTO"
            ):
                continue
            taxa = float(self.rng.uniform(*fin.HONORARIO_DE_RS))
            if int(v["id"]) % passo:
                continue  # na amostra, a mesma fração das colocações
            competencia = _mes(v["dt_fechamento"])
            if competencia <= self.ultima:
                chave = (competencia, contrato_id)
                honorarios[chave] = honorarios.get(chave, 0.0) + taxa * float(
                    v["salario_previsto"]
                ) * int(v["quantidade_posicoes"])
        return honorarios

    def titulos_a_receber(self, faturas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Um título por fatura. Paga em dia, com atraso, ou não paga; e o FIN-01: valor recebido
        diferente do emitido, sem nenhum registro de desconto."""
        saida = {i: c for i, c in self.clientes.items() if not c["ativo"]}
        ultimo_mes_do_cliente: dict[int, date] = {}
        for f in faturas:
            anterior = ultimo_mes_do_cliente.get(f["cliente_id"], f["competencia"])
            ultimo_mes_do_cliente[f["cliente_id"]] = max(anterior, f["competencia"])
        titulos = []
        for fatura_id, f in enumerate(faturas, start=1):
            contrato = self.contratos[f["contrato_id"]]
            vencimento = f["dt_emissao"] + timedelta(days=int(contrato["prazo_pagamento_dias"]))
            sorte = self.rng.random(4)
            ano = f["competencia"].year
            nunca = fin.CALOTE_BASE if ano <= 2023 else fin.CALOTE_NA_CRISE
            de_saida = f["cliente_id"] in saida and f["competencia"] >= _mes(
                ultimo_mes_do_cliente[f["cliente_id"]] - timedelta(days=45)
            )
            if de_saida and ano >= 2025:
                nunca = fin.CALOTE_DE_QUEM_SAI
            if sorte[0] < nunca:
                pagamento = None
            elif sorte[1] < 0.80:
                pagamento = vencimento + timedelta(days=int(self.rng.integers(-2, 3)))
            elif sorte[1] < 0.97:
                pagamento = vencimento + timedelta(days=int(self.rng.integers(3, 31)))
            else:
                pagamento = vencimento + timedelta(days=int(self.rng.integers(31, 91)))
            pago = pagamento is not None and pagamento <= HOJE
            valor_pago = None
            if pago:
                valor_pago = f["valor_liquido"]
                if sorte[2] < fin.RECEBIDO_DIFERENTE:  # FIN-01
                    desvio = float(self.rng.uniform(0.01, 0.08)) * (1 if sorte[3] < 0.2 else -1)
                    valor_pago = round(valor_pago * (1 + desvio), 2)
            status = "PAGO" if pago else ("ATRASADO" if vencimento < HOJE else "ABERTO")
            f["status"] = "QUITADA" if pago else ("EM_ABERTO" if vencimento < HOJE else "EMITIDA")
            if pago and pagamento:
                f["atualizado_em"] = max(_momento(pagamento, 14), f["criado_em"])
            titulos.append(
                {
                    "fatura_id": fatura_id,
                    "cliente_id": f["cliente_id"],
                    "numero_parcela": 1,
                    "dt_vencimento": vencimento,
                    "valor": f["valor_liquido"],
                    "status": status,
                    "dt_pagamento": pagamento if pago else None,
                    "valor_pago": valor_pago,
                    "criado_em": f["criado_em"],
                    "atualizado_em": f["atualizado_em"],
                }
            )
        return titulos

    # ───────────────────────── o que sai ─────────────────────────
    def a_pagar(
        self, faturas: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        titulos = self.titulos_lancados
        apurados: list[dict[str, Any]] = []

        def titulo(
            tipo: str,
            fornecedor: str | None,
            centro: int,
            competencia: date,
            vencimento: date,
            valor: float,
        ) -> int:
            vencimento = _dia_util(vencimento)
            pago = vencimento <= HOJE
            registro = _momento(min(_dia_util(_mes_seguinte(competencia, 2)), vencimento), 10)
            titulos.append(
                {
                    "tipo": tipo,
                    "fornecedor_id": self.id_fornecedor[fornecedor] if fornecedor else None,
                    "centro_custo_id": centro,
                    "competencia": competencia,
                    "dt_vencimento": vencimento,
                    "valor": round(valor, 2),
                    "status": "PAGO" if pago else "ABERTO",
                    "dt_pagamento": vencimento if pago else None,
                    "criado_em": registro,
                    "atualizado_em": max(registro, _momento(vencimento, 16)) if pago else registro,
                }
            )
            return len(titulos)

        # a folha da operação, por filial: líquido, encargos e guias retidas, benefícios
        item = self.t4["folha.folha_item"]
        folha = self.t4["folha.folha_competencia"].set_index("id")
        codigo = np.array(["", *[e[0] for e in cf.EVENTOS]], dtype=object)[
            item["evento_id"].to_numpy()
        ]
        tipo = np.array(["", *[e[2] for e in cf.EVENTOS]], dtype=object)[
            item["evento_id"].to_numpy()
        ]
        quadro = pd.DataFrame(
            {
                "competencia": item["folha_competencia_id"].map(folha["competencia"]).to_numpy(),
                "filial": item["folha_competencia_id"].map(folha["filial_id"]).to_numpy(),
                "valor": item["valor"].to_numpy(),
                "codigo": codigo,
                "tipo": tipo,
            }
        )
        quadro["grupo"] = np.select(
            [
                quadro["tipo"] == "PROVENTO",
                quadro["codigo"].isin(["INSS", "IRRF"]),
                quadro["codigo"].isin(["VT_DESC", "VR_DESC"]),
                quadro["tipo"] == "DESCONTO",
                quadro["codigo"].isin(["VT_EMP", "VR_EMP"]),
                quadro["tipo"] == "ENCARGO",
            ],
            [
                "provento",
                "retido",
                "beneficio_descontado",
                "outro_desconto",
                "beneficio",
                "encargo",
            ],
            default="provisao",
        )
        somas = (
            quadro.groupby(["competencia", "filial", "grupo"])["valor"].sum().unstack().fillna(0.0)
        )
        admissoes = pd.Series(
            [_mes(d) for d in self.t3["pessoas.contrato_trabalho"]["dt_admissao"]]
        ).value_counts()
        linhas_da_folha = zip(somas.index.tolist(), somas.to_dict("records"), strict=True)
        for (competencia_ts, filial_id), s in linhas_da_folha:
            competencia = pd.Timestamp(competencia_ts).date()
            centro = self.centro_da_filial[int(filial_id)]
            liquido = (
                s.get("provento", 0)
                - s.get("retido", 0)
                - s.get("beneficio_descontado", 0)
                - s.get("outro_desconto", 0)
            )
            titulo("FOLHA", None, centro, competencia, _mes_seguinte(competencia, 5), liquido)
            titulo(
                "ENCARGOS",
                None,
                centro,
                competencia,
                _mes_seguinte(competencia, 20),
                s.get("encargo", 0) + s.get("retido", 0),
            )
            beneficios = s.get("beneficio", 0) + s.get("beneficio_descontado", 0)
            titulo(
                "BENEFICIOS",
                fin.OPERADORA_DE_BENEFICIOS,
                centro,
                competencia,
                competencia.replace(day=25),
                beneficios,
            )
        # exames admissionais: um por admissão do mês, rateado pelas filiais com folha no mês
        for competencia in sorted({pd.Timestamp(c).date() for c, _ in somas.index}):
            quantos = int(admissoes.get(competencia, 0)) * self.fracao  # na amostra, a parte dela
            if quantos:
                valor = quantos * fin.EXAME_ADMISSIONAL * self.reajuste[competencia.year]
                titulo(
                    "FORNECEDOR",
                    fin.CLINICA_DE_EXAMES,
                    self.centro_da_retaguarda,
                    competencia,
                    _mes_seguinte(competencia, 10),
                    valor,
                )

        # lucro presumido: ISS por município, PIS e COFINS no mês; IRPJ e CSLL no trimestre
        receita = pd.DataFrame(faturas)
        receita["filial"] = receita["contrato_id"].map(
            lambda k: int(self.contratos[k]["filial_id"])
        )
        por_mes = receita.groupby(["competencia", "filial"])["valor_bruto"].sum()
        mensal = receita.groupby("competencia")["valor_bruto"].sum()
        for competencia in sorted(mensal.index):
            for filial_id in sorted(self.filiais):
                base = float(por_mes.get((competencia, filial_id), 0.0))
                if base:
                    aliquota = fin.ISS_DA_FILIAL[str(self.filiais[filial_id]["codigo"])]
                    apurados.append(
                        self.apurado(
                            competencia,
                            "ISS",
                            self.municipio_da_filial[filial_id],
                            base,
                            aliquota,
                            titulo(
                                "IMPOSTOS",
                                None,
                                self.centro_da_retaguarda,
                                competencia,
                                _mes_seguinte(competencia, 10),
                                base * aliquota,
                            ),
                        )
                    )
            for tributo, aliquota in (("PIS", fin.PIS), ("COFINS", fin.COFINS)):
                base = float(mensal[competencia])
                apurados.append(
                    self.apurado(
                        competencia,
                        tributo,
                        None,
                        base,
                        aliquota,
                        titulo(
                            "IMPOSTOS",
                            None,
                            self.centro_da_retaguarda,
                            competencia,
                            _mes_seguinte(competencia, 25),
                            base * aliquota,
                        ),
                    )
                )
            if competencia.month % 3 == 0:
                trimestre = [
                    c
                    for c in mensal.index
                    if c.year == competencia.year
                    and (c.month - 1) // 3 == (competencia.month - 1) // 3
                ]
                presumido = float(mensal[trimestre].sum()) * fin.BASE_PRESUMIDA
                irpj = (
                    presumido * fin.IRPJ
                    + max(0.0, presumido - fin.LIMITE_DO_ADICIONAL) * fin.ADICIONAL_DO_IRPJ
                )
                vencimento = _fim_do_mes(_mes_seguinte(competencia))
                apurados.append(
                    self.apurado(
                        competencia,
                        "IRPJ",
                        None,
                        presumido,
                        round(irpj / presumido, 4),
                        titulo(
                            "IMPOSTOS",
                            None,
                            self.centro_da_retaguarda,
                            competencia,
                            vencimento,
                            irpj,
                        ),
                        irpj,
                    )
                )
                apurados.append(
                    self.apurado(
                        competencia,
                        "CSLL",
                        None,
                        presumido,
                        fin.CSLL,
                        titulo(
                            "IMPOSTOS",
                            None,
                            self.centro_da_retaguarda,
                            competencia,
                            vencimento,
                            presumido * fin.CSLL,
                        ),
                    )
                )
        self.retaguarda(titulo, receita)
        return titulos, apurados

    def apurado(
        self,
        competencia: date,
        tributo: str,
        municipio: int | None,
        base: float,
        aliquota: float,
        titulo_id: int,
        devido: float | None = None,
    ) -> dict[str, Any]:
        registro = _momento(_dia_util(_mes_seguinte(competencia, 3)), 11)
        return {
            "competencia": competencia,
            "tributo_id": self.id_tributo[tributo],
            "municipio_id": municipio,
            "base_calculo": round(base, 2),
            "aliquota": aliquota,
            "valor_devido": round(base * aliquota if devido is None else devido, 2),
            "titulo_pagar_id": titulo_id,
            "criado_em": registro,
            "atualizado_em": registro,
        }

    def retaguarda(self, titulo: Any, receita: pd.DataFrame) -> None:
        """A despesa da retaguarda fecha o resultado do ano na margem líquida do caso. É o único
        número conduzido desta etapa; se sair negativo ou pequeno demais, a etapa reprova."""
        ja_lancado = pd.DataFrame(self.titulos_lancados)
        for ano in bandas.ANOS:
            do_ano = receita[receita["competencia"].map(lambda c, a=ano: c.year == a)]
            if do_ano.empty:
                continue
            bruta = float(do_ano["valor_bruto"].sum())
            liquida = bruta - float(do_ano["valor_impostos"].sum())
            outras = float(
                ja_lancado[ja_lancado["competencia"].map(lambda c, a=ano: c.year == a)][
                    "valor"
                ].sum()
            )
            total = bruta - outras - bandas.MARGEM_LIQUIDA[ano] * liquida
            self.despesa_da_retaguarda[ano] = total / bruta
            meses = sorted(do_ano["competencia"].unique())
            pesos = np.array(
                [
                    fin.PESO_DA_RETAGUARDA_EM_2026.get(m.month, 1.0) if ano == 2026 else 1.0
                    for m in meses
                ]
            )
            pesos = pesos * (1 + self.rng.uniform(-0.03, 0.03, len(meses)))
            for competencia, peso in zip(meses, pesos / pesos.sum(), strict=True):
                do_mes = total * float(peso)
                titulo(
                    "FOLHA",
                    None,
                    self.centro_da_retaguarda,
                    competencia,
                    _mes_seguinte(competencia, 5),
                    do_mes * fin.PARTE_DA_EQUIPE_INTERNA,
                )
                resto = do_mes * (1 - fin.PARTE_DA_EQUIPE_INTERNA)
                for fornecedor, parte in fin.DESPESAS_FIXAS:
                    titulo(
                        "FORNECEDOR",
                        fornecedor,
                        self.centro_da_retaguarda,
                        competencia,
                        _mes_seguinte(competencia, 10),
                        resto * parte,
                    )

    # ───────────────────────── o consolidado da gerente-geral ─────────────────────────
    def consolidado(self, faturas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        r = etapa2_carteira._registros
        filial_do_contrato_de_trabalho = {
            int(k["id"]): int(k["filial_id"]) for k in r(self.t3["pessoas.contrato_trabalho"])
        }
        dia0 = date(INICIO.year, 1, 1)
        n = (HOJE - dia0).days + 1
        dias = np.array([dia0 + timedelta(days=i) for i in range(n)])
        competencia_do_dia = np.array([_mes(d) for d in dias])
        headcount: dict[int, np.ndarray[Any, Any]] = {f: np.zeros(n + 1) for f in self.filiais}
        passo = max(1, round(1 / self.fracao))
        for a in self.alocacoes.values():
            if a["dt_fim"] is not None and a["dt_fim"] <= a["dt_inicio"]:
                continue
            if int(a["id"]) % passo:
                continue  # na amostra, só as alocações que foram medidas
            serie = headcount[filial_do_contrato_de_trabalho[int(a["contrato_trabalho_id"])]]
            serie[(a["dt_inicio"] - dia0).days] += 1
            serie[((a["dt_fim"] or HOJE) - dia0).days + 1] -= 1
        vagas = pd.DataFrame(
            {
                "filial": self.t3["ats.vaga"]["filial_id"],
                "mes": [_mes(d) for d in self.t3["ats.vaga"]["dt_abertura"]],
            }
        )
        vagas_abertas = vagas.groupby(["mes", "filial"]).size()
        receita = pd.DataFrame(faturas)
        receita["filial"] = receita["contrato_id"].map(
            lambda k: int(self.contratos[k]["filial_id"])
        )
        faturamento = receita.groupby(["competencia", "filial"])["valor_bruto"].sum()
        rateio = self.t4["folha.rateio_custo"]
        custo = (
            rateio.assign(
                filial=rateio["contrato_id"].map(
                    lambda k: int(self.contratos[int(k)]["filial_id"])
                ),
                mes=rateio["competencia"].dt.date,
            )
            .groupby(["mes", "filial"])["custo_total"]
            .sum()
        )

        linhas = []
        for competencia in sorted(set(competencia_do_dia)):
            if competencia > self.ultima:
                continue
            for filial_id, f in self.filiais.items():
                if f["dt_abertura"] > _fim_do_mes(competencia):
                    continue
                do_mes = competencia_do_dia == competencia
                pessoas = round(float(np.cumsum(headcount[filial_id])[:n][do_mes].mean()))
                faturado = float(faturamento.get((competencia, filial_id), 0.0))
                if not pessoas and not faturado:
                    continue  # filial recém-aberta, ainda sem operação: a planilha não tem a linha
                self.real[(competencia, filial_id)] = (pessoas, faturado)
                desvio = fin.DIVERGENCIA_DO_CONSOLIDADO.get(competencia.year, 0.0)
                erros = (
                    desvio
                    * self.rng.uniform(0.6, 1.4, 3)
                    * np.where(self.rng.random(3) < 0.7, -1, 1)
                )
                lancamento = min(
                    _dia_util(_mes_seguinte(competencia, int(self.rng.integers(8, 16)))),
                    HOJE - timedelta(days=1),
                )
                informado = max(0, round(pessoas * (1 + erros[0])))
                if desvio and pessoas and informado == pessoas:
                    informado += (
                        -1 if erros[0] < 0 and pessoas > 1 else 1
                    )  # a partir de 2022 nunca bate
                linhas.append(
                    {
                        "competencia": competencia,
                        "filial_id": filial_id,
                        "headcount_informado": informado,
                        "vagas_abertas_informado": int(
                            vagas_abertas.get((competencia, filial_id), 0)
                        ),
                        "faturamento_informado": round(faturado * (1 + erros[1]), 2),
                        "custo_informado": round(
                            float(custo.get((competencia, filial_id), 0.0)) * (1 + erros[2]), 2
                        ),
                        "dt_lancamento": lancamento,
                        "origem": "PLANILHA",
                        "criado_em": _momento(lancamento, 15),
                        "atualizado_em": _momento(lancamento, 15),
                    }
                )
        return linhas


def _cnpj(base: str) -> str:
    for pesos in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
        resto = sum(int(d) * p for d, p in zip(base, pesos, strict=True)) % 11
        base += str(0 if resto < 2 else 11 - resto)
    return base


def gerar_com_base(
    publicos: Path = etapa1_cadastro.PUBLICOS, fracao: float = 1.0
) -> tuple[Tabelas, dict[str, Any]]:
    f = _Financeiro(publicos, fracao)
    tabelas = f.catalogos()
    faturas, itens = f.faturas()
    titulos_a_receber = f.titulos_a_receber(faturas)
    a_pagar, apurados = f.a_pagar(faturas)
    tabelas |= {
        "financeiro.fatura": tabela(faturas),
        "financeiro.fatura_item": tabela(itens),
        "financeiro.titulo_receber": tabela(titulos_a_receber),
        "financeiro.titulo_pagar": tabela(a_pagar),
        "financeiro.imposto_apurado": tabela(apurados),
        "financeiro.consolidado_gerencial": tabela(f.consolidado(faturas)),
    }
    base = {
        **f.base,
        "etapa4": f.t4,
        "real_do_consolidado": f.real,
        "despesa_da_retaguarda": f.despesa_da_retaguarda,
    }
    return {nome: tabelas[nome] for nome in ORDEM}, base


def gerar(publicos: Path = etapa1_cadastro.PUBLICOS) -> Tabelas:
    tabelas, base = gerar_com_base(publicos)
    conferir(tabelas, base)
    return tabelas


def medir(t: Tabelas, base: dict[str, Any]) -> Medidas:
    r = etapa2_carteira._registros
    faturas, a_pagar = r(t["financeiro.fatura"]), r(t["financeiro.titulo_pagar"])
    margem: dict[str, float] = {}
    for ano in bandas.ANOS:
        do_ano = [f for f in faturas if f["competencia"].year == ano and f["status"] != "CANCELADA"]
        if not do_ano:
            continue
        bruta = sum(f["valor_bruto"] for f in do_ano)
        liquida = bruta - sum(f["valor_impostos"] for f in do_ano)
        despesas = sum(
            p["valor"]
            for p in a_pagar
            if p["competencia"].year == ano and p["status"] != "CANCELADO"
        )
        margem[str(ano)] = (bruta - despesas) / liquida
    contratos = set(base["carteira"]["comercial.contrato"]["id"])
    sem_contrato = sum(1 for f in faturas if f["contrato_id"] not in contratos)
    pagos = [x for x in r(t["financeiro.titulo_receber"]) if x["status"] == "PAGO"]
    diferentes = sum(1 for x in pagos if abs(x["valor_pago"] - x["valor"]) > 0.005)

    real: dict[tuple[date, int], tuple[int, float]] = base["real_do_consolidado"]
    somas: dict[int, list[float]] = {}
    iguais = 0
    for c in r(t["financeiro.consolidado_gerencial"]):
        pessoas, faturado = real[(c["competencia"], int(c["filial_id"]))]
        s = somas.setdefault(c["competencia"].year, [0.0, 0.0, 0.0, 0.0])
        s[0] += abs(c["headcount_informado"] - pessoas)
        s[1] += pessoas
        s[2] += abs(c["faturamento_informado"] - faturado)
        s[3] += faturado
        bate = (
            c["headcount_informado"] == pessoas
            and abs(c["faturamento_informado"] - faturado) < 0.005
        )
        iguais += bate and c["competencia"].year >= 2022
    sujeira = {
        "FIN-01": diferentes / max(1, len(pagos)),
        "GER-01/competencias_sem_divergencia": float(iguais),
    }
    for ano, (erro_h, h, erro_f, f) in somas.items():
        if ano >= 2022 and h and f:
            sujeira[f"GER-01/{ano}"] = (erro_h / h + erro_f / f) / 2
    return {
        "margem_liquida": margem,
        "violacoes": {"C-03": float(sem_contrato)},
        "sujeira": sujeira,
        "linhas_tabela": {"financeiro.fatura_item": float(len(t["financeiro.fatura_item"]))},
    }


def laudo_parcial(medidas: Medidas) -> Laudo:
    entregues = {(m, chave) for m, valores in medidas.items() for chave in valores}
    return avaliar([c for c in bandas.checks() if (c.medida, c.chave) in entregues], medidas)


def conferir(t: Tabelas, base: dict[str, Any], fracao: float = 1.0) -> None:
    problemas: list[str] = []
    fatura = t["financeiro.fatura"]
    for filha, coluna, mae in (
        ("financeiro.fatura_item", "fatura_id", "financeiro.fatura"),
        ("financeiro.titulo_receber", "fatura_id", "financeiro.fatura"),
        ("financeiro.imposto_apurado", "titulo_pagar_id", "financeiro.titulo_pagar"),
        ("financeiro.imposto_apurado", "tributo_id", "financeiro.tributo"),
        ("financeiro.titulo_pagar", "fornecedor_id", "financeiro.fornecedor"),
    ):
        usados = set(t[filha][coluna].dropna().astype(int))
        if not usados <= set(t[mae]["id"]):
            problemas.append(f"{filha}.{coluna} órfã")
    if (
        fatura.duplicated(["numero"]).any()
        or fatura.duplicated(["contrato_id", "competencia"]).any()
    ):
        problemas.append("fatura repetida")
    itens = t["financeiro.fatura_item"].groupby("fatura_id")["valor_total"].sum().astype(float)
    bruto = fatura.set_index("id").loc[itens.index, "valor_bruto"].astype(float)
    if ((bruto - itens).abs() > 0.05).any():
        problemas.append("fatura de posto não fecha com os itens")
    for nome, quadro in t.items():
        if (
            not (quadro["atualizado_em"] >= quadro["criado_em"]).all()
            or not (quadro["atualizado_em"] <= FIM).all()
        ):
            problemas.append(f"{nome}: carimbo fora de ordem ou depois do fim da história")
    # na amostra vale só o sinal; a faixa plausível e as proporções finas são da base inteira
    minimo, maximo = fin.RETAGUARDA_PLAUSIVEL if fracao == 1 else (0.0, 0.5)
    for ano, parte in base["despesa_da_retaguarda"].items():
        if not minimo <= parte <= maximo:
            problemas.append(f"retaguarda de {ano} em {parte:.1%} da receita: fora do plausível")
    medidas = dict(medir(t, base))
    if fracao < 1:  # na amostra o volume não vale, e o headcount por filial é pequeno demais
        medidas.pop("linhas_tabela")
        medidas["sujeira"] = {
            k: v for k, v in medidas["sujeira"].items() if k.endswith("sem_divergencia")
        }
    for r_ in laudo_parcial(medidas).com_situacao(Situacao.REPROVADO):
        problemas.append(f"régua {r_.check.codigo}: {r_.valor} fora de {r_.check.banda}")
    if problemas:
        raise ValueError("etapa 5 reprovada:\n- " + "\n- ".join(problemas))


def escrever_planilhas(t: Tabelas, base: dict[str, Any], pasta: Path = PLANILHAS) -> list[Path]:
    """O consolidado como a gerente-geral o guarda: uma pasta de trabalho por ano, com título,
    cabeçalho na terceira linha, uma linha por competência e filial, e o total no fim."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    nome_da_filial = {
        int(f["id"]): str(f["nome"]).removeprefix("Fictalent ")
        for f in etapa2_carteira._registros(base["mundo"]["cadastro.filial"])
    }
    consolidado = etapa2_carteira._registros(t["financeiro.consolidado_gerencial"])
    pasta.mkdir(parents=True, exist_ok=True)
    escritas = []
    for ano in sorted({c["competencia"].year for c in consolidado}):
        livro = Workbook()
        livro.properties.creator = "Gerência geral (dado sintético)"
        livro.properties.created = livro.properties.modified = datetime(ano, 12, 31, 18, 0)
        folha = livro.worksheets[0]
        folha.title = "Consolidado"
        folha["A1"] = f"Fictalent RH · Consolidado gerencial {ano}"
        folha["A1"].font = Font(bold=True, size=13)
        cabecalho = [
            "Competência",
            "Filial",
            "Headcount",
            "Vagas abertas",
            "Faturamento (R$)",
            "Custo (R$)",
            "Lançado em",
        ]
        folha.append([])
        folha.append(cabecalho)
        for celula in folha[3]:
            celula.font = Font(bold=True)
        do_ano = [c for c in consolidado if c["competencia"].year == ano]
        for c in do_ano:
            folha.append(
                [
                    c["competencia"],
                    nome_da_filial[int(c["filial_id"])],
                    c["headcount_informado"],
                    c["vagas_abertas_informado"],
                    c["faturamento_informado"],
                    c["custo_informado"],
                    c["dt_lancamento"],
                ]
            )
        folha.append(
            [
                "TOTAL",
                None,
                None,
                sum(c["vagas_abertas_informado"] for c in do_ano),
                round(sum(c["faturamento_informado"] for c in do_ano), 2),
                round(sum(c["custo_informado"] for c in do_ano), 2),
                None,
            ]
        )
        for coluna, largura in zip("ABCDEFG", (14, 22, 12, 14, 18, 16, 14), strict=True):
            folha.column_dimensions[coluna].width = largura
        caminho = pasta / f"consolidado_gerencial_{ano}.xlsx"
        livro.save(caminho)
        escritas.append(caminho)
    return escritas
