# Registros de decisão de arquitetura (ADR)

Cada tecnologia que entra neste projeto precisa de um registro dizendo **que necessidade do caso ela atende**. Se a única justificativa fosse "o mercado pede", a ferramenta iria para um laboratório separado, não para cá. Formato: contexto, decisão, alternativas consideradas, consequências. Um ADR aceito não é reescrito: se a decisão mudar, entra um novo que declara o que substitui.

| número | decisão | situação |
|---|---|---|
| [0001](0001-mysql-no-staging-postgres-no-olap.md) | MySQL na réplica do cliente (staging), Postgres no warehouse (OLAP) | aceito em 15/09/2026 |
| [0002](0002-cifra-em-repouso-tablespace.md) | Cifra em repouso por tablespace do InnoDB com keyring próprio, não por coluna | aceito em 16/09/2026 |
| [0003](0003-dagster-orquestracao.md) | Dagster como orquestrador (assets, partições, backfill, histórico) | aceito em 16/09/2026, entra na v0.3.0 |
| [0004](0004-seaweedfs-lake-s3.md) | SeaweedFS como storage S3 do lake (MinIO comunitário abandonado) | aceito em 15/09/2026 |
| [0005](0005-duckdb-parquet-medalhao.md) | DuckDB sobre parquet como motor do lake | aceito em 16/09/2026, entra na v0.6.0 |
| [0006](0006-pandera-e-regua.md) | pandera para esquema, régua própria para a história | aceito em 16/09/2026, entra na v0.4.0 |
| [0007](0007-grafana-so-observabilidade.md) | Grafana só para observabilidade, nunca painel de negócio | aceito em 15/09/2026 |
| [0008](0008-gitflow-por-versao-publicavel.md) | Gitflow com cada fase virando versão publicável | aceito em 15/09/2026 |
| [0009](0009-fastapi-api-dos-indicadores.md) | FastAPI para servir os indicadores com contrato, versão e token | aceito em 16/09/2026, entra na v1.0.0 |
| [0010](0010-httpx-ingestao-de-api.md) | httpx para a ingestão por API, com retry e limite de taxa escritos no projeto | aceito em 17/09/2026, entra na v0.4.0 |

Tecnologia que entrar depois (dbt, PySpark, MLflow, o backend de keyring em produção) ganha o seu ADR antes de ganhar código.
