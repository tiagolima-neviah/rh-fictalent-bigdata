<a id="topo"></a>

# Monitoramento e healthcheck · o que olhar, o que é normal, o que fazer

<!-- nav:start -->
[Home](../README.md) | [← Manual de Operação](08_manual_de_operacao.md)
<!-- nav:end -->

> Três camadas de pergunta, cada uma com a sua ferramenta: **os containers estão vivos?** (healthcheck do Compose e `scripts/saude.sh`), **o pipeline está funcionando?** (Dagster e o painel do Grafana, alimentado pelas métricas de execução) e **o que aconteceu naquela execução?** (logs em JSON por `run_id`). Este documento diz, para cada indicador, o que é normal, o que é alerta e o que fazer.

## 1. As três camadas

| pergunta | ferramenta | quando usar |
|---|---|---|
| os containers estão vivos? | healthcheck de cada serviço; `bash scripts/saude.sh` (fase 1) | depois de subir ou reiniciar; quando algo "não abre" |
| a plataforma funciona por dentro? | `bash scripts/saude.sh` (fase 2): réplica, lake, warehouse, Dagster, Grafana | toda manhã; antes de abrir um PR; depois de mudar o `.env` |
| o pipeline está executando e o dado está fresco? | Grafana, painel *Fictalent · Execuções do pipeline*, e as duas regras de alerta | operação do dia a dia |
| o que uma execução fez, passo a passo? | Dagster (*Runs*) e os logs JSON filtrados por `run_id` | investigar uma falha ou uma lentidão |

## 2. Healthcheck dos containers

Cada serviço declara no `compose.yaml` como se prova vivo, e o Docker reinicia o que morre (`unless-stopped`):

| serviço | teste | intervalo | fica `unhealthy` quando |
|---|---|---|---|
| `mysql-staging` | `mysqladmin ping` | 10 s (60 s de carência na subida) | o servidor não aceita conexão (keyring ausente é a causa mais comum: veja o manual, seção 9) |
| `pg-dw`, `pg-dagster` | `pg_isready` | 10 s | o Postgres não aceita conexão |
| `s3` | `GET /cluster/healthz` | 10 s | o SeaweedFS não está de pé |
| `dagster-web` | `GET /server_info` | 10 s | a interface ou a code location não carregou |
| `dagster-daemon` | `dagster-daemon liveness-check` | 10 s (60 s de carência) | o daemon parou de processar agendas, sensores e fila |
| `grafana` | `GET /api/health` | 10 s | o Grafana ou o banco interno dele caiu |

`docker compose ps` mostra o estado; `docker compose logs <serviço>` mostra o porquê.

## 3. O painel do Grafana, indicador a indicador

