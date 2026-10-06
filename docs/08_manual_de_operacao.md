<a id="topo"></a>

# Manual de Operação · subir, verificar, parar e recuperar

<!-- nav:start -->
[Home](../README.md) | [← Instalação e Reprodução](07_instalacao_e_reproducao.md) | [Monitoramento e Healthcheck →](09_monitoramento_e_healthcheck.md)
<!-- nav:end -->

> O manual de quem opera a plataforma no dia a dia. Todo comando aqui foi executado e conferido na versão em que a seção entrou. Rode todos a partir da **raiz do repositório**. A instalação do zero está em [Instalação e Reprodução](07_instalacao_e_reproducao.md); o que olhar e o que fazer quando algo acende, em [Monitoramento e Healthcheck](09_monitoramento_e_healthcheck.md). Reprocessamento por partição entra com o dado (v0.5.0).

## 1. O que roda, e onde

| serviço | o que é | endereço na sua máquina | publicado na rede? |
|---|---|---|---|
| `mysql-staging` | MySQL · a réplica autorizada do sistema do cliente, de onde o pipeline lê | `127.0.0.1:3316` | não |
| `pg-dw` | Postgres · warehouse dimensional | `127.0.0.1:5441` | não |
| `pg-dagster` | Postgres · metadados do Dagster | sem porta (só rede interna) | não |
| `s3` | SeaweedFS · lake compatível com S3 | `127.0.0.1:8333` | não |
| `s3-init` | job único · cria o bucket do lake e termina | sem porta | não |
| `keyring-init` | job único · prepara o volume da chave de cifra da réplica e termina | sem porta | não |
| `dagster-web` | Dagster · interface web | <http://127.0.0.1:3010> | não |
| `dagster-daemon` | Dagster · agendas, sensores e fila | sem porta | não |
| `grafana` | Grafana · monitoramento e alertas | <http://127.0.0.1:3011> | não |

Todas as portas escutam **apenas em 127.0.0.1**: outra máquina da rede não alcança nenhum serviço. As portas podem ser trocadas no `.env`.

## 2. Primeira subida

**1. Crie o `.env` com senhas geradas.** O compose se recusa a subir se qualquer senha obrigatória faltar. Gere cada senha com `openssl rand -hex 24` (só letras e números, para não quebrar nenhuma string de conexão):

```bash
cp .env.example .env
```

```bash
for v in STAGING_ROOT_PASSWORD PIPELINE_PASSWORD RELATORIOS_PASSWORD REPLICADOR_PASSWORD DAGSTER_PG_PASSWORD S3_SECRET_KEY DW_ADMIN_PASSWORD GRAFANA_ADMIN_PASSWORD GRAFANA_LEITOR_PASSWORD; do sed -i "s/^$v=.*/$v=$(openssl rand -hex 24)/" .env; done && sed -i "s/^S3_ACCESS_KEY=.*/S3_ACCESS_KEY=$(openssl rand -hex 12)/" .env
```

O segredo da pseudonimização da silver é mais longo e gerado à parte. O comando grava no `.env` sem mostrar o valor na tela, e serve também para um `.env` antigo que ainda não tem a linha (é o caso de quem vem da v0.5.0):

```bash
grep -q '^PSEUDONIMIZACAO_SEGREDO=troque' .env && sed -i "s/^PSEUDONIMIZACAO_SEGREDO=.*/PSEUDONIMIZACAO_SEGREDO=$(openssl rand -hex 32)/" .env; grep -q '^PSEUDONIMIZACAO_SEGREDO=' .env || printf 'PSEUDONIMIZACAO_SEGREDO=%s\n' "$(openssl rand -hex 32)" >> .env
```

Guarde o `.env` com o mesmo cuidado de sempre: a chave de cada pessoa na silver é o HMAC do documento com esse segredo. Perdê-lo não perde dado (a silver é refeita da bronze com um segredo novo), mas troca toda chave de pessoa; vazá-lo permite reverter a chave ao CPF por força bruta.

**2. Construa a imagem do Dagster e suba tudo:**

```bash
docker compose up -d --build
```

A primeira subida baixa as imagens e constrói a do Dagster (cerca de 1 minuto medido numa estação com 16 núcleos, mais o tempo de download). As seguintes levam segundos.

**3. Espere tudo ficar pronto:**

```bash
bash scripts/saude.sh
```

