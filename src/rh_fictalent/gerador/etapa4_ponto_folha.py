"""Etapa 4 do gerador: o ponto e a folha (5 tabelas de `ponto`, 7 de `folha`), a etapa de volume.

Parte das alocações da etapa 3. Para cada dia programado pela escala do posto sai um
apontamento (normal, falta, atestado ou feriado) e, nos dias trabalhados, as quatro batidas do
relógio, com a sujeira de origem do catálogo: batida faltante (PON-01) e batida duplicada no
mesmo minuto (PON-02). O mês de cada contrato vira itens de folha (proventos, descontos,
encargos e provisões), a provisão acumula e é baixada na rescisão e no 13º, e o rateio leva o
custo de cada pessoa até o posto onde ela trabalhou: é o que torna a margem por cliente possível.

Aqui tudo é numpy: são milhões de linhas, e as tabelas grandes saem com colunas tipadas (não
`object`). `fracao` gera só uma amostra das alocações, para teste; a base de verdade é 1.0.
A folha é uma aproximação plausível, não um cálculo trabalhista (ver catalogos_folha).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador import catalogos_folha as cf
from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, etapa3_pessoas, historia
from rh_fictalent.gerador.nucleo import FIM, INICIO, Tabelas, aleatorio
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.regua import Laudo, Medidas, Situacao, avaliar

HOJE = FIM.date()
Vetor = np.ndarray[Any, Any]
NORMAL, FALTA, ATESTADO, FERIADO = 0, 1, 2, 3
STATUS = np.array(["NORMAL", "FALTA", "ATESTADO", "FERIADO"], dtype=object)
HORAS = np.array(
    [f"{h:02d}:{m:02d}:{s:02d}" for h in range(24) for m in range(60) for s in range(60)],
    dtype=object,
)
COMPETENCIA_ZERO = INICIO.year * 12  # índice do mês: ano * 12 + mês - 1


def _competencia(indice: int) -> date:
    return date(indice // 12, indice % 12 + 1, 1)


def _fechamento(indice: int) -> date:
    """A folha fecha no dia 5 do mês seguinte (ou no primeiro dia útil depois dele)."""
    dia = _competencia(indice + 1).replace(day=cf.DIA_DO_FECHAMENTO)
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


def _quadro(colunas: dict[str, Any], criado: Any, atualizado: Any | None = None) -> pd.DataFrame:
    quadro = pd.DataFrame(colunas)
    quadro.insert(0, "id", np.arange(1, len(quadro) + 1))
    quadro["criado_em"] = criado
    quadro["atualizado_em"] = criado if atualizado is None else atualizado
    return quadro


# ───────────────────────────── o ponto ─────────────────────────────
def _programacao(base: dict[str, Any], fracao: float) -> dict[str, Vetor]:
    """Um vetor por dia programado de cada alocação: quem, quando, em que posto, com que jornada."""
    r = etapa2_carteira._registros
    t3: Tabelas = base["etapa3"]
    postos = {int(p["id"]): p for p in r(base["carteira"]["comercial.posto"])}
    escala = {int(e["id"]): str(e["codigo"]) for e in r(base["mundo"]["cadastro.escala"])}
    feriados = np.array(
        sorted(
            {
                f["data"]
                for f in r(base["mundo"]["cadastro.feriado"])
                if f["abrangencia"] == "NACIONAL"
            }
        ),
        dtype="datetime64[D]",
    )
    afastamentos: dict[int, list[tuple[np.datetime64, np.datetime64]]] = {}
    for a in r(t3["pessoas.afastamento"]):
        periodo = (np.datetime64(a["dt_inicio"]), np.datetime64(a["dt_fim"] or HOJE))
        afastamentos.setdefault(int(a["colaborador_id"]), []).append(periodo)

    sorteio = aleatorio("etapa4_turnos")
    passo = max(1, round(1 / fracao))
    partes: dict[str, list[Vetor]] = {
        k: [] for k in ("aloc", "colab", "dia", "inicio", "jornada", "folga")
    }
    for a in r(t3["pessoas.alocacao"]):
        revezamento = int(sorteio.integers(3))  # sorteia sempre, para a amostra não mudar o resto
        if a["dt_fim"] is not None and a["dt_fim"] <= a["dt_inicio"]:
            continue  # no-show de primeiro dia: nunca trabalhou
        if int(a["id"]) % passo:
            continue
        posto = postos[int(a["posto_id"])]
        codigo = escala[int(posto["escala_id"])]
        ultimo = np.datetime64(a["dt_fim"] or HOJE) + np.timedelta64(1, "D")
        dias = np.arange(np.datetime64(a["dt_inicio"]), ultimo)
        semana = (dias.astype("int64") + 3) % 7  # segunda = 0
        ordem = np.arange(len(dias))
        if codigo == "5X2":
            programado = semana < 5
        elif codigo == "6X1":
            programado = semana < 6
        elif codigo == "5X1":
            programado = ordem % 6 < 5
        else:  # 12X36
            programado = ordem % 2 == 0
        dias = dias[programado]
        # feriado nacional é folga para quem tem semana fixa; revezamento e 12x36 trabalham
        folga = np.isin(dias, feriados) & (codigo in ("5X2", "6X1"))
        afastado = np.zeros(len(dias), dtype=bool)
        for de, ate in afastamentos.get(int(a["colaborador_id"]), []):
            afastado |= (dias >= de) & (dias <= ate)
        turno = str(posto["turno"])
        inicio = cf.INICIO_DO_TURNO.get(turno, (6 * 60, 14 * 60, 22 * 60)[revezamento])
        n = len(dias)
        partes["aloc"].append(np.full(n, int(a["id"]), dtype=np.int64))
        partes["colab"].append(np.full(n, int(a["colaborador_id"]), dtype=np.int64))
        partes["dia"].append(dias)
        partes["inicio"].append(np.full(n, inicio, dtype=np.int64))
        partes["jornada"].append(np.full(n, cf.JORNADA[codigo]))
        partes["folga"].append(np.where(folga, FERIADO, np.where(afastado, ATESTADO, NORMAL)))
    return {k: np.concatenate(v) for k, v in partes.items()}


def _ponto(base: dict[str, Any], fracao: float) -> tuple[Tabelas, dict[str, Vetor]]:
    rng = aleatorio("etapa4_ponto")
    p = _programacao(base, fracao)
    de_hoje = (p["dia"] == np.datetime64(HOJE)) & (p["folga"] == NORMAL)
    hoje = {k: v[de_hoje] for k, v in p.items()}
    # o apontamento é consolidado de madrugada: o dia de hoje ainda não tem
    consolidado = p["dia"] < np.datetime64(HOJE)
    p = {k: v[consolidado] for k, v in p.items()}
    ordem = np.lexsort((p["colab"], p["dia"]))
    p = {k: v[ordem] for k, v in p.items()}
    n = len(p["dia"])
    ano = p["dia"].astype("datetime64[Y]").astype(int) + 1970
    mes = p["dia"].astype("datetime64[M]").astype(int) % 12 + 1
    do_mes = {m: historia.degradacao(m) for m in historia.meses()}  # por mês, não por linha
    tabela = np.array(
        [
            do_mes[f"{c // 12}-{c % 12 + 1:02d}"]
            for c in range(COMPETENCIA_ZERO, FIM.year * 12 + FIM.month)
        ]
    )
    degradacao = tabela[ano * 12 + mes - 1 - COMPETENCIA_ZERO]

    status = p["folga"].copy()
    falta = (status == NORMAL) & (
        rng.random(n) < cf.FALTA_BASE + cf.FALTA_NA_DEGRADACAO * degradacao
    )
    status[falta] = FALTA
    normal = status == NORMAL
    justificada = falta & (rng.random(n) < cf.FALTA_JUSTIFICADA)
    atraso = np.where(normal & (rng.random(n) < cf.ATRASO), rng.integers(5, 61, n), 0)
    antecipada = np.where(
        normal & (rng.random(n) < cf.SAIDA_ANTECIPADA), rng.integers(10, 121, n), 0
    )
    extra = np.where(normal & (rng.random(n) < cf.HORA_EXTRA), rng.integers(2, 9, n) * 0.25, 0.0)
    jornada_min = np.round(p["jornada"] * 60).astype(np.int64)
    fim_do_turno = p["inicio"] + jornada_min + cf.INTERVALO_MIN
    noturnas = np.clip(
        np.minimum(fim_do_turno, cf.NOITE_ATE) - np.maximum(p["inicio"], cf.NOITE_DE), 0, None
    )
    noturnas = np.where(normal, np.minimum(noturnas / 60, p["jornada"]), 0.0)
    trabalhadas = np.where(normal, p["jornada"] - (atraso + antecipada) / 60, 0.0)

    meia_noite = p["dia"].astype("datetime64[s]")
    consolidacao = np.minimum(
        meia_noite + np.timedelta64(24 * 3600 + 1800, "s"), np.datetime64(FIM, "s")
    )
    apontamento = _quadro(
        {
            "colaborador_id": p["colab"],
            "alocacao_id": p["aloc"],
            "data": p["dia"],
            "horas_trabalhadas": np.round(trabalhadas, 2),
            "horas_extras": extra,
            "horas_noturnas": np.round(noturnas, 2),
            "status": STATUS[status],
        },
        consolidacao,
    )

    # ocorrências: falta (justificada ou não), atraso e saída antecipada
    ids = apontamento["id"].to_numpy()
    blocos = [
        (ids[justificada], "FALTA_JUSTIFICADA", np.zeros(int(justificada.sum()), dtype=np.int64)),
        (
            ids[falta & ~justificada],
            "FALTA_INJUSTIFICADA",
            np.zeros(int((falta & ~justificada).sum()), dtype=np.int64),
        ),
        (ids[atraso > 0], "ATRASO", atraso[atraso > 0]),
        (ids[antecipada > 0], "SAIDA_ANTECIPADA", antecipada[antecipada > 0]),
    ]
    de_quem = np.concatenate([b[0] for b in blocos])
    tipo = np.concatenate([np.full(len(b[0]), b[1], dtype=object) for b in blocos])
    na_ordem = np.argsort(de_quem, kind="stable")
    justificativa = np.full(len(tipo), None, dtype=object)
    com_motivo = np.flatnonzero(tipo == "FALTA_JUSTIFICADA")
    motivos = np.array(cf.JUSTIFICATIVAS, dtype=object)
    justificativa[com_motivo] = motivos[rng.integers(len(motivos), size=len(com_motivo))]
    ocorrencia = _quadro(
        {
            "apontamento_id": de_quem[na_ordem],
            "tipo": tipo[na_ordem],
            "minutos": np.concatenate([b[2] for b in blocos])[na_ordem],
            "justificativa": justificativa[na_ordem],
        },
        consolidacao[de_quem[na_ordem] - 1],
    )

    marcacao = _marcacoes(rng, p, hoje, normal, atraso, antecipada, extra, jornada_min)
    escalas = _escalas(base, fracao)
    mensal = {
        "aloc": p["aloc"],
        "colab": p["colab"],
        "competencia": ano * 12 + mes - 1,
        "programado": np.ones(n),
        "normal": normal.astype(float),
        "falta_injustificada": (falta & ~justificada).astype(float),
        "minutos_a_menos": (atraso + antecipada).astype(float),
        "extras": extra,
        "noturnas": noturnas,
    }
    tabelas = {
        "ponto.escala_colaborador": escalas,
        "ponto.marcacao": marcacao,
        "ponto.apontamento": apontamento,
        "ponto.ocorrencia_ponto": ocorrencia,
    }
    return tabelas, mensal


def _marcacoes(
    rng: np.random.Generator,
    p: dict[str, Vetor],
    hoje: dict[str, Vetor],
    normal: Vetor,
    atraso: Vetor,
    antecipada: Vetor,
    extra: Vetor,
    jornada_min: Vetor,
) -> pd.DataFrame:
    """As quatro batidas de cada dia trabalhado, com a batida que falta e a que se repete."""
    # as batidas de hoje entram até o instante em que a história para
    colab = np.concatenate([p["colab"][normal], hoje["colab"]])
    dia = np.concatenate([p["dia"][normal], hoje["dia"]])
    inicio = np.concatenate([p["inicio"][normal], hoje["inicio"]])
    k = len(hoje["dia"])
    jornada = np.concatenate([jornada_min[normal], np.round(hoje["jornada"] * 60).astype(np.int64)])
    atraso_ = np.concatenate([atraso[normal], np.zeros(k, dtype=np.int64)])
    antecipada_ = np.concatenate([antecipada[normal], np.zeros(k, dtype=np.int64)])
    extra_ = np.concatenate([extra[normal], np.zeros(k)])
    m = len(dia)

    entrada = inicio + np.clip(np.round(rng.normal(-3, 4, m)), -12, 4).astype(np.int64) + atraso_
    saida_intervalo = entrada + jornada // 2 + rng.integers(-5, 6, m)
    retorno = saida_intervalo + cf.INTERVALO_MIN + rng.integers(-4, 5, m)
    saida = (
        inicio + jornada + cf.INTERVALO_MIN + np.round(extra_ * 60).astype(np.int64) - antecipada_
    )
    saida = np.maximum(saida + rng.integers(-2, 5, m), retorno + 30)
    minutos = np.stack([entrada, saida_intervalo, retorno, saida], axis=1)
    segundos = rng.integers(0, 60, size=(m, 4))

    fica = np.ones((m, 4), dtype=bool)
    esquecida = np.flatnonzero(rng.random(m) < cf.MARCACAO_FALTANTE)  # PON-01
    indice_do_tipo = {t: i for i, t in enumerate(cf.TIPOS_DE_MARCACAO)}
    qual = rng.choice(
        [indice_do_tipo[t] for t, _ in cf.QUAL_FALTA],
        size=len(esquecida),
        p=[w for _, w in cf.QUAL_FALTA],
    )
    fica[esquecida, qual] = False
    repetida = np.flatnonzero(rng.random(m) < cf.MARCACAO_DUPLICADA)  # PON-02
    qual_repete = rng.integers(0, 4, len(repetida))
    ainda_existe = fica[repetida, qual_repete]
    repetida, qual_repete = repetida[ainda_existe], qual_repete[ainda_existe]

    linha, coluna = np.nonzero(fica)
    linha = np.concatenate([linha, repetida])
    coluna = np.concatenate([coluna, qual_repete])
    minuto = minutos[linha, coluna]
    segundo = segundos[linha, coluna]
    segundo[len(segundo) - len(repetida) :] = np.minimum(
        59, segundo[len(segundo) - len(repetida) :] + rng.integers(2, 30, len(repetida))
    )
    instante = dia[linha].astype("datetime64[s]") + (minuto * 60 + segundo).astype("timedelta64[s]")
    manual = rng.random(len(linha)) < cf.MARCACAO_MANUAL
    origem_da_pessoa = rng.random(int(colab.max()) + 1) < cf.ORIGEM_POR_ALOCACAO[0][1]
    origem = np.where(
        manual, "MANUAL", np.where(origem_da_pessoa[colab[linha]], "RELOGIO", "APP")
    ).astype(object)
    # a batida manual é lançada pelo RH um a três dias depois, de manhã
    lancamento = dia[linha].astype("datetime64[s]") + (
        rng.integers(1, 4, len(linha)) * 86400 + 36000
    ).astype("timedelta64[s]")
    criado = np.where(manual, lancamento, instante)
    dentro = criado <= np.datetime64(FIM, "s")
    ordem = np.argsort(criado[dentro], kind="stable")
    escolha = np.flatnonzero(dentro)[ordem]
    return _quadro(
        {
            "colaborador_id": colab[linha][escolha],
            "data": dia[linha][escolha],
            "hora": HORAS[(minuto[escolha] % 1440) * 60 + segundo[escolha]],
            "tipo": np.array(cf.TIPOS_DE_MARCACAO, dtype=object)[coluna[escolha]],
            "origem": origem[escolha],
        },
        criado[escolha],
    )


def _escalas(base: dict[str, Any], fracao: float) -> pd.DataFrame:
    r = etapa2_carteira._registros
    postos = {int(p["id"]): int(p["escala_id"]) for p in r(base["carteira"]["comercial.posto"])}
    passo = max(1, round(1 / fracao))
    alocacoes = [a for a in r(base["etapa3"]["pessoas.alocacao"]) if int(a["id"]) % passo == 0]
    criado = [
        base["etapa3"]["pessoas.alocacao"]["criado_em"].iloc[int(a["id"]) - 1] for a in alocacoes
    ]
    quadro = pd.DataFrame(
        {
            "colaborador_id": [int(a["colaborador_id"]) for a in alocacoes],
            "escala_id": [postos[int(a["posto_id"])] for a in alocacoes],
            "vigencia_inicio": pd.Series([a["dt_inicio"] for a in alocacoes], dtype=object),
            "vigencia_fim": pd.Series([a["dt_fim"] for a in alocacoes], dtype=object),
        }
    )
    quadro.insert(0, "id", np.arange(1, len(quadro) + 1))
    quadro["criado_em"] = pd.Series(criado, dtype=object)
    quadro["atualizado_em"] = pd.Series(
        [
            max(c, datetime.combine(a["dt_fim"], time(18, 0))) if a["dt_fim"] else c
            for a, c in zip(alocacoes, criado, strict=True)
        ],
        dtype=object,
    )
    quadro["atualizado_em"] = quadro["atualizado_em"].map(lambda d: min(d, FIM))
    return quadro


# ───────────────────────────── a folha ─────────────────────────────
def _folha(base: dict[str, Any], mensal: dict[str, Vetor], fracao: float) -> Tabelas:
    r = etapa2_carteira._registros
    t3: Tabelas = base["etapa3"]
    alocacao = {int(a["id"]): a for a in r(t3["pessoas.alocacao"])}
    contrato = {int(k["id"]): k for k in r(t3["pessoas.contrato_trabalho"])}
    postos = {int(p["id"]): p for p in r(base["carteira"]["comercial.posto"])}
    comercial = {int(k["id"]): k for k in r(base["carteira"]["comercial.contrato"])}
    funcoes = {i: f for i, f in enumerate(cat.FUNCOES, start=1)}
    evento_id = {codigo: i for i, (codigo, *_) in enumerate(cf.EVENTOS, start=1)}
    reajuste = {
        a: float(np.prod([1 + v for k, v in cat.REAJUSTES.items() if 2018 < k <= a]))
        for a in bandas.ANOS
    }

    # o mês de cada alocação, somado
    chave = mensal["aloc"] * 4096 + (mensal["competencia"] - COMPETENCIA_ZERO)
    unicas, inverso = np.unique(chave, return_inverse=True)
    soma = {
        k: np.bincount(inverso, weights=mensal[k], minlength=len(unicas))
        for k in (
            "programado",
            "normal",
            "falta_injustificada",
            "minutos_a_menos",
            "extras",
            "noturnas",
        )
    }
    grupos = sorted(
        ((int(u % 4096) + COMPETENCIA_ZERO, int(u // 4096), i) for i, u in enumerate(unicas)),
    )
    ultima_fechada = (
        FIM.year * 12 + FIM.month - 2
    )  # a competência do mês corrente ainda está aberta

    itens: list[
        tuple[Any, ...]
    ] = []  # (competência, filial, colaborador, contrato, evento, referência, valor)
    rateios: list[tuple[Any, ...]] = []
    saldo: dict[int, list[float]] = {}
    provisoes: dict[tuple[int, int, str], list[float]] = {}
    banco: dict[tuple[int, int], list[float]] = {}
    for competencia, aloc_id, i in grupos:
        if competencia > ultima_fechada:
            continue
        a = alocacao[aloc_id]
        k = contrato[int(a["contrato_trabalho_id"])]
        k_id, colab, filial = int(k["id"]), int(k["colaborador_id"]), int(k["filial_id"])
        ano = competencia // 12
        base_salarial = float(k["salario_base"])
        primeiro = _competencia(competencia)
        ultimo = _competencia(competencia + 1) - timedelta(days=1)
        dias_no_mes = (
            min(k["dt_rescisao"] or ultimo, ultimo) - max(k["dt_admissao"], primeiro)
        ).days + 1
        dias_pagos = min(30, dias_no_mes) if dias_no_mes < ultimo.day else 30
        funcao = funcoes[int(k["funcao_id"])]
        terceirizado = k["tipo"] == "TERCEIRIZADO"
        hora = base_salarial / 220

        valores: dict[str, tuple[float, float]] = {
            "SALARIO": (dias_pagos, base_salarial * dias_pagos / 30)
        }
        if funcao.insalubre:
            valores["INSALUB"] = (
                dias_pagos,
                cf.INSALUBRIDADE * cf.SALARIO_MINIMO[ano] * dias_pagos / 30,
            )
        if funcao.periculosidade:
            valores["PERICUL"] = (dias_pagos, cf.PERICULOSIDADE * base_salarial * dias_pagos / 30)
        extras, a_menos = float(soma["extras"][i]), float(soma["minutos_a_menos"][i])
        if terceirizado:  # hora extra e atraso vão para o banco de horas
            mov = banco.setdefault((colab, competencia), [0.0, 0.0])
            mov[0] += extras
            mov[1] += a_menos / 60
        else:
            if extras:
                valores["HE50"] = (extras, extras * hora * 1.5)
                valores["DSR_HE"] = (extras, extras * hora * 1.5 / 6)
            if a_menos:
                valores["ATRASOS"] = (a_menos, a_menos / 60 * hora)
        if soma["noturnas"][i]:
            valores["ADIC_NOT"] = (
                float(soma["noturnas"][i]),
                float(soma["noturnas"][i]) * hora * 0.2,
            )
        if soma["falta_injustificada"][i]:
            faltas = float(soma["falta_injustificada"][i])
            valores["FALTAS"] = (faltas, faltas * base_salarial / 30)
        valores = {c: (ref, round(v, 2)) for c, (ref, v) in valores.items()}
        ganho = sum(v for c, (_, v) in valores.items() if c in cf.PROVENTOS_DO_MES)
        perdido = sum(v for c, (_, v) in valores.items() if c in cf.REDUTORES)
        if perdido > ganho and "FALTAS" in valores:  # faltou o mês inteiro: desconta só o que havia
            ref, v = valores["FALTAS"]
            valores["FALTAS"] = (ref, round(max(0.0, v - (perdido - ganho)), 2))
        remuneracao = sum(v for c, (_, v) in valores.items() if c in cf.PROVENTOS_DO_MES)
        remuneracao -= sum(v for c, (_, v) in valores.items() if c in cf.REDUTORES)
        remuneracao = round(max(remuneracao, 0.0), 2)

        trabalhados = float(soma["normal"][i])
        vt = round(trabalhados * cf.BENEFICIOS[0][3] * reajuste[ano], 2)
        vr = round(trabalhados * cf.BENEFICIOS[1][3] * reajuste[ano], 2)
        vt_desconto = round(min(vt, cf.BENEFICIOS[0][4] * valores["SALARIO"][1]), 2)
        vr_desconto = round(vr * cf.BENEFICIOS[1][4], 2)
        em_sm = remuneracao / cf.SALARIO_MINIMO[ano]
        aliquota = next(al for teto, al in cf.INSS_EMPREGADO if em_sm <= teto)
        valores["INSS"] = (aliquota * 100, round(remuneracao * aliquota, 2))
        tributavel = remuneracao - valores["INSS"][1] - cf.IRRF_ISENTO_ATE * cf.SALARIO_MINIMO[ano]
        if tributavel > 0:
            valores["IRRF"] = (cf.IRRF_ALIQUOTA * 100, round(tributavel * cf.IRRF_ALIQUOTA, 2))
        if vt:
            valores["VT_DESC"], valores["VT_EMP"] = (
                (trabalhados, vt_desconto),
                (trabalhados, round(vt - vt_desconto, 2)),
            )
        if vr:
            valores["VR_DESC"], valores["VR_EMP"] = (
                (trabalhados, vr_desconto),
                (trabalhados, round(vr - vr_desconto, 2)),
            )
        for codigo, taxa in cf.ENCARGOS_SOBRE_A_FOLHA:
            valores[codigo] = (taxa * 100, round(remuneracao * taxa, 2))

        # provisão: só conta o avo com 15 dias trabalhados ou mais no mês
        acumulado = saldo.setdefault(k_id, [0.0, 0.0, 0.0])
        if trabalhados >= cf.DIAS_PARA_O_AVO:
            decimo = round(remuneracao / 12, 2)
            ferias = round(remuneracao / 12 * 4 / 3, 2)
            encargos = round((decimo + ferias) * cf.ENCARGOS_SOBRE_PROVISAO, 2)
            for j, (codigo, valor) in enumerate(
                (("PROV_13", decimo), ("PROV_FER", ferias), ("PROV_ENC", encargos))
            ):
                valores[codigo] = (1.0, valor)
                acumulado[j] = round(acumulado[j] + valor, 2)
        baixa = [0.0, 0.0, 0.0]
        rescindiu = k["dt_rescisao"] is not None and primeiro <= k["dt_rescisao"] <= ultimo
        if rescindiu and acumulado[0] + acumulado[1] > 0:
            valores["RESC_13"], valores["RESC_FER"] = (1.0, acumulado[0]), (1.0, acumulado[1])
            baixa = list(acumulado)
        elif primeiro.month == 12 and acumulado[0] > 0:
            valores["DEC_TERC"] = (1.0, acumulado[0])
            baixa = [
                acumulado[0],
                0.0,
                round(acumulado[0] * cf.ENCARGOS_SOBRE_PROVISAO / (1 + 4 / 3), 2),
            ]
            baixa[2] = min(baixa[2], acumulado[2])
        for j, (tipo, codigo) in enumerate(cf.PROVISOES):
            do_mes = valores.get(codigo, (0.0, 0.0))[1]
            if do_mes or baixa[j]:
                acumulado[j] = round(acumulado[j] - baixa[j], 2)
                linha = provisoes.setdefault((competencia, colab, tipo), [0.0, 0.0])
                linha[0] = round(linha[0] + do_mes - baixa[j], 2)
                linha[1] = acumulado[j]

        for codigo, (referencia, valor) in valores.items():
            if valor:
                itens.append(
                    (
                        competencia,
                        filial,
                        colab,
                        k_id,
                        evento_id[codigo],
                        round(referencia, 2),
                        valor,
                    )
                )
        posto = postos[int(a["posto_id"])]
        encargos_do_mes = round(sum(valores[c][1] for c, _ in cf.ENCARGOS_SOBRE_A_FOLHA), 2)
        provisao_do_mes = round(sum(valores.get(c, (0, 0.0))[1] for _, c in cf.PROVISOES), 2)
        beneficios = round(sum(valores.get(c, (0, 0.0))[1] for c in cf.BENEFICIOS_DA_EMPRESA), 2)
        rateios.append(
            (
                competencia,
                colab,
                aloc_id,
                int(comercial[int(posto["contrato_id"])]["centro_custo_id"]),
                int(posto["contrato_id"]),
                int(posto["id"]),
                remuneracao,
                encargos_do_mes,
                provisao_do_mes,
                beneficios,
                round(remuneracao + encargos_do_mes + provisao_do_mes + beneficios, 2),
            )
        )
    return _tabelas_da_folha(base, itens, rateios, provisoes, banco, fracao, ultima_fechada)


def _carimbo_do_fechamento(competencias: Vetor, dias_depois: int = 0) -> Vetor:
    unicas = {
        int(c): np.datetime64(
            datetime.combine(_fechamento(int(c)) + timedelta(days=dias_depois), time(18, 0)), "s"
        )
        for c in np.unique(competencias)
    }
    return np.array(
        [min(unicas[int(c)], np.datetime64(FIM, "s")) for c in competencias], dtype="datetime64[s]"
    )


def _primeiro_dia(competencias: Vetor) -> Vetor:
    return np.array(
        [np.datetime64(_competencia(int(c))) for c in competencias], dtype="datetime64[D]"
    )


def _tabelas_da_folha(
    base: dict[str, Any],
    itens: list[tuple[Any, ...]],
    rateios: list[tuple[Any, ...]],
    provisoes: dict[tuple[int, int, str], list[float]],
    banco: dict[tuple[int, int], list[float]],
    fracao: float,
    ultima_fechada: int,
) -> Tabelas:
    r = etapa2_carteira._registros
    entrada = np.datetime64(datetime.combine(INICIO, time(8, 0)), "s")
    eventos = _quadro(
        {
            "codigo": [e[0] for e in cf.EVENTOS],
            "descricao": [e[1] for e in cf.EVENTOS],
            "tipo": [e[2] for e in cf.EVENTOS],
            "fl_incide_inss": [e[3] for e in cf.EVENTOS],
            "fl_incide_fgts": [e[4] for e in cf.EVENTOS],
            "fl_incide_ir": [e[5] for e in cf.EVENTOS],
        },
        entrada,
    )
    beneficio = _quadro(
        {
            "codigo": [b[0] for b in cf.BENEFICIOS],
            "nome": [b[1] for b in cf.BENEFICIOS],
            "tipo": [b[2] for b in cf.BENEFICIOS],
            "valor_padrao": [b[3] for b in cf.BENEFICIOS],
            "desconto_pct": [b[4] for b in cf.BENEFICIOS],
        },
        entrada,
    )

    item = pd.DataFrame(
        itens,
        columns=[
            "competencia",
            "filial",
            "colaborador_id",
            "contrato_trabalho_id",
            "evento_id",
            "referencia",
            "valor",
        ],
    )
    tipo_do_evento = np.array(["", *[e[2] for e in cf.EVENTOS]], dtype=object)[
        item["evento_id"].to_numpy()
    ]
    # uma folha por competência e filial (a do mês corrente existe, aberta e ainda sem itens)
    filiais = sorted({int(f["id"]) for f in r(base["mundo"]["cadastro.filial"])})
    abertura = {int(f["id"]): f["dt_abertura"] for f in r(base["mundo"]["cadastro.filial"])}
    folhas = [
        (c, f)
        for c in range(COMPETENCIA_ZERO, ultima_fechada + 2)
        for f in filiais
        if abertura[f] <= _competencia(c + 1) - timedelta(days=1)
    ]
    id_da_folha = {cf_: i for i, cf_ in enumerate(folhas, start=1)}
    totais = {
        tipo: item[tipo_do_evento == tipo]
        .groupby(["competencia", "filial"])["valor"]
        .sum()
        .to_dict()
        for tipo in ("PROVENTO", "DESCONTO", "ENCARGO")
    }
    fechada = [c <= ultima_fechada for c, _ in folhas]
    competencias_das_folhas = np.array([c for c, _ in folhas])
    folha = _quadro(
        {
            "competencia": _primeiro_dia(competencias_das_folhas),
            "filial_id": [f for _, f in folhas],
            "dt_fechamento": pd.Series(
                [
                    _fechamento(c) if ok else None
                    for (c, _), ok in zip(folhas, fechada, strict=True)
                ],
                dtype=object,
            ),
            "status": ["FECHADA" if ok else "ABERTA" for ok in fechada],
            "total_proventos": [round(totais["PROVENTO"].get(cf_, 0.0), 2) for cf_ in folhas],
            "total_descontos": [round(totais["DESCONTO"].get(cf_, 0.0), 2) for cf_ in folhas],
            "total_encargos": [round(totais["ENCARGO"].get(cf_, 0.0), 2) for cf_ in folhas],
        },
        _primeiro_dia(competencias_das_folhas).astype("datetime64[s]")
        + np.timedelta64(8 * 3600, "s"),
        np.where(
            fechada,
            _carimbo_do_fechamento(competencias_das_folhas),
            _primeiro_dia(competencias_das_folhas).astype("datetime64[s]")
            + np.timedelta64(8 * 3600, "s"),
        ),
    )
    folha_item = _quadro(
        {
            "folha_competencia_id": [
                id_da_folha[(c, f)]
                for c, f in zip(item["competencia"], item["filial"], strict=True)
            ],
            "colaborador_id": item["colaborador_id"].to_numpy(),
            "contrato_trabalho_id": item["contrato_trabalho_id"].to_numpy(),
            "evento_id": item["evento_id"].to_numpy(),
            "referencia": item["referencia"].to_numpy(),
            "valor": item["valor"].to_numpy(),
        },
        _carimbo_do_fechamento(item["competencia"].to_numpy()),
    )

    chaves = sorted(provisoes)
    provisao = _quadro(
        {
            "competencia": _primeiro_dia(np.array([c for c, _, _ in chaves])),
            "colaborador_id": [k for _, k, _ in chaves],
            "tipo": [t for _, _, t in chaves],
            "valor_mes": [provisoes[c][0] for c in chaves],
            "saldo_acumulado": [provisoes[c][1] for c in chaves],
        },
        _carimbo_do_fechamento(np.array([c for c, _, _ in chaves])),
    )

    rateio = pd.DataFrame(
        rateios,
        columns=[
            "competencia",
            "colaborador_id",
            "alocacao_id",
            "centro_custo_id",
            "contrato_id",
            "posto_id",
            "valor_salario",
            "valor_encargos",
            "valor_provisoes",
            "valor_beneficios",
            "custo_total",
        ],
    )
    carimbo_do_rateio = _carimbo_do_fechamento(rateio["competencia"].to_numpy(), dias_depois=1)
    rateio["competencia"] = _primeiro_dia(rateio["competencia"].to_numpy())
    rateio_custo = _quadro({c: rateio[c].to_numpy() for c in rateio.columns}, carimbo_do_rateio)

    # banco de horas dos terceirizados: o saldo anda de um mês para o outro
    banco_horas = _banco_de_horas(banco)

    beneficios_do_colaborador = _beneficios_dos_colaboradores(base, fracao)
    return {
        "folha.evento_folha": eventos,
        "folha.beneficio": beneficio,
        "folha.folha_competencia": folha,
        "folha.folha_item": folha_item,
        "folha.provisao": provisao,
        "folha.colaborador_beneficio": beneficios_do_colaborador,
        "folha.rateio_custo": rateio_custo,
        "ponto.banco_horas": banco_horas,
    }


def _banco_de_horas(banco: dict[tuple[int, int], list[float]]) -> pd.DataFrame:
    chaves = sorted(
        banco, key=lambda c: (c[1], c[0])
    )  # (colaborador, competência) -> por mês e pessoa
    saldo: dict[int, float] = {}
    linhas = []
    for colab, competencia in chaves:
        creditos, debitos = banco[(colab, competencia)]
        anterior = saldo.get(colab, 0.0)
        saldo[colab] = round(anterior + creditos - debitos, 2)
        linhas.append(
            (colab, competencia, anterior, round(creditos, 2), round(debitos, 2), saldo[colab])
        )
    colunas = [
        "colaborador_id",
        "competencia",
        "saldo_anterior",
        "creditos",
        "debitos",
        "saldo_final",
    ]
    quadro = pd.DataFrame(linhas, columns=colunas)
    carimbo = _carimbo_do_fechamento(quadro["competencia"].to_numpy())
    quadro["competencia"] = _primeiro_dia(quadro["competencia"].to_numpy())
    return _quadro({c: quadro[c].to_numpy() for c in quadro.columns}, carimbo)


def _beneficios_dos_colaboradores(base: dict[str, Any], fracao: float) -> pd.DataFrame:
    r = etapa2_carteira._registros
    passo = max(1, round(1 / fracao))
    contratos = {int(k["id"]): k for k in r(base["etapa3"]["pessoas.contrato_trabalho"])}
    criado_em = base["etapa3"]["pessoas.contrato_trabalho"]["criado_em"].tolist()
    reajuste = {
        a: float(np.prod([1 + v for k, v in cat.REAJUSTES.items() if 2018 < k <= a]))
        for a in bandas.ANOS
    }
    linhas, carimbos = [], []
    for a in r(base["etapa3"]["pessoas.alocacao"]):
        if int(a["id"]) % passo or (a["dt_fim"] is not None and a["dt_fim"] <= a["dt_inicio"]):
            continue
        k = contratos[int(a["contrato_trabalho_id"])]
        for i, b in enumerate(cf.BENEFICIOS, start=1):
            linhas.append(
                (
                    int(k["colaborador_id"]),
                    i,
                    round(b[3] * reajuste[k["dt_admissao"].year], 2),
                    k["dt_admissao"],
                    k["dt_rescisao"],
                )
            )
            carimbos.append(criado_em[int(k["id"]) - 1])
    quadro = pd.DataFrame(
        linhas,
        columns=["colaborador_id", "beneficio_id", "valor", "vigencia_inicio", "vigencia_fim"],
    ).astype({"vigencia_inicio": object, "vigencia_fim": object})
    quadro.insert(0, "id", np.arange(1, len(quadro) + 1))
    quadro["criado_em"] = pd.Series(carimbos, dtype=object)
    quadro["atualizado_em"] = pd.Series(
        [
            min(max(c, datetime.combine(fim, time(18, 0))), FIM) if fim else c
            for c, fim in zip(carimbos, quadro["vigencia_fim"], strict=True)
        ],
        dtype=object,
    )
    return quadro


# ───────────────────────────── entrada, medidas e aceite ─────────────────────────────
ORDEM = (
    "ponto.escala_colaborador",
    "ponto.marcacao",
    "ponto.apontamento",
    "ponto.ocorrencia_ponto",
    "ponto.banco_horas",
    "folha.evento_folha",
    "folha.beneficio",
    "folha.folha_competencia",
    "folha.folha_item",
    "folha.provisao",
    "folha.colaborador_beneficio",
    "folha.rateio_custo",
)


def gerar_com_base(
    publicos: Path = etapa1_cadastro.PUBLICOS, fracao: float = 1.0
) -> tuple[Tabelas, dict[str, Any]]:
    etapa3, gabarito = etapa3_pessoas.gerar_com_gabarito(publicos)
    base = {"etapa3": etapa3, "carteira": gabarito["carteira"], "mundo": gabarito["mundo"]}
    ponto, mensal = _ponto(base, fracao)
    folha = _folha(base, mensal, fracao)
    juntas = {**ponto, **folha}
    return {nome: juntas[nome] for nome in ORDEM}, base


def gerar(publicos: Path = etapa1_cadastro.PUBLICOS) -> Tabelas:
    tabelas, base = gerar_com_base(publicos)
    conferir(tabelas, base)
    return tabelas


def medir(t: Tabelas, base: dict[str, Any]) -> Medidas:
    """Volumes, coerência do ponto e da folha, e a sujeira do relógio."""
    apontamento, marcacao = t["ponto.apontamento"], t["ponto.marcacao"]
    medidas: dict[str, dict[str, float]] = {
        "linhas_tabela": {
            nome: float(len(t[nome]))
            for nome in (
                "ponto.marcacao",
                "ponto.apontamento",
                "folha.folha_item",
                "ponto.ocorrencia_ponto",
                "folha.provisao",
            )
        }
    }
    # C-02: todo apontamento dentro da alocação dele
    alocacao = base["etapa3"]["pessoas.alocacao"]
    inicio = np.array(alocacao["dt_inicio"].tolist(), dtype="datetime64[D]")
    fim = np.array([d or HOJE for d in alocacao["dt_fim"]], dtype="datetime64[D]")
    de_quem = apontamento["alocacao_id"].to_numpy() - 1
    dia = apontamento["data"].to_numpy().astype("datetime64[D]")
    fora = (dia < inicio[de_quem]) | (dia > fim[de_quem])
    # C-04: por competência, o custo da folha é o que o rateio distribui
    item = t["folha.folha_item"]
    codigo = np.array(["", *[e[0] for e in cf.EVENTOS]], dtype=object)[item["evento_id"].to_numpy()]
    no_custo = {
        *cf.PROVENTOS_DO_MES,
        *(c for c, _ in cf.ENCARGOS_SOBRE_A_FOLHA),
        *cf.BENEFICIOS_DA_EMPRESA,
        *(c for _, c in cf.PROVISOES),
    }
    sinal = np.where(
        np.isin(codigo, list(no_custo)),
        1.0,
        np.where(np.isin(codigo, list(cf.REDUTORES)), -1.0, 0.0),
    )
    competencia_da_folha = t["folha.folha_competencia"].set_index("id")["competencia"]
    por_competencia = (
        pd.Series(item["valor"].to_numpy() * sinal)
        .groupby(item["folha_competencia_id"].map(competencia_da_folha).to_numpy())
        .sum()
    )
    rateado = t["folha.rateio_custo"].groupby("competencia")["custo_total"].sum()
    # o redutor pode zerar a remuneração de quem faltou o mês todo; o rateio nunca é negativo
    diferenca = (por_competencia - rateado.reindex(por_competencia.index, fill_value=0.0)).abs()
    medidas["violacoes"] = {"C-02": float(fora.sum()), "C-04": float((diferenca > 1.0).sum())}

    normais = apontamento[apontamento["status"] == "NORMAL"]
    chave_do_dia = normais["colaborador_id"].to_numpy() * 100_000 + (
        normais["data"].to_numpy().astype("datetime64[D]").astype(np.int64)
    )
    chave_da_batida = marcacao["colaborador_id"].to_numpy() * 100_000 + (
        marcacao["data"].to_numpy().astype("datetime64[D]").astype(np.int64)
    )
    dias_com_batida, batidas = np.unique(chave_da_batida, return_counts=True)
    por_dia = dict(zip(dias_com_batida.tolist(), batidas.tolist(), strict=True))
    contagem = np.array([por_dia.get(int(c), 0) for c in chave_do_dia])
    minuto = marcacao["hora"].str.slice(0, 5)
    repetidas = pd.DataFrame(
        {"dia": chave_da_batida, "tipo": marcacao["tipo"], "minuto": minuto}
    ).duplicated(keep=False)
    dias_repetidos = np.unique(chave_da_batida[repetidas.to_numpy()])
    medidas["sujeira"] = {
        "PON-01": float((contagem < 4).mean()),
        "PON-02": float(np.isin(chave_do_dia, dias_repetidos).mean()),
    }
    return medidas


def laudo_parcial(medidas: Medidas) -> Laudo:
    entregues = {(m, chave) for m, valores in medidas.items() for chave in valores}
    return avaliar([c for c in bandas.checks() if (c.medida, c.chave) in entregues], medidas)


def conferir(t: Tabelas, base: dict[str, Any], fracao: float = 1.0) -> None:
    """O aceite da etapa: chaves, unicidade, carimbos e a régua parcial (só na base inteira)."""
    problemas: list[str] = []
    t3: Tabelas = base["etapa3"]
    for filha, coluna, mae in (
        ("ponto.marcacao", "colaborador_id", "pessoas.colaborador"),
        ("ponto.apontamento", "alocacao_id", "pessoas.alocacao"),
        ("ponto.escala_colaborador", "colaborador_id", "pessoas.colaborador"),
        ("ponto.banco_horas", "colaborador_id", "pessoas.colaborador"),
        ("folha.folha_item", "contrato_trabalho_id", "pessoas.contrato_trabalho"),
        ("folha.provisao", "colaborador_id", "pessoas.colaborador"),
        ("folha.rateio_custo", "alocacao_id", "pessoas.alocacao"),
    ):
        if not np.isin(
            t[filha][coluna].to_numpy(), t3[mae]["id"].to_numpy().astype(np.int64)
        ).all():
            problemas.append(f"{filha}.{coluna} órfã")
    if not np.isin(
        t["ponto.ocorrencia_ponto"]["apontamento_id"], t["ponto.apontamento"]["id"]
    ).all():
        problemas.append("ocorrência sem apontamento")
    if not np.isin(
        t["folha.folha_item"]["folha_competencia_id"], t["folha.folha_competencia"]["id"]
    ).all():
        problemas.append("item sem folha")
    for nome, chave in (
        ("ponto.apontamento", ["colaborador_id", "data"]),
        ("ponto.banco_horas", ["colaborador_id", "competencia"]),
        ("folha.provisao", ["competencia", "colaborador_id", "tipo"]),
        ("folha.folha_competencia", ["competencia", "filial_id"]),
    ):
        if t[nome].duplicated(chave).any():
            problemas.append(f"{nome}: chave {chave} repetida")
    limite = pd.Timestamp(FIM)
    for nome, quadro in t.items():
        criado, atualizado = (
            pd.to_datetime(quadro["criado_em"]),
            pd.to_datetime(quadro["atualizado_em"]),
        )
        if not (atualizado >= criado).all() or not (atualizado <= limite).all():
            problemas.append(f"{nome}: carimbo fora de ordem ou depois do fim da história")
    medidas = dict(medir(t, base))
    if fracao < 1:
        medidas.pop("linhas_tabela")  # volume só se confere na base inteira
    for r_ in laudo_parcial(medidas).com_situacao(Situacao.REPROVADO):
        problemas.append(f"régua {r_.check.codigo}: {r_.valor} fora de {r_.check.banda}")
    if problemas:
        raise ValueError("etapa 4 reprovada:\n- " + "\n- ".join(problemas))
