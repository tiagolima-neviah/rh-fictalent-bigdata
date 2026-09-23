"""O job que dá movimento à réplica, e a agenda que o faz rodar antes da carga.

A agenda nasce **desligada**. Ligá-la é uma decisão consciente: a partir daí a réplica deixa de
ser exatamente a base que a régua aprovou, e a conferência passa a depender do registro de
`ingestao.dia_simulado`. Quem quiser o pipeline vivo liga; quem quiser a base parada no marco
deixa desligada, e continua podendo simular um dia à mão quando quiser demonstrar.

Roda às 4h, uma hora antes da carga incremental: primeiro a operação acontece, depois o
pipeline a lê. É a ordem do mundo real, e é ela que torna a demonstração honesta.
"""

# sem `from __future__ import annotations`: o Dagster lê as anotações em tempo de execução
from datetime import date, timedelta

import dagster as dg

from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON, logger_json
from rh_fictalent.orquestracao.recursos import Replica, Warehouse
from rh_fictalent.simulacao import registro
from rh_fictalent.simulacao.dia import FIM_DA_HISTORIA, dias_a_simular, simular

HORA_DA_SIMULACAO = "0 4 * * *"  # uma hora antes da carga incremental
FUSO = "America/Sao_Paulo"
MAXIMO_DE_DIAS = 30  # trava de segurança: nunca mais que um mês de uma vez


class Dias(dg.Config):
    """Até quando simular. Vazio: até ontem, que é o último dia inteiro que existiu."""

    ate: str = ""
    desde: str = ""


@dg.op(description="Escreve na réplica os dias de operação que faltam desde o fim da história.")
def rodar_os_dias(
    context: dg.OpExecutionContext, config: Dias, replica: Replica, warehouse: Warehouse
) -> None:
    registro.criar(warehouse)
    ate = date.fromisoformat(config.ate) if config.ate else date.today() - timedelta(days=1)
    desde = date.fromisoformat(config.desde) if config.desde else None
    dias = dias_a_simular(ate, desde)
    if not dias:
        context.log.info("nada a simular até %s (a história vai até %s)", ate, FIM_DA_HISTORIA)
        return
    if len(dias) > MAXIMO_DE_DIAS:
        raise dg.Failure(
            f"{len(dias)} dias a simular, acima do limite de {MAXIMO_DE_DIAS}. "
            "Rode por partes com `desde` e `ate`, para não escrever um mês inteiro sem olhar."
        )
    novos = pulados = 0
    for dia in dias:
        movimento = simular(replica, dia)
        context.log.info("%s", movimento.resumo())
        if movimento.ja_simulado:
            pulados += 1
            continue
        registro.gravar(warehouse, movimento)
        novos += 1
    context.log.info("dias escritos: %s; já existiam: %s", novos, pulados)


@dg.job(
    name="simular_dias",
    description="Dá movimento à réplica: ponto do dia, vagas fechando, alocações terminando.",
    logger_defs={"json": logger_json},
    config=CONFIG_LOGS_JSON,
)
def simular_dias() -> None:
    rodar_os_dias()


agenda_simulacao = dg.ScheduleDefinition(
    name="simular_dias_diaria",
    job=simular_dias,
    cron_schedule=HORA_DA_SIMULACAO,
    execution_timezone=FUSO,
    # desligada de propósito: ligar faz a réplica divergir da base que a régua aprovou
    default_status=dg.DefaultScheduleStatus.STOPPED,
    description="Todo dia às 4h, escreve o dia anterior de operação na réplica.",
)
