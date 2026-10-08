<a id="topo"></a>

# Do zero ao pipeline · o passo a passo de quem vai construir um destes

<!-- nav:start -->
[Home](../README.md) | [← Solução de problemas](20_solucao_de_problemas.md) | [Bibliografia →](bibliografia.md)
<!-- nav:end -->

> Este é o guia para construir um projeto como este **com as próprias mãos**, de uma máquina vazia até o backend servindo a API, na ordem real em que este repositório foi construído (a ordem do kanban, não a ordem de leitura dos documentos). Ele não ensina a copiar o código daqui: ensina a sequência de decisões, o que cada peça resolve, os comandos para fazer você mesmo, onde comparar com o que está pronto, o que ler antes de cada passo (com livro e capítulo do acervo, ou "buscar na internet" quando o acervo não cobre) e um exercício de mão por capítulo. Foi escrito para quem vai abrir o guia num monitor e um terminal no outro, e anotar enquanto constrói. O capítulo 9 é o rito de Git e Gitflow, porque metade do que dá errado num projeto de dados não é dado.

## 0. A máquina

Tudo o que vem depois supõe um Linux com Docker. No Windows o caminho é o WSL2, e a reprodução do zero de 08/10/2026 ([Instalação, seção 10](07_instalacao_e_reproducao.md)) pagou três lições que viram regras antes do primeiro comando: a distribuição mora num **disco interno** (num SSD externo por USB a escrita sincronizada saiu 140 vezes mais lenta e os bancos não subiram direito); **um só Docker Engine por máquina**, porque todas as distribuições WSL2 dividem o mesmo VM e a mesma rede, e um segundo daemon quebra os containers do primeiro; e **um terminal fica aberto na distribuição** enquanto a plataforma sobe, porque sem sessão ligada o WSL a desliga em segundos.

No PowerShell, uma distribuição nova, com nome e lugar escolhidos (o `--location` é o que a tira do disco `C:`):

```bash
wsl --install Ubuntu-24.04 --name fictalent-dev --location D:\wsl\fictalent-dev
```

Na primeira entrada o Ubuntu pede um nome de usuário e uma senha; esse usuário é o seu, com `sudo`. Confira que o `systemd` está ligado (o Ubuntu 24.04 do WSL já vem assim; `systemctl is-system-running` responde `running`); se não estiver, `/etc/wsl.conf` recebe `[boot]` e `systemd=true`, e `wsl --terminate fictalent-dev` no PowerShell reinicia a distribuição. Dentro dela, o básico:

```bash
sudo apt update && sudo apt install -y ca-certificates curl git openssl
```

O Docker Engine vem do repositório oficial, seguindo a página de instalação para Ubuntu em <https://docs.docker.com/engine/install/ubuntu/> (os cinco comandos do *apt repository*), e o seu usuário entra no grupo `docker` para não precisar de `sudo` a cada comando; saia e entre de novo para o grupo valer. O `uv` vem do instalador oficial (<https://docs.astral.sh/uv/getting-started/installation/>) e mora em `~/.local/bin`; o `gh` vem do repositório do GitHub (<https://github.com/cli/cli/blob/trunk/docs/install_linux.md>). Depois, a sua identidade no git e uma chave para o GitHub:

```bash
git config --global user.name "Seu Nome" && git config --global user.email "voce@exemplo.com" && ssh-keygen -t ed25519 -C "voce@exemplo.com"
```

A chave pública (`~/.ssh/id_ed25519.pub`) entra em *Settings → SSH and GPG keys* no GitHub; `gh auth login` escolhendo SSH como protocolo fecha o acesso (sem navegador no WSL, o `gh` mostra um código para digitar em `github.com/login/device`). Confira tudo de uma vez:

```bash
docker compose version && python3 --version && uv --version && git --version && gh --version && ssh -T git@github.com
```

**Onde está aqui.** [Instalação, seção 1](07_instalacao_e_reproducao.md), a tabela do que precisa estar instalado, e a seção 10, com o que aconteceu ao fazer isso numa máquina limpa.

**O que ler.** Foca Linux, volume iniciante (acervo): o shell, permissões, usuários e grupos, que é o que `sudo`, `usermod -aG docker` e `chmod 600` estão mexendo. Buscar na internet: *WSL2 systemd*, *Docker Engine post-install steps* (o grupo `docker`), *ssh-keygen ed25519 GitHub*.

**Exercício.** Desligue e religue a distribuição (`wsl --terminate` e entrar de novo) e confira que o Docker volta sozinho (`systemctl is-active docker`). Se não voltar, o `systemd` não está ligado, e é melhor descobrir agora.

## 1. Antes de codar

