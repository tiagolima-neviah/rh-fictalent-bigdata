<a id="topo"></a>

# Bibliografia · o que ler, fase a fase e card a card

<!-- nav:start -->
[Home](../README.md) | [← Ingestão](11_ingestao.md) | [Registros de decisão](adr/README.md)
<!-- nav:end -->

> Este projeto foi construído com um acervo ao lado, e cada decisão técnica tem um capítulo que a sustenta. Este documento é a lista dessas leituras, na ordem em que o projeto foi construído: por fase e por card, com livro e capítulo, para quem quer entender o porquê de cada peça antes (ou depois) de ler o código. Serve a quem vai começar um projeto parecido do zero e a quem só quer estudar. A regra da lista é a mesma da régua de validação: capítulo sempre, título nunca sozinho; o que está confirmado é o que foi lido durante a construção, e o que é plano está marcado como plano.

## 1. Como usar esta lista

Cada fase tem uma tabela com os cards que a compuseram, o que se construiu em cada um e a leitura que o sustenta. A coluna de leitura traz o nome curto da obra (a tabela da seção 2 tem o nome inteiro, os autores e o arquivo), o capítulo e a marca **acervo** ou **fora do acervo**. "Acervo" quer dizer que o livro está em `D:\projetos\00_acervo`, o acervo técnico da Neviah, e que o capítulo citado foi conferido no sumário do arquivo; "fora do acervo" quer dizer que o livro ainda não foi adquirido, o capítulo é citado de memória e vale conferir no sumário antes de comprar. A última coluna diz o que procurar no capítulo, porque capítulo inteiro raramente é a resposta: quase sempre é uma seção, uma figura ou uma tabela.

Não é preciso ler tudo. Para quem vai construir, o caminho mais curto é a leitura da fase em que está, na semana em que está nela. Para quem só quer entender o projeto, os quatro capítulos que mais explicam o desenho são o 2 e o 7 do *Fundamentals of Data Engineering*, o 7 do *Designing Data-Intensive Applications* e o 4 do *Data Quality Fundamentals*.

## 2. As obras

| nome curto | obra | autores | no acervo |
|---|---|---|---|
| **DDIA** | Designing Data-Intensive Applications | Martin Kleppmann | Sim, `livro_01` |
| **FoDE** | Fundamentals of Data Engineering | Joe Reis, Matt Housley | Sim, `livro_02` |
| **DEDP** | Data Engineering Design Patterns | Bartosz Konieczny | Sim, `livro_03` |
| **DQF** | Data Quality Fundamentals | Barr Moses, Lior Gavish, Molly Vorwerck | Sim, `livro_04` |
| **Spark** | Spark: The Definitive Guide | Bill Chambers, Matei Zaharia | Sim, `livro_05` |
| **AWS** | Data Engineering with AWS, 2ª ed. | Gareth Eagar | Sim, `livro_07` |
| **DMLS** | Designing Machine Learning Systems | Chip Huyen | Sim, `livro_08` |
| **PracStat** | Practical Statistics for Data Scientists | Peter Bruce, Andrew Bruce | Sim, `livro_10` |
| **Tukey** | Exploratory Data Analysis | John W. Tukey | Sim, `livro_11` |
| **Storytelling** | Storytelling com Dados | Cole Nussbaumer Knaflic | Sim, `negocio_livro_02` |
| **Kahneman** | Rápido e Devagar: Duas Formas de Pensar | Daniel Kahneman | Sim, `negocio_livro_01` (capítulos citados de memória: o arquivo não tem sumário navegável) |
| **Foca Linux** | Guia Foca GNU/Linux (iniciante ao avançado, mais o volume de segurança) | Gleydson Mazioli | Sim, `material_00` a `material_04` (sem sumário navegável) |
| **Kimball** | The Data Warehouse Toolkit, 3ª ed. | Ralph Kimball, Margy Ross | **Não** |
| **Karwin** | SQL Antipatterns, 2ª ed. | Bill Karwin | **Não** |
| **Okken** | Python Testing with pytest, 2ª ed. | Brian Okken | **Não** |
| **McKinney** | Python for Data Analysis, 3ª ed. | Wes McKinney | **Não** (a 3ª edição é lida de graça no site do autor) |
| **Petrella** | Fundamentals of Data Observability | Andy Petrella | **Não** |

