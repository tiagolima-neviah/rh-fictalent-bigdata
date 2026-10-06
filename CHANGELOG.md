# Histórico de versões

Cada versão fecha uma fase inteira, com código, testes e documentação. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o [SemVer](https://semver.org/lang/pt-BR/).

## [0.7.0] · 2026-10-06 · Gold e warehouse

A matriz de barramento virou tabela: a **gold** existe, construída da silver por SQL declarado em código e provada em cinco provas antes de publicar, e o **warehouse Postgres** a serve com quem lê o quê provado por teste, filial a filial. A cadeia do dia fecha sozinha: a carga das 5h, a silver, a gold e o warehouse, cada camada disparada pelo fim da anterior. Ainda sem API nem destino em nuvem: isso é a v1.0.0.

### Matriz de barramento
- 20 fatos (14 de prioridade 1) e 14 dimensões declarados como código, com o grão de cada fato, as dimensões que dividem, de qual fato sai cada um dos 26 indicadores e como cada uma das sete afirmações dos donos é respondida. O `docs/15` é gerado e foi **aprovado como proposta antes de construir**; a regra do resultado por filial (ISS pela filial do município, imposto federal e retaguarda rateados pelo faturamento) foi aprovada em 06/10 pelo Tiago, no papel de cliente.

### Gold
- 11 dimensões conformadas e 14 fatos por processo, em parquet particionado por ano: 25 tabelas, **1,68 milhão de linhas em 11,9 MB**. Cada tabela é montada da silver, gravada em conferência, lida de volta e só então publicada, depois de cinco provas: grão, referências (a linha 0 inclusive), conservação de cada total ao centavo, dimensão de pessoa sem identidade, partição. A gold inteira em 8,8 s pela linha de comando; 26 passos em 56 s no Dagster.
- O **horizonte** (o último dia com movimento, 10/09/2026) e o **calendário** (até 31/12/2027) vêm do dado, nunca digitados; o mês do horizonte é marcado como parcial. A gold conta pessoas, não as identifica, e um teste reprova a dimensão que ganhar nome, documento ou chave.
- O Novo CAGED entrou no lake como asset (`fontes/caged/movimentacao`), e `dim_escopo_mercado` e `fato_mercado_mes` existem para a pergunta "a queda é do mercado?".
- **SQL analítico**: nove consultas com funções de janela, cada uma declarando a pergunta, a origem no `docs/01` e as janelas que usa (partição, ordem, quadro), com a semântica provada em teste; o notebook executado sobre a gold real, com Nota Técnica por seção.
- **A régua da gold** com o motor do contrato de aceite: 187 de 187 checks de conservação e integridade; 50 de 59 medidas do contrato dentro da banda, e as nove de fora explicadas por definição no `docs/16` (a margem em regime de caixa do contrato contra a de competência da gold; o CAD-01 depois do descarte por retenção). Só as famílias da gold reprovam o job; a banda é relatada.

### Warehouse Postgres
- A DDL **gerada do modelo** e dos tipos do DuckDB: chave primária com o ano, chaves estrangeiras para as dimensões, partição declarativa por ano, o comentário da matriz em toda tabela. Carga por partição idempotente (o ano substitui a partição inteira; a dimensão por upsert) e **conferida contra o parquet**: 25 tabelas, 120 partições, 1,68 milhão de linhas, 28 passos em 140 s.
- **DCL por perfil de negócio**: sócio, gerência, coordenação, assistente e financeiro, papéis sem login, cada um lendo os fatos da sua área e, nas dimensões de pessoa, só as colunas de que precisa. Nove acessos indevidos provados por `SET ROLE` no banco de verdade: o teste passa quando o acesso falha.
- **RLS por filial**: política por tabela, a ligação papel → filiais numa tabela que só o administrador escreve, lida por função `SECURITY DEFINER`, fechada por padrão (papel sem filial não vê nada), e a partição não concedida a ninguém. A coordenação de uma filial lê só a filial dela, no próprio banco, sem a aplicação saber.
- **Índices medidos**: oito candidatos com a consulta do painel que os pede, `EXPLAIN (ANALYZE)` sem e com o índice; quatro adotados (de 12 a 66 vezes mais rápido) e quatro descartados com a medida, inclusive o controle de uma coluna de três valores que o planejador ignora.

### A cadeia do dia
- Dois sensores novos: `gold_depois_da_silver` e `warehouse_depois_da_gold`. Provado ao vivo: a silver pela linha de comando (78 passos, 180 s), a gold disparada em seguida (26 passos, 57 s) e o warehouse depois dela (28 passos, 140 s). Da carga ao Postgres atualizado, cerca de 7 minutos, sem agenda nova.

### Documentação e operação
- `docs/15` matriz de barramento (gerado), `docs/16` gold e `docs/17` warehouse, com as tabelas saídas do código e um teste que reprova o documento que deixar de citar tabela, consulta, perfil, índice ou política; `docs/06` com a régua da gold; `docs/03`, `05`, `07` (o caminho do zero até o warehouse), `08` (operação da gold e do warehouse, três sintomas novos), `11` e a bibliografia com a fase 7 confirmada card a card.

### Esteira
- 604 testes (eram 533 na v0.6.0). `multidict` atualizado por uma vulnerabilidade acusada pelo `pip-audit`; actions atualizadas (`checkout` v7, `setup-uv` v10.2.0, `trivy-action` v0.36.0), fim do aviso do Node 20.

### Não inclui
- API, auditoria, backup e nuvem (v1.0.0). Os seis fatos de prioridade 2, a gold incremental, a migração de esquema do warehouse (coluna nova não entra sozinha), a carga pelo ADBC, pessoas cadastradas nos perfis, o notebook de conclusões sobre as sete afirmações e a decisão de qual margem é a do painel, que é do cliente.

## [0.6.0] · 2026-10-01 · Lake

A bronze deixou de ser só um depósito: foi lida com SQL, **auditada às cegas**, e o que a auditoria achou virou um catálogo aprovado antes de qualquer transformação. A **silver** existe, com o mesmo grão da bronze, pseudonimizada, e só publica a tabela que passa em cinco provas. O dado pessoal vencido é descartado com registro. Ainda sem gold nem warehouse carregado: isso é a v0.7.0.

### A bronze lida como um banco
- DuckDB sobre o parquet do lake: uma conexão com **79 views com os nomes da réplica**, de modo que o SQL escrito para o MySQL roda quase sem mexer. Abrir as views leva 0,6 s.
- A conservação entre a réplica e a bronze passou a ser medida: job `conferir_bronze` e o check C-06 da régua (agora 166 checks).

### Auditoria de qualidade, às cegas
- Dez notebooks executados e versionados, um por domínio e um de fechamento, tendo como únicas referências a DDL e o que o cliente declarou. Um teste reprova o notebook que consulte o gerador ou a régua: quem sabe o que foi plantado enxerga o que espera.
- **61 achados**: 4 altos, 17 médios, 19 baixos e 21 registros do que não é defeito. As seis declarações do cliente confirmadas com número, e doze achados médios que ninguém tinha declarado.
- **Dois defeitos do próprio pipeline**, achados pela auditoria e corrigidos: `TINYINT` copiado como booleano e `TIME` copiado como duração. Contar linhas não acusa tipo errado; a comparação de tipo com a DDL entrou em toda auditoria.

### Catálogo de achados
- 40 entradas como código, cada uma com a redação para quem decide e a redação para quem implementa, o tratamento (marcar, derivar, conformar, manter, pedir) e a regra. O `docs/13` é gerado: nenhum número é digitado.
- Aprovado entrada a entrada antes de a silver existir. A silver só implementa o que está aprovado, e um teste cobra.

### Silver
- As 76 tabelas, linha a linha, mais as colunas das **34 regras** aprovadas: marcas `q_<codigo>` e colunas derivadas ao lado do dado original. A silver nunca funde, preenche, apaga nem corrige.
- Cada tabela é gravada numa área de conferência, provada e só então publicada. **Cinco provas**: linhas por ano, valores e tipos originais na tabela inteira, colunas na ordem, marca só em linha avaliada, coluna de chave só com chave. A reprovada nunca substitui a publicada.
- **Prestação de contas**: cada regra roda na data da auditoria e tem de dar o número que o catálogo aprovou. 34 de 34. Na primeira rodada ela reprovou duas regras por um defeito do código, que é para o que ela serve.
- A silver inteira em 31 segundos pela linha de comando; 78 passos em cerca de 3 minutos no Dagster. Ela é refeita sozinha depois de toda carga incremental.

### LGPD
- **Pseudonimização**: uma decisão escrita, com motivo, para cada coluna etiquetada como dado pessoal. O documento vira HMAC-SHA256 com um segredo que vive só no `.env`; a data de nascimento vira ano; nome, telefone, e-mail e endereço não entram. O mesmo CPF dá a mesma chave no candidato e no colaborador.
- **Descarte**: a linha excluída na origem e o candidato não contratado com a retenção vencida têm o dado pessoal apagado na bronze, com conferência antes de trocar o arquivo e registro em `lgpd.descarte`, sem dado pessoal. O prazo (730 dias) é decisão do cliente, declarada em `cadastro.parametro`. O primeiro descarte alcançou 19.119 candidatos.
- **Cadeia de custódia**: o descarte muda a medida da auditoria por força de lei. Cada descarte registra o número de cada regra antes e depois, e a prestação de contas segue essa cadeia em vez de exigir o número antigo.

### A queda de conexão com o lake
- O lake recusava pedidos sob carga, sem erro no servidor. Reproduzido, com duas hipóteses descartadas por medida (teto de memória; evento periódico do armazenamento). Causa: uma conexão TCP nova por pedido esgotava as portas do sistema, 1.421 sockets em espera por abertura das views. Com o reaproveitamento de conexões do `httpfs` são 18. A história está no `docs/12`, seção 8.

### A memória de quem executa
- A silver disparada pelo sensor falhava onde a mesma silver, pela linha de comando, passava. Execução que entra pela fila roda no container do daemon, que tinha teto de 1 GB e já ocupa 600 MB parado: o kernel matava o passo da maior tabela (5 mortes no contador do container). O daemon passou a 3 GB e o DuckDB ganhou teto próprio por passo. Achado no fechamento da versão, ao provar o caminho que um usuário novo percorre.
- O mesmo exercício achou e corrigiu três furos do caminho do zero: a silver logo depois do backfill quebrava por falta de marca d'água (agora diz o que rodar); o sensor reagia ao backfill, que são nove execuções; e a cadeia de custódia acusava quebra depois de recopiar uma tabela da réplica.

### Documentação e operação
- `docs/12` bronze, `docs/13` catálogo de achados (gerado), `docs/14` silver, com as tabelas saídas do código e um teste que reprova o documento que envelhecer; `docs/bibliografia`, o que ler fase a fase e card a card.
- `docs/05` com a pseudonimização e a retenção como feitas; `docs/07` com o caminho do zero até a silver; `docs/08` com o segredo, a operação da silver e do descarte e seis sintomas novos.

### Esteira
- 533 testes (eram 454 na v0.5.0). `urllib3` atualizado por três vulnerabilidades acusadas pelo `pip-audit`.

### Não inclui
- Gold, modelo dimensional, warehouse carregado, API. Views da silver, série diária das marcas com prazo e silver incremental. A ordem: v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.5.0] · 2026-09-23 · Ingestão