O script tem duas fases. A primeira espera cada serviço ficar saudável e os dois jobs de inicialização terminarem. A segunda prova o que está **dentro** dos containers: a réplica responde ao usuário `pipeline` com as 76 tabelas, tem os 75 gatilhos, os 76 tablespaces cifrados e o keyring ativo; o lake tem o bucket; o warehouse aceita o `grafana_leitor` e informa quantas execuções registrou e há quantos minutos foi o último sucesso (aviso acima de 26 h); o Dagster carregou a code location e tem os 4 sensores ligados (3 de métricas e o da silver); o Grafana responde, com as duas fontes `OK`, o painel e as 2 regras provisionados. Cada verificação sai com `✓` ou `✗`, e o fim é `PLATAFORMA OK` ou a contagem de falhas. `SO_CONTAINERS=1 bash scripts/saude.sh` roda só a primeira fase (é o que a CI faz).

**4. A réplica já nasce com as tabelas.** Na primeira inicialização o MySQL executa a DDL de `staging/ddl` (10 módulos, 76 tabelas). Se o volume da réplica já existia antes da DDL entrar no repositório, aplique por cima:

```bash
bash scripts/aplicar_ddl.sh
```

O detalhe do modelo, e como conferir a réplica, está no [Modelo de Dados](04_modelo_dados_staging.md).

## 3. Verificar a saúde

Visão geral, com o estado de saúde de cada serviço:

```bash
docker compose ps
```

Resultado esperado: sete serviços com `(healthy)` e os jobs `s3-init` e `keyring-init` como `Exited (0)`. Um serviço em `(health: starting)` ainda está subindo; em `(unhealthy)`, veja a seção 6.

Esperar até tudo ficar saudável, sem precisar ficar repetindo o comando:

```bash
bash scripts/saude.sh
```

**Não use `docker compose up --wait` neste projeto.** Ele considera falha o job `s3-init` terminar, mesmo com sucesso (código 0), e sai com erro. O `scripts/saude.sh` trata o job de inicialização como deve: pronto quando termina com 0.

O que cada healthcheck confere:

| serviço | teste | significa que |
|---|---|---|
| `mysql-staging` | `mysqladmin ping` | a réplica aceita conexões |
| Postgres (os dois) | `pg_isready` | o banco aceita conexões |
| `s3` | `/cluster/healthz` do SeaweedFS | o armazenamento está de pé |
| `dagster-web` | `/server_info` | a interface e a API do Dagster respondem |
| `dagster-daemon` | `dagster-daemon liveness-check` | o daemon está processando agendas e fila |
| `grafana` | `/api/health` | a interface e o banco interno do Grafana respondem |

Conferir que o bucket do lake foi criado:

```bash
docker compose logs s3-init
```

### O que a fundação de segurança garante, e como conferir

Estes comportamentos foram testados na subida da versão v0.2.0. Os comandos de conferência ficam aqui para quem quiser repetir.

| garantia | como foi provado | resultado esperado |
|---|---|---|
| nenhuma porta aberta para a rede | `docker compose ps` | toda porta aparece como `127.0.0.1:...` |
| Grafana não aceita acesso anônimo | `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3011/api/datasources` | `401` |
| o Grafana lê os bancos com usuário **só de leitura** | teste das fontes na interface do Grafana (Connections, Data sources, Test) | `Database Connection OK` nas duas |
| esse usuário não consegue criar nem apagar nada no banco do Dagster | tentativa de `CREATE TABLE` e de `DELETE FROM runs` com `grafana_leitor` | `permission denied for schema public` e `permission denied for table runs` |
| e nem no warehouse | tentativa de `CREATE TABLE` no Postgres do warehouse com `grafana_leitor` | `permission denied for schema public` |
| a réplica não aceita conexão sem senha | `docker exec fictalent_mysql_staging mysql -uroot -e "select 1"` | `Access denied for user 'root'` |
| os relatórios do cliente não leem dado pessoal | `.venv/bin/pytest -q tests/test_dcl_aplicada.py` | todos passam: `SELECT cpf` e `SELECT *` em `pessoas.colaborador` negados para `relatorios_cliente` |
| o pipeline não escreve e a replicação não faz DDL | mesmo teste | `INSERT` negado para `pipeline`; `CREATE`, `DROP`, `ALTER` e `GRANT` negados para `replicador` |
| dado pessoal não aparece em claro no disco da réplica | `.venv/bin/pytest -q tests/test_cifra_aplicada.py` | todos passam: CPF gravado não é encontrado no `.ibd` cifrado, e é encontrado na tabela de controle em claro |
| o lake exige credencial | listar buckets com chave errada | `InvalidAccessKeyId` |
| Dagster, Grafana e a réplica não rodam como root | `docker exec fictalent_dagster_web id -u` (e o mesmo para `fictalent_grafana` e `fictalent_mysql_staging`) | `10001` (Dagster), `472` (Grafana) e `999` (MySQL) |

