<a id="topo"></a>

# Instalação e reprodução · do clone à plataforma verificada

<!-- nav:start -->
[Home](../README.md) | [← Régua de Validação](06_regua_de_validacao.md) | [Manual de Operação →](08_manual_de_operacao.md)
<!-- nav:end -->

> O caminho completo para ter este projeto rodando numa máquina que nunca o viu, com o comando exato de cada passo e a verificação que diz se deu certo. Todo passo foi executado na versão em que entrou. Tempo total medido: cerca de 5 minutos para a plataforma (a maior parte baixando imagens) e mais 7 para gerar e conferir a base sintética e cerca de 6 para levá-la à bronze e à silver do lake, numa estação com 16 núcleos e conexão boa.

## 1. O que precisa estar instalado

| o quê | versão | para quê | conferir |
|---|---|---|---|
| Docker com Compose v2 | Docker 24 ou mais novo | sobe os 8 serviços e os 2 jobs | `docker compose version` |
| Python | 3.12 | o código do projeto e os testes | `python3 --version` |
| uv | 0.11 ou mais novo | dependências, venv e lock | `uv --version` |
| git | qualquer recente | clonar e contribuir | `git --version` |
| openssl | qualquer | gerar as senhas do `.env` | `openssl version` |
| gh (opcional) | 2.40 ou mais novo | o rito do PR pelo terminal ([Manual, seção 7](08_manual_de_operacao.md)) | `gh --version` |

Máquina: **8 GB de RAM** no mínimo (16 recomendado), 4 núcleos, 20 GB livres em disco. Em repouso a plataforma usa cerca de 1,4 GB; gerar a base sintética pede mais 2,5 GB livres por alguns minutos. No Windows, use o WSL2 com Docker Desktop ou o Docker dentro da distribuição; tudo abaixo é Linux.

Mais duas coisas que o WSL2 cobra e que a reprodução do zero de 08/10/2026 pagou (seção 10): a distribuição e o Docker dela ficam num **disco interno** (num SSD externo por USB a escrita sincronizada saiu 140 vezes mais lenta, e os bancos não sobem direito), e **um terminal fica aberto na distribuição** enquanto a plataforma sobe, porque sem sessão ligada o WSL a desliga em segundos, e um MySQL interrompido na primeira inicialização nasce corrompido. Instalar o Docker Engine no Ubuntu, se faltar: o repositório oficial, em <https://docs.docker.com/engine/install/ubuntu/>, e o seu usuário no grupo `docker`. **No WSL2, um só Docker Engine por máquina:** todas as distribuições rodam no mesmo VM e dividem o mesmo IP e a mesma pilha de rede; um segundo `dockerd` (outra distribuição com Docker, ou o Docker Desktop ao lado de um Engine) reescreve as regras de rede do primeiro, e a plataforma que estava de pé fica com os containers saudáveis e sem alcançar uns aos outros ([Solução de problemas, seção 2](20_solucao_de_problemas.md)). Instalar o uv, se faltar: <https://docs.astral.sh/uv/getting-started/installation/>. O `gh`, no Ubuntu e no Debian, vem do repositório oficial do GitHub (<https://github.com/cli/cli/blob/trunk/docs/install_linux.md>); depois, `gh auth login` uma vez, escolhendo SSH como protocolo do git para continuar usando a sua chave.

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
for v in STAGING_ROOT_PASSWORD PIPELINE_PASSWORD RELATORIOS_PASSWORD REPLICADOR_PASSWORD DAGSTER_PG_PASSWORD S3_SECRET_KEY DW_ADMIN_PASSWORD GRAFANA_ADMIN_PASSWORD GRAFANA_LEITOR_PASSWORD API_DB_PASSWORD; do sed -i "s/^$v=.*/$v=$(openssl rand -hex 24)/" .env; done && sed -i "s/^S3_ACCESS_KEY=.*/S3_ACCESS_KEY=$(openssl rand -hex 12)/" .env && sed -i "s/^PSEUDONIMIZACAO_SEGREDO=.*/PSEUDONIMIZACAO_SEGREDO=$(openssl rand -hex 32)/" .env
```

O `.env` nunca é versionado (`.gitignore`). Só letras e números nas senhas, para nenhuma string de conexão quebrar. As portas e os endereços locais (`127.0.0.1`) podem ficar como estão. O último valor é o segredo da pseudonimização da silver: a chave de cada pessoa é derivada dele, e trocá-lo depois troca todas as chaves ([Silver, seção 3](14_silver.md)).

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

Espera os containers ficarem saudáveis e prova o que está dentro deles: réplica com 76 tabelas, 75 gatilhos e cifra ativa; bucket do lake; warehouse; Dagster com a code location e os sensores; Grafana com fontes, painel e alertas. Termina em **`PLATAFORMA OK`**, com dois avisos que são normais na primeira subida: "ainda sem execução registrada" (o job de verificação logo abaixo resolve) e a API "ainda sem o usuário api no warehouse" (o `--preparar` da seção 7 resolve). Até a v1.0.0 o segundo era contado como falha, e a reprodução do zero de 08/10/2026 foi o que mostrou isso (seção 10).

Depois, a primeira execução de verdade, pela linha de comando:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j verificar_plataforma
```