O dado passou a entrar no pipeline pelas três portas que o caso tem: a réplica do sistema do cliente, as APIs públicas e a planilha da gerência. A bronze existe, é **espelho fiel** da réplica em parquet particionado por ano, e a carga diária traz só o que mudou. Ainda sem auditoria de qualidade nem silver: isso é a v0.6.0.

### Backfill
- A réplica inteira copiada para a bronze: **8.410.929 linhas em 162 MB** de parquet zstd (contra 1,5 GB em disco na réplica), em 124 segundos, 675 partições, nenhuma divergência de contagem.
- 76 assets no Dagster gerados por uma fábrica a partir da lista de tabelas da DDL (tabela nova vira asset sozinha), com `replica/<modulo>/<tabela>` como origem da linhagem.
- Leitura em lote por cursor de streaming; esquema declarado a partir do `information_schema`, nunca inferido do lote; contagem e leitura na mesma foto consistente do InnoDB, para a conferência comparar duas leituras do mesmo banco.
- Partição pelo ano de `criado_em`, a data que não muda: uma linha nunca troca de arquivo. O limite está dito e testado: a partição é técnica, e a marcação da noite de 31/12 mora no ano seguinte.

### Carga incremental
- Só o que tem `atualizado_em` acima da marca d'água, aplicado por merge de id nas partições tocadas, com conferência de contagem por partição. Carga sem nada a fazer em **845 ms**.
- A marca mora no warehouse (`ingestao.marca_dagua`), porque a réplica é do cliente e o pipeline não escreve nela; é um instante do relógio da réplica, não do relógio de quem roda o pipeline. Sem marca, ela é derivada do que a bronze já tem.
- Três armadilhas tratadas, cada uma vinda de uma falha real: a sobreposição de uma hora contra a transação que grava antes do corte e commita depois; a foto renovada a cada tabela, porque em REPEATABLE READ a transação implícita do driver congela o que a conexão enxerga; e a conferência por `criado_em <= corte`, que é o universo que a bronze representa.
- Primeira agenda do projeto: todo dia às 5h, ligada por padrão. A escolha entre marca d'água e captura pelo binlog está no [ADR-0011](docs/adr/0011-marca-dagua-nao-binlog.md).