Este projeto começou com dez dias sem uma linha de código, e foi a fase em que mais se decidiu. O caso foi lido inteiro (quem é a empresa, o que ela vende, o que quebrou), as perguntas que um consultor faria ao cliente foram escritas e respondidas, e só então a pilha foi escolhida: MySQL na réplica porque o cliente tem MySQL, Postgres no warehouse porque é o melhor banco analítico gratuito, Dagster porque orquestra por asset, SeaweedFS porque fala S3 num container só, DuckDB porque lê parquet onde ele estiver. Cada escolha virou um registro de decisão (ADR) de uma página, com a necessidade do caso que ela atende, e isso é o que permite trocar a peça depois sem reabrir a discussão.

**Faça você.** Escreva, antes de qualquer `mkdir`, os três documentos que todo projeto desta série tem: o entendimento do negócio (quem é, como ganha dinheiro, o que quer saber), o entendimento dos dados (que sistemas existem, que tabelas, que qualidade esperar) e a arquitetura (as camadas, a ferramenta de cada uma e o porquê). Se o caso é fictício, o dossiê é seu e as respostas também; se é real, as perguntas vão para o cliente. Decida a pilha por ADR. Então o repositório:

```bash
mkdir meu-projeto && cd meu-projeto && git init -b main && uv init --package --python 3.12 && git add -A && git commit -m "esqueleto"
```

```bash
gh repo create seu-usuario/meu-projeto --public --source=. --push && git checkout -b develop && git push -u origin develop
```

(O `git add -A` só é aceitável neste primeiro commit, quando o diretório é só o esqueleto; a partir daí, `git add` é por caminho, sempre.) No GitHub, em *Settings → Branches*, proteja `main` e `develop`: exigir PR e os checks da CI antes de mesclar; em *Settings → General*, ligue *Automatically delete head branches*. Deixe `main` como branch padrão: é a que o visitante clona.

**Onde está aqui.** [Entendimento do Negócio](01_entendimento_negocio.md), [Entendimento dos Dados](02_entendimento_dados.md), [Arquitetura](03_arquitetura.md), os [registros de decisão](adr/README.md) (onze, do MySQL na réplica ao `httpx` na ingestão) e o [Modelo de Dados](04_modelo_dados_staging.md), que nasceu do caso com cinco perguntas por tabela (chave, carimbos, exclusão, dado pessoal, volume).

**O que ler.** FoDE cap. 1 e 2, o ciclo de vida da engenharia de dados e os *undercurrents* (acervo): é a espinha da arquitetura. FoDE cap. 4, *Choosing Technologies* (acervo): o roteiro de perguntas que cada ADR responde. FoDE cap. 5, *Data Generation in Source Systems* (acervo): o que perguntar sobre um sistema de origem. DDIA cap. 2, modelos de dados (acervo). Karwin, parte I (fora do acervo): os antipadrões de modelagem que as cinco perguntas evitam.

**Exercício.** Escreva um ADR de verdade para uma escolha sua (um banco, uma biblioteca) com as quatro partes: contexto, decisão, consequências, alternativas descartadas. Se não couber numa página, a decisão ainda não está clara.

## 2. Fundação segura

A primeira versão publicável deste projeto não tinha uma linha de dado: tinha a plataforma de pé e a prova, por teste, de que o dado pessoal estaria protegido antes de existir. A ordem importa, e é esta: o `pyproject.toml` e o `uv.lock` (as dependências pinadas, para a máquina de qualquer um ser igual à sua); o `compose.yaml` com os bancos, o S3, o Dagster e o Grafana, cada serviço com `healthcheck` e portas só em `127.0.0.1`; o `.env.example` com todas as variáveis e o `.env` fora do git; a DDL da réplica, módulo a módulo, com um comentário por coluna e uma etiqueta LGPD onde há dado pessoal; e, **gerados da DDL**, os gatilhos da trilha de exclusões, os papéis com `GRANT` coluna a coluna e o dicionário de dados. Gerar em vez de digitar é a regra que mais economizou retrabalho aqui: quando uma tabela muda, os três se refazem com um comando e um teste avisa se alguém esqueceu.

**Faça você.** Comece pelo Compose com um banco só e um `healthcheck`, suba, derrube, suba de novo; só então acrescente o próximo serviço. Para a DDL, escreva uma tabela com as cinco perguntas respondidas no comentário (chave, `criado_em`, `atualizado_em`, `excluido_em` ou gatilho, etiqueta `lgpd:`). Os geradores deste repositório são pequenos e vale lê-los antes de escrever os seus:

```bash
.venv/bin/python -m rh_fictalent.staging.gatilhos && .venv/bin/python -m rh_fictalent.staging.dicionario
```

