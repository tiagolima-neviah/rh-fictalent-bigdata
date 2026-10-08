<a id="topo"></a>

# Solução de problemas · o sintoma, a causa provável e o que fazer

<!-- nav:start -->
[Home](../README.md) | [← Backup e restauração](19_backup_e_restauracao.md) | [Do zero ao pipeline →](21_do_zero_ao_pipeline.md)
<!-- nav:end -->

> Tudo o que já quebrou neste projeto, com o sintoma como ele aparece na tela, a causa que foi encontrada e o que resolveu. A lista cresceu com as versões (cada caso aqui aconteceu de verdade, numa rodada registrada no worklog) e é a primeira parada quando algo não sobe ou não roda. Antes da tabela, o método: como achar a causa quando ela não está aqui.

## 1. Antes da tabela: como investigar

Três perguntas, nesta ordem. **A plataforma está de pé?** `bash scripts/saude.sh` responde em duas fases: os containers (saudáveis, ou qual não está) e as 19 provas de ponta a ponta ([Manual de Operação, seção 3](08_manual_de_operacao.md)). **O que rodou e o que falhou?** Pela interface do Dagster (*Runs*), pelos logs em JSON com o `run_id` (`docker compose logs --no-log-prefix dagster-web dagster-daemon | grep '"run_id": "<id>"'`), pela trilha (`python -m rh_fictalent.trilha --consulta passos_que_falharam --dias 7`) ou pelo painel do Grafana ([Monitoramento, seção 5](09_monitoramento_e_healthcheck.md)). **O erro é do dado ou da infraestrutura?** Reprovação de conferência (a silver, a gold, o warehouse dizem *o que* não conferiu) é determinística e não se repete à toa: investigue o dado. Erro de rede, memória ou disco se repete com outro sintoma: investigue o container.

Duas investigações inteiras estão escritas como exemplo do método: a queda de conexão com o lake, reproduzida, com duas hipóteses descartadas por medida e a causa provada ([Bronze, seção 8](12_bronze.md)); e a silver que falhava pela fila e passava pela linha de comando, que era a memória do daemon ([Silver, seção 7](14_silver.md)).

## 2. Subir a plataforma

| sintoma | causa provável | o que fazer |
|---|---|---|
| `required variable ... is missing a value` | falta uma senha no `.env` | complete o `.env` ([Manual, seção 2](08_manual_de_operacao.md)); desde a v1.0.0 a lista inclui `API_DB_PASSWORD`, e o Compose exige a variável mesmo para subir só a réplica |
| `port is already allocated` | outra aplicação usa a porta | troque a porta correspondente no `.env` |
| `mysql-staging` fica em `health: starting` por mais de um minuto | primeira inicialização do MySQL | normal na primeira subida; acompanhe com `docker compose logs -f mysql-staging` |
| `dagster-daemon` `unhealthy` logo depois de subir | o daemon ainda não publicou o primeiro sinal de vida | espere o `start_period` (60 s); se persistir, `docker compose logs dagster-daemon` |
| Grafana sobe, mas a fonte de dados falha no teste | usuário só de leitura não foi criado (volume antigo, senha trocada) | [Manual, seção 5](08_manual_de_operacao.md), ou recrie o usuário manualmente |
| `mysql-staging` não sobe e o log fala em `keyring` ou `Component_keyring_file` | o volume da chave não está acessível ao usuário do MySQL, ou o manifesto não foi montado | `docker compose logs keyring-init mysql-staging`; confira que `infra/mysql/mysqld.my` e `component_keyring_file.cnf` existem |
| a réplica está de pé, mas sem os databases dos módulos | o volume foi criado antes da DDL existir (a inicialização só roda em volume novo) | `bash scripts/aplicar_ddl.sh` |
| containers de pé e `healthy`, mas `dagster-daemon` ou `dagster-web` `unhealthy` com `connection to server at "pg-dagster" ... timed out` no log | **outro Docker Engine subiu no mesmo VM do WSL2**: outra distribuição com `dockerd` (ou o Docker Desktop) foi iniciada e, como todas as distribuições dividem o mesmo IP e a mesma pilha de rede, o segundo daemon reescreveu as regras de rede do primeiro; o DNS resolve, o TCP não passa, e **nenhum** container alcança outro. Reiniciar a máquina ou hibernar produz o mesmo quadro quando a outra distribuição sobe junto. Provado em 08/10/2026 ao reproduzir o projeto numa distribuição limpa ao lado desta; era a causa de 23/09 e 24/09 | pare o outro daemon (`sudo systemctl stop docker.socket docker` na outra distribuição, ou `wsl --terminate <distro>` no Windows); aqui, `docker compose down` (**sem** `-v`) e `docker compose up -d`, que recria a rede e preserva os volumes; se não bastar, `sudo systemctl restart docker` e de novo `docker compose up -d && bash scripts/saude.sh`. Regra: um só Docker Engine por máquina ([Instalação, seção 1](07_instalacao_e_reproducao.md)) |
| o log do `mysql-staging` mostra `XA crash recovery` na subida | a máquina foi desligada com os containers de pé | desta vez deu certo; da próxima, `docker compose stop` antes de desligar |
| `pg-dagster` ou `grafana` `unhealthy` na primeira subida e o `up` desiste dos dependentes (`dependency failed to start`) | disco lento para escrita sincronizada (SSD externo por USB, disco de rede): o Postgres faz `fsync` de centenas de arquivos ao inicializar (30 s medidos num USB) e o Grafana roda centenas de migrações, uma por segundo; o `start_period` do healthcheck estoura antes | meça: `dd if=/dev/zero of=/tmp/x bs=4k count=500 oflag=dsync` leva cerca de 1 s num SSD interno e levou 142 s no USB; a distribuição (e o Docker dela) vai para um disco interno; `docker compose up -d` de novo termina de subir o que faltou (08/10/2026) |
| `mysql-staging` reinicia sem parar, com `Cannot create redo log files because data files are corrupt or the database was not shut down cleanly after creating the data files` | a primeira inicialização do MySQL foi interrompida antes de os arquivos de dados existirem inteiros: a distribuição do WSL desligou (sem terminal ligado, o WSL a desliga em segundos) ou a máquina reiniciou | o volume nasceu quebrado e não tem dado: `docker compose down -v` (só aqui o `-v` vale, porque não há nada a preservar) e `docker compose up -d`. No WSL, deixe um terminal aberto na distribuição enquanto a plataforma sobe (08/10/2026) |
| `saude.sh` acusa `sensores ligados: N (esperados 6)` | um sensor foi desligado na interface, ou a imagem é anterior aos sensores da cadeia do dia | *Automation* no Dagster; `docker compose up -d --build dagster-web dagster-daemon` |

