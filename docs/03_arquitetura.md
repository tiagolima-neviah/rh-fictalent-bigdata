<a id="topo"></a>

# Arquitetura · do banco de origem ao painel

<!-- nav:start -->
[Home](../README.md) | [← Entendimento dos Dados](02_entendimento_dados.md) | [Manual de Operação →](08_manual_de_operacao.md)
<!-- nav:end -->

> Como este pipeline é montado, peça por peça, com a ferramenta de cada etapa e o **porquê** de cada escolha. Documento vivo: cada etapa que entra atualiza a sua linha com o que foi medido de verdade; o que ainda não existe aparece como **previsto**, nunca como entregue. Números sem medição não entram aqui.

## 1. O pipeline inteiro, etapa por etapa

```
═══════════════════════════════════════════════════════════════════════════════
 CAMADA 0 · INFRAESTRUTURA                                  (tudo roda em Docker)
═══════════════════════════════════════════════════════════════════════════════
  Ubuntu (WSL2) · Docker Compose · Python 3.12 + uv · GitHub Actions (CI)
  Git com Gitflow: feature → develop → release → main, tags SemVer

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 1 · ORIGEM: o sistema que a empresa não tem                (simulado)
═══════════════════════════════════════════════════════════════════════════════
  [Postgres 16]  db_fictalent · 10 schemas · 75 tabelas
     ├─ gatilhos: atualizado_em + trilha de exclusões          (base do incremental)
     ├─ DCL: papéis por perfil (GRANT/REVOKE) com teste de bloqueio
     ├─ RLS: cada filial enxerga só as próprias linhas         (autoatendimento)
     └─ pgcrypto: CPF e dados sensíveis cifrados em repouso    (LGPD)
  [Python]       gerador determinístico (semente fixa), 6 etapas, 2018 a 2026
  [Python]       régua de validação: bandas da história, reprovou regenera

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 2 · INGESTÃO: três naturezas de fonte
═══════════════════════════════════════════════════════════════════════════════
  2a relacional ─ [Python + ADBC]  backfill desde 2018 + incremental diário
                                   (marca d'água por tabela, exclusão lógica)
  2b API REST   ─ [Python + httpx] municípios (IBGE) e feriados (BrasilAPI)
                                   paginação, retry, limite de taxa
  2c arquivo    ─ [pandas + pandera] consolidado gerencial em Excel e
                                   índices sazonais do Novo CAGED em CSV,
                                   ambos com esquema declarado
        ▼
  [Postgres 16]  stg_fictalent · espelho + colunas de linhagem + marca d'água

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 3 · ORQUESTRAÇÃO                              (rege todas as camadas)
═══════════════════════════════════════════════════════════════════════════════
  [Dagster]  assets de cada tabela e camada, dependências desenhadas,
             partições por dia e por ano, agendamento diário, sensores,
             retry, backfill pela interface, histórico de cada execução
             (webserver + daemon em container, metadados no Postgres)

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 4 · LAKE                                  (parquet, storage abstraído)
═══════════════════════════════════════════════════════════════════════════════
  [SeaweedFS]  S3 em container · [fsspec] mesmo código em file:// ou s3://
  BRONZE  ─ [DuckDB]  espelho fiel do staging, linhagem, conferência de contagem
  QUALIDADE [pandera + régua + Jupyter]  auditoria por domínio, catálogo de achados
  SILVER  ─ [DuckDB]  regras aprovadas, prestação de contas auto-reprovável,
                      pseudonimização (o candidato vira chave, não nome)
  GOLD    ─ [DuckDB]  star schema Kimball, dimensões conformadas, fatos por
                      módulo particionadas por ano, funções de janela explícitas

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 5 · OLAP                                                  (warehouse)
═══════════════════════════════════════════════════════════════════════════════
  [MySQL 8]  dw_fictalent · schemas dim e fato · carga por partição idempotente
             DCL no warehouse: perfil de leitura por área, sem acesso a PII
             destino em nuvem compatível com MySQL (previsto, a medir)

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 6 · SERVIR
═══════════════════════════════════════════════════════════════════════════════
  [FastAPI]  API REST dos indicadores da gold: token, versão /v1, OpenAPI

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 7 · OBSERVABILIDADE, SEGURANÇA E AUDITORIA          (atravessa tudo)
═══════════════════════════════════════════════════════════════════════════════
  [healthcheck]  em cada container do Compose + endpoint /saude na API
  [logs JSON]    estruturados, com id de execução
  [Grafana]      painéis como código: execuções do Dagster, duração, linhas,
                 falhas e frescor dos dados; alertas (só observabilidade)
  [auditoria]    log de acesso e alteração na origem, trilha de exclusões,
                 histórico de runs, prestação de contas da silver
  [CI]           ruff · mypy · pytest · bandit · pip-audit · gitleaks · trivy
  [LGPD]         classificação de sensibilidade por coluna, retenção e
                 descarte com prazo executados por job do Dagster

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 8 · CONSUMO                              (projeto rh-fictalent-dashboard)
═══════════════════════════════════════════════════════════════════════════════
  Painel web  [FastAPI + HTMX + ECharts + DuckDB]  sobre o parquet da gold
  Power BI    sobre o MySQL, publicado na web
  Tableau     [Tableau Public] sobre extrato da gold, publicado na web

═══════════════════════════════════════════════════════════════════════════════
 PREVISTO · entram quando servirem ao caso, nunca para enfeitar a lista
═══════════════════════════════════════════════════════════════════════════════
  dbt na gold · PySpark com comparativo medido contra DuckDB ·
  MLflow com modelo de risco de desistência nos primeiros 90 dias
```