## 4. Parar, reiniciar e ver logs

| quero | comando |
|---|---|
| parar tudo, **mantendo os dados** | `docker compose stop` |
| voltar a subir o que foi parado | `docker compose start` |
| reiniciar um serviço | `docker compose restart grafana` |
| reiniciar tudo | `docker compose restart` |
| derrubar os containers, **mantendo os dados** (volumes) | `docker compose down` |
| ver os logs de um serviço, acompanhando | `docker compose logs -f dagster-web` |
| ver as últimas 100 linhas de todos | `docker compose logs --tail 100` |
| reconstruir a imagem do Dagster depois de mudar código | `docker compose up -d --build dagster-web dagster-daemon` |

Os serviços têm política `unless-stopped`: se o Docker ou a máquina reiniciar, eles voltam sozinhos, a não ser que você os tenha parado de propósito.

**Antes de desligar ou reiniciar a máquina, pare os containers.** O motivo é o banco, não a rede: desligado à força, o MySQL volta fazendo recuperação de crash (`XA crash recovery` no log), e é exatamente aí que uma base grande pode se corromper. `docker compose stop` antes; `docker compose up -d && bash scripts/saude.sh` depois. Nunca `down -v`, que apaga os volumes, a base e a chave de cifra.

## 5. Recomeçar do zero (destrutivo)

Apaga **todos os dados**: bancos, lake, histórico do Dagster, configurações do Grafana e a chave de cifra da réplica (sem ela o dado cifrado seria irrecuperável de qualquer jeito). Use só quando quiser uma instalação limpa.

```bash
docker compose down -v
```

Depois disso, a primeira subida da seção 2 recria tudo, inclusive os usuários só de leitura do Grafana; a réplica volta vazia, e a base sintética se regenera em 7 minutos com os comandos da seção 6 de [Instalação e Reprodução](07_instalacao_e_reproducao.md). Se você trocar uma senha no `.env` depois que os volumes já existem, o banco **não** muda a senha sozinho: ou se troca a senha dentro do banco, ou se recomeça do zero. Exceção: as senhas dos três usuários de serviço da réplica (`pipeline`, `relatorios_cliente`, `replicador`) acompanham o `.env` sempre que `bash scripts/aplicar_ddl.sh` roda.

## 6. O Dagster: interface e o primeiro job

A interface está em <http://127.0.0.1:3010>. Em **Assets** aparecem os três assets do grupo `plataforma`; em **Jobs**, o `verificar_plataforma`. Materializar o job (botão *Materialize all* na página do job, ou *Launch run*) prova, de dentro do Dagster, que os recursos alcançam a réplica (76 tabelas, como usuário `pipeline`), o lake (escreve e lê `s3://fictalent-lake/controle/verificacao.txt`) e o warehouse (versão e papel do Grafana). O resultado fica no histórico com os metadados de cada asset.