As obras fora do acervo estão na lista de compras da Neviah, com prioridade; a lista completa, com as demais que o portfólio pede (séries temporais, interpretabilidade, LLM), fica fora deste repositório.

## 3. Fases 0 e 1 · abertura, entendimento e modelagem

Antes de qualquer código, o projeto leu o caso, escolheu a pilha e desenhou o pipeline. É a fase em que mais se decide e menos se digita, e a leitura certa aqui evita refazer as outras oito.

| card | o que se construiu | leitura | o que procurar lá |
|---|---|---|---|
| 0.5 | as decisões de pilha (MySQL na réplica, Postgres no warehouse, Dagster, SeaweedFS, DuckDB, Grafana, Gitflow), cada uma num ADR | FoDE cap. 4, *Choosing Technologies Across the Data Engineering Lifecycle* · acervo | as seções *Cost Optimization and Business Value*, *Immutable Versus Transitory Technologies* e *Build Versus Buy*: é o roteiro de perguntas que cada ADR responde |
| 1.2 | `docs/01`, o negócio da Fictalent: como um pedido de vaga vira pessoa alocada e receita | FoDE cap. 1 e 2 · acervo | no cap. 2, *What Is the Data Engineering Lifecycle?* e os *undercurrents* (segurança, gestão de dados, DataOps, orquestração): o pipeline foi desenhado etapa a etapa sobre esse ciclo |
| 1.3 | `docs/02`, os dados em 10 módulos e o que esperar da qualidade de cada um | FoDE cap. 5, *Data Generation in Source Systems* · acervo | *Source Systems: Main Ideas* e *Source System Practical Details*: o que perguntar sobre um sistema de origem (CRUD, carimbos, exclusões, esquema) é exatamente o roteiro das cinco perguntas do modelo relacional |
| 1.4 | `docs/03`, a arquitetura em camadas (réplica, bronze, silver, gold, warehouse, API, painéis) | FoDE cap. 3, *Designing Good Data Architecture* · acervo; DQF cap. 2, *Assembling the Building Blocks of a Reliable Data System* · acervo; AWS cap. 2, *Data Management Architectures for Analytics* · acervo | no FoDE, *Principles of Good Data Architecture* e *Major Architecture Concepts*; no DQF, *Data Warehouses Versus Data Lakes* e *What About the Data Lakehouse?*; no AWS, a evolução warehouse → lake → lakehouse, que é a história que o desenho deste projeto resume |
| 1.4 (ADR-0001) | a réplica do cliente como fonte, nunca o produtivo | DDIA cap. 5, *Replication* · acervo | *Leaders and Followers* e *Problems with Replication Lag*: a réplica atrasa, e o pipeline foi desenhado sabendo disso (a marca d'água da fase 5 é o relógio da réplica, não o do pipeline) |
| 1.6 | o modelo relacional de 75 tabelas com a resposta padrão às cinco perguntas por tabela | DDIA cap. 2, *Data Models and Query Languages* · acervo; Karwin, parte I, *Logical Database Design Antipatterns* · fora do acervo | no DDIA, a comparação relacional × documento explica por que a réplica é relacional e o lake é colunar; no Karwin, *Keyless Entry* (chave estrangeira que não existe) e *ID Required* são os antipadrões que o modelo evitou de propósito |

## 4. Fase 2 · fundação segura (v0.2.0)

A fase que sobe a plataforma e prova, por teste, que o dado pessoal está protegido antes de existir uma linha de dado. A leitura aqui é de segurança e de operação, não de análise.

| card | o que se construiu | leitura | o que procurar lá |
|---|---|---|---|
| 2.1 | `compose.yaml` com 7 serviços, healthcheck e ordem de dependência, portas só em localhost | FoDE cap. 3, seção *Examples and Types of Data Architecture* · acervo; Foca Linux, volume intermediário · acervo | no FoDE, o que é uma arquitetura modular e por que cada serviço é um container; no Foca, redes, portas e permissões de arquivo, que é o que o Compose está configurando por baixo |
| 2.2 e 2.7 | a DDL comentada com etiqueta LGPD por coluna, e o dicionário de dados gerado da `information_schema` | DQF cap. 2, *Designing a Data Catalog* e *Building a Data Catalog* · acervo; AWS cap. 4, *Data Governance, Security, and Cataloging* · acervo | no DQF, o catálogo como produto gerado, não digitado; no AWS, *Business and technical data catalogs* e *Data security, access, and privacy*: a etiqueta por coluna é o que o Lake Formation faz por permissão |
| 2.3 | a trilha de exclusões por gatilho `BEFORE DELETE` gerado da DDL | DDIA cap. 11, *Stream Processing* · acervo; DEDP cap. 7, *Data Security Design Patterns* · acervo | no DDIA, *Change Data Capture* e *Event Sourcing*: a trilha é um CDC de exclusões feito à mão; no DEDP, o padrão de remoção de dado (*data removal*) e o que ele exige da trilha |
| 2.4 | DCL por função (`pipeline`, `relatorios_cliente`, `replicador`), com `GRANT` coluna a coluna gerado das etiquetas | FoDE cap. 10, *Security and Privacy* · acervo; DEDP cap. 7 · acervo | no FoDE, *Technology*, o princípio do menor privilégio e a separação entre quem lê e quem escreve; no DEDP, os padrões de controle de acesso |
| 2.5 | cifra em repouso da réplica inteira (tablespace, redo, undo, binlog) com keyring próprio, provada no disco por teste | FoDE cap. 10 · acervo; DEDP cap. 7, padrões de proteção de dado · acervo | *encryption at rest* e onde a chave mora: o ADR-0002 explica por que a cifra é por tablespace e não por coluna, e o capítulo dá o vocabulário |
| 2.8 | CI em três trilhos (qualidade, réplica provada no runner, segurança) e o espelho local `esteira.sh` | FoDE cap. 2, o *undercurrent* DataOps · acervo; Okken cap. 2 a 5 · fora do acervo | no FoDE, automação, observabilidade e resposta a incidente como parte do ciclo; no Okken, funções de teste, fixtures e parametrização: a suíte do projeto usa as três desde o primeiro card |
| 2.9 | `docs/05`, o modelo de ameaça camada a camada e a LGPD princípio por princípio | FoDE cap. 10, *People* e *Processes* · acervo; material de cibersegurança do acervo (sem sumário navegável) | o modelo de ameaça é um exercício de *processes*: para cada camada, quem ataca, o que ganha, o que impede; a lei entra na seção 10 deste documento |

## 5. Fase 3 · orquestração e observabilidade base (v0.3.0)

A fase em que a plataforma passa a se explicar sozinha: o Dagster orquestra, o log é estruturado, a métrica vai para o warehouse e o Grafana mostra.

| card | o que se construiu | leitura | o que procurar lá |
|---|---|---|---|
| 3.1 | o projeto Dagster: recursos por ambiente, convenções de camada e chave, partições diária e anual, job `verificar_plataforma` | FoDE cap. 2, o *undercurrent* orquestração · acervo; DEDP cap. 6, *Data Flow Design Patterns* · acervo; AWS cap. 10, *Orchestrating the Data Pipeline* · acervo | no DEDP, os padrões de sequência e de *fan-in*, que é como os 76 assets da bronze dependem da réplica; no AWS, *Understanding the core concepts for pipeline orchestration* (DAG, dependência, retentativa), que vale para qualquer orquestrador |
| 3.2 | logs em JSON com `run_id` em todo evento | DQF cap. 4, *Monitoring and Anomaly Detection for Your Data Pipelines* · acervo; DEDP cap. 10, *Data Observability Design Patterns* · acervo | no DQF, *Investigating a Data Anomaly*: investigar exige seguir uma execução de ponta a ponta, e o `run_id` é o fio; no DEDP, os padrões de detector e de observador de dataset |
| 3.3 | métricas de execução no warehouse (`observabilidade.execucao` e `execucao_passo`) por sensores | DQF cap. 4, seções *Monitoring for Freshness* e *Building Monitors for Schema and Lineage* · acervo; Petrella · fora do acervo | frescor, volume e duração como as três métricas mínimas de um pipeline; o Petrella formaliza o que o DQF apresenta |
| 3.4 | Grafana como código: painel de execuções, frescor e falhas, duas regras de alerta | DQF cap. 5, *How to Set SLAs, SLOs, and SLIs for Your Data* · acervo; Storytelling cap. 2 e 3 · acervo | no DQF, os dois alertas do projeto (falha em 15 min; sem sucesso há 26 h) são SLOs; no Storytelling, *a escolha de um visual eficaz* e *a saturação é sua inimiga*: um painel de operação é um painel, e as mesmas regras valem |
| 3.5 | `saude.sh` em duas fases, com a prova ponta a ponta de cada garantia | DDIA cap. 1, *Reliable, Scalable, and Maintainable Applications* · acervo | *Reliability* e *Maintainability*: o healthcheck é a definição operacional de "funciona", e o capítulo dá o critério para decidir o que entra nele |

## 6. Fase 4 · dado sintético (v0.4.0)

A fase que fabrica a base da Fictalent (8,4 milhões de linhas, 2018 a 2026) contra um contrato escrito antes: a régua. É a fase mais estatística do projeto, e a leitura acompanha.

| card | o que se construiu | leitura | o que procurar lá |
|---|---|---|---|
| 4.1 | o índice sazonal por mês derivado dos microdados do Novo CAGED | Tukey cap. 7, *Smoothing Sequences* · acervo; Tukey cap. 10 e 11, *Two-Way Analyses* · acervo | a análise linha-mais-coluna (mês × ano) é o jeito de Tukey separar o sazonal do tendencial, e é a conta que o índice faz |
| 4.2 | o cliente HTTP com timeout, retry com recuo exponencial e limite de taxa (ADR-0010) | DDIA cap. 8, *The Trouble with Distributed Systems* · acervo; DEDP cap. 3, *Error Management Design Patterns* · acervo | no DDIA, *Unreliable Networks* e *Timeouts and Unbounded Delays*: o motivo de todo retry ter recuo e limite; no DEDP, os padrões de retentativa e de dado tardio |
| 4.3 | a régua de validação antes do gerador: 165 checks em seis famílias, com banda, laudo e veredito (ADR-0006) | DQF cap. 3, *Alerting and Testing* · acervo; DEDP cap. 9, *Data Quality Design Patterns* · acervo; PracStat cap. 2 · acervo | no DQF, o teste unitário de dado (dbt, Great Expectations) é o parente da régua; no DEDP, *audit-write-audit-publish*, que é o aceite por etapa; no PracStat, *Confidence Intervals* e *Long-Tailed Distributions* explicam por que a banda tem tolerância e por que a média engana |
| 4.4 a 4.9 | o gerador determinístico em seis etapas: cadastro, carteira, funil e pessoas, ponto e folha, financeiro, conformidade | PracStat cap. 2, *Data and Sampling Distributions* · acervo; DMLS cap. 4, *Training Data*, seção de amostragem · acervo; Kahneman, parte I · acervo | as distribuições dos sorteios (binomial para "aconteceu ou não", Poisson para "quantas vezes", cauda longa para prazos) estão no PracStat; a amostragem sem viés está no DMLS; e o Kahneman explica por que uma base que "parece plausível" engana o próprio autor, o que justificou o contrato escrito antes |
| 4.10 | o aceite: a base inteira contra a régua inteira, medidas e laudo versionados | DEDP cap. 9, padrão *audit-write-audit-publish* · acervo; PracStat cap. 3, seção *Multiple Testing* · acervo | com 165 checks, algum passa raspando por acaso; o capítulo 3 é a trava contra ler ruído como achado, e o `docs/06` §5 é a aplicação |
| 4.13 | o rito de uma versão (Gitflow, PR, tag, release, back-merge uma vez só) | FoDE cap. 2, DataOps, e o ADR-0008 · acervo | versionamento e automação como parte do ciclo de vida; o rito em si está no `docs/08` §8 |

## 7. Fase 5 · ingestão (v0.5.0)

A fase em que o dado entra pelas três portas do caso (réplica, API, arquivo) e a bronze passa a existir como espelho fiel em parquet. É a fase mais "engenharia" do projeto, e é a que mais capítulo tem.

| card | o que se construiu | leitura | o que procurar lá |
|---|---|---|---|
| 5.1 | o backfill réplica → bronze: esquema declarado do `information_schema`, cursor de streaming, parquet zstd por ano, contagem conferida em foto consistente | FoDE cap. 7, *Ingestion*, seção *Batch Ingestion Considerations* · acervo; FoDE cap. 6, *Storage* · acervo; FoDE apêndice A, *Serialization and Compression* · acervo; DDIA cap. 3, *Storage and Retrieval* · acervo; DEDP cap. 2 e 8 · acervo | no cap. 7, *snapshot or differential extraction* e *file-based export*; no cap. 6, *object storage* e *data lake*; no apêndice A, *Columnar Serialization* (parquet) e *Compression* (zstd); no DDIA, *Column-Oriented Storage* explica por que 1,5 GB viram 162 MB; no DEDP, o padrão *full load* (cap. 2) e o de particionamento (cap. 8), que decide "partição por ano de `criado_em`" |
| 5.2 | a carga incremental por marca d'água, com sobreposição de uma hora, foto renovada por tabela e merge por id (ADR-0011) | DDIA cap. 7, *Transactions* · acervo; DDIA cap. 11, *Stream Processing* · acervo; DEDP cap. 2, *incremental load* e cap. 4, *Idempotency Design Patterns* · acervo; AWS cap. 6, *Ingesting data from a relational database* · acervo | no cap. 7 do DDIA, *Snapshot Isolation and Repeatable Read*: é a foto presa que escondeu um UPDATE e virou a regra "nova foto por tabela"; no cap. 11, *Change Data Capture* contra a marca d'água, a comparação do ADR-0011; no DEDP, o padrão *merger* (upsert) e o *transactional writer*; no AWS, o DMS como o CDC de mercado que o projeto decidiu não usar ainda |
| 5.3 | exclusões como marcação (`excluido_em`), a trilha como 76ª tabela da bronze | DDIA cap. 11, *Event Sourcing* e *State, Streams, and Immutability* · acervo; DEDP cap. 7, padrão de remoção de dado · acervo | a bronze imutável que marca em vez de apagar é a ideia de *immutability* do DDIA aplicada a uma tabela; o DEDP dá o padrão do direito ao esquecimento, que a fase 6 aplica na silver |
| 5.4 | planilhas com pandera: preparar e validar separados, esquema estrito, total conferido contra o que a gerente fechou | DQF cap. 3, *Schema Checking and Type Coercion* e *Syntactic Versus Semantic Ambiguity in Data* · acervo; DEDP cap. 9, padrão de compatibilidade de esquema · acervo; McKinney cap. 7, *Data Cleaning and Preparation* · fora do acervo | o DQF descreve exatamente o que o `preparar` faz (coerção de tipo) e o que o `validar` recusa (ambiguidade semântica); o McKinney é o manual do pandas para a parte de limpeza |
| 5.5 | os dias correntes: a réplica volta a se mexer, um dia por vez, idempotente | DEDP cap. 4, *Idempotency Design Patterns* · acervo; DDIA cap. 7, seção *Atomicity* · acervo | simular o mesmo dia duas vezes não pode fazer nada: é o padrão de escrita idempotente, e a transação única é a atomicidade do DDIA |
| 5.6 | `docs/11`, a ingestão explicada com as três armadilhas reais | FoDE cap. 7, *Key Engineering Considerations for the Ingestion Phase* · acervo | a lista de perguntas do capítulo (bounded ou unbounded, frequência, síncrono ou não, serialização, confiabilidade) é o esqueleto do documento |

## 8. Fase 6 · lake (v0.6.0, em construção)

A fase em que a bronze é auditada às cegas, o catálogo de achados é aprovado e a silver nasce com prestação de contas. As linhas dos cards ainda não construídos são plano e serão confirmadas quando cada card fechar.

| card | o que se constrói | leitura | o que procurar lá |
|---|---|---|---|
| 6.1 | DuckDB sobre a bronze: 79 views com os nomes da réplica, `httpfs` medido contra `fsspec`, job `conferir_bronze` e o check C-06 da régua (conservação réplica → bronze) | FoDE cap. 8, *Queries, Modeling, and Transformation*, seção *Queries* · acervo; DQF cap. 4, seção *Monitoring for Freshness* e o pilar volume · acervo; DEDP cap. 10, padrão de observador de dataset · acervo | no FoDE, *Query Optimizer*, *Improving Query Performance* e a diferença entre view e tabela materializada: a decisão "views cruas" está aí; no DQF, a contagem de linhas entre origem e destino como o pilar volume da observabilidade, que é o C-06 |
| 6.2 | a auditoria de qualidade às cegas: dez notebooks, um por domínio, com o esquema e o entendimento do negócio como únicas referências, e as declarações do cliente como hipóteses | PracStat cap. 1, *Exploratory Data Analysis* · acervo; PracStat cap. 3, seção *Multiple Testing* · acervo; Tukey cap. 2, *Schematic Summaries* · acervo; DQF cap. 3, *Schema Checking and Type Coercion* · acervo; Kahneman cap. 7, a máquina de tirar conclusões precipitadas · acervo; Karwin, parte III, *Query Antipatterns* · fora do acervo | no PracStat, as estimativas de localização e variabilidade que abrem cada perfil de coluna, e a trava contra ler ruído como achado quando se fazem centenas de testes; no Tukey, cercas e valores externos; no DQF, a coerção de tipo é o que os dois defeitos de ingestão achados pela auditoria violavam; no Kahneman, o motivo de a auditoria ser às cegas (quem sabe o que foi plantado vê o que espera); no Karwin, *Fear of the Unknown* (os nulos que são regra e os que são falha) |
| 6.3 (plano) | o catálogo de achados com regras propostas, aprovado antes de transformar | DQF cap. 6, *Fixing Data Quality Issues at Scale*, seção *Root Cause Analysis* · acervo; DQF cap. 8, *Treating Your "Data" Like a Product* · acervo | achado sem causa não vira regra; e a regra aprovada por quem conhece o negócio é a versão de "dono do dado" do capítulo 8 |
| 6.4 (plano) | a silver com prestação de contas auto-reprovável | DEDP cap. 9, padrões de reforço de qualidade · acervo; DQF cap. 3, *Ensuring Data Quality During Transformation* · acervo; FoDE cap. 8, seção *Transformations* · acervo; McKinney cap. 7 e 10 · fora do acervo | a silver que reprova a si mesma é o *audit-write-audit-publish* do DEDP com a conta feita dentro do job; o FoDE separa transformação em lote de virtualizada, e a silver é a primeira |
| 6.5 (plano) | pseudonimização na silver e o job de retenção e descarte | DEDP cap. 7, padrões de proteção de dado e de remoção · acervo; DEDP cap. 8, seção sobre ciclo de vida do dado · acervo; FoDE cap. 10 · acervo | pseudonimizar não é anonimizar (a chave existe, e mora em outro lugar); a retenção é uma política, não um script, e o padrão de ciclo de vida do cap. 8 diz onde ela se declara |

## 9. Fases 7 a 9 e o previsto (planejado)

Estas fases ainda não foram construídas. A leitura abaixo é a que o plano prevê, e cada linha será confirmada ou corrigida quando o card fechar, com data, como a régua faz com as bandas.

| fase · card | o que se planeja | leitura | o que procurar lá |
|---|---|---|---|
| 7.1 e 7.2 | matriz de barramento e a gold: dimensões conformadas e fatos por módulo | Kimball cap. 1, 2 e 4 · fora do acervo; FoDE cap. 8, seção *Data Modeling* · acervo | no Kimball, o *bus matrix* e as dimensões conformadas (cap. 4, o caso de estoque, é onde o conceito aparece inteiro); o cap. 9, *Human Resources Management*, é o caso mais próximo da Fictalent; enquanto o Kimball não estiver no acervo, o FoDE resume Kimball, Inmon e Data Vault e basta para começar |
| 7.3 | SQL analítico com funções de janela explícitas e comentadas | Spark cap. 7, *Aggregations*, seção *Window Functions* · acervo; Karwin, parte III, *Query Antipatterns* · fora do acervo | o Spark explica janela com a mesma semântica do SQL padrão que o DuckDB usa; o Karwin lista o que não fazer numa consulta analítica (*Spaghetti Query*, *Implicit Columns*) |
| 7.4 | a régua da gold: conservação, integridade de chaves, coerência com as bandas | DEDP cap. 9 · acervo; DQF cap. 7, *Building End-to-End Lineage* · acervo | a conservação camada a camada é a linhagem em números; o DQF mostra o que uma linhagem de campo precisa guardar |
| 7.5 a 7.8 | o warehouse Postgres: DDL dimensional, carga por partição, DCL por área, índices medidos por plano de execução, RLS por filial | DDIA cap. 3, seção *Transaction Processing or Analytics?* · acervo; AWS cap. 9, *What not to do: anti-patterns for a data warehouse* · acervo; FoDE cap. 9, *Serving Data for Analytics* · acervo | o DDIA explica por que um banco de linhas serve como warehouse neste volume; o AWS lista os erros clássicos de warehouse; o FoDE trata do que servir e para quem |
| 8.1 e 8.2 | a API dos indicadores (FastAPI) com token e testes, incluindo acesso negado | FoDE cap. 9, seção *Ways to Serve Data* · acervo; DDIA cap. 4, *Encoding and Evolution* · acervo; Okken cap. 6 e 7 · fora do acervo | no DDIA, *Dataflow Through Services: REST and RPC* e compatibilidade de versões de contrato (`/v1`); no Okken, marcadores e estratégia de teste para uma API |
| 8.3 e 8.4 | consultas de auditoria e backup com restauração testada | FoDE cap. 10, seção *Processes* · acervo; DDIA cap. 5 · acervo | backup que nunca foi restaurado não é backup: o capítulo de segurança do FoDE diz isso em outras palavras, e o DDIA explica o que uma restauração precisa reconstruir |
| 9.3 a 9.5 | os painéis: web, Power BI e Tableau Public | Storytelling cap. 1 a 6 · acervo; DQF cap. 8, *Democratizing Data Quality* · acervo | contexto, visual, saturação, atenção, design e a dissecagem de modelos: os seis capítulos são o manual de cada tela; o DQF diz o que o consumidor precisa saber sobre a confiabilidade do que vê |
| P.2 | PySpark sobre a fato de maior volume, com comparativo medido contra DuckDB | Spark cap. 1, 2, 4 e 9 · acervo; DDIA cap. 10, *Batch Processing* · acervo | o Spark responde "quando o cluster compensa"; o DDIA cap. 10 explica MapReduce e o que veio depois, que é o contexto do comparativo |
| P.3 | MLflow com modelo de risco de desistência nos primeiros 90 dias | DMLS cap. 4 a 8 · acervo; PracStat cap. 4 a 6 · acervo; `livro_09` (Feature Engineering) e `livro_06` (Hands-On ML) · acervo | dado de treino, features, avaliação offline, serviço e desvio de distribuição, na ordem em que o DMLS apresenta |

## 10. Fora dos livros: documentação oficial e a lei

Parte do que o projeto usa não está em livro nenhum, ou está melhor na fonte. Tudo abaixo é gratuito.

| assunto | fonte | onde se usa |
|---|---|---|
| LGPD | Lei nº 13.709/2018, texto no Planalto: art. 6º (princípios), art. 7º (bases legais), art. 13 §4º (pseudonimização), art. 15 e 16 (término do tratamento e eliminação), art. 46 (segurança), art. 48 (comunicação de incidente) | `docs/05` §4 e §6, cards 2.2, 2.4, 2.7, 6.5 |
| MySQL 8 | manual de referência: *InnoDB Data-at-Rest Encryption*, *Keyring Component*, `START TRANSACTION WITH CONSISTENT SNAPSHOT`, *Transaction Isolation Levels*, `INFORMATION_SCHEMA` | cards 2.5, 2.7, 5.1, 5.2 |
| Dagster | documentação: *Software-defined assets*, *Partitions*, *Schedules and sensors*, *Resources*, *Run status sensors* | fases 3 e 5 |
| DuckDB | documentação: `read_parquet`, extensão `httpfs` e a configuração S3, `extension_directory`, `union_by_name` | card 6.1 |
| pandera | documentação: *DataFrameSchema*, *Checks*, *Lazy validation* | card 5.4 |
| Apache Parquet | especificação do formato e a documentação do PyArrow sobre partição por diretório (`ano=`) e compressão | card 5.1 |
| SeaweedFS | documentação da API S3 e do estilo de URL por caminho (*path style*) | ADR-0004, card 6.1 |
| Gitflow, Keep a Changelog, SemVer | o artigo original de Vincent Driessen (2010), keepachangelog.com, semver.org | ADR-0008, `docs/08` §8, `CHANGELOG.md` |
| Novo CAGED, IBGE, BrasilAPI | as páginas de metadados de cada fonte, citadas em `dados/publicos` com o `fonte.json` de cada tabela | cards 4.1 e 4.2 |

## 11. Como a lista cresce

Toda entrega que cita bibliografia cita capítulo, e a citação entra aqui na linha do card, no mesmo PR. Título citado que não esteja na tabela da seção 2 é acrescentado na hora, com a marca do acervo. Quando um card planejado fecha, a linha dele sai da seção 9 e entra na seção da fase, confirmada ou corrigida. Obra adquirida muda de "Não" para "Sim" com o nome do arquivo. A lista não cresce por assunto interessante: cresce por capítulo que sustentou uma decisão registrada.

---

[Início](#topo)
