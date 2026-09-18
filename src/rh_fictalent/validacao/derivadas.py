"""Medidas derivadas: o que transforma uma série mensal num número que a régua confere.

A régua só sabe comparar um número com uma banda. Os checks de naturalidade e de sazonalidade
partem de séries (headcount por mês, admissões por mês, entradas de clientes por mês), e é
aqui que a série vira número: o maior desvio contra a média móvel, o desvio contra o índice
do CAGED, a concentração de eventos num mês. Séries mensais são dicionários "AAAA-MM" -> valor.
"""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

from rh_fictalent.validacao.bandas import CAGED_ESCOPO, CAGED_GRUPO, INICIO_DA_CRISE, PANDEMIA

SerieMensal = Mapping[str, float]
INDICE_CAGED = Path("dados/publicos/caged/indice_sazonal.csv")


def meses_de_choque(serie: SerieMensal) -> set[str]:
    """Meses em que variar muito é a história, não um defeito: janeiro (saída em massa dos
    temporários), fevereiro (o vale, medido contra uma média que ainda tem dezembro) e a
    pandemia (março a junho de 2020)."""
    return {mes for mes in serie if mes[5:] in ("01", "02")} | set(PANDEMIA)


def desvio_maximo_da_media_movel(serie: SerieMensal, choques: Iterable[str] | None = None) -> float:
    """O maior |mês ÷ média dos três meses anteriores - 1|, fora dos meses de choque."""
    fora = set(choques) if choques is not None else meses_de_choque(serie)
    meses = sorted(serie)
    maior = 0.0
    for i in range(3, len(meses)):
        if meses[i] in fora:
            continue
        media = statistics.fmean(serie[m] for m in meses[i - 3 : i])
        if media > 0:
            maior = max(maior, abs(serie[meses[i]] / media - 1))
    return maior


def indice_sazonal(serie: SerieMensal) -> dict[int, float]:
    """Por mês do ano: mês ÷ média do ano, na média dos anos completos (a conta do CAGED)."""
    por_ano: dict[str, dict[int, float]] = defaultdict(dict)
    for mes, valor in serie.items():
        por_ano[mes[:4]][int(mes[5:])] = float(valor)
    razoes: dict[int, list[float]] = defaultdict(list)
    for meses in por_ano.values():
        if len(meses) != 12:
            continue
        media = statistics.fmean(meses.values())
        if media > 0:
            for numero, valor_do_mes in meses.items():
                razoes[numero].append(valor_do_mes / media)
    return {numero: statistics.fmean(v) for numero, v in sorted(razoes.items())}


def comparar_indices(
    base: Mapping[int, float], referencia: Mapping[int, float]
) -> dict[str, float]:
    """O índice da base contra o de referência: maior desvio, desvio médio e correlação."""
    meses = sorted(set(base) & set(referencia))
    if len(meses) != 12:
        raise ValueError(f"índices precisam dos 12 meses; em comum: {meses}")
    desvios = [abs(base[m] - referencia[m]) for m in meses]
    try:
        correlacao = statistics.correlation(
            [base[m] for m in meses], [referencia[m] for m in meses]
        )
    except statistics.StatisticsError:  # série sem variação não acompanha ritmo nenhum
        correlacao = 0.0
    return {
        "desvio_maximo": max(desvios),
        "desvio_medio": statistics.fmean(desvios),
        "correlacao": correlacao,
    }


def referencia_caged(
    coluna: str = "indice_admissoes",
    caminho: Path = INDICE_CAGED,
    escopo: str = CAGED_ESCOPO,
    grupo: str = CAGED_GRUPO,
) -> dict[int, float]:
    """O índice sazonal do Novo CAGED para o escopo e o grupo de referência da régua."""
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        indice = {
            int(linha["mes"]): float(linha[coluna])
            for linha in csv.DictReader(arquivo)
            if linha["escopo"] == escopo and linha["grupo"] == grupo
        }
    if len(indice) != 12:
        raise ValueError(f"{caminho}: índice de {escopo}/{grupo} com {len(indice)} meses")
    return indice


def sazonalidade_contra_caged(
    serie: SerieMensal, coluna: str = "indice_admissoes"
) -> dict[str, float]:
    """A medida da família 4: a série mensal da base comparada ao índice do CAGED."""
    return comparar_indices(indice_sazonal(serie), referencia_caged(coluna))


def maximo_no_mes(eventos: SerieMensal, fora: Iterable[str] = ()) -> float:
    """O maior número de eventos (entradas ou saídas de clientes) num mês, fora dos excluídos."""
    excluidos = set(fora)
    return max((v for mes, v in eventos.items() if mes not in excluidos), default=0.0)


def meses_de_crise(eventos: SerieMensal) -> set[str]:
    """A pandemia e a crise de 2025 em diante: onde sair mais de dois clientes é a história."""
    return set(PANDEMIA) | {mes for mes in eventos if mes >= INICIO_DA_CRISE}


def concentracao_maxima(eventos: SerieMensal, minimo_no_ano: int = 8) -> float:
    """A maior parcela dos eventos de um ano num único mês (anos com poucos eventos não contam)."""
    por_ano: dict[str, list[float]] = defaultdict(list)
    for mes, valor in eventos.items():
        por_ano[mes[:4]].append(float(valor))
    parcelas = [max(v) / sum(v) for v in por_ano.values() if sum(v) >= minimo_no_ano]
    return max(parcelas, default=0.0)


def naturalidade(
    headcount: SerieMensal, entradas: SerieMensal, saidas: SerieMensal
) -> dict[str, float]:
    """A medida da família 2 inteira, a partir das três séries mensais."""
    return {
        "headcount_desvio_maximo": desvio_maximo_da_media_movel(headcount),
        "saidas_max_mes_fora_crise": maximo_no_mes(saidas, meses_de_crise(saidas)),
        "entradas_max_mes": maximo_no_mes(entradas),
        "entradas_concentracao_max": concentracao_maxima(entradas),
    }