## 2. Onde cada ferramenta cabe, e por quê

| etapa | ferramenta | o que ela faz aqui | por que ela, e não outra |
|---|---|---|---|
| infraestrutura | **Docker Compose** | sobe os 8 serviços com um comando, com healthcheck, reinício automático e portas só em localhost | o analista roda o projeto inteiro na própria máquina |
| versionamento | **Git + Gitflow** | ramo por funcionalidade, `develop` de integração, versão marcada em `main` | é o fluxo que as equipes de dados maiores exigem |
| origem e staging | **Postgres 16** | o banco transacional e o espelho de onde o pipeline lê | banco livre mais usado em PME, com RLS e pgcrypto nativos |
| ingestão relacional | **ADBC** (Arrow) | traz o dado do Postgres em lotes colunares | não estoura a memória e preserva os tipos |
| ingestão de API | **httpx** | consome as APIs públicas do IBGE e da BrasilAPI | cliente HTTP moderno, com timeout e retry controlados |
| ingestão de arquivo | **pandas + pandera** | lê Excel e CSV contra um esquema declarado | arquivo sem esquema é o começo de todo relatório que não bate |
| orquestração | **Dagster** | decide quando e em que ordem cada etapa roda, repete o que falha, guarda o histórico | trabalha com **ativos de dado**, não só tarefas: a dependência entre tabelas vira desenho |
| storage | **SeaweedFS + fsspec** | um S3 dentro do Compose | o mesmo código vai para AWS, GCP ou disco local só trocando o endereço. O MinIO, escolha óbvia até 2025, deixou de publicar a imagem da edição comunitária; a última disponível não recebe atualização de segurança há um ano. O SeaweedFS é Apache 2.0, ativo e fala a mesma API S3 |
| transformação | **DuckDB** | SQL sobre parquet, sem servidor | rápido no laptop; o volume deste caso não justifica cluster |
| formato | **parquet** (zstd, partição por ano) | armazena cada camada | colunar, compacto, lido por qualquer ferramenta |
| qualidade | **pandera + régua própria** | valida esquema e bandas de negócio | pandera é a linguagem de mercado; a régua carrega a história |
| OLAP | **MySQL 8** | o warehouse que as ferramentas de BI consultam | o cenário do caso: o cliente já tem MySQL em casa e quer consumir o warehouse de lá, com as ferramentas que já usa. É o banco relacional mais presente em PME, e o repositório passa a mostrar Postgres e MySQL juntos |
| servir | **FastAPI** | API REST dos indicadores | tipagem, validação e documentação OpenAPI geradas do código |
| observabilidade | **Grafana** | painéis de execução, falha e frescor, com alerta | painel é arquivo versionado e existe plano gratuito na nuvem. Fica só na observabilidade: painel de negócio é papel do painel web, do Power BI e do Tableau, e duplicá-lo criaria uma quarta versão do mesmo número |
| segurança no CI | **bandit, pip-audit, gitleaks, trivy** | código, dependências, segredos e imagens | cada um olha um vetor diferente; juntos cobrem o básico de supply chain |

**Dagster e Airflow.** São os dois orquestradores mais pedidos no mercado. O Airflow organiza **tarefas**; o Dagster organiza **ativos** (a tabela, o arquivo, o modelo) e deduz a ordem a partir das dependências entre eles, o que casa com o jeito medallion de pensar. Quem aprende um lê o outro: um *asset* do Dagster corresponde a uma tarefa que produz um dado no Airflow, um *job* a uma DAG, um *schedule* a um `schedule_interval`.

## 3. Por que uma origem simulada, e o que ela representa

Num cliente real, a origem é o sistema dele. Aqui a origem é **um Postgres que o projeto cria e popula**, com o modelo relacional completo dos 10 módulos. Três motivos: o caso pede (a Fictalent tem quatro sistemas desconectados, e modelar o que ela deveria ter é o que permite mostrar o pipeline inteiro); ensina o contraste entre um banco **transacional normalizado** e um banco **analítico dimensional**, com as mesmas informações e desenhos opostos; e não expõe ninguém, porque nenhum dado real entra em etapa alguma.

