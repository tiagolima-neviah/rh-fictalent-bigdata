"""O logger de job do Dagster em JSON: todo evento de toda execução sai como uma linha JSON.

O Dagster tem dois caminhos de log: o logger do job (por onde passam os eventos de execução,
STEP_SUCCESS, RUN_FAILURE, e também as mensagens de context.log) e os handlers da instância.
Trocar o logger do job pelo JSON é o que faz o pipeline inteiro falar uma língua só. O Dagster
só instancia um logger de job quando ele aparece na configuração da execução, então cada job
carrega CONFIG_LOGS_JSON como configuração padrão (define_asset_job(config=...)), e as
Definitions expõem o logger em `loggers`. Nível DEBUG: os eventos STEP_* são DEBUG.
"""

from __future__ import annotations

import logging
import sys

import dagster as dg

from rh_fictalent.observabilidade.logs import FormatadorJSON

# todo job do projeto usa isto como configuração padrão: define_asset_job(config=CONFIG_LOGS_JSON)
CONFIG_LOGS_JSON: dict[str, object] = {"loggers": {"json": {"config": {"nivel": "DEBUG"}}}}


@dg.logger(
    config_schema={"nivel": dg.Field(str, is_required=False, default_value="INFO")},
    description="Uma linha JSON por evento, com run_id, job, passo e evento.",
)
def logger_json(init_context: dg.InitLoggerContext) -> logging.Logger:
    nivel = str(init_context.logger_config["nivel"]).upper()
    logger = logging.Logger("dagster_json", level=getattr(logging, nivel, logging.INFO))
    saida = logging.StreamHandler(sys.stdout)
    saida.setFormatter(FormatadorJSON())
    logger.addHandler(saida)
    return logger
