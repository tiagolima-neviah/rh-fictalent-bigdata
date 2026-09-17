"""Ponto de entrada do Dagster para o projeto Fictalent RH.

Tudo o que o Dagster conhece passa por aqui: assets, jobs, recursos e, mais adiante,
agendas e sensores. Na v0.3.0 entram os recursos (réplica, lake, warehouse) e o grupo de
verificação da plataforma e os sensores que gravam as métricas de execução no warehouse; os
assets de dado (geração, ingestão, camadas do lake, warehouse)
entram com as versões seguintes, sempre pelas convenções de rh_fictalent.orquestracao.convencoes.
"""

from __future__ import annotations

import dagster as dg

from rh_fictalent.orquestracao.logger_json import logger_json
from rh_fictalent.orquestracao.recursos import recursos_do_ambiente
from rh_fictalent.orquestracao.sensores import SENSORES
from rh_fictalent.orquestracao.verificacao import (
    lake_pronto,
    replica_pronta,
    verificar_plataforma,
    warehouse_pronto,
)

defs = dg.Definitions(
    assets=[replica_pronta, lake_pronto, warehouse_pronto],
    jobs=[verificar_plataforma],
    sensors=SENSORES,  # fim de execução vira linhas em observabilidade.execucao(_passo)
    resources=recursos_do_ambiente(),
    loggers={"json": logger_json},  # todo evento de toda execução sai como linha JSON
)
