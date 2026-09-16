<a id="topo"></a>

# Manual de Operação · subir, verificar, parar e recuperar

<!-- nav:start -->
[Home](../README.md) | [← Modelo de Dados](04_modelo_dados_staging.md)
<!-- nav:end -->

> O manual de quem opera a plataforma no dia a dia. Todo comando aqui foi executado e conferido na versão em que a seção entrou. Rode todos a partir da **raiz do repositório**. Este documento cresce com o projeto: nesta versão (v0.2.0) ele cobre a infraestrutura; execução de pipelines, agendas e reprocessamento entram com a Fase 3.

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

**2. Construa a imagem do Dagster e suba tudo:**

```bash
docker compose up -d --build
```

A primeira subida baixa as imagens e constrói a do Dagster (cerca de 1 minuto medido numa estação com 16 núcleos, mais o tempo de download). As seguintes levam segundos.

**3. Espere tudo ficar pronto:**

```bash
bash scripts/saude.sh
```

O script espera cada serviço ficar saudável e os dois jobs de inicialização terminarem, e termina com `OK` ou com a lista do que falhou.

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

## 5. Recomeçar do zero (destrutivo)

Apaga **todos os dados**: bancos, lake, histórico do Dagster, configurações do Grafana e a chave de cifra da réplica (sem ela o dado cifrado seria irrecuperável de qualquer jeito). Use só quando quiser uma instalação limpa.

```bash
docker compose down -v
```

Depois disso, a primeira subida da seção 2 recria tudo, inclusive os usuários só de leitura do Grafana. Se você trocar uma senha no `.env` depois que os volumes já existem, o banco **não** muda a senha sozinho: ou se troca a senha dentro do banco, ou se recomeça do zero. Exceção: as senhas dos três usuários de serviço da réplica (`pipeline`, `relatorios_cliente`, `replicador`) acompanham o `.env` sempre que `bash scripts/aplicar_ddl.sh` roda.

## 6. A chave de cifra da réplica

A réplica é cifrada em repouso ([Modelo de Dados, seção 8](04_modelo_dados_staging.md#8-cifra-em-repouso)). A chave mestra fica no volume `mysql_keyring`, nunca no repositório. Trocar a chave mestra, sem parar nada:

```bash
docker exec -e MYSQL_PWD="$(grep -E '^STAGING_ROOT_PASSWORD=' .env | cut -d= -f2-)" fictalent_mysql_staging mysql -uroot -e "ALTER INSTANCE ROTATE INNODB MASTER KEY"
```

Conferir que o componente está ativo e onde está a chave:

```bash
docker exec -e MYSQL_PWD="$(grep -E '^STAGING_ROOT_PASSWORD=' .env | cut -d= -f2-)" fictalent_mysql_staging mysql -uroot -e "SELECT * FROM performance_schema.keyring_component_status"
```

Backup da réplica sem o keyring é backup de nada: os dois viajam juntos (manual de backup, v1.0.0).

## 7. Quando algo não sobe

| sintoma | causa provável | o que fazer |
|---|---|---|
| `required variable ... is missing a value` | falta uma senha no `.env` | complete o `.env` (seção 2) |
| `port is already allocated` | outra aplicação usa a porta | troque a porta correspondente no `.env` |
| `mysql-staging` fica em `health: starting` por mais de um minuto | primeira inicialização do MySQL | normal na primeira subida; acompanhe com `docker compose logs -f mysql-staging` |
| `dagster-daemon` `unhealthy` logo depois de subir | o daemon ainda não publicou o primeiro sinal de vida | espere o `start_period` (60 s); se persistir, `docker compose logs dagster-daemon` |
| Grafana sobe, mas a fonte de dados falha no teste | usuário só de leitura não foi criado (volume antigo, senha trocada) | seção 5, ou recrie o usuário manualmente |
| `mysql-staging` não sobe e o log fala em `keyring` ou `Component_keyring_file` | o volume da chave não está acessível ao usuário do MySQL, ou o manifesto não foi montado | `docker compose logs keyring-init mysql-staging`; confira que `infra/mysql/mysqld.my` e `component_keyring_file.cnf` existem |
| a réplica está de pé, mas sem os databases dos módulos | o volume foi criado antes da DDL existir (a inicialização só roda em volume novo) | `bash scripts/aplicar_ddl.sh` |

---

[Início](#topo)
