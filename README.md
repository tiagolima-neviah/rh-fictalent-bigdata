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
| v0.5.0 | Ingestão: backfill, incremental, exclusões, planilhas | próxima |
| v0.6.0 | Lake: bronze, auditoria de qualidade, silver com pseudonimização | previsto |
| v0.7.0 | Gold, funções de janela, warehouse Postgres com RLS por filial | previsto |
| v1.0.0 | API REST, auditoria, backup e restauração, destino em nuvem | previsto |
| (outro repositório) | Painel web, Power BI e Tableau Public | previsto |

## Requisitos

O projeto sobe sete serviços em containers. Em repouso, a plataforma inteira ocupou **cerca de 1,4 GB de RAM** (medido na v0.2.0, ainda sem dados); com a base sintética gerada, a réplica ocupa cerca de **1,5 GB** em disco e o gerador pede até 2,4 GB de RAM por alguns minutos; a referência é **8 GB de RAM no mínimo (16 GB recomendado)**, 4 núcleos e cerca de 20 GB livres em disco. O que precisa estar instalado: **Docker** (com Compose), **Python 3.12** e **git**. O gerenciamento de dependências é feito com [uv](https://docs.astral.sh/uv/).

## Como rodar (estado atual)

O projeto está em construção. Na v0.4.0 já é possível subir a plataforma inteira (réplica cifrada e com controle de acesso, warehouse, lake, Dagster com o primeiro job e os sensores de métricas, Grafana com painel e alertas) e **gerar a base sintética da Fictalent**, de 2018 a setembro de 2026:

```bash
cp .env.example .env        # e gere as senhas: o manual tem o comando pronto
docker compose up -d --build
bash scripts/saude.sh       # espera tudo ficar saudável e diz o que falhou
```

```bash
.venv/bin/python -m rh_fictalent.gerador --etapa 1 --gravar --zerar && for e in 2 3 4 5 6; do .venv/bin/python -m rh_fictalent.gerador --etapa $e --gravar || break; done
.venv/bin/python -m rh_fictalent.gerador --aceite --replica   # RÉGUA APROVADA: 165 de 165
```

São cerca de 7 minutos para 8,4 milhões de linhas em 76 tabelas, com o mesmo resultado em qualquer máquina. O passo a passo completo do zero, com requisitos, geração das senhas e verificação, está em [Instalação e Reprodução](docs/07_instalacao_e_reproducao.md); o que a régua confere, em [Régua de Validação](docs/06_regua_de_validacao.md); o dia a dia, no [Manual de Operação](docs/08_manual_de_operacao.md).

## Qualidade e segurança a cada mudança

Todo PR passa por três trilhos no GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): **qualidade** (ruff, mypy, pytest), **réplica provada** (sobe o MySQL no runner com um `.env` descartável e roda os testes de integração: DDL, trilha de exclusões, controle de acesso, cifra no disco e dicionário) e **segurança** (bandit no código, pip-audit nas dependências do lock, gitleaks no histórico, trivy no repositório). O espelho local é `bash scripts/esteira.sh`.

## Estrutura de diretórios

```
rh-fictalent-bigdata/
├── docs/                    # a documentação navegável (leia na ordem)
│   ├── adr/                 # registros de decisão: que necessidade do caso cada tecnologia atende
│   └── dicionario/          # dicionário de dados gerado da information_schema
├── compose.yaml             # a plataforma inteira: 7 serviços com healthcheck
├── infra/                   # Dockerfile do Dagster, inicialização dos bancos, keyring da réplica, provisionamento do Grafana
├── staging/                 # DDL da réplica (MySQL), módulo a módulo, e os gatilhos gerados
├── dados/publicos/          # tabelas de fonte pública (Novo CAGED, IBGE, BrasilAPI), cada uma com a fonte; o bruto fica fora do git
├── dados/gerencial/         # o consolidado gerencial em Excel (sintético): a fonte de arquivo do pipeline
├── dados/regua/             # o aceite da base sintética: as medidas e o laudo da régua (165 de 165)
├── src/rh_fictalent/
│   ├── orquestracao/        # definições do Dagster (assets, jobs, schedules)
│   ├── staging/             # geradores: gatilhos, papéis, cifra e dicionário (o que deriva das tabelas nasce aqui)
│   ├── fontes/              # fontes públicas: CAGED (FTP, agregação) e APIs (IBGE, BrasilAPI) com retry e limite de taxa
│   ├── gerador/             # o gerador determinístico dos dados sintéticos
│   ├── validacao/           # a régua: bandas e checks de aceite
│   ├── bronze/  silver/  gold/   # as camadas do lake
│   └── warehouse/           # carga do star schema no destino
├── notebooks/               # auditoria de qualidade e demonstrações
└── tests/                   # esteira de qualidade (ruff, mypy, pytest) e as provas da réplica
```

## Documentação

<details>
<summary><strong>Regras de negócio e documentação técnica</strong> (leia na ordem)</summary>

- [01 · Entendimento do Negócio](docs/01_entendimento_negocio.md): quem é a Fictalent, como um pedido de vaga vira pessoa alocada e receita, e a história de 2018 a 2026 que os dados precisam contar.
- [02 · Entendimento dos Dados](docs/02_entendimento_dados.md): o banco relacional em 10 módulos, o que cada um guarda e o que esperar da qualidade desses dados.
- [03 · Arquitetura](docs/03_arquitetura.md): o pipeline inteiro etapa por etapa, a ferramenta de cada uma e o porquê de cada escolha.
- [04 · Modelo de Dados](docs/04_modelo_dados_staging.md): a réplica em MySQL, módulo a módulo, com as convenções, o espinhaço da margem por cliente e como a DDL é aplicada e conferida.
- [05 · Segurança e LGPD](docs/05_seguranca_e_lgpd.md): o modelo de ameaça camada a camada, o comando que prova cada garantia, a LGPD princípio por princípio e o que ainda não existe.
- [06 · Régua de Validação](docs/06_regua_de_validacao.md): o contrato de aceite do dado sintético, 165 checks em seis famílias, de onde vem cada alvo, o laudo versionado e o que a régua não faz.
- [07 · Instalação e Reprodução](docs/07_instalacao_e_reproducao.md): do clone à plataforma verificada numa máquina limpa, a geração da base sintética e o aceite; atualizar, recomeçar, desinstalar.
- [Dicionário de dados](docs/dicionario/README.md): gerado da `information_schema` da réplica, coluna a coluna, com a classificação LGPD e o inventário de dado pessoal.
- [Registros de decisão (ADR)](docs/adr/README.md): que necessidade do caso cada tecnologia atende, a começar por MySQL na réplica e Postgres no warehouse.

- [08 · Manual de Operação](docs/08_manual_de_operacao.md): subir, verificar a saúde, parar, reiniciar e recuperar a plataforma; Dagster, logs, métricas e a chave de cifra.
- [09 · Monitoramento e Healthcheck](docs/09_monitoramento_e_healthcheck.md): as três camadas, o painel indicador a indicador, os alertas, como investigar uma execução e a rotina.

Os demais manuais (auditoria, backup e restauração) entram com as versões em que cada assunto passa a existir; solução de problemas está na seção 9 do manual de operação.

</details>

---

Empresa fictícia, dados sintéticos, licença [MIT](LICENSE). Uma solução [Neviah](https://www.neviah.com.br).

[Início](#topo)