**Origem e staging são bancos separados**, porque é a separação que torna a carga incremental honesta: o pipeline nunca lê a origem, exatamente como num cliente onde tocar a produção é proibido.

## 4. Backfill e carga incremental

**Backfill histórico (uma vez).** Traz tudo o que existe na origem desde 2018. É a resposta à pergunta do dono: não, ele não recomeça do zero. Sem backfill não existe comparação ano a ano, e sem ela não é possível responder por que a empresa perdeu contratos.

**Carga incremental (todo dia, agendada no Dagster).** Traz só o que mudou desde a última carga. Cada tabela da origem carrega `criado_em` e `atualizado_em` mantidos por gatilho, e o staging guarda, por tabela, a **marca d'água** da última carga. A carga seguinte pede apenas o que está acima dela.

**Exclusões.** Uma linha apagada na origem não tem `atualizado_em` para ser encontrada. Por isso a origem mantém uma **trilha de exclusões** alimentada por gatilho de `DELETE`, e a carga incremental aplica essas exclusões no staging como **marcação lógica**, nunca com apagamento físico: o dado apagado continua no histórico analítico, marcado e datado.

## 5. Segurança e LGPD por desenho

RH é o domínio do dado pessoal por excelência, e este projeto trata isso como requisito de arquitetura, não como apêndice.

- **Minimização.** Cada camada carrega só o que o indicador precisa. A gold não tem nome nem CPF.
- **Pseudonimização.** A partir da silver, pessoa é identificada por uma chave derivada, estável e irreversível sem o segredo, que fica fora do repositório.
- **Cifra em repouso.** Colunas sensíveis da origem são cifradas com `pgcrypto`.
- **Controle de acesso por perfil.** Papéis de banco com `GRANT` e `REVOKE` explícitos para sócio, gerente-geral, coordenação, assistente e financeiro, e **testes automatizados que provam o bloqueio**: o teste passa quando o acesso indevido falha.
- **Isolamento por filial.** Políticas de *row level security* fazem a assistente de Extrema enxergar só as linhas de Extrema, no próprio banco, sem depender da aplicação.
- **Trilha de auditoria.** Quem acessou e quem alterou o quê, com data.
- **Retenção e descarte.** Candidato não contratado tem prazo declarado de retenção, e um job do Dagster executa o descarte e registra o que foi descartado.
- **Classificação por coluna.** O dicionário de dados marca cada coluna como pública, interna, pessoal ou pessoal sensível.

O detalhe, com os comandos e os testes, fica no manual de segurança e LGPD (`docs/05`, versão v0.2.0).

## 6. Operação: como se liga, se verifica e se recupera

Todo serviço do Compose tem **healthcheck**, e a ordem de subida respeita as dependências (bancos antes do Dagster, Dagster antes da API). O [Manual de Operação](08_manual_de_operacao.md) já cobre subir, verificar, parar e recuperar a infraestrutura. Os manuais cobrem, com o comando exato de cada situação:

| manual | cobre |
|---|---|
| instalação e reprodução | do clone ao pipeline rodando, com requisitos e verificação final |
| operação | subir, parar, reiniciar um serviço ou todos, reprocessar um dia ou um ano |
| monitoramento e healthcheck | o que cada painel do Grafana mostra, o que é normal, o que é alerta |
| auditoria | onde está cada trilha e como consultar |
| backup e restauração | dos bancos e do lake, com teste de restauração |
| solução de problemas | as falhas conhecidas, o sintoma e o remédio |

## 7. Estado atual, etapa por etapa

| camada | situação |
|---|---|
| 0 · infraestrutura | Compose com 8 serviços e healthchecks, imagens com versão fixa, portas só em localhost, segredos obrigatórios via `.env` (v0.2.0, card 2.1) |
| 1 · origem | modelo relacional aprovado, DDL a iniciar |
| 2 · ingestão | a iniciar |
| 3 · orquestração | a iniciar |
| 4 · lake | a iniciar |
| 5 · OLAP | a iniciar |
| 6 · servir | a iniciar |
| 7 · observabilidade, segurança e auditoria | a iniciar |
| 8 · consumo | projeto separado, a iniciar |

## 8. O que este projeto deliberadamente não faz

Não usa processamento distribuído como motor principal: cerca de 8 milhões de linhas cabem num laptop, e cluster aqui ensinaria a resolver o problema errado (PySpark entra como comparativo medido, não como base). Não tem telas transacionais: isso é projeto futuro, e o modelo relacional já nasce preparado para ele. E não passou por auditoria de segurança independente, que é o motivo pelo qual, mesmo com as proteções acima, o aviso do README continua valendo.

---

[Início](#topo)