Pela linha de comando, de dentro do container:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j verificar_plataforma
```

E da sua máquina, contra a plataforma de pé (é o que o teste de integração faz):

```bash
.venv/bin/pytest -q tests/test_orquestracao.py
```

Depois de mudar código em `src/`, reconstrua a imagem: `docker compose up -d --build dagster-web dagster-daemon`.

**As fontes públicas** (grupo `fontes`, desde a v0.4.0) são os primeiros assets de dado: `fontes/ibge/municipios` (job `carregar_municipios`), `fontes/brasilapi/feriados` (job `carregar_feriados`, particionado por ano) e, desde a v0.7.0, `fontes/caged/movimentacao` (job `carregar_caged`), que não chama API nenhuma: lê a tabela derivada versionada em `dados/publicos/caged`, que a imagem carrega. Materializar grava parquet no lake em `s3://fictalent-lake/fontes/...`; os metadados da execução mostram as linhas e o caminho. Na interface, o job dos feriados pede a partição (um ano) ou aceita um *backfill* de 2018 a 2026, que vira uma execução por ano. Pela linha de comando, o job sem partição roda com `job execute`; o particionado, com `asset materialize`, que é quem aceita `--partition`:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j carregar_municipios
docker compose exec dagster-web dagster asset materialize -m rh_fictalent.orquestracao.definicoes --select "fontes/brasilapi/feriados" --partition 2024
```

As APIs são públicas e sem contrato: o cliente (`src/rh_fictalent/fontes/apis.py`) espera no máximo 30 s por pedido, tenta 5 vezes com recuo exponencial em 429, 5xx e queda de rede, e deixa 0,5 s entre pedidos. Os limites são configuração do recurso `apis` (na página *Launchpad* do job). As mesmas tabelas, versionadas para o gerador, se regeneram com `.venv/bin/python -m rh_fictalent.fontes.apis`.

**Os logs são JSON, uma linha por evento**, e toda linha nascida dentro de uma execução carrega o `run_id` dela (mais `job`, `passo` e `evento`). Para ver o que uma execução fez, do começo ao fim, em qualquer serviço:

```bash
docker compose logs --no-log-prefix dagster-web dagster-daemon | grep '"run_id": "<id da execução>"'
```

O id está na página da execução (*Runs*). Só os erros: `grep '"nivel": "ERROR"'`; uma exceção vem inteira no campo `excecao`. O formato é o de `src/rh_fictalent/observabilidade/logs.py`, aplicado pelo logger de job `json` (`rh_fictalent.orquestracao.logger_json`), padrão de toda execução desta code location.

**Toda execução que termina vira linhas no warehouse**, gravadas pelos sensores `metricas_sucesso`, `metricas_falha` e `metricas_cancelamento` (ligados por padrão; aparecem em *Automation*): `observabilidade.execucao` (uma por execução) e `observabilidade.execucao_passo` (uma por passo, com asset, partição, duração, status, linhas, metadados e erro). É o que o Grafana lê. As últimas execuções, direto no warehouse:

```bash
docker exec -e PGPASSWORD="$(grep -E '^DW_ADMIN_PASSWORD=' .env | cut -d= -f2-)" fictalent_pg_dw psql -U fictalent_admin -d dw_fictalent -c "SELECT job, status, inicio, duracao_s, passos, passos_falhos FROM observabilidade.execucao ORDER BY inicio DESC LIMIT 10"
```

O sensor dispara até 15 segundos depois do fim da execução; se a tabela não aparecer, `docker compose logs dagster-daemon | grep metricas`.

**O painel do Grafana** está em <http://127.0.0.1:3011> (usuário e senha do `.env`), pasta *Fictalent*, painel *Fictalent · Execuções do pipeline*: execuções e falhas nas últimas 24 h, **frescor** (minutos desde o último sucesso: verde até 1 h, âmbar até 25 h, vermelho depois), duração média, execuções por dia e status, duração por job e por passo, últimas execuções e os passos que falharam com o erro. O painel é arquivo (`infra/grafana/provisioning/dashboards/json/execucoes.json`) e a interface não o edita: mudou, mudou no repositório. Em *Alerting → Alert rules* estão as duas regras provisionadas (`infra/grafana/provisioning/alerting/regras.yaml`): **Execução do pipeline falhou** (falha nos últimos 15 minutos) e **Dado envelheceu** (sem execução com sucesso há mais de 26 horas; enquanto não há agenda diária, ela acende sempre que a plataforma passa um dia parada, o que é o comportamento certo). Sem ponto de contato externo neste laboratório: o alerta acende na interface.

**A silver e a LGPD** (v0.6.0). O job `construir_silver` aplica o descarte de dado pessoal e monta as 76 tabelas da silver, pseudonimizadas, cada uma gravada em `silver/_em_conferencia/`, conferida e só então publicada; o último passo, `silver/prestacao_de_contas`, reprova se alguma regra não reproduzir o número esperado. Ele roda sozinho depois de toda carga incremental que termina bem (sensor `silver_depois_da_carga`, em *Automation*), porque a carga muda a bronze e pode trazer de volta, em claro, uma linha que o descarte já tinha apagado. O backfill não o dispara: são nove execuções, uma por ano, e quem fecha o ciclo depois de um backfill é a primeira carga incremental, que também cria a marca d'água de onde sai a data de referência. O job `aplicar_descarte` é o caminho curto, para rodar à mão: o descarte, a silver das 12 tabelas com dado pessoal e a prestação. Não rode os dois ao mesmo tempo: eles escrevem nos mesmos arquivos. Pela linha de comando, fora do Dagster:

```bash
.venv/bin/python -m rh_fictalent.lgpd --simular
```

```bash
.venv/bin/python -m rh_fictalent.silver --prestar-contas
```

O primeiro mostra quantas linhas seriam descartadas, por tabela e motivo, sem apagar nada; o segundo mostra, por regra, o número esperado, de onde ele veio (a auditoria ou o último descarte) e o que a regra deu. O prazo de retenção é decisão do cliente e mora na réplica, em `cadastro.parametro`; neste laboratório quem faz o papel do cliente é o gerador:

```bash
.venv/bin/python -m rh_fictalent.gerador --parametro RETENCAO_CANDIDATO_DIAS 730 2026-10-01
```

Cada descarte fica registrado no warehouse, sem dado pessoal:

```bash
docker exec -e PGPASSWORD="$(grep -E '^DW_ADMIN_PASSWORD=' .env | cut -d= -f2-)" fictalent_pg_dw psql -U fictalent_admin -d dw_fictalent -c "SELECT executado_em, tabela, eliminadas, vencidas, regra_retencao FROM lgpd.descarte ORDER BY id"
```

**A gold e o warehouse** (v0.7.0). O job `construir_gold` monta as 11 dimensões e os 14 fatos da silver, cada tabela gravada em `gold/_em_conferencia/`, conferida em cinco provas e só então publicada; o último passo, `gold/regua`, grava o laudo em `gold/_regua.json` e falha se uma conservação ou uma chave reprovar (a medida do contrato de aceite fora da banda é relatada, não reprova). O job `carregar_warehouse` leva a gold ao Postgres (dimensões por upsert, fatos por partição de ano, cada tabela conferida contra o parquet) e fecha com `warehouse/indices`, `warehouse/dcl` e `warehouse/rls`. Os dois rodam sozinhos: o sensor `gold_depois_da_silver` dispara a gold depois de toda silver que termina bem, e o `warehouse_depois_da_gold` dispara o warehouse depois de toda gold aprovada, de modo que a cadeia do dia (carga das 5h, silver, gold, warehouse) fecha sem agenda nova; o `aplicar_descarte` e a execução que falha não disparam nada. Pela linha de comando, fora do Dagster:

```bash
.venv/bin/python -m rh_fictalent.gold --publicar
```

```bash
.venv/bin/python -m rh_fictalent.gold --regua --so-problemas
```

```bash
.venv/bin/python -m rh_fictalent.gold --warehouse
```

O primeiro publica a gold (8,8 s); o segundo imprime o laudo e o que saiu da banda; o terceiro carrega e confere o warehouse inteiro. `--ddl`, `--dcl` e `--rls` imprimem o SQL gerado; `--dcl --aplicar` e `--rls --aplicar` o aplicam; `--indices --medir` mede os índices antes e depois e grava o laudo em `gold/_indices.json`. Dar acesso a uma pessoa é rito do administrador, no `psql`: `CREATE ROLE ana LOGIN IN ROLE perfil_coordenacao`, a senha pelo `\password`, e a filial em `acesso.filial_do_papel` ([Warehouse, seção 5](17_warehouse_postgres.md)).

## 7. Antes de abrir um PR

O mesmo que a CI vai fazer, na sua máquina:

```bash
bash scripts/esteira.sh
```

Roda lint, formato, tipos, testes (os de integração, se a réplica estiver de pé), bandit e pip-audit; com docker disponível, também gitleaks e trivy por container. Termina com `ESTEIRA VERDE` ou com a contagem de falhas.

**A esteira prova a venv, não a imagem.** Se a mudança tocou dependência (`pyproject.toml`) ou arquivo que o Dagster lê ao carregar (a DDL, os dados que um asset abre), reconstrua a imagem antes de rodar a esteira: `docker compose up -d --build dagster-web dagster-daemon && bash scripts/saude.sh`. O `test_saude` fala com o container que está de pé; se ele ainda for o da versão anterior, o teste passa e a imagem nova quebra. Foi assim na v0.5.0: a fábrica de assets lia a DDL no import, a imagem não a carregava, e a code location subiu com zero assets.

## 8. O rito de uma versão

Cada fase fechada vira versão publicável ([ADR-0008](adr/0008-gitflow-por-versao-publicavel.md)). O rito tem
**cinco passos, nesta ordem**, e a ordem importa: quem cria a tag antes do merge marca o commit errado, e quem
faz o back-merge duas vezes descobre na recusa do push.

**1. O card de fechamento.** Uma branch como qualquer outra, com o `CHANGELOG.md` da versão e o status no
`README.md`. Entra em `develop` por PR, com a CI verde.

**2. A versão: PR de `develop` para `main`.** Pela interface do GitHub, base `main`, comparação `develop`,
título `vX.Y.Z · Nome da fase`. Espere a CI e faça o merge. **É este merge que a tag vai marcar.**

**3. A tag, só depois do merge.** Atualize o local e confirme que o último commit é o merge do PR antes de marcar:

```bash
git checkout main && git pull --ff-only && git log -1 --oneline
```

```bash
git tag -a vX.Y.Z -m "vX.Y.Z · Nome da fase" && git push origin vX.Y.Z
```

**4. O release no GitHub.** *Releases* → *Draft a new release* → escolha a tag que já existe (nunca deixe o
GitHub criar a tag por você, ou ela nasce no commit errado), título igual ao da tag, texto a partir do
`CHANGELOG.md`.

**5. O back-merge, uma vez só.** A `main` recebeu o commit de merge do passo 2, que a `develop` não tem; sem o
back-merge as duas divergem. Como a `develop` é protegida e exige PR com CI, o caminho é a interface: PR com
base `develop` e comparação `main`, título `back-merge vX.Y.Z`. Depois, no terminal:

```bash
git checkout develop && git pull --ff-only && git log -1 --oneline
```

**Não faça também `git merge --ff-only main` localmente.** Os dois caminhos levam o mesmo conteúdo, mas por
históricos diferentes: o seu `develop` local fica num commit que o servidor não tem, e o push é recusado com
`Updates were rejected`. A recusa é o git protegendo o trabalho que só existe no servidor; a saída é sempre
`git pull --ff-only`, nunca `--force`.

### Se algo sair de ordem

| sintoma | o que aconteceu | o que fazer |
|---|---|---|
| `! [rejected] develop -> develop (fetch first)` | o remoto tem um commit que você não tem (em geral o back-merge feito pela interface) | `git pull --ff-only`; se ele recusar, pare e olhe o grafo com `git log --oneline --graph --all -10` antes de qualquer coisa |
| a tag aponta para o commit do card, não para o merge | a tag foi criada antes do merge do PR de versão | `git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`, depois refaça o passo 3. Só vale enquanto ninguém usou a tag |
| `error: branch '...' not found` na faxina | o GitHub já apagou a branch no merge (auto-delete) e a local também já saiu | nada: a faxina já estava feita |
| `warning: deleting branch ... not yet merged to HEAD` | você apagou a branch antes de atualizar a `develop` local | nada: o commit está no remoto; o `git pull` seguinte traz tudo |

Conferir, a qualquer momento, se as duas branches estão alinhadas e onde a tag caiu:

```bash
git fetch --all --tags && git log --oneline --graph --all -8 && git diff --stat origin/develop origin/main
```

Alinhadas, o `git diff` não imprime nada.

## 9. A chave de cifra da réplica

A réplica é cifrada em repouso ([Modelo de Dados, seção 8](04_modelo_dados_staging.md#8-cifra-em-repouso)). A chave mestra fica no volume `mysql_keyring`, nunca no repositório. Trocar a chave mestra, sem parar nada:

```bash
docker exec -e MYSQL_PWD="$(grep -E '^STAGING_ROOT_PASSWORD=' .env | cut -d= -f2-)" fictalent_mysql_staging mysql -uroot -e "ALTER INSTANCE ROTATE INNODB MASTER KEY"
```

Conferir que o componente está ativo e onde está a chave:

```bash
docker exec -e MYSQL_PWD="$(grep -E '^STAGING_ROOT_PASSWORD=' .env | cut -d= -f2-)" fictalent_mysql_staging mysql -uroot -e "SELECT * FROM performance_schema.keyring_component_status"
```

Backup da réplica sem o keyring é backup de nada: os dois viajam juntos (manual de backup, v1.0.0).

## 10. Quando algo não sobe

| sintoma | causa provável | o que fazer |
|---|---|---|
| `required variable ... is missing a value` | falta uma senha no `.env` | complete o `.env` (seção 2) |
| `port is already allocated` | outra aplicação usa a porta | troque a porta correspondente no `.env` |
| `mysql-staging` fica em `health: starting` por mais de um minuto | primeira inicialização do MySQL | normal na primeira subida; acompanhe com `docker compose logs -f mysql-staging` |
| `dagster-daemon` `unhealthy` logo depois de subir | o daemon ainda não publicou o primeiro sinal de vida | espere o `start_period` (60 s); se persistir, `docker compose logs dagster-daemon` |
| Grafana sobe, mas a fonte de dados falha no teste | usuário só de leitura não foi criado (volume antigo, senha trocada) | seção 5, ou recrie o usuário manualmente |
| `mysql-staging` não sobe e o log fala em `keyring` ou `Component_keyring_file` | o volume da chave não está acessível ao usuário do MySQL, ou o manifesto não foi montado | `docker compose logs keyring-init mysql-staging`; confira que `infra/mysql/mysqld.my` e `component_keyring_file.cnf` existem |
| a réplica está de pé, mas sem os databases dos módulos | o volume foi criado antes da DDL existir (a inicialização só roda em volume novo) | `bash scripts/aplicar_ddl.sh` |
| containers de pé e `healthy`, mas `dagster-daemon` ou `dagster-web` `unhealthy` com `connection to server at "pg-dagster" ... timed out` no log | a rede bridge do Docker quebrou (em geral depois de a máquina reiniciar ou hibernar): o DNS resolve, o TCP não passa, e **nenhum** container alcança outro. `restart`, `down`/`up` e recriar o container não resolvem, porque o problema é no `dockerd` | primeiro `docker compose down` (**sem** `-v`) e `docker compose up -d`, que recria a rede e preserva os volumes (resolveu em 23/09 e 24/09); se não bastar, `sudo systemctl restart docker` e de novo `docker compose up -d && bash scripts/saude.sh` |
| `required variable PSEUDONIMIZACAO_SEGREDO is missing a value` | `.env` anterior à v0.6.0 | gere o segredo com o comando da seção 2; nada mais muda |
| a silver falha com `sem marca d'água: rode o job carga_incremental` | a silver foi pedida logo depois do backfill, antes de qualquer carga incremental | rode `carga_incremental` uma vez; ela cria a marca e dispara a silver |
| a prestação de contas reprova as regras do candidato logo depois de recopiar uma tabela | a recópia trouxe o dado pessoal de volta e o descarte ainda não rodou | rode `construir_silver` (ou espere a próxima carga): o descarte registra o elo e a cadeia fecha |
| um passo falha com `ChildProcessCrashException`, sem mais nada no erro | o kernel matou o processo do passo por falta de memória no container do daemon, que é quem executa agenda, sensor e o que a interface lança | confirme com `dmesg \| grep -i 'out of memory'`; o teto do daemon está em `compose.yaml` (3 GB) e o do DuckDB por passo em `DUCKDB_MEMORY_LIMIT` |
| a silver falha com `defina PSEUDONIMIZACAO_SEGREDO no .env` | o container subiu sem o segredo | complete o `.env` e recrie os containers do Dagster: `docker compose up -d dagster-web dagster-daemon` |
| o log do `mysql-staging` mostra `XA crash recovery` na subida | a máquina foi desligada com os containers de pé | desta vez deu certo; da próxima, `docker compose stop` antes de desligar (seção 4) |
| um leitor do warehouse vê zero linhas em todo fato | o papel dele é de filial (coordenação ou assistente) e não tem linha em `acesso.filial_do_papel`: o RLS fecha por padrão | o administrador insere o papel e a filial na tabela de acesso (`docs/17`, seção 5) |
| `permission denied for table candidato` num `SELECT *` | o perfil não tem as colunas de atributo de pessoa; o asterisco pede todas | nomeie as colunas; se o perfil precisa do atributo, a declaração em `gold/dcl.py` é o lugar de mudar, com teste |
| `warehouse/fato/...` falha com `não confere com o parquet` | a tabela do Postgres foi alterada por fora, ou a gold foi republicada no meio da carga | rode `carregar_warehouse` de novo: a carga por partição substitui o ano inteiro e a conferência volta a fechar |

---

[Início](#topo)
