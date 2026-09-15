# Registros de decisão de arquitetura (ADR)

Cada tecnologia que entra neste projeto precisa de um registro dizendo **que necessidade do caso ela atende**. Se a única justificativa fosse "o mercado pede", a ferramenta iria para um laboratório separado, não para cá. Formato: contexto, decisão, alternativas consideradas, consequências. Um ADR aceito não é reescrito: se a decisão mudar, entra um novo que declara o que substitui.

| número | decisão | situação |
|---|---|---|
| [0001](0001-mysql-no-staging-postgres-no-olap.md) | MySQL na réplica do cliente (staging), Postgres no warehouse (OLAP) | aceito em 15/09/2026 |

Os demais (Dagster, SeaweedFS, DuckDB, pandera, Grafana, FastAPI, Gitflow) entram com o card 2.9 da v0.2.0.
