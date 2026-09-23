"""Os assets da bronze: uma tabela da réplica, um asset; um ano, uma partição.

São 75 assets, um por tabela de negócio, todos gerados pela mesma fábrica a partir da lista de
tabelas da DDL. Escrever 75 funções iguais à mão seria pior de três jeitos: erra, envelhece
quando a DDL muda, e esconde que a regra é uma só. A fábrica também garante que **tabela nova
na DDL vira asset sozinha**, sem ninguém lembrar.

A linhagem fica `replica/modulo/tabela` (o que existe no sistema do cliente, que o pipeline
observa mas não produz) para `bronze/modulo/tabela` (o parquet no lake). Assim o grafo do
Dagster mostra de onde veio cada arquivo, e a silver vai pendurar nele.

Rematerializar uma partição reescreve o parquet daquele ano inteiro. É de propósito: o arquivo
é o dado, e reescrever é a operação idempotente mais simples que existe.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string
import dagster as dg

from rh_fictalent.ingestao.backfill import copiar_ano
from rh_fictalent.ingestao.exclusoes import TRILHA
from rh_fictalent.orquestracao.convencoes import MODULO_META, PARTICAO_ANUAL, chave
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake, Replica
from rh_fictalent.staging.gatilhos import tabelas_por_modulo

GRUPO = "bronze"
# da DDL, na ordem dos arquivos: tabela nova entra sozinha. A trilha de exclusões entra
# junto porque a bronze precisa dela para saber o que foi apagado (card 5.3).
TABELAS = tabelas_por_modulo() | {MODULO_META: [TRILHA[1]]}


def _origem(modulo: str, tabela: str) -> dg.AssetSpec:
    """A tabela na réplica: o pipeline não a produz, só a lê. É a raiz da linhagem."""
    return dg.AssetSpec(
        key=chave("replica", modulo, tabela),
        group_name="replica",
        description=f"Tabela {modulo}.{tabela} na réplica do sistema do cliente.",
    )


def _asset_bronze(modulo: str, tabela: str) -> dg.AssetsDefinition:
    @dg.asset(
        name=tabela,
        key_prefix=["bronze", modulo],
        group_name=GRUPO,
        partitions_def=PARTICAO_ANUAL,
        deps=[chave("replica", modulo, tabela)],
        description=f"Espelho de {modulo}.{tabela} em parquet, particionado pelo ano de criação.",
        compute_kind="mysql",
    )
    def bronze(context: dg.AssetExecutionContext, replica: Replica, lake: Lake) -> None:
        ano = int(context.partition_key)
        con = replica.conectar()
        try:
            copia = copiar_ano(con, lake, modulo, tabela, ano)
        finally:
            con.close()
        if not copia.confere:
            raise dg.Failure(
                f"{modulo}.{tabela} de {ano}: {copia.linhas} linhas gravadas, "
                f"{copia.esperadas} na réplica"
            )
        context.log.info(
            "%s.%s de %s: %s linhas em %s", modulo, tabela, ano, copia.linhas, copia.caminho
        )
        context.add_output_metadata(
            {
                "linhas": copia.linhas,
                "conferidas_na_replica": copia.esperadas,
                "bytes": copia.bytes_escritos,
                "caminho": copia.caminho,
                "ano": ano,
            }
        )

    return bronze


ORIGENS = [_origem(m, t) for m, tabelas in TABELAS.items() for t in tabelas]
ASSETS = [_asset_bronze(m, t) for m, tabelas in TABELAS.items() for t in tabelas]

backfill_bronze = dg.define_asset_job(
    name="backfill_bronze",
    selection=dg.AssetSelection.groups(GRUPO),
    description="Traz a réplica inteira para a bronze, uma partição por ano.",
    config=CONFIG_LOGS_JSON,
)
