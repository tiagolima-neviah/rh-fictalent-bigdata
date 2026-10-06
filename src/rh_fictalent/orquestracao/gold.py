"""Os assets da gold: uma tabela do modelo dimensional, um asset.

A linhagem sai do próprio modelo: o asset `gold/<tabela>` depende das tabelas da silver que o
SQL dele lê e das dimensões que ele referencia. Por isso o Dagster monta as dimensões antes
dos fatos sem ninguém escrever a ordem, e o grafo mostra de onde vem cada número.

Cada asset **se reprova**, como na silver: a tabela é gravada em `gold/_em_conferencia/`,
conferida ali (grão, referências, conservação dos totais contra a silver) e só então movida
para o endereço que o warehouse lê. A conexão é a de `lake.consulta.abrir_silver`: quem
constrói a gold enxerga só a silver, e dela só as linhas vivas.

A gold não é particionada no Dagster, pelo mesmo motivo da silver: o fato do posto por mês
cruza anos (a vigência atravessa o ano). O arquivo no lake é um por ano.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string

import dagster as dg

from rh_fictalent.gold import construcao, modelo, regua
from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.convencoes import chave_fonte
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake
from rh_fictalent.orquestracao.silver import MAX_CONCORRENTES, NOVA_TENTATIVA

GRUPO = "gold"


def chave_gold(nome: str) -> dg.AssetKey:
    return dg.AssetKey([GRUPO, nome])


def dependencias(tabela: modelo.Tabela) -> list[dg.AssetKey]:
    """As tabelas da silver e as fontes públicas que o SQL lê, e as dimensões referenciadas."""
    lidas = []
    for fonte in sorted(tabela.fontes):
        modulo, nome = fonte.split(".")
        if modulo == consulta.ESQUEMA_FONTES:
            lidas.append(chave_fonte(*consulta.ASSETS_DAS_FONTES[nome]))
        else:
            lidas.append(dg.AssetKey(["silver", modulo, nome]))
    return [*lidas, *(chave_gold(d) for d in sorted(set(tabela.referencias.values())))]


def _asset_gold(tabela: modelo.Tabela) -> dg.AssetsDefinition:
    tipo = "fato" if tabela.fato else "dimensão"

    @dg.asset(
        key=chave_gold(tabela.nome),
        group_name=GRUPO,
        deps=dependencias(tabela),
        description=f"{tabela.nome}: {tipo} da matriz de barramento, com o grão em "
        f"({', '.join(tabela.chave)}); só é publicada se passar na conferência contra a silver.",
        compute_kind="duckdb",
        retry_policy=NOVA_TENTATIVA,
    )
    def gold(context: dg.AssetExecutionContext, lake: Lake) -> None:
        con = consulta.abrir_silver(lake)
        try:
            horizonte = modelo.preparar(con)
            resultado = construcao.publicar(con, lake, tabela)
        except RuntimeError as erro:  # silver sem movimento: repetir não cria o dado
            raise dg.Failure(str(erro), allow_retries=False) from erro
        finally:
            con.close()
        context.log.info("%s: %s linhas", tabela.nome, resultado.linhas)
        context.add_output_metadata(
            {
                "linhas": resultado.linhas,
                "horizonte": horizonte,
                "caminho": construcao.pasta(lake, tabela.nome),
                **{f"conservado: {o}": v for o, v in resultado.conservado.items()},
            }
        )
        if not resultado.aprovada:
            raise dg.Failure(
                f"a gold de {tabela.nome} não se confirma:\n- " + "\n- ".join(resultado.problemas),
                allow_retries=False,
            )

    return gold


ASSETS = [_asset_gold(t) for t in modelo.TABELAS]
REGUA = chave_gold("regua")
LAUDO = "_regua.json"  # no lake, ao lado das tabelas da gold


@dg.asset(
    key=REGUA,
    group_name=GRUPO,
    deps=[a.key for a in ASSETS],
    description=(
        "A régua da gold, com o motor do contrato de aceite: conservação de cada total contra a "
        "silver, integridade de chaves e as medidas do contrato que a gold reproduz, conferidas "
        "contra as bandas. Reprova por conservação ou chave; a banda é relatada."
    ),
    compute_kind="duckdb",
    retry_policy=NOVA_TENTATIVA,
)
def regua_da_gold(context: dg.AssetExecutionContext, lake: Lake) -> None:
    con = consulta.abrir_silver(lake)
    try:
        consulta.criar_views_da_gold(con, lake)
        resultado = regua.laudo(con)
    finally:
        con.close()
    caminho = lake.caminho(construcao.CAMADA, LAUDO)
    with lake.sistema().open(caminho, "w") as arquivo:
        arquivo.write(resultado.laudo.para_json())
    context.log.info(resultado.veredito)
    context.add_output_metadata(
        {
            "veredito": dg.MetadataValue.md(resultado.veredito),
            "resumo": dg.MetadataValue.json(resultado.laudo.resumo()),
            "fora_da_banda": len(resultado.fora_da_banda),
            "caminho": caminho,
        }
    )
    if not resultado.aprovada:
        raise dg.Failure(resultado.veredito, allow_retries=False)


construir_gold = dg.define_asset_job(
    name="construir_gold",
    selection=dg.AssetSelection.groups(GRUPO),
    description=(
        "Monta o modelo dimensional a partir da silver: as dimensões e depois os fatos, cada "
        "tabela conferida contra a silver antes de ser publicada; no fim, a régua da gold."
    ),
    config=CONFIG_LOGS_JSON,
    executor_def=dg.multiprocess_executor.configured({"max_concurrent": MAX_CONCORRENTES}),
)
