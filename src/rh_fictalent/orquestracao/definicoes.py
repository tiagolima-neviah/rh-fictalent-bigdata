"""Ponto de entrada do Dagster para o projeto Fictalent RH.

Tudo o que o Dagster conhece passa por aqui: assets, jobs, recursos e, mais adiante,
agendas e sensores. Na v0.3.0 entram os recursos (réplica, lake, warehouse) e o grupo de
verificação da plataforma e os sensores que gravam as métricas de execução no warehouse; na
v0.4.0, as fontes públicas por API (grupo fontes); na v0.5.0, a bronze; na v0.6.0, a silver
com a prestação de contas contra a auditoria, a pseudonimização e o descarte de dado pessoal;
na v0.7.0, a gold (o modelo dimensional conferido contra a silver) e o warehouse Postgres
carregado dela.
Os assets de dado (geração, ingestão, camadas do lake, warehouse) entram com as versões
seguintes, sempre pelas convenções de rh_fictalent.orquestracao.convencoes.
"""

from __future__ import annotations

import dagster as dg

from rh_fictalent.orquestracao.bronze import ASSETS as BRONZE
from rh_fictalent.orquestracao.bronze import ORIGENS as REPLICA
from rh_fictalent.orquestracao.bronze import backfill_bronze
from rh_fictalent.orquestracao.conservacao import conferir_bronze
from rh_fictalent.orquestracao.fontes import (
    carregar_caged,
    carregar_feriados,
    carregar_municipios,
    feriados_brasilapi,
    movimentacao_caged,
    municipios_ibge,
)
from rh_fictalent.orquestracao.gold import ASSETS as GOLD
from rh_fictalent.orquestracao.gold import construir_gold, regua_da_gold
from rh_fictalent.orquestracao.incremental import agenda_incremental, carga_incremental
from rh_fictalent.orquestracao.lgpd import aplicar_descarte, descarte_de_dado_pessoal
from rh_fictalent.orquestracao.logger_json import logger_json
from rh_fictalent.orquestracao.planilhas import carregar_consolidado, consolidado_em_planilha
from rh_fictalent.orquestracao.recursos import recursos_do_ambiente
from rh_fictalent.orquestracao.sensores import SENSORES
from rh_fictalent.orquestracao.silver import ASSETS as SILVER
from rh_fictalent.orquestracao.silver import (
    construir_silver,
    prestacao_de_contas,
    silver_depois_da_carga,
)
from rh_fictalent.orquestracao.simulacao import agenda_simulacao, simular_dias
from rh_fictalent.orquestracao.verificacao import (
    lake_pronto,
    replica_pronta,
    verificar_plataforma,
    warehouse_pronto,
)
from rh_fictalent.orquestracao.warehouse import ASSETS as WAREHOUSE
from rh_fictalent.orquestracao.warehouse import (
    carregar_warehouse,
    dcl_do_warehouse,
    rls_do_warehouse,
)

defs = dg.Definitions(
    assets=[
        replica_pronta,
        lake_pronto,
        warehouse_pronto,
        municipios_ibge,
        feriados_brasilapi,
        movimentacao_caged,
        *REPLICA,
        *BRONZE,
        consolidado_em_planilha,
        descarte_de_dado_pessoal,
        *SILVER,
        prestacao_de_contas,
        *GOLD,
        regua_da_gold,
        *WAREHOUSE,
        dcl_do_warehouse,
        rls_do_warehouse,
    ],
    jobs=[
        verificar_plataforma,
        carregar_municipios,
        carregar_feriados,
        carregar_caged,
        backfill_bronze,
        carga_incremental,
        carregar_consolidado,
        simular_dias,
        conferir_bronze,
        construir_silver,
        aplicar_descarte,
        construir_gold,
        carregar_warehouse,
    ],
    schedules=[agenda_incremental, agenda_simulacao],
    # fim de execução vira linhas em observabilidade.execucao(_passo); fim de carga incremental
    # dispara o descarte de dado pessoal e a silver
    sensors=[*SENSORES, silver_depois_da_carga],
    resources=recursos_do_ambiente(),
    loggers={"json": logger_json},  # todo evento de toda execução sai como linha JSON
)
