"""O job que pergunta, de dentro do Dagster, se a bronze ainda é o espelho da réplica.

É o C-06 da régua como operação: para cada tabela, as linhas vivas na bronze (lidas com DuckDB)
contra as linhas na réplica. Serve depois de uma carga, depois de um dia simulado, ou quando
alguém desconfiar. Divergência é falha, com a lista de tabelas e a diferença de cada uma.
"""

# sem `from __future__ import annotations`: o Dagster lê as anotações em tempo de execução
import dagster as dg

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON, logger_json
from rh_fictalent.orquestracao.recursos import Lake, Replica


@dg.op(description="Conta as linhas vivas de cada tabela na bronze e compara com a réplica.")
def comparar_com_a_replica(context: dg.OpExecutionContext, replica: Replica, lake: Lake) -> None:
    con = replica.conectar()
    try:
        conservacao = consulta.conservacao(con, lake)
    finally:
        con.close()
    diferentes = consulta.divergentes(conservacao)
    context.log.info(
        "conservação réplica → bronze: %s tabelas conferidas, %s divergentes",
        len(conservacao),
        len(diferentes),
    )
    context.add_output_metadata(
        {
            "tabelas": len(conservacao),
            "divergentes": len(diferentes),
            "linhas_vivas_na_bronze": sum(v for v, _ in conservacao.values()),
            "linhas_na_replica": sum(r for _, r in conservacao.values()),
        }
    )
    if diferentes:
        detalhes = "\n- ".join(
            f"{nome}: {vivas} vivas na bronze, {na_replica} na réplica"
            for nome, (vivas, na_replica) in sorted(diferentes.items())
        )
        raise dg.Failure(f"a bronze não é o espelho da réplica:\n- {detalhes}")


@dg.job(
    name="conferir_bronze",
    description="C-06 como operação: a bronze tem, viva, exatamente o que a réplica tem?",
    logger_defs={"json": logger_json},
    config=CONFIG_LOGS_JSON,
)
def conferir_bronze() -> None:
    comparar_com_a_replica()