### Exclusões
- `DELETE` na réplica vira **marcação**, não sumiço: a linha continua na bronze com `excluido_em`, lido da trilha `meta.exclusao_auditoria` que os gatilhos da v0.2.0 alimentam. Quem pergunta quantas linhas existem filtra as vivas; quem pergunta o que sumiu, quando e por quem, tem resposta.
- A trilha é a 76ª tabela da bronze, porque a bronze com marcação não é reconstruível só a partir da réplica: recopiar traz o presente e esqueceria quem morreu.

### Arquivo
- As nove planilhas do consolidado gerencial entram com esquema **pandera** declarado (primeiro uso, como o [ADR-0006](docs/adr/0006-pandera-e-regua.md) previa): preparar (descartar título e TOTAL, renomear, consertar os tipos que a planilha misturou) e validar (`strict`, unicidade de competência e filial, checks de negócio) são etapas separadas. Esquema reprovado, asset reprovado. 237 linhas, com o nome do arquivo em cada uma.

### Dias correntes
- A réplica volta a se mexer: um job escreve o dia de operação que falta (ponto de quem está em campo, vagas fechando, alocações terminando, uma batida apagada de vez em quando), determinístico pela data, numa transação só. 3.816 linhas por dia.
- A agenda dele nasce **desligada**, porque ligar faz a réplica deixar de ser exatamente a base que a régua aprovou; o que a operação acrescenta fica registrado em `ingestao.dia_simulado`, para a conferência continuar possível. A fronteira está declarada: é a operação continuando, não uma continuação do gerador.

