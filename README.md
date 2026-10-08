<a id="topo"></a>

# Fictalent RH · Pipeline de dados ponta a ponta

[![ci](https://github.com/tiagolima-neviah/rh-fictalent-bigdata/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/tiagolima-neviah/rh-fictalent-bigdata/actions/workflows/ci.yml)

<!-- nav:start -->
[Entendimento do Negócio](docs/01_entendimento_negocio.md) | [Entendimento dos Dados](docs/02_entendimento_dados.md) | [Arquitetura](docs/03_arquitetura.md) | [Modelo de Dados](docs/04_modelo_dados_staging.md) | [Segurança e LGPD](docs/05_seguranca_e_lgpd.md)
<!-- nav:end -->

> Pipeline completo e moderno de dados construído sobre a **Fictalent RH**, uma empresa **fictícia** de gestão de mão de obra (recrutamento e seleção, trabalho temporário, terceirização e treinamentos) com dados **100% sintéticos**: de uma réplica **MySQL** do sistema do cliente, em 10 módulos, com **backfill histórico desde 2018 e carga incremental diária**, orquestrado com **Dagster**, das camadas bronze, silver e gold em parquet ao modelo multidimensional (star schema) num warehouse **Postgres**, com observabilidade em **Grafana**, API REST dos indicadores, controle de acesso por perfil e **LGPD aplicada** a dado pessoal, pronto para painel web, Power BI e Tableau. A sazonalidade dos dados sintéticos é **calibrada por fonte pública** (microdados do Novo CAGED). O repositório existe para ajudar analistas em início de carreira a percorrer um projeto de engenharia de dados e BI do jeito que ele acontece no mundo real, com custo baixo e total portabilidade.

> **Aviso:** a Fictalent RH não existe. Empresa, clientes, pessoas, documentos e valores são fictícios e gerados sinteticamente. Este projeto não possui afiliação com nenhuma empresa real; qualquer semelhança é coincidência.

## ⚠️ Disclaimer: projeto de estudo, não use em produção

Este repositório é um **CASE fictício com dados sintéticos, criado exclusivamente para fins de estudo e portfólio**. Ele **não deve, em hipótese alguma, ser usado em ambiente de produção real**. As práticas de segurança e de proteção de dados demonstradas aqui existem para ensinar, e não substituem um projeto de produção: o código não passou por auditoria de segurança independente, não tem suporte, e as configurações de exemplo (credenciais em `.env` local, certificados, parâmetros de rede e de retenção) não são adequadas a um ambiente real.

O software é fornecido **"no estado em que se encontra" (AS IS), sem garantias de qualquer natureza**, nos termos da [licença MIT](LICENSE) deste repositório. Os autores e a Neviah **não se responsabilizam por quaisquer danos** decorrentes do uso deste material; qualquer utilização fora do contexto de estudo, incluindo ambientes produtivos, é feita **por conta e risco exclusivos de quem a fizer**.

Tem interesse em implementar este projeto de verdade na sua empresa? Entre em contato pela **[www.neviah.com.br](https://www.neviah.com.br)**: a implementação real é feita de forma completa e correta, considerando todas as políticas de segurança da informação e de proteção de dados (LGPD).

## Por que este projeto existe

Os dois primeiros casos desta série resolveram o problema de **volume** (uma operadora logística com 25 milhões de linhas) e o problema de **confiança** (uma empresa comercial sem nenhum relatório que fechasse). Este resolve um terceiro, que é o mais comum em empresas de serviço: a que **cresceu rápido demais para o próprio processo**.

A Fictalent administra mão de obra. O trabalhador alocado é, ao mesmo tempo, o produto entregue ao cliente, a unidade de receita e um empregado CLT dela própria. Isso torna o dado dela **híbrido por natureza**: um funil comercial de vagas, uma folha de milhares de pessoas, uma carteira de contratos com margem por posto e um dever de compliance com prazo legal. Cada pedaço mora num sistema diferente, e a pergunta que mais importa, **qual cliente dá margem e qual só dá trabalho**, exige cruzar os quatro na mão, toda vez.

Duas coisas neste caso não existiam nos anteriores e são o motivo de ele ser interessante:

1. **Backfill histórico.** O pipeline não começa a contar a história a partir de hoje: ele reconstrói **desde 2018**, porque o histórico é o que permite comparar ano a ano e responder por que a empresa perdeu contratos. É também a resposta para a pergunta que todo dono faz na primeira reunião: não, você não vai recomeçar do zero.
2. **Sazonalidade calibrada por dado público.** A curva mensal do gerador não é invenção plausível: ela é ajustada a partir dos **microdados do Novo CAGED** (admissões e desligamentos por mês, município e CNAE) para os CNAEs do segmento na região do caso. O arco da história é ficção; o ritmo do ano é real.

## O caso

A Fictalent RH (matriz em Atibaia, filiais em Bragança Paulista e Extrema, no eixo Fernão Dias) coloca e administra pessoas em indústrias, transportadoras, galpões de armazenagem e varejo da região. Fundada em 2018, ela atravessa uma pandemia, cresce muito entre 2022 e 2024, e a partir do fim de 2025 começa a perder contratos sem saber por quê.

O que quebrou não foi o negócio, foi o processo de informação: um time que exportava planilhas e as cruzava à mão dava conta de 150 pessoas alocadas e não dá conta de 1.400. As coordenadoras, que deveriam analisar, foram absorvidas pelo operacional, e a empresa passou a crescer sem saber de onde vinha o lucro. A história completa está no [Entendimento do Negócio](docs/01_entendimento_negocio.md).

## Arquitetura

```
Sistema do cliente (fora daqui: a consultoria não o toca)
   │  replicação autorizada
   ▼
Staging: réplica em MySQL (10 módulos, DCL por perfil, cifra em repouso, trilha de exclusões)
   │  ingestão: relacional (backfill + incremental) · API REST · arquivo
   ▼
Lake em SeaweedFS/S3 (parquet, fsspec) ── Bronze ► Silver ► Gold  [DuckDB]
   ▼
OLAP: Postgres (star schema, carga por partição, perfis de leitura, RLS por filial)
   ▼
API REST [FastAPI]  ·  Painel web  ·  Power BI  ·  Tableau

Atravessando tudo: Dagster (orquestração) · Grafana (monitoramento e alertas)
                   auditoria · LGPD · CI com varredura de segurança
```

Detalhe de cada etapa, com as decisões e os porquês, em [Arquitetura](docs/03_arquitetura.md).

## Status do projeto

O projeto é entregue em versões publicáveis. Cada versão fecha um bloco inteiro, com código, testes e documentação; o detalhe de cada uma está no [histórico de versões](CHANGELOG.md).

| versão | bloco | situação |
|---|---|---|
| v0.1.0 | Entendimento do negócio e dos dados, arquitetura, modelo relacional | concluído |
| v0.2.0 | Fundação segura: Compose, DDL dos 10 módulos na réplica MySQL, trilha de exclusões, DCL, cifra em repouso, dicionário, CI em três trilhos | concluído |
| v0.3.0 | Orquestração (Dagster: recursos, convenções, primeiro job), logs em JSON, métricas por sensor, Grafana como código, saúde de ponta a ponta | concluído |
| v0.4.0 | Dado sintético: CAGED e APIs públicas, régua de 165 checks, gerador de 2018 a 2026 e a réplica com 8,4 milhões de linhas | concluído |
| v0.5.0 | Ingestão: a bronze em parquet (8,4 milhões de linhas em 162 MB), backfill, carga diária por marca d'água, exclusões como marcação, planilhas com pandera e a réplica em movimento | concluído |
| v0.6.0 | Lake: a bronze lida com SQL (DuckDB), auditoria de qualidade às cegas com 61 achados, catálogo aprovado antes de transformar, silver com cinco provas por tabela e prestação de contas, pseudonimização e descarte de dado pessoal por retenção | concluído |
| v0.7.0 | Gold provada antes de publicar, SQL analítico com funções de janela, warehouse Postgres com perfis de negócio, RLS por filial e índices medidos; a cadeia do dia por sensores | concluído |
| v1.0.0 | API REST, auditoria, backup e restauração, destino em nuvem | próxima |
| (outro repositório) | Painel web, Power BI e Tableau Public | previsto |

## Requisitos

O projeto sobe oito serviços em containers. Em repouso, a plataforma inteira ocupou **cerca de 1,4 GB de RAM** (medido na v0.2.0, ainda sem dados); com a base sintética gerada, a réplica ocupa cerca de **1,5 GB** em disco e o gerador pede até 2,4 GB de RAM por alguns minutos; a referência é **8 GB de RAM no mínimo (16 GB recomendado)**, 4 núcleos e cerca de 20 GB livres em disco. O que precisa estar instalado: **Docker** (com Compose), **Python 3.12** e **git**. O gerenciamento de dependências é feito com [uv](https://docs.astral.sh/uv/).

## Como rodar (estado atual)

Na v1.0.0 é possível subir a plataforma inteira (réplica cifrada e com controle de acesso, warehouse, lake, Dagster, Grafana com painel e alertas, API), **gerar a base sintética da Fictalent** de 2018 a setembro de 2026, **ingeri-la na bronze do lake**, chegar à **silver pseudonimizada, com prestação de contas**, à **gold provada antes de publicar** e ao **warehouse Postgres com perfis de leitura e isolamento por filial**, com a cadeia diária inteira rodando sozinha:

```bash
cp .env.example .env        # e gere as senhas: o manual tem o comando pronto
docker compose up -d --build
bash scripts/saude.sh       # espera tudo ficar saudável e diz o que falhou
```

```bash
.venv/bin/python -m rh_fictalent.gerador --etapa 1 --gravar --zerar && for e in 2 3 4 5 6; do .venv/bin/python -m rh_fictalent.gerador --etapa $e --gravar || break; done
.venv/bin/python -m rh_fictalent.gerador --aceite --replica   # depois do backfill: RÉGUA APROVADA: 166 de 166
```

São cerca de 7 minutos para 8,4 milhões de linhas em 76 tabelas, com o mesmo resultado em qualquer máquina. Depois, o backfill pela interface do Dagster (<http://127.0.0.1:3010>, job `backfill_bronze`, backfill das nove partições) leva a réplica inteira para o lake em cerca de 2 minutos, e a carga incremental das 5h traz só o que mudou; como o dado entra, e quanto custa, está em [Ingestão](docs/11_ingestao.md). Ao fim de cada carga incremental, o pipeline descarta o dado pessoal vencido e refaz a silver sozinho, em cerca de 3 minutos: 76 tabelas pseudonimizadas, cada uma conferida contra a bronze antes de publicar, e a prestação de contas das 34 regras aprovadas no catálogo ([Bronze](docs/12_bronze.md), [Catálogo de achados](docs/13_catalogo_de_achados.md), [Silver](docs/14_silver.md)). Depois da silver, a gold e o warehouse seguem sozinhos, por sensor: o modelo dimensional da matriz de barramento (11 dimensões, 14 fatos, 1,68 milhão de linhas) é montado e provado em cerca de 1 minuto, e o Postgres o recebe em pouco mais de 2, com perfis de leitura por área, isolamento por filial e índices medidos ([Matriz de barramento](docs/15_matriz_de_barramento.md), [Gold](docs/16_gold.md), [Warehouse Postgres](docs/17_warehouse_postgres.md)). Por cima do warehouse, a **API REST** serve os indicadores com o banco decidindo quem vê o quê ([API](docs/18_api.md)); a **trilha de auditoria** responde treze perguntas sem dado pessoal ([Auditoria](docs/10_auditoria.md)); o **backup** guarda réplica, chave, warehouse, Dagster e lake e prova que restaura antes de precisar ([Backup e restauração](docs/19_backup_e_restauracao.md)); e o mesmo warehouse pode ser carregado num **Postgres em nuvem** gratuito, para quem quer o painel fora da máquina ([Warehouse, seção 10](docs/17_warehouse_postgres.md)). O passo a passo completo do zero, com requisitos, geração das senhas e verificação, está em [Instalação e Reprodução](docs/07_instalacao_e_reproducao.md); o que a régua confere, em [Régua de Validação](docs/06_regua_de_validacao.md); o dia a dia, no [Manual de Operação](docs/08_manual_de_operacao.md).

## Qualidade e segurança a cada mudança

Todo PR passa por três trilhos no GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): **qualidade** (ruff, mypy, pytest), **réplica provada** (sobe o MySQL no runner com um `.env` descartável e roda os testes de integração: DDL, trilha de exclusões, controle de acesso, cifra no disco e dicionário) e **segurança** (bandit no código, pip-audit nas dependências do lock, gitleaks no histórico, trivy no repositório). O espelho local é `bash scripts/esteira.sh`.

## Estrutura de diretórios

```
rh-fictalent-bigdata/
├── docs/                    # a documentação navegável (leia na ordem)
│   ├── adr/                 # registros de decisão: que necessidade do caso cada tecnologia atende
│   └── dicionario/          # dicionário de dados gerado da information_schema
├── compose.yaml             # a plataforma inteira: 8 serviços com healthcheck e 2 jobs de inicialização
├── infra/                   # Dockerfile do Dagster, inicialização dos bancos, keyring da réplica, provisionamento do Grafana
├── staging/                 # DDL da réplica (MySQL), módulo a módulo, e os gatilhos gerados
├── dados/publicos/          # tabelas de fonte pública (Novo CAGED, IBGE, BrasilAPI), cada uma com a fonte; o bruto fica fora do git
├── dados/gerencial/         # o consolidado gerencial em Excel (sintético): a fonte de arquivo do pipeline
├── dados/regua/             # o aceite da base sintética: as medidas e o laudo da régua (166 de 166)
├── dados/auditoria/         # os achados da auditoria de qualidade, um JSON por domínio: a entrada do catálogo
├── notebooks/auditoria/     # a auditoria às cegas da bronze: dez notebooks executados, com Nota Técnica por seção
├── notebooks/gold/          # o SQL analítico sobre a gold: funções de janela, executado, com Nota Técnica por seção
├── src/rh_fictalent/
│   ├── orquestracao/        # definições do Dagster (assets, jobs, schedules)
│   ├── staging/             # geradores: gatilhos, papéis, cifra e dicionário (o que deriva das tabelas nasce aqui)
│   ├── fontes/              # fontes públicas: CAGED (FTP, agregação) e APIs (IBGE, BrasilAPI) com retry e limite de taxa
│   ├── gerador/             # o gerador determinístico dos dados sintéticos
│   ├── validacao/           # a régua: bandas e checks de aceite
│   ├── ingestao/  lake/     # a bronze: backfill, carga incremental por marca d'água, exclusões; o lake por fsspec
│   ├── auditoria/           # a auditoria de qualidade às cegas: checagens, achados, executor dos notebooks
│   ├── bronze/  silver/  gold/   # as camadas do lake: leitura por SQL, pseudonimização e descarte, modelo dimensional
│   ├── lgpd/                # o descarte de dado pessoal por retenção e a cadeia de custódia
│   ├── warehouse/           # a DDL gerada do modelo e a carga por partição no Postgres
│   ├── api/                 # a API REST dos indicadores (FastAPI), com o banco decidindo quem vê o quê
│   ├── trilha/              # as treze perguntas de auditoria, sem dado pessoal
│   ├── backup/              # backup, prova de restauração em alvos descartáveis e restauração
│   └── observabilidade/     # logs em JSON e as métricas por execução
├── scripts/                 # saude.sh, esteira.sh, aplicar_ddl.sh, medir_cifra.sh
└── tests/                   # esteira de qualidade (ruff, mypy, pytest) e as provas sobre a plataforma de pé
```

## Documentação

<details>
<summary><strong>Regras de negócio e documentação técnica</strong> (leia na ordem)</summary>

- [01 · Entendimento do Negócio](docs/01_entendimento_negocio.md): quem é a Fictalent, como um pedido de vaga vira pessoa alocada e receita, e a história de 2018 a 2026 que os dados precisam contar.
- [02 · Entendimento dos Dados](docs/02_entendimento_dados.md): o banco relacional em 10 módulos, o que cada um guarda e o que esperar da qualidade desses dados.
- [03 · Arquitetura](docs/03_arquitetura.md): o pipeline inteiro etapa por etapa, a ferramenta de cada uma e o porquê de cada escolha.
- [04 · Modelo de Dados](docs/04_modelo_dados_staging.md): a réplica em MySQL, módulo a módulo, com as convenções, o espinhaço da margem por cliente e como a DDL é aplicada e conferida.
- [05 · Segurança e LGPD](docs/05_seguranca_e_lgpd.md): o modelo de ameaça camada a camada, o comando que prova cada garantia, a LGPD princípio por princípio e o que ainda não existe.
- [06 · Régua de Validação](docs/06_regua_de_validacao.md): o contrato de aceite do dado sintético, 166 checks em seis famílias, de onde vem cada alvo, o laudo versionado e o que a régua não faz.
- [07 · Instalação e Reprodução](docs/07_instalacao_e_reproducao.md): do clone à plataforma verificada numa máquina limpa, a geração da base sintética e o aceite; atualizar, recomeçar, desinstalar.
- [Dicionário de dados](docs/dicionario/README.md): gerado da `information_schema` da réplica, coluna a coluna, com a classificação LGPD e o inventário de dado pessoal.
- [Registros de decisão (ADR)](docs/adr/README.md): que necessidade do caso cada tecnologia atende, a começar por MySQL na réplica e Postgres no warehouse.
- [Bibliografia](docs/bibliografia.md): o que ler, fase a fase e card a card, com livro e capítulo, dizendo o que está no acervo e o que ainda não; confirmado para o que já foi construído, plano para o que vem.

- [08 · Manual de Operação](docs/08_manual_de_operacao.md): subir, verificar a saúde, parar, reiniciar e recuperar a plataforma; Dagster, logs, métricas e a chave de cifra.
- [09 · Monitoramento e Healthcheck](docs/09_monitoramento_e_healthcheck.md): as três camadas, o painel indicador a indicador, os alertas, como investigar uma execução e a rotina.
- [10 · Auditoria](docs/10_auditoria.md): onde está cada trilha (acesso, alteração, exportação, exclusão, execuções, descartes, quem lê o warehouse, a API), as treze perguntas prontas sem dado pessoal, o relatório em pasta e o que a base de hoje responde.
- [11 · Ingestão](docs/11_ingestao.md): as três naturezas de fonte, a bronze, o backfill, a carga incremental por marca d'água, as exclusões, a planilha com esquema e os dias correntes, com os tempos medidos.
- [12 · Bronze](docs/12_bronze.md): o que o lake guarda e o que a camada promete, os tipos do MySQL ao parquet e os dois defeitos que a auditoria achou, como ler a bronze com SQL, como conferir que ela ainda é o espelho da réplica, o dado pessoal e o descarte, e a investigação da queda de conexão com o lake.
- [Auditoria de qualidade](notebooks/auditoria/README.md): os dez notebooks da auditoria às cegas da bronze, um por domínio e um de fechamento, executados e versionados; como rodar e o que sai deles.
- [SQL analítico sobre a gold](notebooks/gold/README.md): as perguntas do `docs/01` respondidas com funções de janela sobre a gold, executadas e versionadas, com Nota Técnica por seção.
- [13 · Catálogo de achados](docs/13_catalogo_de_achados.md): a decisão sobre cada achado da auditoria, em duas redações (para quem decide e para quem implementa), com o tratamento aprovado para a silver e o que nunca se faz; gerado do código e dos registros, aprovado entrada a entrada antes de qualquer transformação.
- [14 · Silver](docs/14_silver.md): a bronze linha a linha, pseudonimizada, com as colunas das 34 regras aprovadas; as cinco provas de cada tabela, a prestação de contas contra a auditoria e a cadeia de custódia dos descartes, com os tempos medidos.
- [15 · Matriz de barramento](docs/15_matriz_de_barramento.md): o desenho do modelo dimensional antes de ele existir: os fatos e o grão de cada um, as dimensões que eles dividem, de qual fato sai cada indicador e como cada uma das sete afirmações dos donos é respondida; gerada do código.
- [16 · Gold](docs/16_gold.md): o modelo dimensional construído da silver, as cinco provas de cada tabela, o horizonte e o calendário, as decisões que a matriz não tinha, a régua da gold e onde ela diverge do contrato de aceite, o SQL analítico com funções de janela, com os tempos medidos.
- [17 · Warehouse Postgres](docs/17_warehouse_postgres.md): a DDL gerada do modelo, a carga por partição conferida contra o parquet, quem lê o quê (os perfis de negócio, sem atributo de pessoa fora da necessidade), cada filial enxergando só as próprias linhas, os índices medidos por plano de execução e a cadeia do dia fechada por sensores.
- [18 · API dos indicadores](docs/18_api.md): a gold servida do warehouse com o banco decidindo quem vê o quê, o contrato `/v1`, o rito de cadastrar consumidor e token, como testar com `curl`, os erros, a operação e os testes de acesso negado.

- [19 · Backup e restauração](docs/19_backup_e_restauracao.md): o que se guarda e por quê, fazer, provar em alvos descartáveis, restaurar de verdade, a pasta como dado pessoal, os tempos medidos.
- [20 · Solução de problemas](docs/20_solucao_de_problemas.md): como investigar, e tudo o que já quebrou, com o sintoma, a causa provada e o que resolveu.

</details>

---

Empresa fictícia, dados sintéticos, licença [MIT](LICENSE). Uma solução [Neviah](https://www.neviah.com.br).

[Início](#topo)
