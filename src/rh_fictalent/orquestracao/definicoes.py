"""Ponto de entrada do Dagster para o projeto Fictalent RH.

Tudo o que o Dagster conhece passa por aqui: assets, jobs, recursos e, mais adiante,
agendas e sensores. Na v0.3.0 entram os recursos (réplica, lake, warehouse) e o grupo de
verificação da plataforma; os assets de dado (geração, ingestão, camadas do lake, warehouse)
entram com as versões seguintes, sempre pelas convenções de rh_fictalent.orquestracao.convencoes.
"""

from __future__ import annotations

import dagster as dg

from rh_fictalent.orquestracao.recursos import recursos_do_ambiente
from rh_fictalent.orquestracao.verificacao import (
    lake_pronto,
    replica_pronta,
    verificar_plataforma,
    warehouse_pronto,
)

defs = dg.Definitions(
    assets=[replica_pronta, lake_pronto, warehouse_pronto],
    jobs=[verificar_plataforma],
    resources=recursos_do_ambiente(),
)