### Documentação e operação
- `docs/11` ingestão: as três naturezas de fonte, a bronze, o backfill, a carga, as exclusões, a planilha, os dias correntes e a tabela de tempos medidos.
- `docs/08` ganhou o rito de uma versão (seção 8), "antes de desligar a máquina, pare os containers" e dois sintomas novos: a rede bridge do Docker quebrada depois de reinício e o `XA crash recovery` do MySQL.

### Esteira
- 454 testes (eram 393 na v0.4.0). Os testes que mexem na réplica devolvem réplica e bronze ao estado anterior, e a bronze serviu de backup para isso.

### Não inclui
- Auditoria de qualidade, silver, gold, warehouse carregado, API. A ordem: v0.6.0 lake (bronze, auditoria, silver), v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.4.0] · 2026-09-21 · Dado sintético

A réplica deixou de ser um banco vazio: **8,4 milhões de linhas em 76 tabelas** contam a história da Fictalent de janeiro de 2018 a 10 de setembro de 2026. O dado não foi sorteado para parecer plausível; foi **simulado e conferido contra um contrato escrito antes de ele existir**, com 165 checks em seis famílias. Ainda sem ingestão: ler a réplica e os arquivos é a v0.5.0.

### Fontes públicas
- Novo CAGED (2023 a 2025) agregado em `dados/publicos/caged`: movimentação mensal por escopo e grupo CNAE, e o índice sazonal que a régua usa para conferir o ritmo do ano. Pico de admissões em outubro e novembro, desligamentos em dezembro.
- Municípios (IBGE) e feriados nacionais (BrasilAPI) como assets do Dagster, com cliente HTTP próprio: tempo limite, cinco tentativas com recuo exponencial, limite de taxa e transporte injetável para teste ([ADR-0010](docs/adr/0010-httpx-ingestao-de-api.md)). As tabelas derivadas são versionadas com a fonte declarada (`fonte.json`), o bruto fica fora do git.