A cifra em repouso vem no fim da fase, quando a DDL já está estável: o componente de keyring do MySQL, `ENCRYPTION='Y'` em cada tabela, redo e undo cifrados, e um teste que procura uma string conhecida no arquivo do disco e exige não encontrar. A CI nasce junto, em três trilhos: qualidade (`ruff`, `mypy`, `pytest`), a réplica provada num runner descartável (sobe o MySQL com um `.env` gerado e roda os testes de integração) e segurança (`bandit`, `pip-audit`, `gitleaks`, `trivy`). O espelho local é um script, `esteira.sh`, que roda o mesmo antes de cada PR.

**Onde está aqui.** [`compose.yaml`](../compose.yaml), [`.env.example`](../.env.example), [`staging/ddl`](../staging/ddl), [`src/rh_fictalent/staging`](../src/rh_fictalent/staging) (gatilhos, papéis, cifra, dicionário), [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), [`scripts/esteira.sh`](../scripts/esteira.sh); [Modelo de Dados](04_modelo_dados_staging.md), [Segurança e LGPD](05_seguranca_e_lgpd.md) e o [dicionário](dicionario/README.md).

**O que ler.** FoDE cap. 3, *Examples and Types of Data Architecture* (acervo): por que cada serviço é um container. FoDE cap. 10, *Security and Privacy* (acervo): menor privilégio e cifra em repouso. DEDP cap. 7, padrões de segurança (acervo). DQF cap. 2, o catálogo como produto gerado (acervo). DDIA cap. 11, *Change Data Capture* (acervo): a trilha de exclusões é um CDC feito à mão. Okken cap. 2 a 5 (fora do acervo): funções de teste, fixtures e parametrização, que a suíte usa desde o primeiro card. Foca Linux, volume intermediário (acervo): redes e portas. Buscar na internet: *Docker Compose healthcheck depends_on condition*, *MySQL component_keyring_file*, *uv lock frozen*.

**Exercício.** Acrescente uma coluna com etiqueta de dado pessoal a uma tabela, regenere os papéis e o dicionário e veja o `GRANT` do usuário de relatórios deixar de incluí-la. Depois rode a esteira e veja qual teste reprova se você esquecer de regenerar.

## 3. Orquestração e observabilidade

Antes de o dado entrar, a plataforma aprendeu a se explicar. O Dagster entrou com três recursos por ambiente (`Replica`, `Lake`, `Warehouse`, com os segredos lidos de variáveis, nunca escritos em código), um job de verificação que prova que os três respondem, e as convenções que todo asset depois seguiu (nome por camada e tabela, partição por ano ou por dia). O log passou a sair em JSON com o `run_id` em todo evento, para uma execução poder ser seguida de ponta a ponta com um `grep`. As métricas de cada execução (job, passo, duração, linhas, erro) vão para o warehouse por três sensores, um por desfecho, e o Grafana as mostra num painel provisionado como código, com duas regras de alerta. E o `saude.sh` passou a provar, em dois estágios, que os containers estão saudáveis e que o que está dentro deles funciona.

