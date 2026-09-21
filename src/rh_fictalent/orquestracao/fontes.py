"""Assets das fontes públicas: a primeira ingestão do pipeline, por API REST, gravada no lake.

Cada fonte é um asset do grupo `fontes`, com chave fontes/provedor/conjunto. O asset chama o
cliente HTTP de rh_fictalent.fontes.apis (timeout, retry, limite de taxa) e grava o resultado
em parquet no lake, sob s3://bucket/fontes/... Os feriados são particionados por ano, então o
backfill pela interface do Dagster (2018 a 2026) e a rematerialização de um ano só são a
mesma operação com chaves diferentes.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string
import dagster as dg

from rh_fictalent.fontes.apis import feriados, municipios
from rh_fictalent.orquestracao.convencoes import GRUPO_FONTES, PARTICAO_ANUAL, chave_fonte
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import ApisPublicas, Lake


@dg.asset(
    key=chave_fonte("ibge", "municipios"),
    group_name=GRUPO_FONTES,
    description="Municípios de SP e MG (IBGE), código de 7 dígitos e regiões, em parquet no lake.",
)
def municipios_ibge(context: dg.AssetExecutionContext, apis: ApisPublicas, lake: Lake) -> None:
    tabela = municipios(apis.cliente())
    caminho = lake.caminho("fontes", "ibge", "municipios.parquet")
    lake.escrever_parquet(tabela, caminho)
    por_uf = {str(uf): int(n) for uf, n in tabela["uf"].value_counts().items()}
    context.log.info("%s municípios gravados em %s", len(tabela), caminho)
    context.add_output_metadata(
        {"linhas": len(tabela), "por_uf": dg.MetadataValue.json(por_uf), "caminho": caminho}
    )


@dg.asset(
    key=chave_fonte("brasilapi", "feriados"),
    group_name=GRUPO_FONTES,
    partitions_def=PARTICAO_ANUAL,
    description="Feriados nacionais do ano (BrasilAPI), uma partição por ano, em parquet no lake.",
)
def feriados_brasilapi(context: dg.AssetExecutionContext, apis: ApisPublicas, lake: Lake) -> None:
    ano = int(context.partition_key)
    tabela = feriados(apis.cliente(), (ano,))
    caminho = lake.caminho("fontes", "brasilapi", "feriados", f"ano={ano}.parquet")
    lake.escrever_parquet(tabela, caminho)
    context.log.info("%s feriados de %s gravados em %s", len(tabela), ano, caminho)
    context.add_output_metadata({"linhas": len(tabela), "ano": ano, "caminho": caminho})


carregar_municipios = dg.define_asset_job(
    name="carregar_municipios",
    selection=dg.AssetSelection.assets(municipios_ibge),
    description="Traz os municípios de SP e MG do IBGE para o lake.",
    config=CONFIG_LOGS_JSON,
)

carregar_feriados = dg.define_asset_job(
    name="carregar_feriados",
    selection=dg.AssetSelection.assets(feriados_brasilapi),  # particionado por ano, como o asset
    description="Traz os feriados nacionais de um ano da BrasilAPI para o lake.",
    config=CONFIG_LOGS_JSON,
)