Ou pela interface: <http://127.0.0.1:3010> → *Jobs* → `verificar_plataforma` → *Materialize all*. Em até 15 segundos o sensor grava as métricas e o painel do Grafana (<http://127.0.0.1:3011>, usuário e senha do `.env`) mostra a execução.

A esteira inteira (`bash scripts/esteira.sh`) fica para o fim da seção 7, de propósito: os testes vivos pressupõem a base carregada, e numa plataforma vazia 17 deles reprovam e 31 nem montam (medido na reprodução do zero de 08/10/2026, seção 10). Até a v1.0.0 este documento a pedia aqui, e prometia verde.

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

Numa distribuição recém-criada o disco virtual ainda cresce a cada escrita, e a mesma geração levou 17 minutos na reprodução do zero de 08/10/2026 (seção 10); da segunda vez em diante, o tempo é o da tabela.

O aceite da base fica para depois do backfill (seção 7, passo 1): um dos 166 checks, o C-06, confere a bronze contra a réplica, e antes de o lake existir ele não tem o que medir. Pedir o aceite com `--replica` agora termina em `bronze vazia` e não grava nada.

## 7. Levar a base ao lake e ao warehouse: bronze, silver, gold

A base está na réplica. Quatro passos a levam ao lake e ao warehouse, e do terceiro em diante é automático.