**Faça você.** O vocabulário do Dagster está no [Manual de Operação, seção 6](08_manual_de_operacao.md): *asset* é uma coisa que existe (uma tabela, um arquivo) e a função que a produz; *job* é um conjunto de assets para materializar juntos; *run* é uma execução; *sensor* dispara um job quando algo acontece; *schedule* dispara por relógio. Comece com um asset que conta as linhas de uma tabela, um job que o contém e o `dagster dev` local, e só depois ponha o Dagster no Compose (um container para a interface, outro para o daemon, os dois com a mesma imagem). Rode o primeiro job pelo terminal e pela interface:

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j verificar_plataforma
```

**Onde está aqui.** [`src/rh_fictalent/orquestracao`](../src/rh_fictalent/orquestracao) (`recursos.py`, `definicoes.py`, os sensores de métricas), [`src/rh_fictalent/observabilidade`](../src/rh_fictalent/observabilidade), [`infra/dagster`](../infra/dagster), [`infra/grafana`](../infra/grafana), [`scripts/saude.sh`](../scripts/saude.sh); [Monitoramento e Healthcheck](09_monitoramento_e_healthcheck.md).

**O que ler.** FoDE cap. 2, o *undercurrent* de orquestração (acervo). DEDP cap. 6, padrões de fluxo (acervo): sequência e *fan-in*. DEDP cap. 10, padrões de observabilidade (acervo). DQF cap. 4, monitorar frescor, volume e esquema (acervo), e cap. 5, SLAs e SLOs (acervo): os dois alertas daqui são SLOs. DDIA cap. 1 (acervo): o que "funciona" quer dizer, que é o critério do healthcheck. Storytelling cap. 2 e 3 (acervo): um painel de operação também é um gráfico, e a saturação é inimiga. Buscar na internet: *Dagster run status sensor*, *Grafana provisioning dashboards*.

**Exercício.** Faça um asset falhar de propósito (uma divisão por zero) e siga a execução pelo `run_id`: na interface, no log em JSON, na tabela de métricas e no painel do Grafana. Os quatro lugares têm de contar a mesma história.

## 4. Dado sintético

O projeto precisava de 8,4 milhões de linhas de uma empresa que não existe, e a decisão que fez a diferença foi escrever o **contrato antes do gerador**: a régua, 166 checks em seis famílias, cada um com uma banda tirada do entendimento do negócio (quantos clientes ativos em cada ano, qual o *time to fill*, quanta sujeira de cadastro é verossímil). O gerador então foi construído em seis etapas, cada uma gerando em memória, conferindo a si mesma contra a parte da régua que lhe cabe e só então gravando na réplica numa transação. A sazonalidade mensal não é inventada: sai dos microdados do Novo CAGED para os CNAEs do caso. E a semente fixa faz a mesma base nascer em qualquer máquina, que é o que permitiu versionar o laudo e a reprodução do zero conferir "166 de 166" ([Instalação, seção 10](07_instalacao_e_reproducao.md)).

**Faça você.** Escreva primeiro dez checks com banda, em código (uma `dataclass` com nome, família, banda e uma função que mede), e um laudo que diz aprovado, reprovado ou pendente. Só então gere: comece pelo cadastro (a etapa 1), com poucas tabelas, e rode a régua parcial a cada etapa. Para sortear, use um gerador com semente por etapa (`numpy.random.default_rng(semente)`) e distribuições com nome: binomial para "aconteceu ou não", Poisson para "quantas vezes", cauda longa para valores. Em paralelo SQL → pandas: o `GROUP BY competencia, filial_id` que confere o headcount é `df.groupby(["competencia", "filial_id"]).size()`, e o `HAVING` é um filtro depois do `groupby`.

```bash
.venv/bin/python -m rh_fictalent.gerador --etapa 1 --gravar --zerar && .venv/bin/python -m rh_fictalent.gerador --aceite --replica
```

**Onde está aqui.** [`src/rh_fictalent/validacao`](../src/rh_fictalent/validacao) (a régua), [`src/rh_fictalent/gerador`](../src/rh_fictalent/gerador) (núcleo, história, as seis etapas, o aceite), [`src/rh_fictalent/fontes`](../src/rh_fictalent/fontes) (CAGED, IBGE, BrasilAPI, com o cliente HTTP de retentativa), [`dados/regua`](../dados/regua); [Régua de Validação](06_regua_de_validacao.md).

**O que ler.** DQF cap. 3, *Alerting and Testing* (acervo): o teste unitário de dado é parente da régua. DEDP cap. 9, *audit-write-audit-publish* (acervo): o aceite por etapa é esse padrão. PracStat cap. 2, distribuições e amostragem (acervo), e cap. 3, *Multiple Testing* (acervo): com 166 checks, algum passa raspando por acaso. Tukey cap. 7, 10 e 11 (acervo): a análise linha-mais-coluna que separa o sazonal do tendencial no CAGED. DDIA cap. 8, redes não confiáveis (acervo), e DEDP cap. 3, padrões de erro (acervo): por que todo pedido HTTP tem timeout, recuo e limite. Kahneman, parte I (acervo): por que o gerador precisa de ruído e de cauda, e por que "parece plausível" não é critério.

**Exercício.** Aperte uma banda até a régua reprovar, leia o laudo, e decida se o erro é da banda ou do gerador. Essa é a conversa que o aceite obriga a ter.

## 5. Ingestão

O dado entrou por três portas, como no caso real: a réplica relacional (backfill histórico e carga incremental diária), as APIs públicas (municípios, feriados) e o arquivo (as planilhas da gerente-geral). A bronze é parquet em S3, uma tabela por pasta, um arquivo por ano de criação da linha, e promete ser espelho fiel da réplica: o backfill lê com cursor em streaming, grava em zstd e confere a contagem contra uma foto consistente do banco. A carga incremental usa marca d'água pela coluna `atualizado_em` da réplica (não o binlog, e o ADR-0011 diz por quê), com uma hora de sobreposição e merge por id, o que a torna idempotente: rodar duas vezes a mesma janela não muda nada. As exclusões viram marcação (`excluido_em`), nunca apagamento, lidas da trilha de gatilhos da fase 2. As planilhas passam por um esquema estrito (`pandera`) e pelo total que a gerente fechou. E um simulador faz a réplica se mexer um dia por vez, para a carga diária ter o que trazer.

**Faça você.** Backfill de uma tabela só, por ano, com a contagem conferida; depois a marca d'água, numa tabela de controle no warehouse; depois a janela com sobreposição e o merge por id. Teste a idempotência antes de qualquer coisa: a mesma janela duas vezes, o mesmo parquet. Em SQL → pandas: o `WHERE atualizado_em > :marca AND atualizado_em <= :corte` vira `df[(df.atualizado_em > marca) & (df.atualizado_em <= corte)]`, e o merge por id é "remova todas as linhas com esses ids e acrescente as novas" (`df[~df.id.isin(novos.id)]` seguido de `concat`).

```bash
docker compose exec dagster-web dagster job backfill -m rh_fictalent.orquestracao.definicoes -j backfill_bronze --partitions 2018,2019,2020,2021,2022,2023,2024,2025,2026 --noprompt
```

**Onde está aqui.** [`src/rh_fictalent/ingestao`](../src/rh_fictalent/ingestao) (backfill, marca d'água, incremental, exclusões, planilhas), [`src/rh_fictalent/simulacao`](../src/rh_fictalent/simulacao), [`src/rh_fictalent/lake`](../src/rh_fictalent/lake), os jobs `backfill_bronze`, `carga_incremental`, `carregar_consolidado`, `carregar_municipios`, `carregar_caged`, `carregar_feriados` e a agenda `carga_incremental_diaria`; [Ingestão](11_ingestao.md) e [Bronze](12_bronze.md).

**O que ler.** FoDE cap. 7, *Ingestion* (acervo): as perguntas (bounded ou unbounded, frequência, serialização, confiabilidade) são o esqueleto da fase. FoDE cap. 6 e apêndice A (acervo): parquet, colunar, compressão. DDIA cap. 3 (acervo): como o armazenamento funciona por baixo. DDIA cap. 7, *Snapshot Isolation* (acervo): a foto consistente do backfill. DDIA cap. 11, *Event Sourcing* e imutabilidade (acervo): a bronze que marca em vez de apagar. DEDP cap. 2 e 4, carga incremental e idempotência (acervo). AWS cap. 6, ingerir de um banco relacional (acervo). DQF cap. 3, esquema e coerção de tipos (acervo), e McKinney cap. 7 (fora do acervo, lido de graça no site do autor): limpeza e preparação em pandas.

**Exercício.** Altere uma linha na réplica com o usuário que escreve (`replicador`), rode a carga incremental e ache a linha nova na bronze com DuckDB. Depois apague uma linha e veja a trilha explicar a marcação. Se o apagamento não deixar trilha, o gatilho da fase 2 não está armado.

## 6. Lake e silver

Com a bronze cheia, o projeto parou para olhar o dado antes de transformá-lo. O DuckDB passou a abrir a bronze inteira como views com os nomes da réplica, e a auditoria de qualidade foi feita **às cegas**: dez notebooks, um por domínio, só com o esquema e o entendimento do negócio como referência, sem olhar o gerador (um teste reprova o notebook que o importe). Os 61 achados viraram um catálogo como código, com uma redação para quem decide e outra para quem implementa, aprovado entrada a entrada pelo Tiago no papel de cliente antes de qualquer transformação. Só então a silver: a bronze linha a linha, mais as colunas das 34 regras aprovadas, gravada numa área de conferência, provada em quatro provas e publicada; a prestação de contas roda cada regra na data da auditoria e exige o mesmo número. A pseudonimização (documento vira HMAC com um segredo do `.env`, nascimento vira ano, nome e contato não entram) e o descarte por retenção, com cadeia de custódia, fecharam a fase.

**Faça você.** Abra a bronze com DuckDB e responda dez perguntas do negócio em SQL antes de escrever uma linha de transformação; anote o que não bate. Para cada achado, decida: corrigir na origem, marcar na silver, derivar coluna, conformar nome ou ignorar com motivo. Escreva a silver como uma função por tabela que recebe a bronze e devolve a bronze mais colunas, nunca menos linhas. Em SQL → pandas, a marca de qualidade `CASE WHEN cpf !~ '^\d{11}$' THEN true ELSE false END` é `df.cpf.str.fullmatch(r"\d{11}").eq(False)`, e a conferência "mesmas linhas" é `len(silver) == len(bronze)` mais um `merge` por id com `indicator=True`.

```bash
.venv/bin/python -m rh_fictalent.auditoria --executar && .venv/bin/python -m rh_fictalent.silver --publicar && .venv/bin/python -m rh_fictalent.silver --prestar-contas
```

**Onde está aqui.** [`src/rh_fictalent/lake/consulta.py`](../src/rh_fictalent/lake/consulta.py), [`src/rh_fictalent/auditoria`](../src/rh_fictalent/auditoria) e [`notebooks/auditoria`](../notebooks/auditoria), [`src/rh_fictalent/silver`](../src/rh_fictalent/silver), [`src/rh_fictalent/lgpd`](../src/rh_fictalent/lgpd); [Bronze](12_bronze.md), [Catálogo de achados](13_catalogo_de_achados.md) e [Silver](14_silver.md), com a investigação da queda de conexão com o lake na seção 8 da bronze.

**O que ler.** PracStat cap. 1, análise exploratória (acervo), e Tukey cap. 2 (acervo): como olhar dado antes de ter hipótese. DQF cap. 6, causa raiz (acervo), e cap. 8, dado como produto (acervo): achado sem causa não vira regra. DEDP cap. 9, *Quality Enforcement* (acervo): a área de conferência e a publicação condicionada. DEDP cap. 7, padrões de proteção e remoção de dado (acervo): HMAC, retenção, direito ao esquecimento. FoDE cap. 8, *Queries* (acervo): o DuckDB é o motor dessa seção. DDIA cap. 8, *Unreliable Networks* (acervo): a investigação da queda de conexão. Buscar na internet: *DuckDB httpfs S3*, *HMAC pseudonymization LGPD*.

**Exercício.** Pegue um achado seu e escreva as duas redações: a de uma frase para o dono do negócio ("há 1.200 CPFs inválidos, 3% do cadastro") e a de implementação ("marcar `q_cad_01` quando o CPF não tiver onze dígitos ou o dígito verificador falhar"). Se a segunda não sai de uma linha, o achado ainda não está entendido.

## 7. Gold e warehouse

A gold começou por um desenho aprovado antes de existir: a matriz de barramento, com os fatos e o grão de cada um, as dimensões que eles dividem, de qual fato sai cada indicador, gerada como documento a partir do código e aprovada como proposta. Depois, cada dimensão conformada e cada fato por processo foram montados da silver por SQL declarado, gravados em conferência e provados em cinco provas (grão, referências, conservação de cada total ao centavo, dimensão de pessoa sem identidade, partição) antes de publicar. O SQL analítico veio em seguida, com funções de janela explícitas e comentadas. E o warehouse Postgres recebeu a gold por partição, com a DDL gerada do modelo, cinco perfis de negócio em DCL provado por teste (o acesso indevido tem de falhar), *row level security* por filial e índices adotados só com a medida do `EXPLAIN ANALYZE`. Dois sensores fecharam a cadeia do dia: a silver dispara a gold, a gold dispara o warehouse.

**Faça você.** Desenhe a matriz antes: uma tabela com os fatos nas linhas, as dimensões nas colunas e o grão escrito numa frase ("uma linha por posto por dia de ponto"). Construa a primeira dimensão (a de tempo), o primeiro fato, e a prova de conservação (a soma do fato é a soma da silver, ao centavo). Só então o resto. No Postgres, a ordem é DDL, carga, DCL, RLS, índices, cada um com o seu teste. Em SQL → pandas, a função de janela `SUM(faturamento) OVER (PARTITION BY cliente_id ORDER BY mes ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)` é `df.groupby("cliente_id").faturamento.transform(lambda s: s.rolling(12, min_periods=1).sum())`, e vale fazer as duas e comparar.

```bash
.venv/bin/python -m rh_fictalent.gold --matriz && .venv/bin/python -m rh_fictalent.gold --publicar && .venv/bin/python -m rh_fictalent.gold --regua
```

```bash
.venv/bin/python -m rh_fictalent.gold --warehouse && .venv/bin/python -m rh_fictalent.gold --dcl --aplicar && .venv/bin/python -m rh_fictalent.gold --rls --aplicar && .venv/bin/python -m rh_fictalent.gold --indices --medir
```

**Onde está aqui.** [`src/rh_fictalent/gold`](../src/rh_fictalent/gold) (barramento, modelo, construção, régua, analítico, warehouse, dcl, rls, índices), [`src/rh_fictalent/warehouse`](../src/rh_fictalent/warehouse), [`notebooks/gold`](../notebooks/gold); [Matriz de barramento](15_matriz_de_barramento.md), [Gold](16_gold.md) e [Warehouse Postgres](17_warehouse_postgres.md).

**O que ler.** Kimball cap. 1 a 4 (fora do acervo; é a compra mais importante do projeto): grão, dimensões conformadas, matriz de barramento, fatos por processo. Spark cap. 7, *Window Functions* (acervo): a melhor explicação de janela, vale para qualquer SQL. Karwin, parte III (fora do acervo): antipadrões de consulta e o *Index Shotgun*. DDIA cap. 3, *Transaction Processing or Analytics?* e índices (acervo). AWS cap. 9, antipadrões de warehouse (acervo). FoDE cap. 9, servir (acervo). Postgres 16, *Row Security Policies*, *Using EXPLAIN* e *SECURITY DEFINER* (documentação oficial, fora dos livros). DQF cap. 7, linhagem de ponta a ponta (acervo).

**Exercício.** Entre no warehouse como um perfil de filial (`SET ROLE`), conte um fato, troque de perfil e conte de novo. Depois tente ler a partição direto, por baixo da tabela. Se der certo, a RLS tem um buraco.

## 8. Servir e cuidar

A última fase do backend serve e protege: a API (FastAPI) lê o warehouse com um usuário sem direito nenhum, que a cada pedido assume o papel do consumidor (`SET LOCAL ROLE`), de modo que quem decide o que cada um vê é o banco, com o mesmo DCL e a mesma RLS, e não o código da API; o token é guardado só como hash e todo pedido deixa trilha. A trilha de auditoria ficou pronta como treze perguntas declaradas em código, sem dado pessoal, respondidas em tabela ou em relatório. O backup guarda réplica, chave, warehouse, Dagster e lake com um manifesto, e **prova** que restaura em alvos descartáveis antes de alguém precisar. E o mesmo warehouse foi carregado num Postgres gratuito em nuvem, para quem quer o painel fora da máquina, com a mesma DDL, o mesmo DCL e a mesma RLS, medidos.

**Faça você.** Comece a API por um endpoint de saúde e um de lista, com o banco decidindo o acesso; só depois o contrato inteiro. Cada erro tem um código e um teste: 401 sem token, 403 quando o perfil não lê a tabela, 422 para parâmetro errado. A trilha de auditoria nasce das perguntas que um auditor faria, escritas em português antes do SQL. O backup só existe quando o `--provar` passa.

```bash
.venv/bin/python -m rh_fictalent.api --preparar && .venv/bin/python -m rh_fictalent.api --consumidor eu_socio --perfil socio && .venv/bin/python -m rh_fictalent.api --token eu_socio
```

```bash
.venv/bin/python -m rh_fictalent.trilha --relatorio dados/auditoria/trilha && .venv/bin/python -m rh_fictalent.backup --fazer backups && .venv/bin/python -m rh_fictalent.backup --provar "$(ls -d backups/*/ | tail -1)"
```

**Onde está aqui.** [`src/rh_fictalent/api`](../src/rh_fictalent/api), [`src/rh_fictalent/trilha`](../src/rh_fictalent/trilha), [`src/rh_fictalent/backup`](../src/rh_fictalent/backup), o `--destino nuvem` da gold; [API](18_api.md), [Auditoria](10_auditoria.md), [Backup e restauração](19_backup_e_restauracao.md) e a seção 10 do [Warehouse](17_warehouse_postgres.md).

**O que ler.** FoDE cap. 9, *Ways to Serve Data* (acervo). DDIA cap. 4, *Dataflow Through Services* e compatibilidade de contrato (acervo): o `/v1`. Okken cap. 6 e 7 (fora do acervo): marcadores e estratégia de teste para uma API. FoDE cap. 10, *Processes* (acervo), e DDIA cap. 5 (acervo): o que uma restauração precisa reconstruir. Buscar na internet: *FastAPI dependencies security bearer*, *psycopg SET LOCAL ROLE*, *pg_dump custom format restore*.

**Exercício.** Cadastre um consumidor de filial, peça o funil e compare com o do sócio. Depois revogue o token e peça de novo. Depois restaure o backup num banco de prova e conte as linhas. Três provas, três minutos, e você sabe que o sistema faz o que diz.

## 9. O rito de Git e Gitflow

Metade do que trava um projeto não é código. Este é o rito que este repositório seguiu em 79 PRs e sete versões, com os tropeços incluídos.

**O desenho.** Duas branches vivem para sempre: `main` é o que está publicado (toda versão é uma tag nela) e `develop` é o que está pronto mas ainda não publicado. Cada card nasce de `develop` numa branch própria, volta por PR e morre. Cada fase fechada vira uma versão: PR de `develop` para `main`, tag, release, e um back-merge para `develop` ficar igual.

```
main     ──●───────────────●──────────────────●──────▶   (v0.6.0)      (v0.7.0)      (v1.0.0)
            \             ↑ \                ↑ \
