# Histórico de versões

Cada versão fecha uma fase inteira, com código, testes e documentação. O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o [SemVer](https://semver.org/lang/pt-BR/).

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

[0.5.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.5.0
[0.4.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.4.0
[0.3.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.3.0
[0.2.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.2.0
[0.1.0]: https://github.com/tiagolima-neviah/rh-fictalent-bigdata/releases/tag/v0.1.0