## 3. Silver, LGPD e a cadeia do dia

| sintoma | causa provável | o que fazer |
|---|---|---|
| `required variable PSEUDONIMIZACAO_SEGREDO is missing a value` | `.env` anterior à v0.6.0 | gere o segredo com o comando do [Manual, seção 2](08_manual_de_operacao.md); nada mais muda |
| a silver falha com `sem marca d'água: rode o job carga_incremental` | a silver foi pedida logo depois do backfill, antes de qualquer carga incremental | rode `carga_incremental` uma vez; ela cria a marca e dispara a silver |
| a prestação de contas reprova as regras do candidato logo depois de recopiar uma tabela | a recópia trouxe o dado pessoal de volta e o descarte ainda não rodou | rode `construir_silver` (ou espere a próxima carga): o descarte registra o elo e a cadeia fecha |
| um passo falha com `ChildProcessCrashException`, sem mais nada no erro | o kernel matou o processo do passo por falta de memória no container do daemon, que é quem executa agenda, sensor e o que a interface lança | confirme com `dmesg \| grep -i 'out of memory'`; o teto do daemon está em `compose.yaml` (3 GB) e o do DuckDB por passo em `DUCKDB_MEMORY_LIMIT` |
| a silver falha com `defina PSEUDONIMIZACAO_SEGREDO no .env` | o container subiu sem o segredo | complete o `.env` e recrie os containers do Dagster: `docker compose up -d dagster-web dagster-daemon` |
| a gold ou o warehouse não rodaram depois da silver | o sensor só dispara para `construir_silver` que termina bem; o `aplicar_descarte` e a silver que falha não disparam | veja a silver em *Runs*; se ela passou, confira o sensor em *Automation* |
| `gold/regua` falha | uma conservação ou uma chave reprovou (a medida do contrato fora da banda não reprova) | o veredito diz qual total ou chave; a causa é um join da gold ou a silver republicada no meio; `python -m rh_fictalent.gold --regua --so-problemas` |

## 4. Warehouse, acesso e API

