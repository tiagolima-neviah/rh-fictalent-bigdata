"""Ponto de entrada do Dagster para o projeto Fictalent RH.

Nesta versão (v0.2.0, fundação) o Dagster sobe vazio: a plataforma existe, os
metadados já vão para o Postgres dedicado, e os ativos de cada camada entram
com os cards da Fase 3 em diante (geração, ingestão, bronze, silver, gold,
warehouse). Declarar o ponto de entrada agora é o que permite validar a
infraestrutura inteira antes de existir qualquer dado.
"""

from __future__ import annotations

import dagster as dg

defs = dg.Definitions(assets=[])
