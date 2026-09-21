<a id="topo"></a>

# Instalação e reprodução · do clone à plataforma verificada

<!-- nav:start -->
[Home](../README.md) | [← Régua de Validação](06_regua_de_validacao.md) | [Manual de Operação →](08_manual_de_operacao.md)
<!-- nav:end -->

> O caminho completo para ter este projeto rodando numa máquina que nunca o viu, com o comando exato de cada passo e a verificação que diz se deu certo. Todo passo foi executado na versão em que entrou. Tempo total medido: cerca de 5 minutos para a plataforma (a maior parte baixando imagens) e mais 7 para gerar e conferir a base sintética, numa estação com 16 núcleos e conexão boa.

## 1. O que precisa estar instalado

| o quê | versão | para quê | conferir |
|---|---|---|---|
| Docker com Compose v2 | Docker 24 ou mais novo | sobe os 7 serviços e os 2 jobs | `docker compose version` |
| Python | 3.12 | o código do projeto e os testes | `python3 --version` |
| uv | 0.11 ou mais novo | dependências, venv e lock | `uv --version` |
| git | qualquer recente | clonar e contribuir | `git --version` |
| openssl | qualquer | gerar as senhas do `.env` | `openssl version` |

Máquina: **8 GB de RAM** no mínimo (16 recomendado), 4 núcleos, 20 GB livres em disco. Em repouso a plataforma usa cerca de 1,4 GB; gerar a base sintética pede mais 2,5 GB livres por alguns minutos. No Windows, use o WSL2 com Docker Desktop ou o Docker dentro da distribuição; tudo abaixo é Linux.

Instalar o uv, se faltar: <https://docs.astral.sh/uv/getting-started/installation/>.

## 2. Clonar e preparar o ambiente Python

```bash
git clone https://github.com/tiagolima-neviah/rh-fictalent-bigdata.git
cd rh-fictalent-bigdata
uv sync --frozen --group dev
```

O `--frozen` obriga o uso exato do `uv.lock`: a mesma versão de cada pacote que a CI e o autor usam. A venv fica em `.venv/`.

## 3. Segredos: o `.env`

O compose se recusa a subir sem todas as senhas. Gere todas de uma vez:

```bash
cp .env.example .env
for v in STAGING_ROOT_PASSWORD PIPELINE_PASSWORD RELATORIOS_PASSWORD REPLICADOR_PASSWORD DAGSTER_PG_PASSWORD S3_SECRET_KEY DW_ADMIN_PASSWORD GRAFANA_ADMIN_PASSWORD GRAFANA_LEITOR_PASSWORD; do sed -i "s/^$v=.*/$v=$(openssl rand -hex 24)/" .env; done && sed -i "s/^S3_ACCESS_KEY=.*/S3_ACCESS_KEY=$(openssl rand -hex 12)/" .env
```

O `.env` nunca é versionado (`.gitignore`). Só letras e números nas senhas, para nenhuma string de conexão quebrar. As portas e os endereços locais (`127.0.0.1`) podem ficar como estão.

## 4. Subir a plataforma

```bash
docker compose up -d --build
```

Primeira vez: baixa as imagens (MySQL, Postgres, SeaweedFS, Grafana, Python) e constrói a do Dagster. A réplica MySQL nasce com a DDL dos 10 módulos, os gatilhos, os papéis e a cifra aplicados na inicialização; o warehouse nasce com o papel de leitura do Grafana; o Grafana nasce com as fontes, o painel e os alertas provisionados.

**Não use `docker compose up --wait`:** ele trata os jobs de inicialização que terminam com sucesso como falha.

## 5. Verificar

```bash
bash scripts/saude.sh
```

Espera os containers ficarem saudáveis e prova o que está dentro deles: réplica com 76 tabelas, 75 gatilhos e cifra ativa; bucket do lake; warehouse; Dagster com a code location e os sensores; Grafana com fontes, painel e alertas. Termina em **`PLATAFORMA OK`**. Um aviso de "ainda sem execução registrada" é normal na primeira subida.

