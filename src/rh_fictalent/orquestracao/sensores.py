"""Sensores de fim de execução: cada execução que termina vira linhas na tabela de métricas.

Três sensores, um por desfecho (sucesso, falha, cancelamento), ligados por padrão e observando
toda code location (um run status sensor só vê a própria por padrão, e a CLI lança de outra).
Rodam no daemon, que tem o recurso do warehouse; ao disparar, leem o event log da execução e
gravam observabilidade.execucao e observabilidade.execucao_passo (upsert). O cursor nasce no
primeiro tique: execuções terminadas antes de o daemon subir não são registradas.
"""

from __future__ import annotations

import dagster as dg

from rh_fictalent.observabilidade.metricas import registrar_execucao
from rh_fictalent.orquestracao.recursos import Warehouse

INTERVALO_S = 15


def _registrar(context: dg.RunStatusSensorContext, status: str, warehouse: Warehouse) -> None:
    passos = registrar_execucao(context.instance, context.dagster_run, status, warehouse)
    context.log.info(
        "métricas gravadas: %s %s, %s passos (%s com falha)",
        context.dagster_run.job_name,
        status,
        len(passos),
        sum(1 for p in passos if p.status == "FALHA"),
    )


@dg.run_status_sensor(
    run_status=dg.DagsterRunStatus.SUCCESS,
    name="metricas_sucesso",
    minimum_interval_seconds=INTERVALO_S,
    default_status=dg.DefaultSensorStatus.RUNNING,
    monitor_all_code_locations=True,  # inclusive execuções lançadas pela CLI (-m), de outra origem
    description="Grava as métricas de toda execução que termina com sucesso.",
)
def metricas_sucesso(context: dg.RunStatusSensorContext, warehouse: Warehouse) -> None:
    _registrar(context, "SUCESSO", warehouse)


@dg.run_status_sensor(
    run_status=dg.DagsterRunStatus.FAILURE,
    name="metricas_falha",
    minimum_interval_seconds=INTERVALO_S,
    default_status=dg.DefaultSensorStatus.RUNNING,
    monitor_all_code_locations=True,  # inclusive execuções lançadas pela CLI (-m), de outra origem
    description="Grava as métricas de toda execução que falha, com o erro de cada passo.",
)
def metricas_falha(context: dg.RunStatusSensorContext, warehouse: Warehouse) -> None:
    _registrar(context, "FALHA", warehouse)


@dg.run_status_sensor(
    run_status=dg.DagsterRunStatus.CANCELED,
    name="metricas_cancelamento",
    minimum_interval_seconds=INTERVALO_S,
    default_status=dg.DefaultSensorStatus.RUNNING,
    monitor_all_code_locations=True,  # inclusive execuções lançadas pela CLI (-m), de outra origem
    description="Grava as métricas de toda execução cancelada.",
)
def metricas_cancelamento(context: dg.RunStatusSensorContext, warehouse: Warehouse) -> None:
    _registrar(context, "CANCELADA", warehouse)


SENSORES = [metricas_sucesso, metricas_falha, metricas_cancelamento]
