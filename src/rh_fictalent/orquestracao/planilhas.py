"""O asset da planilha do consolidado: a ingestão de arquivo entra no grafo como as outras.

Uma partição por ano, que é como a gerente guarda os arquivos. O asset não depende da réplica:
é a mesma informação por outro caminho, e é justamente por serem dois caminhos que dá para
perguntar, na silver, qual dos dois está certo quando discordarem. O caso inteiro gira em torno
dessa pergunta.

Falhar aqui é o comportamento correto: esquema reprovado, asset reprovado. A planilha de gente
muda de forma sozinha (alguém insere uma coluna, renomeia um cabeçalho, deixa um total a mais),
e o pipeline tem de parar no arquivo, não três camadas adiante, com um número errado num painel.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string
from pathlib import Path

import dagster as dg

from rh_fictalent.ingestao.planilhas import (
    MODULO,
    PASTA,
    TABELA,
    caminho_do_ano,
    ingerir,
    total_declarado,
)
from rh_fictalent.orquestracao.convencoes import PARTICAO_ANUAL, chave
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake

GRUPO = "bronze"


class Planilhas(dg.Config):
    pasta: str = str(PASTA)


@dg.asset(
    key=chave("bronze", MODULO, TABELA),
    group_name=GRUPO,
    partitions_def=PARTICAO_ANUAL,
    description="A planilha do consolidado do ano, validada por esquema e gravada em parquet.",
    compute_kind="excel",
)
def consolidado_em_planilha(
    context: dg.AssetExecutionContext, config: Planilhas, lake: Lake
) -> None:
    ano = int(context.partition_key)
    caminho = caminho_do_ano(Path(config.pasta), ano)
    linhas, destino = ingerir(lake, caminho)
    conferido = total_declarado(caminho)
    context.log.info("%s: %s linhas validadas e gravadas em %s", caminho.name, linhas, destino)
    context.add_output_metadata(
        {
            "linhas": linhas,
            "arquivo": caminho.name,
            "caminho": destino,
            "ano": ano,
            # o total que a planilha declara, para quem quiser comparar com a soma das linhas
            "total_declarado_faturamento": conferido["faturamento"],
            "total_declarado_custo": conferido["custo"],
        }
    )


carregar_consolidado = dg.define_asset_job(
    name="carregar_consolidado",
    selection=dg.AssetSelection.assets(consolidado_em_planilha),
    description="Lê as planilhas do consolidado gerencial de um ano para a bronze, com esquema.",
    config=CONFIG_LOGS_JSON,
)