Depois, a primeira execução de verdade, pela linha de comando:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j verificar_plataforma
```

Ou pela interface: <http://127.0.0.1:3010> → *Jobs* → `verificar_plataforma` → *Materialize all*. Em até 15 segundos o sensor grava as métricas e o painel do Grafana (<http://127.0.0.1:3011>, usuário e senha do `.env`) mostra a execução.

E a esteira inteira, igual à CI:

```bash
bash scripts/esteira.sh
```

Lint, tipos, testes (os de integração rodam porque a plataforma está de pé), bandit, pip-audit e, com o docker disponível, gitleaks e trivy. Termina em `ESTEIRA VERDE`.

## 6. Gerar a base sintética

A plataforma sobe com a réplica vazia. A base (a Fictalent de 2018 a 10/09/2026, 8,4 milhões de linhas em 76 tabelas) é gerada por um gerador determinístico em seis etapas, cada uma continuando a anterior: a mesma semente produz a mesma base em qualquer máquina.

```bash
.venv/bin/python -m rh_fictalent.gerador --etapa 1 --gravar --zerar && for e in 2 3 4 5 6; do .venv/bin/python -m rh_fictalent.gerador --etapa $e --gravar || break; done
```

| etapa | o que gera | linhas | tempo medido |
|---|---|---|---|
| 1 | o mundo cadastral: filiais, funções, convenções e pisos, feriados, municípios | 1,7 mil | 3 s |
| 2 | a carteira comercial: clientes, contratos, postos, preços, SLA e ocorrências | 4,7 mil | 1 s |
| 3 | o funil de recrutamento e as pessoas: vagas, candidatos, candidaturas, entrevistas, admissões, alocações | 1,33 milhão | 1 min |
| 4 | ponto e folha: marcações, apontamentos, folha, provisões e rateio de custo | 6,82 milhões | 3 min 25 s |
| 5 | financeiro: faturas, títulos, impostos e o consolidado gerencial (também em Excel, em `dados/gerencial`) | 18,8 mil | 30 s |
| 6 | conformidade e acesso: treinamentos, exames, programas, acidentes, usuários, permissões e trilha de auditoria | 233 mil | 35 s |

Cada etapa gera em memória, confere a si mesma (chaves, carimbos e a régua parcial, que sai impressa) e só então grava, numa transação. Gravar duas vezes, ou fora de ordem, é recusado; regenerar é sempre recomeçar pela etapa 1 com `--zerar`, que esvazia a réplica inteira (pede a senha de `root` do `.env`). A etapa 4 é a que pesa: pico de 2,4 GB de RAM. No fim a réplica ocupa cerca de 1,5 GB de dado e índice.

Depois, o aceite: a base inteira contra a régua inteira, com as linhas contadas na réplica.

```bash
.venv/bin/python -m rh_fictalent.gerador --aceite --replica
```

Termina em **`RÉGUA APROVADA: 165 de 165`** e reescreve `dados/regua/medidas.json` e `laudo.txt` com o mesmo conteúdo que está versionado (se `git status` mostrar diferença, a sua base não é a do repositório). O que cada check confere está em [Régua de Validação](06_regua_de_validacao.md).

## 7. O que está onde

| endereço | o quê | credencial |
|---|---|---|
| `127.0.0.1:3316` | réplica MySQL (10 databases) | `root` com `STAGING_ROOT_PASSWORD`; ou `pipeline`, `relatorios_cliente`, `replicador` com as senhas do `.env` |
| `127.0.0.1:5441` | warehouse Postgres (`dw_fictalent`) | `fictalent_admin` com `DW_ADMIN_PASSWORD`; `grafana_leitor` só leitura |
| `127.0.0.1:8333` | lake S3 (bucket `fictalent-lake`) | `S3_ACCESS_KEY` e `S3_SECRET_KEY` |
| <http://127.0.0.1:3010> | Dagster | sem autenticação (só localhost) |
| <http://127.0.0.1:3011> | Grafana | `admin` com `GRAFANA_ADMIN_PASSWORD` |

Tudo escuta só em `127.0.0.1`: nada fica acessível a partir da rede. Para um cliente de banco (DBeaver, por exemplo), use esses endereços; no MySQL deixe o campo *Database* vazio para ver os 10 databases.

## 8. Atualizar, recomeçar, desinstalar

**Atualizar** para uma versão nova do repositório:

```bash
git pull && uv sync --frozen --group dev && docker compose up -d --build && bash scripts/aplicar_ddl.sh && bash scripts/saude.sh
```

O `aplicar_ddl.sh` reaplica a DDL da réplica num volume que já existia (a inicialização automática só roda em volume novo); mudança de coluna ou comentário em tabela existente pede `ALTER` ou recomeço, enquanto a réplica não tem dado.

**Recomeçar do zero** (apaga todos os dados, inclusive a chave de cifra):

```bash
docker compose down -v && docker compose up -d --build && bash scripts/saude.sh
```

**Desinstalar**: `docker compose down -v --rmi local` remove containers, volumes e a imagem do Dagster; apagar a pasta do repositório remove o resto. As imagens públicas baixadas (MySQL, Postgres, SeaweedFS, Grafana, Python) ficam no Docker até `docker image prune`.

## 9. Reproduzir numa máquina limpa

O trilho `réplica provada` da CI faz exatamente isto a cada PR, num runner descartável do GitHub: clona, gera um `.env`, sobe a réplica e roda os testes de integração. É a prova de que este documento não depende de nada que só exista na máquina do autor. Se um passo daqui falhar na sua máquina e não na CI, a diferença está no ambiente (versão do Docker, porta ocupada, WSL sem memória), e a seção 9 do manual de operação tem os sintomas conhecidos.

---

[Início](#topo)
