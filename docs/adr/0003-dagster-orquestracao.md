# ADR-0003 · Dagster como orquestrador

**Situação:** aceito em 16/09/2026. Entra na v0.3.0.

## Contexto

O pipeline tem 75 tabelas na réplica, três naturezas de fonte (relacional com backfill e incremental, API REST, arquivo), quatro camadas de parquet, um warehouse e uma API, com carga diária e um histórico desde 2018 que precisa ser reprocessável por período. Precisa de algo que saiba **a ordem** (o que depende do quê), **o recorte** (um dia, um ano, tudo), **a repetição** (falhou, tenta de novo; mudou a regra, reprocessa 2023) e **a memória** (o que rodou, quando, quanto demorou). A cadeia de scripts com CLI da Fictitur resolve a ordem, mas não o recorte nem a memória.

## Decisão

Dagster orquestra o projeto inteiro: cada tabela e cada camada é um **asset**, com dependências declaradas; partições por dia (incremental) e por ano (histórico); agendamento diário; sensores para arquivo novo; retentativa; backfill pela interface; histórico de cada execução em Postgres próprio. Webserver e daemon em container, imagem própria sem root.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| cron + CLI própria (o que a Fictitur faz) | resolve a ordem; não dá partição, backfill por período, retentativa nem histórico consultável. Serve à Fictitur, que é menor e já está pronta; a ausência deliberada lá é evidência de critério |
| Airflow | organiza **tarefas**, não ativos: a dependência entre tabelas vira código de DAG em vez de desenho; mais pesado para uma máquina só; partição por data existe, mas backfill de ativo específico é mais trabalhoso |
| Prefect | bom para fluxos; o modelo de ativo com partição e linhagem é menos central |
| dbt sozinho | transforma dentro de um banco; não ingere, não agenda, não fala com API nem com arquivo |

## Consequências

- Postgres de metadados (`pg-dagster`), imagem própria (`infra/dagster/Dockerfile`), fila de execuções; um serviço a mais para operar e monitorar.
- A CLI própria vira atalho de desenvolvimento, não o caminho oficial.
- Quem sabe Dagster lê Airflow: asset ≈ tarefa que produz um dado, job ≈ DAG, schedule ≈ `schedule_interval`.
