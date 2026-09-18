<a id="topo"></a>

# Arquitetura · da réplica do sistema do cliente ao painel

<!-- nav:start -->
[Home](../README.md) | [← Entendimento dos Dados](02_entendimento_dados.md) | [Modelo de Dados →](04_modelo_dados_staging.md)
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
 CAMADA 1 · STAGING: a réplica do sistema do cliente                  (MySQL 8)
═══════════════════════════════════════════════════════════════════════════════
  O sistema produtivo do cliente fica FORA deste ambiente: a consultoria nunca
  o toca. O que existe aqui é a réplica autorizada, em ambiente apartado.
  [MySQL 8]  10 schemas · 75 tabelas · mapa de escopo documentado (seção 3)
     ├─ atualizado_em nativo e indexado + trilha de exclusões  (base do incremental)
     ├─ DCL: papéis por função (pipeline, relatórios sem PII, replicação)
     │       com GRANT gerado das etiquetas LGPD e teste de bloqueio
     └─ cifra em repouso: tablespaces, redo, undo e binlog,     (LGPD)
        chave mestra em keyring fora do repositório e dos dados
  [Python]   gerador determinístico (semente fixa), 6 etapas, 2018 a 2026:
             faz o papel do sistema do cliente e da replicação que chega dele
  [Python]   régua de validação: bandas da história, reprovou regenera

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 2 · INGESTÃO: três naturezas de fonte, todas desembocam na bronze
═══════════════════════════════════════════════════════════════════════════════
  2a relacional ─ [Python + Arrow] backfill desde 2018 + incremental diário
                                   a partir do MySQL (marca d'água por tabela,
                                   exclusão lógica)
  2b API REST   ─ [Python + httpx] municípios (IBGE) e feriados (BrasilAPI)
                                   timeout, retry com recuo, limite de taxa
  2c arquivo    ─ [pandas + pandera] consolidado gerencial em Excel e
                                   índices sazonais do Novo CAGED em CSV,
                                   ambos com esquema declarado

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
  BRONZE  ─ [DuckDB]  espelho fiel da réplica, linhagem, marca d'água por
                      tabela, conferência de contagem
  QUALIDADE [pandera + régua + Jupyter]  auditoria por domínio, catálogo de achados
  SILVER  ─ [DuckDB]  regras aprovadas, prestação de contas auto-reprovável,
                      pseudonimização (o candidato vira chave, não nome)
  GOLD    ─ [DuckDB]  star schema Kimball, dimensões conformadas, fatos por
                      módulo particionadas por ano, funções de janela explícitas

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 5 · OLAP                                                  (warehouse)
═══════════════════════════════════════════════════════════════════════════════
  [Postgres 16]  dw_fictalent · schemas dim e fato · carga por partição idempotente
                 DCL no warehouse: perfil de leitura por área, sem dado pessoal
                 RLS: cada filial enxerga só as próprias linhas
                 destino gratuito em nuvem Postgres (previsto, a medir)

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 6 · SERVIR
═══════════════════════════════════════════════════════════════════════════════
  [FastAPI]  API REST dos indicadores da gold: token, versão /v1, OpenAPI

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 7 · OBSERVABILIDADE, SEGURANÇA E AUDITORIA          (atravessa tudo)
═══════════════════════════════════════════════════════════════════════════════
  [healthcheck]  em cada container do Compose + scripts/saude.sh de ponta a ponta
                 (réplica, lake, warehouse, Dagster, Grafana) + endpoint /saude na API
  [logs JSON]    estruturados, com id de execução
  [Grafana]      painéis como código: execuções do Dagster, duração, linhas,
                 falhas e frescor dos dados; alertas (só observabilidade)
  [auditoria]    log de acesso e alteração na réplica, trilha de exclusões,
                 histórico de runs, prestação de contas da silver
  [CI]           ruff · mypy · pytest · bandit · pip-audit · gitleaks · trivy
  [LGPD]         classificação de sensibilidade por coluna, retenção e
                 descarte com prazo executados por job do Dagster

═══════════════════════════════════════════════════════════════════════════════
 CAMADA 8 · CONSUMO                              (projeto rh-fictalent-dashboard)
