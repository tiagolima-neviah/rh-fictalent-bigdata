# Histórico de versões

Cada versão fecha uma fase inteira, com código, testes e documentação. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o [SemVer](https://semver.org/lang/pt-BR/).

## [0.3.0] · 2026-09-17 · Orquestração e observabilidade

O Dagster deixou de ser vazio e a plataforma passou a se observar: recursos, convenções, o primeiro job, logs em JSON, métricas de execução no warehouse, Grafana como código e a verificação de ponta a ponta. Ainda sem dado: o dado sintético é a v0.4.0.

### Orquestração (Dagster)
- Recursos `Replica` (MySQL, como usuário `pipeline`), `Lake` (S3 via fsspec) e `Warehouse` (Postgres), configurados pelo ambiente, com segredos por `EnvVar`; dentro do Compose os hosts são os serviços, fora dele `127.0.0.1`.
- Convenções de todo asset: camada como grupo, chave `camada/modulo/tabela`, partição diária desde 2018-01-02 e anual 2018 a 2026.
- Job `verificar_plataforma` (grupo `plataforma`): prova de dentro do Dagster que réplica, lake e warehouse estão alcançáveis, com metadados no histórico.
- Logs estruturados: uma linha JSON por evento de toda execução, com `run_id`, `job`, `passo`, `evento` e `excecao`; logger de job selecionado pela configuração padrão de cada job.

### Observabilidade
- Métricas de execução no warehouse (`observabilidade.execucao` e `execucao_passo`), gravadas por três sensores de fim de execução (sucesso, falha, cancelamento), ligados por padrão, com upsert.
- Grafana como código: painel *Fictalent · Execuções do pipeline* (execuções e falhas em 24 h, frescor com faixas, duração média, por dia e status, por job, por passo, últimas execuções, falhas com o erro) e duas regras de alerta (execução falhou; dado envelheceu), provisionados por arquivo e não editáveis pela interface.
- `scripts/saude.sh` em duas fases: containers saudáveis e prova de ponta a ponta (réplica, gatilhos, cifra, keyring, bucket, `grafana_leitor`, métricas e frescor, code location e sensores, fontes, painel e alertas), terminando em `PLATAFORMA OK`.

### Documentação
- `docs/07` instalação e reprodução (do clone à plataforma verificada, atualizar, recomeçar, desinstalar) e `docs/09` monitoramento e healthcheck (três camadas, painel indicador a indicador, alertas, investigar por `run_id`, rotina). Manual `docs/08` ganhou Dagster, logs, métricas e a chave de cifra.

### Esteira
- 285 testes; os de integração materializam o job, capturam os logs, registram métricas e executam cada consulta do Grafana como `grafana_leitor`.

### Não inclui
- Dado, ingestão, assets de dado, agendas. A ordem: v0.4.0 dado sintético, v0.5.0 ingestão, v0.6.0 lake, v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.2.0] · 2026-09-16 · Fundação segura

A réplica do sistema do cliente, de pé, cifrada, com controle de acesso e provada por teste a cada PR. Ainda sem dado: o dado sintético é a v0.4.0.

### Plataforma
- Docker Compose com 7 serviços e 2 jobs de inicialização: réplica MySQL 8.4, warehouse Postgres 16, Postgres de metadados do Dagster, SeaweedFS (S3), Dagster (web e daemon), Grafana; healthcheck em todo serviço, portas só em `127.0.0.1`, imagens com versão exata, `no-new-privileges`, Dagster, Grafana e MySQL sem root, segredos só no `.env` (a falta derruba a subida).
- `scripts/saude.sh` (espera a plataforma inteira ficar saudável) e `scripts/aplicar_ddl.sh` (aplica a DDL num volume existente, idempotente).

### Réplica (MySQL 8)
- DDL dos 10 módulos: 75 tabelas de negócio mais a trilha de exclusões, comentário em toda tabela, chaves estrangeiras entre databases (dois ciclos fechados com `ALTER` idempotente), `CHECK` no lugar de `ENUM`, `atualizado_em` nativo e indexado em toda tabela (a marca d'água do incremental), etiqueta LGPD no comentário de cada coluna de dado pessoal.
- Trilha de exclusões: 75 gatilhos `BEFORE DELETE` **gerados da DDL**, com `USER()` como autor e `DROP` + `CREATE` para reaplicação; testado com um `DELETE` de verdade.
- Controle de acesso por função: `pipeline` (só leitura, inclusive a trilha), `relatorios_cliente` (leitura sem dado pessoal, com `GRANT` coluna a coluna **gerado das etiquetas LGPD**) e `replicador` (escreve o negócio, sem DDL, `GRANT` ou trilha); testes que passam quando o acesso indevido falha.
- Cifra em repouso da réplica inteira: tablespaces, redo, undo e binlog, com `component_keyring_file` e chave mestra em volume próprio; **provada no disco** (CPF gravado não aparece no `.ibd`) e **medida** (escrita +3% a +8%, leitura dentro do ruído, disco igual).
- Dicionário de dados gerado da `information_schema`, com a classificação por coluna (4 pessoais sensíveis, 24 pessoais, 55 públicas, 599 internas) e o inventário de dado pessoal.

### Esteira
- CI em três trilhos no GitHub Actions: qualidade (ruff, mypy, pytest), **réplica provada no runner** (MySQL com `.env` descartável e os testes de integração) e segurança (bandit, pip-audit, gitleaks, trivy). Espelho local em `scripts/esteira.sh`. 249 testes.

### Documentação
- `docs/03` arquitetura em 9 camadas com o mapa de escopo da réplica; `docs/04` modelo de dados; `docs/05` segurança e LGPD (modelo de ameaça, conferência por garantia, LGPD princípio a princípio, resposta a incidente); `docs/08` manual de operação; dicionário de dados; nove ADRs (bancos, cifra, Dagster, SeaweedFS, DuckDB, pandera e régua, Grafana, Gitflow, FastAPI).

### Decisões
- MySQL na réplica e Postgres no warehouse (ADR-0001): não existe "origem" no ambiente da consultoria; o staging é a réplica autorizada do sistema do cliente.
- Réplica parcial por pertinência como regra: replica-se o que a dor contratada exige, com mapa de escopo; neste caso a réplica é completa por autorização do cliente.
- Cifra de tablespace, não de coluna (ADR-0002).

### Não inclui
- Dado, ingestão, assets do Dagster, lake, gold, warehouse carregado, API. A ordem: v0.3.0 orquestração e observabilidade, v0.4.0 dado sintético, v0.5.0 ingestão, v0.6.0 lake, v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.1.0] · 2026-09-15 · Entendimento e modelagem

- Entendimento do negócio (`docs/01`) e dos dados (`docs/02`): a Fictalent RH, o ciclo do pedido à receita, a história de 2018 a 2026 em cinco atos.
- Arquitetura (`docs/03`) com a especificação de mercado incorporada e o plano de versões.
- Modelo relacional de 75 tabelas em 10 módulos aprovado; plano de sintetização aprovado.
- Repositório público com Gitflow (`develop` como branch padrão).

[0.3.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.3.0
[0.2.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.2.0
[0.1.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.1.0