### Régua de validação
- `validacao/` com banda, check, laudo e veredito: **165 checks em seis famílias** (escala e forma, naturalidade, a história, sazonalidade, coerência interna e a sujeira na medida certa), escritos **antes** da primeira linha de dado. Cada alvo vem do dossiê do caso ou de dado público; cada tolerância é decisão declarada.
- Linha de comando própria: `--contrato` mostra o que a régua espera receber, `--medidas` dá o laudo e o código de saída é o veredito (0 aprovada, 1 reprovada, 2 incompleta).
- Quatro revisões de banda, cada uma com data e motivo no histórico de `bandas.py`: duas corrigiram estimativas de volume do rascunho do modelo, duas trocaram um limite genérico por um que descreve o negócio de temporada.

### Gerador
- Gerador determinístico em seis etapas, cada uma continuando a anterior na réplica, com a mesma semente produzindo a mesma base em qualquer máquina: mundo cadastral, carteira comercial, funil e pessoas, ponto e folha, financeiro, conformidade e acesso.
- **Nada é escrito por decreto.** O headcount de 2024 não é um número no código: a carteira abre postos, o funil converte candidatos, as pessoas são admitidas, alocadas e desligadas uma a uma, e o headcount é o que sobra. A defasagem de 6 a 9 meses entre a qualidade cair e o cliente romper o contrato **emerge** da mecânica (o cliente decide perto da renovação, olhando os últimos meses), em vez de ser um parâmetro.
- Ponto e folha em numpy (6,8 milhões de linhas): marcação, apontamento, folha com encargos e provisões, e o rateio de custo fechando com a folha em toda competência.
- Financeiro com a margem do caso: a receita nasce da medição do mês, e a despesa da retaguarda é o único número conduzido, fechando o ano na margem do plano, sempre positiva. O consolidado gerencial vai para a réplica e para nove planilhas Excel em `dados/gerencial`, que divergem da operação a partir de 2022: a declaração D6 da gerente virando dado.
- Escrita transacional com guarda de continuidade: cada tabela tem de estar exatamente no ponto em que a etapa a continua, e gravar duas vezes é recusado. Regenerar é sempre recomeçar, nunca remendar.
- A sujeira do catálogo (candidato duplicado, CPF inválido, admissão retroativa, temporário fora do prazo, marcação faltante, ASO vencido, título pago diferente, consolidado divergente) sai na proporção combinada, medida check a check.

### Aceite
- `--aceite --replica` gera as seis etapas de ponta a ponta, confere cada uma, junta as medidas, conta as linhas **na réplica** (têm de ser as que o gerador produz, tabela a tabela) e passa a régua inteira: **165 de 165 aprovados**, em 35 segundos.
- Medidas e laudo versionados em `dados/regua`. Um teste gera a base e compara número a número com o laudo do repositório: mexeu no gerador e uma medida mudou, o aceite tem de ser refeito.