═══════════════════════════════════════════════════════════════════════════════
  Painel web  [FastAPI + HTMX + ECharts + DuckDB]  sobre o parquet da gold
  Power BI    sobre o warehouse Postgres, publicado na web
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
| infraestrutura | **Docker Compose** | sobe os 7 serviços e os 2 jobs de inicialização com um comando, com healthcheck, reinício automático e portas só em localhost | o analista roda o projeto inteiro na própria máquina |
| versionamento | **Git + Gitflow** | ramo por funcionalidade, `develop` de integração, versão marcada em `main` | é o fluxo que as equipes de dados maiores exigem |
| staging | **MySQL 8** | a réplica autorizada do sistema do cliente, de onde o pipeline lê | é o motor mais provável do sistema próprio de uma PME, e o que o mercado pede é saber **ingerir de** MySQL. Fecha a terceira técnica de carga incremental da série (Fictitur: coluna temporal; Fictoria: `rowversion`; Fictalent: a partir de MySQL). [ADR-0001](adr/0001-mysql-no-staging-postgres-no-olap.md) |
| ingestão relacional | **leitor com saída Arrow** (ADBC, se houver driver MySQL maduro; senão ConnectorX) | traz o dado do MySQL em lotes colunares | não estoura a memória e preserva os tipos. A escolha é medida e registrada em ADR na v0.5.0 |
| ingestão de API | **httpx** | consome as APIs públicas do IBGE e da BrasilAPI | cliente HTTP moderno, com timeout e retry controlados ([ADR-0010](adr/0010-httpx-ingestao-de-api.md)) |
| ingestão de arquivo | **pandas + pandera** | lê Excel e CSV contra um esquema declarado | arquivo sem esquema é o começo de todo relatório que não bate |
| orquestração | **Dagster** | decide quando e em que ordem cada etapa roda, repete o que falha, guarda o histórico | trabalha com **ativos de dado**, não só tarefas: a dependência entre tabelas vira desenho |
| storage | **SeaweedFS + fsspec** | um S3 dentro do Compose | o mesmo código vai para AWS, GCP ou disco local só trocando o endereço. O MinIO, escolha óbvia até 2025, deixou de publicar a imagem da edição comunitária; a última disponível não recebe atualização de segurança há um ano. O SeaweedFS é Apache 2.0, ativo e fala a mesma API S3 |
| transformação | **DuckDB** | SQL sobre parquet, sem servidor | rápido no laptop; o volume deste caso não justifica cluster |
| formato | **parquet** (zstd, partição por ano) | armazena cada camada | colunar, compacto, lido por qualquer ferramenta |
| qualidade | **pandera + régua própria** | valida esquema e bandas de negócio | pandera é a linguagem de mercado; a régua carrega a história |
| OLAP | **Postgres 16** | o warehouse que a API e as ferramentas de BI consultam | banco analítico de verdade para o volume do caso: *row level security* nativa, visão materializada, consulta paralela, schemas para separar `dim` e `fato`, e destino gratuito em nuvem já provado na série. [ADR-0001](adr/0001-mysql-no-staging-postgres-no-olap.md) |
| servir | **FastAPI** | API REST dos indicadores | tipagem, validação e documentação OpenAPI geradas do código |
| observabilidade | **Grafana** | painéis de execução, falha e frescor, com alerta | painel é arquivo versionado e existe plano gratuito na nuvem. Fica só na observabilidade: painel de negócio é papel do painel web, do Power BI e do Tableau, e duplicá-lo criaria uma quarta versão do mesmo número |
| segurança no CI | **bandit, pip-audit, gitleaks, trivy** | código, dependências, segredos e imagens | cada um olha um vetor diferente; juntos cobrem o básico de supply chain |

**Decisões registradas.** Cada tecnologia deste projeto tem um registro de decisão ligando-a a uma necessidade do caso, em [`docs/adr`](adr/README.md): bancos (0001), cifra (0002), Dagster (0003), SeaweedFS (0004), DuckDB (0005), pandera e régua (0006), Grafana (0007), Gitflow (0008) e FastAPI (0009). Se a única justificativa fosse "o mercado pede", a ferramenta iria para um laboratório separado, não para cá.

