"""Os assets do warehouse: uma tabela da gold no Postgres, um asset.

`warehouse/dim/cliente` depende de `gold/dim_cliente`; `warehouse/fato/posto_mes` depende de
`gold/fato_posto_mes` e das dimensões que referencia já no warehouse, porque a chave
estrangeira do Postgres exige a dimensão carregada antes. A carga é por partição (o ano do
parquet substitui a partição) e termina conferida: contagem e totais iguais no parquet e no
Postgres, senão o asset falha e o que estava carregado antes continua como estava.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string
import dagster as dg

from rh_fictalent.gold import dcl, indices, modelo, rls, warehouse
from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.gold import chave_gold
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake, Warehouse
from rh_fictalent.orquestracao.silver import NOVA_TENTATIVA

GRUPO = "warehouse"


def chave_warehouse(tabela: modelo.Tabela) -> dg.AssetKey:
    destino = warehouse.alvo(tabela)
    return dg.AssetKey([GRUPO, destino.esquema, destino.nome])


def dependencias(tabela: modelo.Tabela) -> list[dg.AssetKey]:
    """A tabela na gold e, no fato, as dimensões que ele referencia já no warehouse."""
    dimensoes = sorted(set(tabela.referencias.values()))
    return [chave_gold(tabela.nome), *(chave_warehouse(modelo.tabela(d)) for d in dimensoes)]


def _construir(tabela: modelo.Tabela) -> dg.AssetsDefinition:
    destino = warehouse.alvo(tabela)

    @dg.asset(
        key=chave_warehouse(tabela),
        group_name=GRUPO,
        deps=dependencias(tabela),
        description=(
            f"{destino.qualificado} no Postgres, carregada do parquet da gold "
            f"({'por partição de ano' if tabela.fato else 'por upsert pelo id'}) e conferida: "
            "contagem e totais iguais nos dois lados."
        ),
        compute_kind="postgres",
        retry_policy=NOVA_TENTATIVA,
    )
    def carga(context: dg.AssetExecutionContext, lake: Lake, warehouse: Warehouse) -> None:
        from rh_fictalent.gold import warehouse as modulo  # o parâmetro `warehouse` é o recurso

        con = consulta.abrir_gold(lake)
        try:
            resultado = modulo.carregar(con, warehouse, tabela)
        finally:
            con.close()
        context.log.info("%s: %s linhas no Postgres", destino.qualificado, resultado.linhas)
        context.add_output_metadata(
            {
                "linhas": resultado.linhas,
                "anos": ", ".join(str(a) for a in resultado.anos) or "dimensão",
                "tabela": destino.qualificado,
                **{f"conferido: {o}": v for o, v in resultado.conferido.items()},
            }
        )
        if not resultado.aprovada:
            raise dg.Failure(
                f"{destino.qualificado} não confere com o parquet:\n- "
                + "\n- ".join(resultado.problemas),
                allow_retries=False,
            )

    return carga


ASSETS = [_construir(t) for t in modelo.TABELAS]
DCL = dg.AssetKey([GRUPO, "dcl"])


@dg.asset(
    key=DCL,
    group_name=GRUPO,
    deps=[a.key for a in ASSETS],
    description=(
        "O DCL do warehouse: os perfis de negócio (sócio, gerência, coordenação, assistente, "
        "financeiro) com leitura por tabela e, nas dimensões de pessoa, por coluna. Gerado "
        "da declaração em gold.dcl e reaplicado depois de toda carga; idempotente."
    ),
    compute_kind="postgres",
)
def dcl_do_warehouse(context: dg.AssetExecutionContext, lake: Lake, warehouse: Warehouse) -> None:
    con = consulta.abrir_gold(lake)
    try:
        comandos = dcl.aplicar(con, warehouse)
    finally:
        con.close()
    context.log.info("DCL aplicado: %s comandos, %s perfis", comandos, len(dcl.PERFIS))
    context.add_output_metadata(
        {"comandos": comandos, "perfis": ", ".join(p.papel for p in dcl.PERFIS)}
    )


INDICES = dg.AssetKey([GRUPO, "indices"])


@dg.asset(
    key=INDICES,
    group_name=GRUPO,
    deps=[a.key for a in ASSETS],
    description=(
        "Os índices do warehouse, só os adotados por medida de plano de execução (gold.indices), "
        "e o ANALYZE de todo fato, porque a carga envelhece as estatísticas; idempotente."
    ),
    compute_kind="postgres",
)
def indices_do_warehouse(context: dg.AssetExecutionContext, warehouse: Warehouse) -> None:
    quantos = indices.criar(warehouse)
    context.log.info("índices: %s adotados garantidos, estatísticas atualizadas", quantos)
    context.add_output_metadata(
        {"indices": quantos, "nomes": ", ".join(i.nome for i in indices.adotados())}
    )


RLS = dg.AssetKey([GRUPO, "rls"])


@dg.asset(
    key=RLS,
    group_name=GRUPO,
    deps=[DCL],
    description=(
        "O RLS do warehouse: cada filial enxerga só as próprias linhas. A política por tabela "
        "(a empresa inteira para sócio, gerência e financeiro; só as filiais do papel para "
        "coordenação e assistente) e a tabela acesso.filial_do_papel, que só o administrador "
        "escreve. Gerado de gold.rls, depois do DCL; idempotente."
    ),
    compute_kind="postgres",
)
def rls_do_warehouse(context: dg.AssetExecutionContext, warehouse: Warehouse) -> None:
    comandos = rls.aplicar(warehouse)
    tabelas = [t.nome for t in rls.tabelas_com_filial()]
    context.log.info("RLS aplicado: %s comandos, %s tabelas", comandos, len(tabelas))
    context.add_output_metadata({"comandos": comandos, "tabelas": ", ".join(tabelas)})


carregar_warehouse = dg.define_asset_job(
    name="carregar_warehouse",
    selection=dg.AssetSelection.groups(GRUPO),
    description=(
        "Leva a gold ao Postgres: as dimensões por upsert, os fatos por partição de ano, "
        "cada tabela conferida contra o parquet; no fim, os índices medidos, o DCL dos perfis "
        "de leitura e o RLS por filial."
    ),
    config=CONFIG_LOGS_JSON,
    executor_def=dg.multiprocess_executor.configured({"max_concurrent": 2}),
)