### Documentação
- `docs/06` régua de validação: o método, as seis famílias com a origem de cada alvo, a história em números, o catálogo de sujeira, o aceite, **onde a régua passa raspando** e **o que a régua não faz**.
- `docs/07` ganhou a geração da base: o comando, a tabela por etapa com linhas e tempo medido, e o aceite. `docs/03` com as seis etapas; `dados/publicos`, `dados/gerencial` e `dados/regua` com README próprio.

### Esteira
- 393 testes (eram 285 na v0.3.0). Entre eles, o que gera a base inteira e confere o laudo versionado.

### Não inclui
- Ingestão, assets de dado, lake, gold, warehouse carregado, API. A ordem: v0.5.0 ingestão, v0.6.0 lake, v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.3.0] · 2026-09-17 · Orquestração e observabilidade

O Dagster deixou de ser vazio e a plataforma passou a se observar: recursos, convenções, o primeiro job, logs em JSON, métricas de execução no warehouse, Grafana como código e a verificação de ponta a ponta. Ainda sem dado: o dado sintético é a v0.4.0.

### Orquestração (Dagster)
- Recursos `Replica` (MySQL, como usuário `pipeline`), `Lake` (S3 via fsspec) e `Warehouse` (Postgres), configurados pelo ambiente, com segredos por `EnvVar`; dentro do Compose os hosts são os serviços, fora dele `127.0.0.1`.
- Convenções de todo asset: camada como grupo, chave `camada/modulo/tabela`, partição diária desde 2018-01-02 e anual 2018 a 2026.
- Job `verificar_plataforma` (grupo `plataforma`): prova de dentro do Dagster que réplica, lake e warehouse estão alcançáveis, com metadados no histórico.
- Logs estruturados: uma linha JSON por evento de toda execução, com `run_id`, `job`, `passo`, `evento` e `excecao`; logger de job selecionado pela configuração padrão de cada job.

### Observabilidade
- Métricas de execução no warehouse (`observabilidade.execucao` e `execucao_passo`), gravadas por três sensores de fim de execução (sucesso, falha, cancelamento), ligados por padrão, com upsert.
- Grafana como código: painel *Fictalent · Execuções do pipeline* (execuções e falhas em 24 h, frescor com faixas, duração média, por dia e status, por job, por passo, últimas execuções, falhas com o erro) e duas regras de alerta (execução falhou; dado envelheceu), provisionados por arquivo e não editáveis pela interface.
- `scripts/saude.sh` em duas fases: containers saudáveis e prova de ponta a ponta (réplica, gatilhos, cifra, keyring, bucket, `grafana_leitor`, métricas e frescor, code location e sensores, fontes, painel e alertas), terminando em `PLATAFORMA OK`.

### Documentação
- `docs/07` instalação e reprodução (do clone à plataforma verificada, atualizar, recomeçar, desinstalar) e `docs/09` monitoramento e healthcheck (três camadas, painel indicador a indicador, alertas, investigar por `run_id`, rotina). Manual `docs/08` ganhou Dagster, logs, métricas e a chave de cifra.

### Esteira
- 285 testes; os de integração materializam o job, capturam os logs, registram métricas e executam cada consulta do Grafana como `grafana_leitor`.

### Não inclui
- Dado, ingestão, assets de dado, agendas. A ordem: v0.4.0 dado sintético, v0.5.0 ingestão, v0.6.0 lake, v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.2.0] · 2026-09-16 · Fundação segura

A réplica do sistema do cliente, de pé, cifrada, com controle de acesso e provada por teste a cada PR. Ainda sem dado: o dado sintético é a v0.4.0.