Painel *Fictalent · Execuções do pipeline* (<http://127.0.0.1:3011>, pasta *Fictalent*), atualizado a cada minuto, lendo `observabilidade.execucao` e `execucao_passo` no warehouse:

| indicador | o que mostra | normal | atenção | o que fazer |
|---|---|---|---|---|
| Execuções nas últimas 24 h | quantas execuções começaram | ao menos uma por agenda prevista (a partir da v0.5.0, uma por dia) | zero num dia útil | o daemon está de pé? `docker compose ps dagster-daemon`; as agendas estão ligadas em *Automation*? |
| Falhas nas últimas 24 h | execuções com status FALHA | 0 | qualquer valor | abra a tabela *Passos que falharam* e leia o erro; depois os logs por `run_id` |
| Frescor | minutos desde o último sucesso | verde até 1 h; âmbar até 25 h | vermelho (mais de 25 h) | igual ao alerta *Dado envelheceu*, abaixo |
| Duração média | segundos por execução nas últimas 24 h | estável de um dia para o outro | dobrou sem mudança de volume | veja *Duração por passo*: o passo que cresceu aponta o gargalo |
| Execuções por dia e status | barras empilhadas por SUCESSO, FALHA, CANCELADA | verde | vermelho ou laranja aparecendo | investigue as falhas; cancelamento repetido indica alguém interrompendo execuções |
| Duração de cada execução, por job | pontos no tempo | linha estável | degrau para cima | mudança de volume ou de infraestrutura; compare com o passo |
| Duração média por passo | barras por asset | os passos de leitura curtos, os de escrita maiores | um passo fora da curva | é o candidato a otimização (índice, partição, lote) |
| Últimas execuções | tabela com job, status, duração, passos | | | o `inicio` e o job levam à execução em *Runs* |
| Passos que falharam, com o erro | tabela com fim, job, passo, erro | vazia | qualquer linha | o erro é a mensagem da exceção do passo; o `run_id` dá o resto |

## 4. Os alertas

Regras em *Alerting → Alert rules*, provisionadas por arquivo, avaliadas a cada minuto:

| regra | acende quando | por quanto tempo antes de acender | o que fazer |
|---|---|---|---|
| **Execução do pipeline falhou** | alguma execução terminou com FALHA nos últimos 15 minutos | 1 minuto | painel → *Passos que falharam* → erro → logs por `run_id`; corrigido, reprocesse a partição pela interface do Dagster |
| **Dado envelheceu** | nenhuma execução terminou com sucesso nas últimas 26 horas (ou nunca) | 5 minutos | o daemon está de pé? a agenda está ligada? a última execução falhou? Enquanto não existe agenda diária (v0.5.0), o alerta acende sempre que a plataforma fica um dia sem rodar o `verificar_plataforma`: é esperado |

Neste laboratório o alerta acende só na interface (ponto de contato padrão, sem e-mail nem chat). Em produção, o ponto de contato é provisionado do mesmo jeito (`infra/grafana/provisioning/alerting`), apontando para e-mail, Slack ou Teams.

## 5. Investigar uma execução

1. **Achar o `run_id`**: no Dagster, *Runs*, a execução tem o id no topo; no Grafana, a tabela *Últimas execuções* dá o `inicio` e o job para localizar em *Runs*.
2. **Ver o que o Dagster viu**: a página da execução mostra cada passo, duração, metadados (as tabelas contadas, o caminho no lake, a versão do warehouse) e a exceção inteira em caso de falha.
3. **Ler os logs, todos do mesmo `run_id`**:

```bash
docker compose logs --no-log-prefix dagster-web dagster-daemon | grep '"run_id": "<id>"'
```

Cada linha é JSON: `instante`, `nivel`, `passo`, `evento`, `mensagem`; `"nivel": "ERROR"` e o campo `excecao` são o que interessa numa falha.

4. **Conferir as métricas gravadas** (o que o painel está mostrando vem daqui):

```bash
docker exec -e PGPASSWORD="$(grep -E '^DW_ADMIN_PASSWORD=' .env | cut -d= -f2-)" fictalent_pg_dw psql -U fictalent_admin -d dw_fictalent -c "SELECT passo, status, duracao_s, erro FROM observabilidade.execucao_passo WHERE run_id = '<id>' ORDER BY inicio"
```

## 6. Rotina sugerida

| quando | o quê |
|---|---|
| ao ligar a máquina | `docker compose start` e `bash scripts/saude.sh` |
| todo dia, 1 minuto | painel do Grafana: falhas em zero, frescor verde |
| antes de abrir um PR | `bash scripts/esteira.sh` |
| quando o alerta acender | seção 4 desta página |
| ao encerrar | `docker compose stop` (os dados ficam nos volumes) |

## 7. O que ainda não existe

- Frescor **por asset** (cada tabela da bronze, silver e gold com a sua idade): entra quando houver dado (v0.6.0); hoje o frescor é por execução.
- Notificação externa dos alertas (e-mail, chat): ponto de contato por provisioning, fora deste laboratório.
- Métricas de infraestrutura (CPU, memória, disco por container): `docker stats` cobre o suficiente para uma máquina só; Prometheus e exportadores entram apenas se o caso pedir (ADR-0007).
- Auditoria de acesso à réplica (quem consultou o quê): v1.0.0, com ADR.

---

[Início](#topo)