**Dagster e Airflow.** São os dois orquestradores mais pedidos no mercado. O Airflow organiza **tarefas**; o Dagster organiza **ativos** (a tabela, o arquivo, o modelo) e deduz a ordem a partir das dependências entre eles, o que casa com o jeito medallion de pensar. Quem aprende um lê o outro: um *asset* do Dagster corresponde a uma tarefa que produz um dado no Airflow, um *job* a uma DAG, um *schedule* a um `schedule_interval`.

## 3. Por que o staging é uma réplica, e o que ela representa

Num cliente real, o sistema produtivo é dele, e a consultoria **não o toca**: nenhuma consulta analítica roda no banco que emite a folha e fecha o caixa. O que a consultoria recebe é uma **réplica** em ambiente apartado, alimentada pela replicação que o cliente autoriza. Neste projeto, essa réplica é o staging: um MySQL 8 que o projeto cria e popula com o modelo relacional completo dos 10 módulos. Como a Fictalent é fictícia, o gerador faz o papel do sistema dela e da replicação: escreve na réplica como se fosse a carga diária chegando do cliente.

Três motivos para modelar a réplica inteira em vez de partir de planilhas: o caso pede (a Fictalent tem quatro sistemas desconectados, e modelar o que ela deveria ter é o que permite mostrar o pipeline inteiro); ensina o contraste entre um banco **transacional normalizado** e um banco **analítico dimensional**, com as mesmas informações e desenhos opostos; e não expõe ninguém, porque nenhum dado real entra em etapa alguma.

**Réplica parcial por pertinência.** A regra da casa é replicar **só os schemas e tabelas ligados à dor contratada**, nunca o banco inteiro: é menos volume, menos custo, menos superfície de ataque, e é a minimização de dados que a LGPD pede. Um cliente com 10 schemas e 650 tabelas que contrata projeção financeira e margem recebe no staging o schema financeiro e as tabelas dos outros schemas diretamente ligadas à movimentação financeira; recrutamento e seleção ficam de fora. Toda réplica exige, por isso, um **mapa de escopo**: o que entra e a que pergunta de negócio cada parte serve.

**O mapa de escopo deste caso.** A Fictalent contratou a resposta a uma pergunta que atravessa a empresa inteira (qual cliente dá margem e qual só dá trabalho), e a margem por posto nasce no funil, passa pela folha e termina no título a receber. Por isso o cliente autorizou a **réplica completa**, e o gestor de TI dele preferiu assim: a réplica passa a absorver toda a leitura analítica e desafoga o sistema produtivo por inteiro. Ele foi além: **nem os relatórios do próprio sistema batem no produtivo**. O produtivo fica só com o CRUD e os selects simples de tela; todo relatório com filtro e histórico é apontado para a réplica, trabalho dos desenvolvedores do cliente. A réplica tem, portanto, dois consumidores, o pipeline e os relatórios do sistema, e é por isso que o controle de acesso por perfil (seção 5) inclui um papel só de leitura para esses relatórios, sem as colunas sensíveis. O mapa, mesmo com tudo dentro, existe:

| schema | tabelas | a que pergunta serve |
|---|---|---|
| `cadastro` | 12 | as regras do jogo: filiais, cargos, postos, parâmetros (base de toda dimensão) |
| `comercial` | 8 | a carteira que gera receita: clientes, contratos e preço por posto |
| `ats` | 9 | o funil de colocação: quanto custa e quanto demora preencher uma vaga |
| `pessoas` | 8 | quem foi admitido, onde está e por que saiu: headcount e rotatividade |
| `ponto` | 5 | o dia a dia de quem está em campo: horas, faltas e extras (o que se fatura e o que se paga) |
| `folha` | 7 | o custo por cabeça: a outra metade da margem |
| `financeiro` | 10 | receita, títulos, inadimplência e impostos: a margem realizada |
| `treinamento` | 5 | turmas com validade: compliance e o custo de manter a habilitação |
| `sst` | 6 | saúde, segurança e compliance: exames, afastamentos e o custo de cada um |
| `seguranca` | 5 | quem pode ver o quê: perfis e trilha de auditoria |
| `meta` | 2 | infraestrutura da carga (trilha de exclusões); não é módulo de negócio |

