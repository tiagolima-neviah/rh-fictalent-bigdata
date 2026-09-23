"""Convenções dos assets: camadas, chaves e partições. Todo asset do projeto obedece a isto.

- Cada camada é um grupo do Dagster (aparece separada na interface): replica, bronze, silver,
  gold, warehouse; plataforma é o grupo dos assets de verificação.
- A chave de um asset é camada/modulo/tabela (ex.: bronze/ats/candidato), o que deixa a
  linhagem legível: bronze/ats/candidato depende de replica/ats/candidato.
- Partição diária desde o primeiro dia da história (2018-01-02) para o incremental;
  partição anual para o histórico (backfill e gold por ano).
- As fontes públicas externas (IBGE, BrasilAPI) formam o grupo fontes, com chave
  fontes/provedor/conjunto (ex.: fontes/ibge/municipios); não são camada do pipeline,
  são o que entra nele por API.
"""

from __future__ import annotations

import dagster as dg

CAMADAS = ("replica", "bronze", "silver", "gold", "warehouse")
MODULOS = (
    "cadastro",
    "comercial",
    "ats",
    "pessoas",
    "ponto",
    "folha",
    "financeiro",
    "treinamento",
    "sst",
    "seguranca",
)
PRIMEIRO_DIA = "2018-01-02"
ANOS = tuple(str(ano) for ano in range(2018, 2027))

MODULO_META = "meta"  # a trilha de exclusões: infraestrutura da carga, não negócio
GRUPO_FONTES = "fontes"
PROVEDORES = ("ibge", "brasilapi")

PARTICAO_DIARIA = dg.DailyPartitionsDefinition(start_date=PRIMEIRO_DIA, timezone="UTC")
PARTICAO_ANUAL = dg.StaticPartitionsDefinition(list(ANOS))


def chave(camada: str, modulo: str, tabela: str) -> dg.AssetKey:
    if camada not in CAMADAS:
        raise ValueError(f"camada desconhecida: {camada!r}")
    if modulo not in (*MODULOS, MODULO_META):
        raise ValueError(f"módulo desconhecido: {modulo!r}")
    return dg.AssetKey([camada, modulo, tabela])


def chave_fonte(provedor: str, conjunto: str) -> dg.AssetKey:
    if provedor not in PROVEDORES:
        raise ValueError(f"provedor desconhecido: {provedor!r}")
    return dg.AssetKey([GRUPO_FONTES, provedor, conjunto])