**1. As cargas iniciais.** As 76 tabelas entram pelo backfill, na interface do Dagster (<http://127.0.0.1:3010>): *Jobs* → `backfill_bronze` → *Materialize all* → backfill das nove partições, de 2018 a 2026. São cerca de 2 minutos ([Ingestão, seção 3](11_ingestao.md)). As nove planilhas do consolidado entram do mesmo jeito, pelo job `carregar_consolidado`. Quem prefere o terminal pede o mesmo backfill ao daemon, que é o que a interface faz (o `job execute` não aceita partição; o `job backfill` sim):

```bash
docker compose exec dagster-web dagster job backfill -m rh_fictalent.orquestracao.definicoes -j backfill_bronze --partitions 2018,2019,2020,2021,2022,2023,2024,2025,2026 --noprompt
```

```bash
docker compose exec dagster-web dagster job backfill -m rh_fictalent.orquestracao.definicoes -j carregar_consolidado --partitions 2018,2019,2020,2021,2022,2023,2024,2025,2026 --noprompt
```

Se o backfill da bronze for pulado, a primeira carga incremental percebe a tabela sem marca e sem bronze e recopia tudo sozinha (10 minutos em vez de 2, porque faz tabela a tabela); as planilhas, não: elas só entram pelo job delas. As três fontes públicas entram pela linha de comando (os feriados, um ano por vez; repita para os anos de 2018 a 2026):

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j carregar_municipios
```

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j carregar_caged
```

```bash
docker compose exec dagster-web dagster asset materialize -m rh_fictalent.orquestracao.definicoes --select "fontes/brasilapi/feriados" --partition 2024
```

As cinco cargas são necessárias: a leitura do lake cria uma view por conjunto, e conjunto sem arquivo nenhum faz a abertura falhar.

Com a bronze cheia, o aceite: a base inteira contra a régua inteira, com as linhas contadas na réplica e a conservação medida no lake.

```bash
.venv/bin/python -m rh_fictalent.gerador --aceite --replica
```

Termina em **`RÉGUA APROVADA: 166 de 166`** e reescreve `dados/regua/medidas.json` e `laudo.txt` com o mesmo conteúdo que está versionado; as nove planilhas de `dados/gerencial` também saem byte a byte iguais às versionadas. Se `git status` mostrar diferença, a sua base não é a do repositório. O que cada check confere está em [Régua de Validação](06_regua_de_validacao.md).

**2. A primeira carga incremental.** Ela cria a marca d'água de cada tabela, de onde sai a data de referência das regras com prazo:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j carga_incremental
```

**3. A silver, sozinha.** Ao fim da carga, o sensor `silver_depois_da_carga` dispara o job `construir_silver`: o descarte de dado pessoal, as 76 tabelas pseudonimizadas e conferidas, e a prestação de contas. São 78 passos em cerca de 3 minutos; acompanhe em *Runs*. Para conferir pela linha de comando:

```bash
.venv/bin/python -m rh_fictalent.silver --prestar-contas
```

Termina em **`34 regras conferidas; 0 reprovadas`**. O número bate porque o gerador é determinístico: a sua base é a mesma que foi auditada, e cada regra reproduz o que a auditoria mediu ([Silver, seção 6](14_silver.md)).

**4. A gold e o warehouse, sozinhos.** Ao fim da silver, o sensor `gold_depois_da_silver` dispara o job `construir_gold` (as 11 dimensões, os 14 fatos e a régua da gold, 26 passos em cerca de 1 minuto) e, ao fim dele, o sensor `warehouse_depois_da_gold` dispara o `carregar_warehouse` (as 25 tabelas no Postgres, os índices, o DCL e o RLS, 28 passos em pouco mais de 2 minutos). Acompanhe em *Runs*; os dois também rodam pela linha de comando, nesta ordem:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j construir_gold
```

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j carregar_warehouse
```

Para conferir: `.venv/bin/python -m rh_fictalent.gold --regua` termina em **`RÉGUA DA GOLD APROVADA: 187 de 187`** ([Gold, seção 6](16_gold.md)), e no warehouse `SET ROLE perfil_financeiro` seguido de `SELECT count(*) FROM fato.faturamento` devolve 9.934 ([Warehouse, seção 8](17_warehouse_postgres.md)).

**5. A API, para quem vai ler.** Com o warehouse carregado, prepare o usuário da API, cadastre um consumidor no seu perfil e um token (gere com `openssl rand -hex 32`; o cadastro o pede escondido):

```bash
.venv/bin/python -m rh_fictalent.api --preparar && .venv/bin/python -m rh_fictalent.api --consumidor eu_socio --perfil socio && .venv/bin/python -m rh_fictalent.api --token eu_socio
```

O token é digitado no terminal, de propósito: o cadastro lê do teclado (não de um pipe nem de um argumento) para o segredo não ficar em histórico nem em script. Abra `http://127.0.0.1:8010/v1/docs`, autorize com o token e peça `/v1/filiais`; ou, no terminal, `curl` como o [API, seção 4](18_api.md) mostra.

**6. A esteira inteira, igual à CI.** Agora, com a base na réplica, no lake e no warehouse e a API preparada:

```bash
bash scripts/esteira.sh
```

Lint, tipos, testes (os vivos rodam contra a plataforma de pé e conferem o que foi carregado), bandit, pip-audit e, com o docker disponível, gitleaks e trivy (na primeira vez, as duas imagens são baixadas). Termina em `ESTEIRA VERDE`. Antes da base, não: os testes perguntam à bronze por um parquet, à réplica por um contrato de 2019 e ao warehouse pela tabela de tokens, e a resposta vazia é reprovação, não pulo. É assim de propósito: a esteira é o espelho da CI sobre a plataforma inteira, e um teste que pula quando falta dado esconderia uma carga que não aconteceu.

**Opcional: o prazo de retenção.** A base gerada não traz prazo de retenção, porque ele é decisão do cliente. Para declará-lo, como o caso fez em 01/10/2026:

```bash
.venv/bin/python -m rh_fictalent.gerador --parametro RETENCAO_CANDIDATO_DIAS 730 2026-10-01
```

A carga incremental seguinte traz o parâmetro, e o descarte apaga da bronze o dado pessoal dos candidatos não contratados sem atividade há mais de 730 dias, registrando o efeito em cada regra. O número de candidatos alcançados depende do dia em que você roda, porque o prazo conta a partir da data da carga.

## 8. O que está onde

| endereço | o quê | credencial |
|---|---|---|
| `127.0.0.1:3316` | réplica MySQL (10 databases) | `root` com `STAGING_ROOT_PASSWORD`; ou `pipeline`, `relatorios_cliente`, `replicador` com as senhas do `.env` |
| `127.0.0.1:5441` | warehouse Postgres (`dw_fictalent`) | `fictalent_admin` com `DW_ADMIN_PASSWORD`; `grafana_leitor` só leitura; os leitores de negócio entram por um papel de login criado no perfil deles (`perfil_socio`, `perfil_gerencia`, `perfil_coordenacao`, `perfil_assistente`, `perfil_financeiro`), pelo rito do [Warehouse, seção 5](17_warehouse_postgres.md) |
| `127.0.0.1:8333` | lake S3 (bucket `fictalent-lake`) | `S3_ACCESS_KEY` e `S3_SECRET_KEY` |
| <http://127.0.0.1:3010> | Dagster | sem autenticação (só localhost) |
| <http://127.0.0.1:3011> | Grafana | `admin` com `GRAFANA_ADMIN_PASSWORD` |

Tudo escuta só em `127.0.0.1`: nada fica acessível a partir da rede. Para um cliente de banco (DBeaver, por exemplo), use esses endereços; no MySQL deixe o campo *Database* vazio para ver os 10 databases.

## 9. Atualizar, recomeçar, desinstalar

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

## 10. Reproduzir numa máquina limpa

O trilho `réplica provada` da CI clona, gera um `.env`, sobe a réplica e roda os testes de integração num runner descartável a cada PR; mas ele não gera a base nem leva o dado até o warehouse. Por isso, antes de fechar a v1.0.0, este documento foi seguido ao pé da letra numa máquina que nunca tinha visto o projeto: uma distribuição WSL2 recém-instalada (Ubuntu 24.04, em 08/10/2026), com Docker Engine, uv e o clone por HTTPS feitos como a seção 1 e a seção 2 mandam, e cada passo cronometrado. O que a tabela mostra é o que uma pessoa com o manual na mão encontra.

| passo | tempo medido | o que saiu |
|---|---|---|
| seção 1 e 2: Docker Engine, uv, clone, `uv sync --frozen` | 70 s (mais o `apt`) | venv igual à do autor |
| seção 3: `.env` pelo comando do manual | 1 s | 27 variáveis, nenhuma vazia |
| seção 4: `docker compose up -d --build` | 312 s | 8 serviços saudáveis |
| seção 5: `saude.sh` e `verificar_plataforma` | 41 s e 21 s | dois avisos, nenhuma falha |
| seção 6: as seis etapas do gerador | 1.051 s (17 min) | 8,4 milhões de linhas |
| seção 7: fontes públicas e consolidado | 263 s | cinco conjuntos no lake |
| seção 7: primeira carga incremental (recopiou a bronze inteira) | 588 s | 76 tabelas |
| silver, gold e warehouse, pelos sensores | 503 s, 179 s e 536 s | 34 regras, 0 reprovadas; 187 de 187; 25 tabelas |
| aceite com a bronze cheia | 113 s | 166 de 166, `git status` limpo |
| API: preparar, consumidor, token, `/v1/filiais` | 10 s | 200 com as três filiais |
| esteira inteira | 973 s | 654 testes, 1 pulado (o Neon, sem `NUVEM_*`) |
| trilha: as treze perguntas e o relatório | 60 s | 14 arquivos |
| backup pequeno e prova de restauração | 46 s e 60 s | tudo confere |

Os tempos são maiores que os das seções anteriores porque o disco virtual de uma distribuição nova cresce a cada escrita; da segunda rodada em diante eles caem para os valores de lá. A distribuição inteira, com imagens, volumes e a base, ocupou 15 GB, e a plataforma de pé com tudo carregado usou 6 GB de memória.

A reprodução achou sete coisas que a máquina do autor escondia, todas corrigidas no mesmo card. O `saude.sh` contava como falha a API ainda sem o usuário `api` no warehouse, que é o estado normal de uma plataforma recém-nascida (virou aviso). A esteira era pedida na seção 5, antes de a base existir, e prometia verde: 17 testes reprovavam e 31 nem montavam, porque perguntam à bronze, à réplica e ao warehouse por dados que ainda não há (mudou para o fim da seção 7). O aceite com `--replica` quebrava numa bronze vazia com um erro do DuckDB em vez de dizer que o C-06 não tem o que medir (agora avisa e sai sem gravar, e o aceite mudou para depois do backfill). As nove planilhas do consolidado saíam diferentes das versionadas a cada geração, porque o openpyxl carimba a hora da gravação (o gerador fixa o instante no fechamento do ano, e o arquivo sai byte a byte igual). O `esteira.sh` só conhecia o caminho do `uv` da máquina do autor (procura em `~/.local/bin` e no mise, e aceita `UV=`). E duas lições do WSL2, registradas na seção 1 e em [Solução de problemas](20_solucao_de_problemas.md): um só Docker Engine por máquina, porque o segundo quebra a rede dos containers do primeiro (foi a causa das quedas de rede de setembro), e a distribuição desliga sozinha sem um terminal aberto, o que corrompeu um MySQL na primeira inicialização. Um SSD externo por USB também foi tentado e descartado com medida: a escrita sincronizada saiu 140 vezes mais lenta, e os bancos não sobem direito nele.

Se um passo daqui falhar na sua máquina e não falhou nesta, a diferença está no ambiente (versão do Docker, porta ocupada, WSL sem memória), e [Solução de problemas](20_solucao_de_problemas.md) tem os sintomas conhecidos.

---

[Início](#topo)