## 4. Backfill e carga incremental

**Backfill histórico (uma vez).** Traz da réplica para a bronze tudo o que existe desde 2018. É a resposta à pergunta do dono: não, ele não recomeça do zero. Sem backfill não existe comparação ano a ano, e sem ela não é possível responder por que a empresa perdeu contratos.

**Carga incremental (todo dia, agendada no Dagster).** Traz só o que mudou desde a última carga. Cada tabela da réplica carrega `criado_em` e `atualizado_em` mantidos pelo próprio motor (`ON UPDATE`) e indexados, e o pipeline guarda, por tabela, a **marca d'água** da última carga. A carga seguinte pede apenas o que está acima dela.

**Exclusões.** Uma linha apagada no sistema do cliente some da réplica quando a replicação aplica o `DELETE`, e uma linha que sumiu não tem `atualizado_em` para ser encontrada. Por isso a réplica mantém uma **trilha de exclusões** alimentada por gatilho de `DELETE` (`meta.exclusao_auditoria`), e a carga incremental aplica essas exclusões na bronze como **marcação lógica**, nunca com apagamento físico: o dado apagado continua no histórico analítico, marcado e datado. Se a replicação do cliente for por binlog, a alternativa de ler as exclusões direto dele fica registrada em ADR quando a ingestão for construída (v0.5.0).

## 5. Segurança e LGPD por desenho

RH é o domínio do dado pessoal por excelência, e este projeto trata isso como requisito de arquitetura, não como apêndice.

- **Minimização.** Cada camada carrega só o que o indicador precisa, e a réplica só entra completa porque o cliente autorizou (seção 3). A gold não tem nome nem CPF.
- **Pseudonimização.** A partir da silver, pessoa é identificada por uma chave derivada, estável e irreversível sem o segredo, que fica fora do repositório.
- **Cifra em repouso.** Toda a réplica é cifrada pelo InnoDB (tablespaces, redo, undo e binlog), com a chave mestra num keyring fora do repositório e fora do diretório de dados, rotacionável. A escolha contra a cifra de coluna, e o custo medido, estão no [ADR-0002](adr/0002-cifra-em-repouso-tablespace.md); a prova de que o CPF não aparece em claro no disco é um teste.
- **Controle de acesso.** Na réplica, papéis de banco **por função** (pipeline só lê; relatórios do cliente leem sem dado pessoal, coluna a coluna, com o `GRANT` gerado das etiquetas LGPD; a replicação escreve o negócio e nada mais). No warehouse, papéis **por perfil de negócio** (sócio, gerente-geral, coordenação, assistente, financeiro) com isolamento por filial. Nos dois, **testes automatizados que provam o bloqueio**: o teste passa quando o acesso indevido falha.
- **Isolamento por filial.** Políticas de *row level security* no warehouse fazem a coordenadora de Extrema enxergar só as linhas de Extrema, no próprio banco, sem depender da aplicação.
- **Trilha de auditoria.** Quem acessou e quem alterou o quê, com data.
- **Retenção e descarte.** Candidato não contratado tem prazo declarado de retenção, e um job do Dagster executa o descarte e registra o que foi descartado.
- **Classificação por coluna.** O [dicionário de dados](dicionario/README.md), gerado da `information_schema`, marca cada coluna como pública, interna, pessoal ou pessoal sensível, a partir das etiquetas da DDL, e abre pelo inventário de dado pessoal.

O detalhe, com o modelo de ameaça, o comando de conferência de cada garantia e o que ainda não existe, está em [Segurança e LGPD](05_seguranca_e_lgpd.md).

## 6. Operação: como se liga, se verifica e se recupera

Todo serviço do Compose tem **healthcheck**, e a ordem de subida respeita as dependências (bancos antes do Dagster, Dagster antes da API). O [Manual de Operação](08_manual_de_operacao.md) já cobre subir, verificar, parar e recuperar a infraestrutura. Os manuais cobrem, com o comando exato de cada situação:

