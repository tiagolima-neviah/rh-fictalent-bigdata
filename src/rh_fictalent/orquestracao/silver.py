"""Os assets da silver: uma tabela da bronze, um asset; e a prestação de contas no fim.

São 76 assets feitos pela mesma fábrica da bronze, a partir da mesma lista de tabelas: tabela
nova na DDL vira asset da silver sozinha e atravessa igual até alguém aprovar uma regra para
ela. A linhagem é `bronze/modulo/tabela` para `silver/modulo/tabela`, mais as tabelas da
bronze que as regras daquela tabela leem (a alocação depende do ASO e do certificado porque
é nela que ficam as marcas de ASO vencido e de curso obrigatório faltando). Assim o grafo do
Dagster mostra por que uma tabela da silver muda quando outra da bronze muda.

Os assets da silver não são particionados: a regra de duplicidade olha a tabela inteira, de
todos os anos, e uma partição por ano esconderia o cadastro repetido que atravessa o ano. O
arquivo no lake continua sendo um por ano, igual ao da bronze.

Cada asset **se reprova**: a tabela é gravada em `silver/_em_conferencia/`, conferida ali e
só então movida para o endereço que a gold lê; se a conferência acusar qualquer problema, a
materialização falha, a tabela reprovada fica na área de conferência e a silver publicada
antes continua como estava. O último asset,
`silver/prestacao_de_contas`, roda as regras na data da auditoria e falha se alguma não
reproduzir o número aprovado no catálogo; o relatório fica gravado no lake.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string
import json

import dagster as dg

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.convencoes import chave
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake, Warehouse
from rh_fictalent.silver import construcao, contas, regras

GRUPO = "silver"
PRESTACAO = dg.AssetKey(["silver", "prestacao_de_contas"])
RELATORIO = "_prestacao_de_contas.json"  # no lake, ao lado das tabelas da silver
MAX_CONCORRENTES = 2
# Nova tentativa só para a falha de infraestrutura. Em 24/09 a conexão com o lake caiu duas
# vezes em duas rodadas completas ("Failure when receiving data from the peer"), sem nenhum erro
# no log do SeaweedFS; repetir é seguro porque a tabela só é publicada depois de conferida e a
# construção é idempotente. A reprovação na conferência não se repete (`allow_retries=False`):
# ela é determinística, e tentar de novo só adiaria a mesma resposta.
NOVA_TENTATIVA = dg.RetryPolicy(max_retries=2, delay=10, backoff=dg.Backoff.EXPONENTIAL)


def lidas(tabela: str) -> list[str]:
    """A tabela da bronze e as outras que as regras dela leem, sem repetir, na ordem."""
    outras = [t for _, d in regras.por_tabela().get(tabela, []) for t in d.le]
    return list(dict.fromkeys([tabela, *outras]))


def _asset_silver(tabela: str) -> dg.AssetsDefinition:
    modulo, nome = tabela.split(".")
    codigos = sorted({r.codigo for r, _ in regras.por_tabela().get(tabela, [])})
    descricao = f"{tabela} conformada: a bronze linha a linha" + (
        f", mais as colunas das regras {', '.join(codigos)} do catálogo de achados."
        if codigos
        else ", sem regra aprovada."
    )

    @dg.asset(
        name=nome,
        key_prefix=["silver", modulo],
        group_name=GRUPO,
        deps=[chave("bronze", *t.split(".")) for t in lidas(tabela)],
        description=descricao,
        compute_kind="duckdb",
        retry_policy=NOVA_TENTATIVA,
    )
    def silver(context: dg.AssetExecutionContext, lake: Lake, warehouse: Warehouse) -> None:
        referencia = construcao.referencia_atual(warehouse)
        con = consulta.abrir(lake)
        try:
            resultado = construcao.publicar(con, lake, tabela, referencia)
        finally:
            con.close()
        context.log.info("%s: %s linhas, marcas %s", tabela, resultado.linhas, resultado.marcas)
        context.add_output_metadata(
            {
                "linhas": resultado.linhas,
                "referencia": referencia.isoformat(),
                "regras": ", ".join(codigos) or "nenhuma",
                "caminho": construcao.caminho_silver(lake, tabela),
                **{f"marcadas_{m}": n for m, n in resultado.marcas.items()},
            }
        )
        if not resultado.aprovada:
            raise dg.Failure(
                f"a silver de {tabela} não se confirma:\n- " + "\n- ".join(resultado.problemas),
                allow_retries=False,
            )

    return silver


ASSETS = [_asset_silver(t) for t in construcao.TABELAS]


@dg.asset(
    key=PRESTACAO,
    group_name=GRUPO,
    deps=[a.key for a in ASSETS],
    description=(
        "Cada regra da silver rodada na data da auditoria contra o número que a auditoria gravou "
        "para o achado; reprova se algum não bater ou se a regra não estiver aprovada no catálogo."
    ),
    compute_kind="duckdb",
    retry_policy=NOVA_TENTATIVA,
)
def prestacao_de_contas(context: dg.AssetExecutionContext, lake: Lake) -> None:
    con = consulta.abrir(lake)
    try:
        resultado = contas.prestar(con)
    finally:
        con.close()
    relatorio = contas.relatorio(resultado)
    caminho = lake.caminho(construcao.CAMADA, RELATORIO)
    with lake.sistema().open(caminho, "w") as arquivo:
        arquivo.write(json.dumps(relatorio, ensure_ascii=False, indent=2))
    ruins = contas.reprovadas(resultado)
    context.add_output_metadata(
        {
            "regras": len(resultado),
            "reprovadas": len(ruins),
            "caminho": caminho,
            "contas": dg.MetadataValue.md(
                "| regra | tabela | auditoria | regra | confere |\n|---|---|---:|---:|---|\n"
                + "\n".join(
                    f"| {c.codigo} | {c.tabela} | {c.auditoria} | {c.regra} | "
                    f"{'sim' if c.confere else 'NÃO'} |"
                    for c in resultado
                )
            ),
        }
    )
    if ruins:
        raise dg.Failure(
            "a silver não reproduz a auditoria:\n- "
            + "\n- ".join(
                f"{c.codigo}: auditoria {c.auditoria}, regra {c.regra} ({c.situacao})"
                for c in ruins
            ),
            allow_retries=False,
        )


construir_silver = dg.define_asset_job(
    name="construir_silver",
    selection=dg.AssetSelection.groups(GRUPO),
    description="Monta a silver inteira a partir da bronze e presta contas contra a auditoria.",
    config=CONFIG_LOGS_JSON,
    # cada passo é um processo com o Dagster e o DuckDB carregados; o padrão (um por núcleo)
    # passa do limite de memória do container. Duas tabelas por vez levaram a silver inteira
    # em 3 a 5 minutos nas rodadas de 24/09, e o gargalo é o lake, não a CPU.
    executor_def=dg.multiprocess_executor.configured({"max_concurrent": MAX_CONCORRENTES}),
)
