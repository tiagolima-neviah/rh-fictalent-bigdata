"""As curvas da história: o que conduz o gerador mês a mês, de 2018-01 a 2026-09.

O plano de sintetização dá os pontos de chegada por ano (as bandas da régua). Aqui eles viram
curvas mensais que as etapas consultam: o headcount alvo com o ritmo do ano, as posições
contratadas que sustentam esse headcount, a degradação da qualidade que explica 2025, quantos
clientes entram por ano e em que meses. Nenhuma etapa escreve esses números direto na base:
eles orientam decisões mensais (abrir posto, fechar posto, entrar cliente), e o que a base
mostra é a soma dessas decisões.
"""

from __future__ import annotations

from datetime import date

from rh_fictalent.gerador.nucleo import FIM, INICIO
from rh_fictalent.validacao.bandas import (
    CLIENTES_ATIVOS,
    DEGRADACAO,
    HEADCOUNT_MEDIO,
    HEADCOUNT_PICO,
)

# forma do ano (média 1): vale em fevereiro, subida de agosto a dezembro
FORMA_DO_ANO = (0.80, 0.72, 0.76, 0.80, 0.84, 0.88, 0.92, 0.98, 1.10, 1.25, 1.42, 1.55)
# anos que não seguem a forma: a fundação (rampa), a pandemia (o vale de abril a junho)
# e 2026 (a crise: queda em linha reta até setembro)
CURVAS_PROPRIAS = {
    2018: (30, 40, 50, 60, 70, 80, 90, 100, 115, 130, 145, 150),
    2020: (165, 160, 140, 110, 105, 110, 125, 140, 155, 170, 180, 190),
    2026: (900, 888, 875, 862, 850, 838, 825, 812, 800),
}
PANDEMIA = ("2020-03", "2020-04", "2020-05", "2020-06")

FUNDADORES = 3  # os clientes âncora, que abrem a empresa em janeiro de 2018
ESFORCO_COMERCIAL = 0.5  # quanto da distância até a meta de clientes o comercial fecha por mês

# contrato novo nasce mais em janeiro (orçamento do cliente) e em julho e agosto (a temporada)
PESO_DO_MES_PARA_ENTRADA = (1.5, 0.8, 0.9, 0.9, 0.9, 0.9, 1.5, 1.5, 1.0, 0.8, 0.7, 0.6)

# parcela das posições em terceirização (estável no ano); o resto é temporário, que leva a
# sazonalidade inteira. A empresa nasce mais R&S e temporário e ganha terceirização com o tempo.
PARCELA_TERCEIRIZACAO = {
    2018: 0.20,
    2019: 0.25,
    2020: 0.32,
    2021: 0.32,
    2022: 0.35,
    2023: 0.37,
    2024: 0.38,
    2025: 0.40,
    2026: 0.42,
}

# degradação da qualidade, de 0 (operação saudável) a 1 (o pior momento): pontos de passagem
_DEGRADACAO = (
    ("2022-12", 0.00),
    ("2023-07", 0.25),
    ("2024-07", 0.60),
    ("2025-07", 1.00),
    ("2026-02", 1.00),
    ("2026-09", 0.97),
)


def meses() -> list[str]:
    """Todos os meses da história, "AAAA-MM", de 2018-01 a 2026-09."""
    lista, ano, mes = [], INICIO.year, INICIO.month
    while (ano, mes) <= (FIM.year, FIM.month):
        lista.append(f"{ano}-{mes:02d}")
        ano, mes = (ano, mes + 1) if mes < 12 else (ano + 1, 1)
    return lista


def _indice(mes: str) -> int:
    return int(mes[:4]) * 12 + int(mes[5:]) - 1


def headcount_alvo() -> dict[str, float]:
    """O headcount alvo de cada mês: a média do ano com a forma do ano, esticada até o pico."""
    alvo: dict[str, float] = {}
    for mes in meses():
        ano, numero = int(mes[:4]), int(mes[5:])
        if ano in CURVAS_PROPRIAS:
            alvo[mes] = float(CURVAS_PROPRIAS[ano][numero - 1])
            continue
        pico_sobre_media = HEADCOUNT_PICO[ano] / HEADCOUNT_MEDIO[ano]
        amplitude = (pico_sobre_media - 1) / (FORMA_DO_ANO[11] - 1)
        alvo[mes] = HEADCOUNT_MEDIO[ano] * (1 + amplitude * (FORMA_DO_ANO[numero - 1] - 1))
    return alvo


def clientes_alvo() -> dict[str, float]:
    """Clientes ativos que o comercial persegue em cada mês: linha reta entre os fins de ano."""
    alvo: dict[str, float] = {}
    for mes in meses():
        ano, numero = int(mes[:4]), int(mes[5:])
        anterior = float(CLIENTES_ATIVOS.get(ano - 1, FUNDADORES))
        meses_do_ano = FIM.month if ano == FIM.year else 12
        alvo[mes] = anterior + (CLIENTES_ATIVOS[ano] - anterior) * numero / meses_do_ano
    return alvo


def fill_rate(ano: int) -> float:
    indicador = next(i for i in DEGRADACAO if i.medida == "fill_rate")
    baixo, alto = indicador.referencia()[ano]
    return (baixo + alto) / 2


def posicoes_alvo() -> dict[str, float]:
    """Posições contratadas que sustentam o headcount: headcount ÷ fill rate do ano."""
    return {mes: h / fill_rate(int(mes[:4])) for mes, h in headcount_alvo().items()}


def degradacao(mes: str) -> float:
    """Quanto a operação já cedeu no mês, de 0 a 1 (interpolação linear entre os pontos)."""
    x = _indice(mes)
    pontos = [(_indice(m), v) for m, v in _DEGRADACAO]
    if x <= pontos[0][0]:
        return pontos[0][1]
    for (x0, v0), (x1, v1) in zip(pontos, pontos[1:], strict=False):
        if x <= x1:
            return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
    return pontos[-1][1]


def referencia_do_ano(medida: str, ano: int) -> float:
    """O centro da banda de um indicador de qualidade no ano (ex.: reclamacoes_100_postos)."""
    indicador = next(i for i in DEGRADACAO if i.medida == medida)
    baixo, alto = indicador.referencia()[ano]
    return (baixo + alto) / 2


def limites_do_mes(mes: str) -> tuple[date, date]:
    """Primeiro e último dia do mês, sem passar do fim da história."""
    ano, numero = int(mes[:4]), int(mes[5:])
    primeiro = date(ano, numero, 1)
    seguinte = date(ano + 1, 1, 1) if numero == 12 else date(ano, numero + 1, 1)
    ultimo = date.fromordinal(seguinte.toordinal() - 1)
    return max(primeiro, INICIO), min(ultimo, FIM.date())
