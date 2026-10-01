"""O descarte de dado pessoal no Dagster: um asset e o job que o aplica.

O asset `lgpd/descarte` apaga da bronze o dado pessoal das linhas excluídas na origem e dos
candidatos com retenção vencida (`rh_fictalent.lgpd.descarte`) e registra cada descarte no
warehouse. Ele depende da bronze das tabelas com dado pessoal e das que decidem quem está
vencido (o parâmetro, a candidatura, o colaborador); a silver das tabelas com dado pessoal
depende dele. Assim o grafo mostra a ordem que a lei pede: a silver nunca é montada antes do
descarte.

O job `aplicar_descarte` roda o descarte e tudo o que vem depois dele (a silver das tabelas
com dado pessoal e a prestação de contas): é o caminho curto, para rodar à mão. No dia a dia
o descarte roda dentro do `construir_silver`, que o sensor `silver_depois_da_carga`
(`orquestracao.silver`) dispara depois de toda carga incremental, porque a carga pode trazer
de volta, em claro, uma linha que mudou na réplica.
"""

# sem `from __future__ import annotations`: o Dagster lê as anotações em tempo de execução
import dagster as dg

from rh_fictalent.lake import consulta
from rh_fictalent.lgpd import descarte
from rh_fictalent.orquestracao.convencoes import chave
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake, Warehouse
from rh_fictalent.orquestracao.silver import (
    DESCARTE,
    GRUPO_LGPD,
    MAX_CONCORRENTES,
    NOVA_TENTATIVA,
    referencia_da_carga,
)
from rh_fictalent.staging import lgpd as etiquetas

# além das tabelas com dado pessoal, as que decidem quem está vencido
DECIDEM = ("cadastro.parametro", "ats.candidatura", "pessoas.colaborador")


@dg.asset(
    key=DESCARTE,
    group_name=GRUPO_LGPD,
    deps=[
        chave("bronze", *t.split("."))
        for t in dict.fromkeys([*sorted(etiquetas.colunas()), *DECIDEM])
    ],
    description=(
        "Apaga da bronze o dado pessoal das linhas excluídas na origem e dos candidatos não "
        "contratados com a retenção vencida (RETENCAO_CANDIDATO_DIAS), conferindo antes de "
        "trocar cada arquivo, e registra o descarte em lgpd.descarte, sem dado pessoal."
    ),
    compute_kind="duckdb",
    retry_policy=NOVA_TENTATIVA,
)
def descarte_de_dado_pessoal(
    context: dg.AssetExecutionContext, lake: Lake, warehouse: Warehouse
) -> None:
    referencia = referencia_da_carga(warehouse)
    con = consulta.abrir(lake)
    try:
        vigente, resultados = descarte.aplicar(con, lake, referencia)
    finally:
        con.close()
    gravadas = descarte.registrar(warehouse, referencia, vigente, resultados, context.run_id)
    context.log.info(
        "descarte em %s: %s tabelas com alvo, %s registradas", referencia, len(resultados), gravadas
    )
    context.add_output_metadata(
        {
            "referencia": referencia.isoformat(),
            "retencao": vigente.texto if vigente else "parâmetro não declarado",
            "tabelas": len(resultados),
            "eliminadas": sum(r.eliminadas for r in resultados),
            "vencidas": sum(r.vencidas for r in resultados),
            "registrados": gravadas,
        }
    )
    ruins = [r for r in resultados if r.problemas]
    if ruins:
        raise dg.Failure(
            "descarte recusado na conferência (a bronze original ficou como estava):\n- "
            + "\n- ".join(f"{r.tabela}: {p}" for r in ruins for p in r.problemas),
            allow_retries=False,
        )


aplicar_descarte = dg.define_asset_job(
    name="aplicar_descarte",
    selection=dg.AssetSelection.assets(DESCARTE).downstream(),
    description="Descarta o dado pessoal vencido ou eliminado e refaz a silver que dependia dele.",
    config=CONFIG_LOGS_JSON,
    executor_def=dg.multiprocess_executor.configured({"max_concurrent": MAX_CONCORRENTES}),
)