develop  ────●──●──●──●──●──●──●──●──●──●──●──●──●──▶
              \    /  \    /     \       /  \     /
feature        ●──●    ●──●       ●──●──●    ●──●         (um card = uma branch = um PR)
```

**O rito do card**, inteiro no terminal, com a esteira verde antes:

```bash
git checkout develop && git pull --ff-only && git checkout -b feature/8.1-api
```

```bash
git add src/meu_modulo/novo.py tests/test_novo.py docs/18_api.md && git commit
```

```bash
git push -u origin "$(git branch --show-current)" && gh pr create --base develop --fill && gh pr checks --watch
```

```bash
gh pr merge --merge --delete-branch && git pull --ff-only && git log -1 --oneline
```

O `git add` é por caminho, sempre: `git add -A` é como um `.env` vai parar no GitHub. A mensagem do commit tem um título curto com o escopo (`feat(api): …`, `fix(ci): …`, `docs(8.6): …`) e um corpo que diz o que mudou e por quê, porque o `--fill` do `gh` faz dela o texto do PR. O `--watch` espera os três trilhos da CI e sai com erro se algum falhar, e é aí que se para: não se faz merge de PR vermelho, mesmo "sabendo" que é o ambiente. Depois do merge, a branch some no servidor (`--delete-branch`) e localmente (`git pull --ff-only` na `develop` já basta; `git branch -d` se sobrar).

**O rito da versão** tem cinco passos, nesta ordem, e a ordem importa ([Manual de Operação, seção 8](08_manual_de_operacao.md)): o card de fechamento (CHANGELOG, status no README, a versão no `pyproject.toml`, no `uv.lock` e na tag da imagem) entra em `develop` por PR; o PR de `develop` para `main` com o título da versão; a tag **só depois do merge**, conferindo que o último commit da `main` é o merge; o release no GitHub escolhendo a tag que já existe; e o back-merge de `main` para `develop`, **uma vez só**, por PR. Os dois tropeços reais: na v0.2.0 a tag foi criada antes do merge e marcou a `main` antiga; na v0.4.0 o back-merge foi feito duas vezes (por PR e localmente) e o push foi recusado, porque a `develop` local tinha um commit que o servidor não tinha. A saída de "push recusado" é sempre `git pull --ff-only`, nunca `--force`.

**Em equipe.** A fase é a release; o card é a feature; "sprint" é uma caixa de tempo, não uma branch. Ninguém faz push na `develop` nem na `main`: tudo entra por PR, com a CI verde e a revisão de um colega, e as duas branches são protegidas para o GitHub recusar o push direto. A `develop` nunca fecha: com dois ou três desenvolvedores, cada um tem a sua feature em paralelo, e quem vai abrir o PR primeiro atualiza a branch com a `develop` (`git merge develop` dentro da feature) para o PR entrar limpo.

**O hotfix do colega no mesmo arquivo.** Um bug em produção não espera a fase: o hotfix nasce da `main`, entra na `main` por PR, vira um patch (`v1.0.1`, tag e release) e volta para a `develop` por back-merge. No dia seguinte, a sua feature mexeu no mesmo arquivo. Você faz `git merge develop` dentro da feature; o Git marca o conflito com `<<<<<<<`, `=======` e `>>>>>>>`; você resolve preservando a correção do colega, roda os testes e só então abre o PR, que entra limpo. A regra: **quem chega depois resolve, na própria branch, antes do PR.** Para sentir isso sem medo, reproduza num repositório descartável: crie um arquivo, faça a `main` e uma feature mudarem a mesma linha, mescle e resolva. Dez minutos, e o conflito deixa de ser assustador.

**O que ler.** Pro Git, cap. 3, *Git Branching* (fora do acervo; lido de graça em <https://git-scm.com/book/pt-br>): branches, merge, conflito e o fluxo de trabalho. FoDE cap. 2, DataOps (acervo): versionamento e automação como parte do ciclo de vida. O [ADR-0008](adr/0008-gitflow-por-versao-publicavel.md). Buscar na internet: *conventional commits*, *GitHub branch protection rules*, *gh pr create fill*.

**Exercício.** Faça um card inteiro pelo rito, do `checkout -b` ao `merge --delete-branch`, num repositório seu, e anote cada ponto em que teve de olhar o guia. Na terceira vez não vai mais precisar.

## 10. Como seguir

O quarto projeto da série é seu: você escreve o código, monta o processo e faz os testes, com o Code como par (revisor, explicador, quem demonstra quando a explicação não basta), não como construtor. Vai demorar mais, e isso é o objetivo. O jeito de usar este guia é na ordem dos capítulos, um por vez, sem pular a máquina (capítulo 0) nem o "antes de codar" (capítulo 1), porque é aí que os projetos que dão errado dão errado. Em cada capítulo, faça o exercício antes de seguir, e anote no seu kanban privado o que travou: o worklog deste projeto tem 300 entradas, e as lições que viraram capítulo do `docs/20` nasceram todas de um tropeço anotado no dia.

Três compromissos para o caminho. O `git add` por caminho e o `.env` fora do git desde o primeiro commit. A régua antes do gerador, a prova antes de publicar, o backup provado antes de precisar: a ordem "contrato, depois construção, depois prova" vale em toda camada. E a bibliografia: cada capítulo aponta o livro e o capítulo; quando o acervo não cobre, a busca é dirigida ("buscar na internet: termo"), não aberta. A lista inteira, fase a fase e card a card, está na [Bibliografia](bibliografia.md).

---

[Início](#topo)