| manual | cobre |
|---|---|
| [instalação e reprodução](07_instalacao_e_reproducao.md) | do clone ao pipeline rodando, com requisitos e verificação final |
| [operação](08_manual_de_operacao.md) | subir, parar, reiniciar um serviço ou todos, reprocessar um dia ou um ano |
| [monitoramento e healthcheck](09_monitoramento_e_healthcheck.md) | o que cada painel do Grafana mostra, o que é normal, o que é alerta |
| auditoria | onde está cada trilha e como consultar |
| backup e restauração | dos bancos e do lake, com teste de restauração |
| solução de problemas | as falhas conhecidas, o sintoma e o remédio |

## 7. Estado atual, etapa por etapa

| camada | situação |
|---|---|
| 0 · infraestrutura | Compose com 7 serviços e healthchecks, imagens com versão fixa, portas só em localhost, segredos obrigatórios via `.env` (v0.2.0, cards 2.1 e 2.1.1) |
| 1 · staging (réplica) | MySQL 8 (ADR-0001) com a DDL dos 10 módulos aplicada: 75 tabelas de negócio mais a trilha de exclusões, comentário em toda tabela, chaves entre databases, etiqueta LGPD por coluna trilha de exclusões por gatilho gerado da DDL e papéis por função com GRANT gerado das etiquetas LGPD, provados por teste, cifra em repouso de tudo com keyring próprio e dicionário de dados gerado da `information_schema` ([Modelo de Dados](04_modelo_dados_staging.md), v0.2.0, cards 2.2 a 2.7); calibração do dado sintético iniciada: índice sazonal por mês, escopo e grupo CNAE derivado dos microdados do Novo CAGED, com a fonte, em `dados/publicos/caged` (v0.4.0, card 4.1); a régua de validação existe antes do gerador ([ADR-0006](adr/0006-pandera-e-regua.md)): 165 checks em seis famílias (escala, naturalidade, a história, sazonalidade contra o CAGED, coerência interna e sujeira na medida certa), com laudo aprovado, reprovado ou incompleto e a regra "reprovou, regenera" (`python -m rh_fictalent.validacao --contrato`, card 4.3) |
| 2 · ingestão | por API feita: um cliente HTTP com timeout, retry com recuo exponencial e limite de taxa ([ADR-0010](adr/0010-httpx-ingestao-de-api.md)) traz os municípios de SP e MG (IBGE) e os feriados nacionais (BrasilAPI) como assets do grupo `fontes`, gravados em parquet no lake, os feriados particionados por ano; as mesmas funções geram as tabelas versionadas em `dados/publicos` (v0.4.0, card 4.2); relacional e arquivo entram na v0.5.0 |
| 3 · orquestração | projeto Dagster com recursos (réplica, lake, warehouse) configurados pelo ambiente, convenções de camada, chave e partição, e o job `verificar_plataforma` que prova os três alcances de dentro do Dagster (v0.3.0, card 3.1); assets de dado entram com as versões seguintes |
| 4 · lake | a iniciar |
| 5 · OLAP | motor definido (Postgres 16, ADR-0001), modelo dimensional a iniciar |
| 6 · servir | a iniciar |
| 7 · observabilidade, segurança e auditoria | CI com três trilhos: qualidade, réplica provada no runner e segurança (bandit, pip-audit, gitleaks, trivy), espelhada em `scripts/esteira.sh` (v0.2.0, card 2.8); logs estruturados em JSON com id de execução em todo evento do Dagster (card 3.2) e métricas de execução gravadas no warehouse por sensor a cada fim de execução (`observabilidade.execucao` e `execucao_passo`, card 3.3) e Grafana como código lendo essas tabelas: painel de execuções, frescor e falhas mais duas regras de alerta (card 3.4), v0.3.0; auditoria a seguir |
| 8 · consumo | projeto separado, a iniciar |

## 8. O que este projeto deliberadamente não faz

Não usa processamento distribuído como motor principal: cerca de 8 milhões de linhas cabem num laptop, e cluster aqui ensinaria a resolver o problema errado (PySpark entra como comparativo medido, não como base). Não tem telas transacionais: isso é projeto futuro, e o modelo relacional já nasce preparado para ele. E não passou por auditoria de segurança independente, que é o motivo pelo qual, mesmo com as proteções acima, o aviso do README continua valendo.

---

[Início](#topo)