### Plataforma
- Docker Compose com 7 serviços e 2 jobs de inicialização: réplica MySQL 8.4, warehouse Postgres 16, Postgres de metadados do Dagster, SeaweedFS (S3), Dagster (web e daemon), Grafana; healthcheck em todo serviço, portas só em `127.0.0.1`, imagens com versão exata, `no-new-privileges`, Dagster, Grafana e MySQL sem root, segredos só no `.env` (a falta derruba a subida).
- `scripts/saude.sh` (espera a plataforma inteira ficar saudável) e `scripts/aplicar_ddl.sh` (aplica a DDL num volume existente, idempotente).

### Réplica (MySQL 8)
- DDL dos 10 módulos: 75 tabelas de negócio mais a trilha de exclusões, comentário em toda tabela, chaves estrangeiras entre databases (dois ciclos fechados com `ALTER` idempotente), `CHECK` no lugar de `ENUM`, `atualizado_em` nativo e indexado em toda tabela (a marca d'água do incremental), etiqueta LGPD no comentário de cada coluna de dado pessoal.
- Trilha de exclusões: 75 gatilhos `BEFORE DELETE` **gerados da DDL**, com `USER()` como autor e `DROP` + `CREATE` para reaplicação; testado com um `DELETE` de verdade.
- Controle de acesso por função: `pipeline` (só leitura, inclusive a trilha), `relatorios_cliente` (leitura sem dado pessoal, com `GRANT` coluna a coluna **gerado das etiquetas LGPD**) e `replicador` (escreve o negócio, sem DDL, `GRANT` ou trilha); testes que passam quando o acesso indevido falha.
- Cifra em repouso da réplica inteira: tablespaces, redo, undo e binlog, com `component_keyring_file` e chave mestra em volume próprio; **provada no disco** (CPF gravado não aparece no `.ibd`) e **medida** (escrita +3% a +8%, leitura dentro do ruído, disco igual).
- Dicionário de dados gerado da `information_schema`, com a classificação por coluna (4 pessoais sensíveis, 24 pessoais, 55 públicas, 599 internas) e o inventário de dado pessoal.

### Esteira
- CI em três trilhos no GitHub Actions: qualidade (ruff, mypy, pytest), **réplica provada no runner** (MySQL com `.env` descartável e os testes de integração) e segurança (bandit, pip-audit, gitleaks, trivy). Espelho local em `scripts/esteira.sh`. 249 testes.

### Documentação
- `docs/03` arquitetura em 9 camadas com o mapa de escopo da réplica; `docs/04` modelo de dados; `docs/05` segurança e LGPD (modelo de ameaça, conferência por garantia, LGPD princípio a princípio, resposta a incidente); `docs/08` manual de operação; dicionário de dados; nove ADRs (bancos, cifra, Dagster, SeaweedFS, DuckDB, pandera e régua, Grafana, Gitflow, FastAPI).

### Decisões
- MySQL na réplica e Postgres no warehouse (ADR-0001): não existe "origem" no ambiente da consultoria; o staging é a réplica autorizada do sistema do cliente.
- Réplica parcial por pertinência como regra: replica-se o que a dor contratada exige, com mapa de escopo; neste caso a réplica é completa por autorização do cliente.
- Cifra de tablespace, não de coluna (ADR-0002).

### Não inclui
- Dado, ingestão, assets do Dagster, lake, gold, warehouse carregado, API. A ordem: v0.3.0 orquestração e observabilidade, v0.4.0 dado sintético, v0.5.0 ingestão, v0.6.0 lake, v0.7.0 gold e warehouse, v1.0.0 API, auditoria, backup e nuvem.

## [0.1.0] · 2026-09-15 · Entendimento e modelagem

- Entendimento do negócio (`docs/01`) e dos dados (`docs/02`): a Fictalent RH, o ciclo do pedido à receita, a história de 2018 a 2026 em cinco atos.
- Arquitetura (`docs/03`) com a especificação de mercado incorporada e o plano de versões.
- Modelo relacional de 75 tabelas em 10 módulos aprovado; plano de sintetização aprovado.
- Repositório público com Gitflow (`develop` como branch padrão).

[0.6.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.6.0
[0.5.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.5.0
[0.4.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.4.0
[0.3.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.3.0
[0.2.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.2.0
[0.1.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.1.0