| sintoma | causa provável | o que fazer |
|---|---|---|
| um leitor do warehouse vê zero linhas em todo fato | o papel dele é de filial (coordenação ou assistente) e não tem linha em `acesso.filial_do_papel`: o RLS fecha por padrão | o administrador insere o papel e a filial ([Warehouse, seção 5](17_warehouse_postgres.md)) |
| `permission denied for table candidato` num `SELECT *` | o perfil não tem as colunas de atributo de pessoa; o asterisco pede todas | nomeie as colunas; se o perfil precisa do atributo, a declaração em `gold/dcl.py` é o lugar de mudar, com teste |
| `warehouse/fato/...` falha com `não confere com o parquet` | a tabela do Postgres foi alterada por fora, ou a gold foi republicada no meio da carga | rode `carregar_warehouse` de novo: a carga por partição substitui o ano inteiro e a conferência volta a fechar |
| a API responde 401 com token certo | o token venceu (`valido_ate`) ou foi revogado; ou o cabeçalho não é `Authorization: Bearer <token>` | `python -m rh_fictalent.trilha --consulta tokens_da_api`; cadastre outro ([API, seção 3](18_api.md)) |
| a API responde 403 `permission denied to set role` | o papel do consumidor existe mas a API não é membro dele (faltou `GRANT <papel> TO api`) | repita `python -m rh_fictalent.api --consumidor <papel> --perfil <perfil>` |
| a API responde 403 com o nome de uma tabela | o perfil do consumidor não lê aquela tabela: é o DCL funcionando | se o perfil deveria ler, a declaração é `gold/dcl.py`; a tabela de erros está no [API, seção 5](18_api.md) |
| `saude.sh` avisa `tabela de tokens ausente` | o preparo da API não rodou neste warehouse | `python -m rh_fictalent.api --preparar` |
| `/saude` da API diz `degradada` | a API não alcança o warehouse (senha do `api` trocada, Postgres fora) | `docker compose logs api`; se a senha mudou no `.env`, `--preparar` de novo e `docker compose up -d api` |
| no Neon, `permission denied to set role "perfil_..."` para o dono do banco | o dono não é superusuário: cria papéis mas não é membro deles | `GRANT perfil_x TO <dono> WITH SET TRUE, INHERIT FALSE` só para testar, e `REVOKE` depois ([Warehouse, seção 10](17_warehouse_postgres.md)) |
| `--destino nuvem` falha com `password authentication failed` ou o host tem `-pooler` | a string colada era a do pooler, ou a senha veio errada do console | use a string direta (sem `-pooler`) e, se preciso, *Reset password* no Neon; o código exige TLS sozinho |

## 5. Backup, restauração e ferramentas

| sintoma | causa provável | o que fazer |
|---|---|---|
| `--provar` reprova o Dagster por poucas linhas em `job_ticks` | o banco escreveu entre o dump e a contagem (backups anteriores à v1.0.0 não guardavam a contagem de antes) | refaça o backup: o manifesto novo guarda as contagens antes e depois, e a prova aceita o intervalo |
| `--fazer` falha no lake com `The specified key does not exist` | versão anterior ao download arquivo a arquivo; o SeaweedFS lista uma pasta vazia como objeto | atualize; o download pula entradas de tamanho zero |
| `--provar` deixa `fictalent_prova_mysql` de pé | a prova foi interrompida no meio (Ctrl+C) | `docker rm -f fictalent_prova_mysql`; a próxima prova também o remove antes de começar |
| a esteira falha em `dependências (pip-audit)` com `invalid requirements input: /tmp/requisitos-auditoria.txt` e, logo acima, `uv: No such file or directory` | o `esteira.sh` não achou o `uv` (fora do PATH num shell não interativo, ou instalado em outro lugar); até a v1.0.0 o script só conhecia o caminho da máquina do autor, e a reprodução do zero de 08/10/2026 foi quem pegou | o script procura em `~/.local/bin` e no mise; se o seu `uv` mora em outro lugar, `UV=/caminho/do/uv bash scripts/esteira.sh` |
| `gh` não abre o navegador no WSL (`xdg-open ... not found`) | o WSL não tem navegador | abra `https://github.com/login/device` no Windows e digite o código mostrado; `sudo apt install -y wslu` faz o `gh` abrir o Chrome da próxima vez |
| `gh pr create` diz que nenhum remoto aponta para um host do GitHub | o remoto usa um apelido do `~/.ssh/config` que o `gh` não resolveu | `gh repo set-default tiagolima-neviah/rh-fictalent-bigdata`, uma vez |
| a CI falha nos três trilhos em poucos segundos, no *Set up job* | uma action referencia uma tag que não existe | confira a tag na API (`/repos/<dono>/<action>/git/ref/tags/<tag>`): o `setup-uv` não tem tag maior desde a v7, o `trivy-action` prefixa com `v` |

## 6. Quando a resposta não está aqui

Reproduza com a menor plataforma que ainda mostra o sintoma, meça antes de concluir (a hipótese "é memória" se prova com `dmesg` e o contador `oom_kill` do container, não com a sensação), escreva a investigação no worklog com o que foi descartado e por quê, e, quando a causa estiver provada, acrescente a linha aqui. Foi assim que todas as linhas acima nasceram.

---

[Início](#topo)
