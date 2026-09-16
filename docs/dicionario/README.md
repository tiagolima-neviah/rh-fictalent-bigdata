<a id="topo"></a>

# Dicionário de dados · a réplica descrevendo a si mesma

[Home](../../README.md) | [Modelo de Dados](../04_modelo_dados_staging.md)

> **Arquivo gerado** por `src/rh_fictalent/staging/dicionario.py` a partir da `information_schema` da réplica MySQL. Não edite à mão: rode `python -m rh_fictalent.staging.dicionario` com a réplica de pé e versione o resultado. Um teste de integração confere que este arquivo é igual ao que o banco produz.

## Classificação de sensibilidade

Toda coluna carrega uma classe, derivada das etiquetas nos comentários da DDL: **pessoal sensível** (saúde: CID, resultado de exame, acidente), **pessoal** (identifica ou contata uma pessoa, ou é remuneração individual), **pública** (referência de domínio público: município, feriado, CBO, tributo) e **interna** (todo o resto). A classe alimenta o controle de acesso da réplica (o `GRANT` de coluna dos relatórios do cliente exclui pessoal e pessoal sensível) e a pseudonimização na silver.

| classe | colunas |
|---|---|
| pessoal sensível | 4 |
| pessoal | 24 |
| pública | 55 |
| interna | 599 |

76 tabelas, 682 colunas.

## Inventário de dado pessoal

As colunas que a LGPD alcança, por módulo. É a lista que o encarregado de dados pede primeiro.

| módulo | tabela | coluna | classe | descrição |
|---|---|---|---|---|
| `cadastro` | `endereco` | `logradouro` | pessoal | quando o endereço é de colaborador |
| `cadastro` | `endereco` | `cep` | pessoal | quando o endereço é de colaborador |
| `comercial` | `cliente_contato` | `nome` | pessoal |  |
| `comercial` | `cliente_contato` | `email` | pessoal |  |
| `comercial` | `cliente_contato` | `telefone` | pessoal |  |
| `ats` | `candidato` | `nome` | pessoal |  |
| `ats` | `candidato` | `cpf` | pessoal | sem UNIQUE de propósito: duplicados e inválidos são sujeira de origem, medida na auditoria |
| `ats` | `candidato` | `dt_nascimento` | pessoal |  |
| `ats` | `candidato` | `sexo` | pessoal | F, M ou N (não informado) |
| `ats` | `candidato` | `telefone` | pessoal |  |
| `ats` | `candidato` | `email` | pessoal |  |
| `pessoas` | `afastamento` | `cid_grupo` | pessoal sensível | grupo da CID, dado de saúde |
| `pessoas` | `colaborador` | `nome` | pessoal |  |
| `pessoas` | `colaborador` | `cpf` | pessoal |  |
| `pessoas` | `colaborador` | `dt_nascimento` | pessoal |  |
| `pessoas` | `colaborador` | `endereco_id` | pessoal |  |
| `pessoas` | `colaborador` | `pis` | pessoal |  |
| `pessoas` | `colaborador_documento` | `numero` | pessoal |  |
| `pessoas` | `dependente` | `nome` | pessoal |  |
| `pessoas` | `dependente` | `dt_nascimento` | pessoal |  |
| `folha` | `folha_item` | `valor` | pessoal | remuneração individual |
| `sst` | `acidente` | `tipo` | pessoal sensível | TIPICO, TRAJETO ou DOENCA |
| `sst` | `acidente` | `gravidade` | pessoal sensível | LEVE, MODERADA, GRAVE ou FATAL |
| `sst` | `aso` | `resultado` | pessoal sensível | APTO, INAPTO ou APTO_RESTRICAO, dado de saúde |
| `seguranca` | `log_auditoria` | `valor_anterior` | pessoal | pode carregar o dado alterado |
| `seguranca` | `log_auditoria` | `valor_novo` | pessoal | pode carregar o dado alterado |
| `seguranca` | `usuario` | `nome` | pessoal |  |
| `seguranca` | `usuario` | `email` | pessoal |  |

## Módulos

- [`cadastro`](#cadastro) · 12 tabelas
- [`comercial`](#comercial) · 8 tabelas
- [`ats`](#ats) · 9 tabelas
- [`pessoas`](#pessoas) · 8 tabelas
- [`ponto`](#ponto) · 5 tabelas
- [`folha`](#folha) · 7 tabelas
- [`financeiro`](#financeiro) · 10 tabelas
- [`treinamento`](#treinamento) · 5 tabelas
- [`sst`](#sst) · 6 tabelas
- [`seguranca`](#seguranca) · 5 tabelas
- [`meta`](#meta) · 1 tabelas

<a id="cadastro"></a>

## `cadastro`

### `cadastro.centro_custo`

O eixo do rateio de custo e da apuração de resultado

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(20)` | não | único |  | interna |  |
| `nome` | `varchar(100)` | não |  |  | interna |  |
| `tipo` | `varchar(12)` | não |  |  | interna | FILIAL, RETAGUARDA ou CONTRATO |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial |  | interna |  |
| `contrato_id` | `bigint unsigned` | sim | FK → comercial.contrato |  | interna | só para centro de custo de contrato; FK declarada em 02_comercial.sql |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.convencao_coletiva`

Convenção coletiva por sindicato e município: explica por que o mesmo cargo custa diferente por cidade

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `sindicato` | `varchar(160)` | não |  |  | interna |  |
| `municipio_id` | `bigint unsigned` | não | FK → cadastro.municipio |  | interna |  |
| `mes_data_base` | `tinyint unsigned` | não |  |  | interna | mês do reajuste anual (1 a 12) |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.endereco`

Endereços de filial, cliente, local de trabalho e colaborador

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `logradouro` | `varchar(160)` | não |  |  | pessoal | quando o endereço é de colaborador |
| `numero` | `varchar(20)` | sim |  |  | interna |  |
| `complemento` | `varchar(60)` | sim |  |  | interna |  |
| `bairro` | `varchar(80)` | sim |  |  | interna |  |
| `municipio_id` | `bigint unsigned` | não | FK → cadastro.municipio |  | interna |  |
| `cep` | `char(8)` | sim |  |  | pessoal | quando o endereço é de colaborador |
| `tipo` | `varchar(20)` | não |  |  | interna | FILIAL, CLIENTE, LOCAL_TRABALHO ou COLABORADOR |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.escala` · referência pública

Escalas de trabalho: definem a jornada esperada no ponto

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `codigo` | `varchar(10)` | não | único |  | pública | 5x2, 6x1, 12x36 |
| `descricao` | `varchar(100)` | não |  |  | pública |  |
| `horas_semanais` | `decimal(5,2)` | não |  |  | pública |  |
| `dias_ciclo` | `tinyint unsigned` | não |  |  | pública | tamanho do ciclo em dias |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |

### `cadastro.feriado` · referência pública

Feriados (vêm da BrasilAPI e dos municípios): quase todo indicador é medido em dias úteis

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `data` | `date` | não |  |  | pública |  |
| `nome` | `varchar(100)` | não |  |  | pública |  |
| `abrangencia` | `varchar(10)` | não |  |  | pública | NACIONAL, ESTADUAL ou MUNICIPAL |
| `municipio_id` | `bigint unsigned` | sim | FK → cadastro.municipio |  | pública | só para feriado municipal |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |

### `cadastro.filial`

As três unidades: Atibaia (matriz), Bragança Paulista e Extrema

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(10)` | não | único |  | interna |  |
| `nome` | `varchar(80)` | não |  |  | interna |  |
| `tipo` | `varchar(10)` | não |  |  | interna | MATRIZ ou FILIAL |
| `endereco_id` | `bigint unsigned` | não | FK → cadastro.endereco |  | interna |  |
| `dt_abertura` | `date` | não |  |  | interna |  |
| `ativo` | `tinyint(1)` | não |  | 1 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.funcao` · referência pública

Cerca de 40 funções: auxiliar de produção, operador de empilhadeira, conferente, repositor

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `codigo` | `varchar(10)` | não | único |  | pública |  |
| `nome` | `varchar(100)` | não |  |  | pública |  |
| `cbo` | `char(6)` | sim |  |  | pública | Classificação Brasileira de Ocupações |
| `familia` | `varchar(60)` | sim |  |  | pública | PRODUCAO, LOGISTICA, ADMINISTRATIVO, COMERCIO |
| `nivel` | `varchar(20)` | sim |  |  | pública | AUXILIAR, OPERADOR, TECNICO, LIDER |
| `fl_insalubre` | `tinyint(1)` | não |  | 0 | pública |  |
| `fl_periculosidade` | `tinyint(1)` | não |  | 0 | pública |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |

### `cadastro.motivo`

Catálogo único de motivos: desligamento, reprovação, cancelamento de vaga, perda de contrato, afastamento

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `tipo` | `varchar(30)` | não | único |  | interna | a que evento o motivo se aplica |
| `codigo` | `varchar(20)` | não | único |  | interna |  |
| `descricao` | `varchar(160)` | não |  |  | interna |  |
| `grupo` | `varchar(40)` | sim |  |  | interna | agrupamento analítico (MERCADO, SERVICO, PESSOAL, LEGAL) |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.municipio` · referência pública

Município: usado por cliente, posto, colaborador e pela alíquota de ISS

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `nome` | `varchar(120)` | não |  |  | pública |  |
| `uf` | `char(2)` | não |  |  | pública |  |
| `regiao_id` | `bigint unsigned` | não | FK → cadastro.regiao |  | pública |  |
| `codigo_ibge` | `char(7)` | não | único |  | pública | código IBGE de 7 dígitos, chave para a API de municípios |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |

### `cadastro.parametro`

Parâmetros com vigência: prazos legais (180 e 90 dias), markup padrão, limites de alerta

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `chave` | `varchar(60)` | não | único |  | interna | ex.: PRAZO_TEMPORARIO_DIAS, MARKUP_PADRAO, ALERTA_ASO_DIAS |
| `valor` | `varchar(200)` | não |  |  | interna |  |
| `vigencia_inicio` | `date` | não | único |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.piso_salarial`

Piso por convenção e função, com vigência: a base do custo por cabeça

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `convencao_id` | `bigint unsigned` | não | FK → cadastro.convencao_coletiva |  | interna |  |
| `funcao_id` | `bigint unsigned` | não | FK → cadastro.funcao |  | interna |  |
| `valor_piso` | `decimal(14,2)` | não |  |  | interna |  |
| `adicional_insalubridade_pct` | `decimal(7,4)` | não |  | 0.0000 | interna |  |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `cadastro.regiao` · referência pública

Agrupamento comercial de municípios (eixo Fernão Dias, Vale, etc.)

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `nome` | `varchar(60)` | não | único |  | pública |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |


<a id="comercial"></a>

## `comercial`

### `comercial.cliente`

Cerca de 90 clientes ao longo do arco, cerca de 45 ativos hoje

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `razao_social` | `varchar(160)` | não |  |  | interna |  |
| `nome_fantasia` | `varchar(120)` | sim |  |  | interna |  |
| `cnpj` | `char(14)` | não | único |  | interna |  |
| `porte` | `varchar(10)` | não |  |  | interna | MEI, ME, EPP, MEDIA ou GRANDE |
| `setor` | `varchar(60)` | não |  |  | interna | INDUSTRIA, LOGISTICA, VAREJO, SERVICOS, AGRO |
| `municipio_id` | `bigint unsigned` | não | FK → cadastro.municipio |  | interna |  |
| `endereco_id` | `bigint unsigned` | sim | FK → cadastro.endereco |  | interna |  |
| `dt_primeiro_contrato` | `date` | sim |  |  | interna |  |
| `origem` | `varchar(12)` | não |  |  | interna | como o cliente chegou: INDICACAO, PROSPECCAO, LICITACAO, SITE, RETORNO |
| `ativo` | `tinyint(1)` | não |  | 1 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.cliente_contato`

Quem cobra o SLA do outro lado

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `cliente_id` | `bigint unsigned` | não | FK → comercial.cliente |  | interna |  |
| `nome` | `varchar(120)` | não |  |  | pessoal |  |
| `cargo` | `varchar(80)` | sim |  |  | interna |  |
| `email` | `varchar(160)` | sim |  |  | pessoal |  |
| `telefone` | `varchar(20)` | sim |  |  | pessoal |  |
| `fl_principal` | `tinyint(1)` | não |  | 0 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.contrato`

O vínculo comercial; o encerramento com motivo é o que responde por que a empresa perdeu contratos

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `numero` | `varchar(20)` | não | único |  | interna |  |
| `cliente_id` | `bigint unsigned` | não | FK → comercial.cliente |  | interna |  |
| `tipo_servico` | `varchar(15)` | não |  |  | interna | TEMPORARIO, TERCEIRIZACAO, RECRUTAMENTO ou TREINAMENTO |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial |  | interna |  |
| `centro_custo_id` | `bigint unsigned` | não | FK → cadastro.centro_custo |  | interna |  |
| `dt_assinatura` | `date` | não |  |  | interna |  |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = prazo indeterminado |
| `prazo_pagamento_dias` | `smallint unsigned` | não |  | 30 | interna |  |
| `indice_reajuste` | `varchar(20)` | sim |  |  | interna | IPCA, INPC, CONVENCAO |
| `garantia_reposicao_dias` | `smallint unsigned` | não |  | 0 | interna | prazo para repor um colaborador sem custo |
| `status` | `varchar(10)` | não |  |  | interna | ATIVO, SUSPENSO ou ENCERRADO. O sistema real guarda status e vigência; a auditoria confere se batem |
| `dt_encerramento` | `date` | sim |  |  | interna |  |
| `motivo_encerramento_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna | responde se o cliente saiu por mercado ou por serviço |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.contrato_aditivo`

A linha do tempo do contrato: prorrogações, reajustes e mudanças de escopo

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato, único |  | interna |  |
| `numero` | `smallint unsigned` | não | único |  | interna |  |
| `tipo` | `varchar(12)` | não |  |  | interna | PRORROGACAO, REAJUSTE ou ESCOPO |
| `dt_assinatura` | `date` | não |  |  | interna |  |
| `vigencia_nova` | `date` | sim |  |  | interna |  |
| `percentual_reajuste` | `decimal(7,4)` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.contrato_ocorrencia`

A curva de reclamações que antecede a saída do cliente em 6 a 9 meses

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato |  | interna |  |
| `posto_id` | `bigint unsigned` | sim | FK → comercial.posto |  | interna |  |
| `dt_ocorrencia` | `date` | não |  |  | interna |  |
| `tipo` | `varchar(15)` | não |  |  | interna | RECLAMACAO, ELOGIO, ADVERTENCIA ou AVISO_RESCISAO |
| `descricao` | `varchar(500)` | sim |  |  | interna |  |
| `motivo_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.posto`

A unidade de receita: o cliente contrata postos, não pessoas

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato |  | interna |  |
| `funcao_id` | `bigint unsigned` | não | FK → cadastro.funcao |  | interna |  |
| `quantidade` | `smallint unsigned` | não |  |  | interna | posições contratadas neste posto |
| `turno` | `varchar(12)` | não |  |  | interna | MANHA, TARDE, NOITE, COMERCIAL ou REVEZAMENTO |
| `escala_id` | `bigint unsigned` | não | FK → cadastro.escala |  | interna |  |
| `endereco_id` | `bigint unsigned` | não | FK → cadastro.endereco |  | interna | local de trabalho |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.posto_preco`

Preço do posto com vigência própria, para o reajuste não reescrever o passado

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `posto_id` | `bigint unsigned` | não | FK → comercial.posto |  | interna |  |
| `valor_mensal` | `decimal(14,2)` | não |  |  | interna |  |
| `valor_hora` | `decimal(14,2)` | não |  |  | interna |  |
| `markup_aplicado` | `decimal(7,4)` | não |  |  | interna | multiplicador sobre o custo estimado |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `comercial.sla_contrato`

Metas contratuais: é o que permite dizer se o cliente saiu por mercado ou por serviço

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato, único |  | interna |  |
| `indicador` | `varchar(15)` | não | único |  | interna | TIME_TO_FILL, REPOSICAO ou ABSENTEISMO |
| `meta_valor` | `decimal(10,2)` | não |  |  | interna |  |
| `unidade` | `varchar(20)` | não |  |  | interna | DIAS ou PCT |
| `penalidade_pct` | `decimal(7,4)` | não |  | 0.0000 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="ats"></a>

## `ats`

### `ats.candidato`

Cerca de 60 mil candidatos; é aqui que moram os duplicados e os CPF inválidos. Prazo de retenção para não contratado definido em cadastro.parametro

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `nome` | `varchar(160)` | não |  |  | pessoal |  |
| `cpf` | `char(11)` | sim |  |  | pessoal | sem UNIQUE de propósito: duplicados e inválidos são sujeira de origem, medida na auditoria |
| `dt_nascimento` | `date` | sim |  |  | pessoal |  |
| `sexo` | `char(1)` | sim |  |  | pessoal | F, M ou N (não informado) |
| `municipio_id` | `bigint unsigned` | sim | FK → cadastro.municipio |  | interna |  |
| `telefone` | `varchar(20)` | sim |  |  | pessoal |  |
| `email` | `varchar(160)` | sim |  |  | pessoal |  |
| `escolaridade` | `varchar(20)` | sim |  |  | interna | FUNDAMENTAL, MEDIO, TECNICO, SUPERIOR |
| `fonte_id` | `bigint unsigned` | não | FK → ats.fonte_candidato |  | interna |  |
| `dt_cadastro` | `date` | não |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.candidato_experiencia`

Experiências anteriores: matéria para triagem e para análise de aderência

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `candidato_id` | `bigint unsigned` | não | FK → ats.candidato |  | interna |  |
| `empresa` | `varchar(160)` | não |  |  | interna |  |
| `funcao_id` | `bigint unsigned` | sim | FK → cadastro.funcao |  | interna |  |
| `dt_inicio` | `date` | não |  |  | interna |  |
| `dt_fim` | `date` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.candidatura`

Cerca de 300 mil: a linha do funil. Um candidato, várias candidaturas

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `vaga_id` | `bigint unsigned` | não | FK → ats.vaga |  | interna |  |
| `candidato_id` | `bigint unsigned` | não | FK → ats.candidato |  | interna |  |
| `dt_inscricao` | `date` | não |  |  | interna |  |
| `etapa_atual_id` | `bigint unsigned` | não | FK → ats.etapa_funil |  | interna |  |
| `status` | `varchar(12)` | não |  |  | interna | EM_ANDAMENTO, APROVADA, REPROVADA, DESISTENCIA ou CANCELADA |
| `dt_conclusao` | `date` | sim |  |  | interna |  |
| `motivo_reprovacao_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.candidatura_etapa`

Cerca de 750 mil: cada passagem de etapa com data, o que produz conversão e tempo por etapa

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `candidatura_id` | `bigint unsigned` | não | FK → ats.candidatura |  | interna |  |
| `etapa_id` | `bigint unsigned` | não | FK → ats.etapa_funil |  | interna |  |
| `dt_entrada` | `datetime(6)` | não |  |  | interna |  |
| `dt_saida` | `datetime(6)` | sim |  |  | interna |  |
| `resultado` | `varchar(10)` | não |  | PENDENTE | interna | APROVADO, REPROVADO, DESISTIU ou PENDENTE |
| `motivo_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.entrevista`

O no-show de entrevista mora aqui

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `candidatura_id` | `bigint unsigned` | não | FK → ats.candidatura |  | interna |  |
| `tipo` | `varchar(8)` | não |  |  | interna | INTERNA ou CLIENTE |
| `dt_agendada` | `datetime(6)` | não |  |  | interna |  |
| `dt_realizada` | `datetime(6)` | sim |  |  | interna |  |
| `fl_compareceu` | `tinyint(1)` | sim |  |  | interna | NULL enquanto não aconteceu; FALSE é o no-show |
| `usuario_id` | `bigint unsigned` | sim | FK → seguranca.usuario |  | interna | quem conduziu; FK declarada em 10_seguranca.sql |
| `resultado` | `varchar(15)` | sim |  |  | interna | APROVADO, REPROVADO, REAGENDAR ou NAO_COMPARECEU |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.etapa_funil`

Triagem, entrevista interna, encaminhamento, entrevista no cliente, aprovação

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(20)` | não | único |  | interna |  |
| `nome` | `varchar(80)` | não |  |  | interna |  |
| `ordem` | `tinyint unsigned` | não |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.fonte_candidato`

De onde o candidato veio: base do custo por contratação por fonte

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `nome` | `varchar(15)` | não | único |  | interna | INDICACAO, PORTAL, REDES, BANCO_INTERNO ou PRESENCIAL |
| `custo_medio` | `decimal(14,2)` | não |  | 0.00 | interna | custo médio por candidato captado |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.requisicao`

O pedido do cliente: o começo de tudo

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `numero` | `varchar(20)` | não | único |  | interna |  |
| `cliente_id` | `bigint unsigned` | não | FK → comercial.cliente |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato |  | interna |  |
| `posto_id` | `bigint unsigned` | sim | FK → comercial.posto |  | interna |  |
| `quantidade` | `smallint unsigned` | não |  |  | interna |  |
| `dt_abertura` | `date` | não |  |  | interna |  |
| `dt_necessidade` | `date` | não |  |  | interna | quando o cliente precisa da pessoa no posto |
| `prioridade` | `varchar(8)` | não |  |  | interna | BAIXA, NORMAL, ALTA ou URGENTE |
| `status` | `varchar(15)` | não |  |  | interna | ABERTA, EM_ATENDIMENTO, ATENDIDA ou CANCELADA |
| `motivo_cancelamento_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ats.vaga`

Cerca de 20 mil vagas no arco; o time-to-fill nasce de dt_abertura e dt_fechamento

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `requisicao_id` | `bigint unsigned` | não | FK → ats.requisicao |  | interna |  |
| `codigo` | `varchar(20)` | não | único |  | interna |  |
| `titulo` | `varchar(120)` | não |  |  | interna |  |
| `funcao_id` | `bigint unsigned` | não | FK → cadastro.funcao |  | interna |  |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial |  | interna | filial que atende a vaga |
| `quantidade_posicoes` | `smallint unsigned` | não |  |  | interna |  |
| `dt_abertura` | `date` | não |  |  | interna |  |
| `dt_fechamento` | `date` | sim |  |  | interna |  |
| `status` | `varchar(12)` | não |  |  | interna | ABERTA, EM_TRIAGEM, PREENCHIDA ou CANCELADA |
| `salario_previsto` | `decimal(14,2)` | não |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="pessoas"></a>

## `pessoas`

### `pessoas.afastamento`

Absenteísmo e vínculo com acidente

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `tipo` | `varchar(10)` | não |  |  | interna | ATESTADO, ACIDENTE, LICENCA ou SUSPENSAO |
| `dt_inicio` | `date` | não |  |  | interna |  |
| `dt_fim` | `date` | sim |  |  | interna | NULL = afastado hoje |
| `motivo_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna |  |
| `cid_grupo` | `varchar(10)` | sim |  |  | pessoal sensível | grupo da CID, dado de saúde |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.alocacao`

A tabela mais importante do banco: headcount, ocupação, dias descobertos e custo por contrato saem dela

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `contrato_trabalho_id` | `bigint unsigned` | não | FK → pessoas.contrato_trabalho |  | interna |  |
| `posto_id` | `bigint unsigned` | não | FK → comercial.posto |  | interna |  |
| `dt_inicio` | `date` | não |  |  | interna |  |
| `dt_fim` | `date` | sim |  |  | interna | NULL = alocado hoje |
| `motivo_fim_id` | `bigint unsigned` | sim | FK → cadastro.motivo |  | interna |  |
| `substituindo_alocacao_id` | `bigint unsigned` | sim | FK → pessoas.alocacao |  | interna | quando esta alocação repõe outra (garantia de reposição) |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.colaborador`

O candidato depois de admitido. Uma pessoa, uma matrícula, vários contratos de trabalho ao longo do tempo

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `candidato_id` | `bigint unsigned` | sim | FK → ats.candidato, único |  | interna | o vínculo com o funil permite medir o custo de conversão |
| `matricula` | `varchar(12)` | não | único |  | interna |  |
| `nome` | `varchar(160)` | não |  |  | pessoal |  |
| `cpf` | `char(11)` | não | único |  | pessoal |  |
| `dt_nascimento` | `date` | não |  |  | pessoal |  |
| `municipio_id` | `bigint unsigned` | não | FK → cadastro.municipio |  | interna |  |
| `endereco_id` | `bigint unsigned` | sim | FK → cadastro.endereco |  | pessoal |  |
| `pis` | `char(11)` | sim |  |  | pessoal |  |
| `dt_admissao_primeira` | `date` | não |  |  | interna |  |
| `ativo` | `tinyint(1)` | não |  | 1 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.colaborador_documento`

Documentação da admissão

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `tipo` | `varchar(12)` | não |  |  | interna | RG, CTPS, TITULO, RESERVISTA ou CNH |
| `numero` | `varchar(30)` | não |  |  | pessoal |  |
| `orgao` | `varchar(30)` | sim |  |  | interna |  |
| `dt_emissao` | `date` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.contrato_trabalho`

O vínculo CLT: o prazo legal do temporário mora aqui

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `tipo` | `varchar(12)` | não |  |  | interna | TEMPORARIO, EFETIVO ou TERCEIRIZADO |
| `funcao_id` | `bigint unsigned` | não | FK → cadastro.funcao |  | interna |  |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial |  | interna |  |
| `dt_admissao` | `date` | não |  |  | interna |  |
| `dt_prevista_termino` | `date` | sim |  |  | interna | só para temporário |
| `dt_rescisao` | `date` | sim |  |  | interna |  |
| `salario_base` | `decimal(14,2)` | não |  |  | interna |  |
| `escala_id` | `bigint unsigned` | não | FK → cadastro.escala |  | interna |  |
| `prazo_legal_dias` | `smallint unsigned` | sim |  |  | interna | temporário: 180 dias, mais 90 com prorrogação. Prazo estourado sem prorrogação é irregularidade |
| `status` | `varchar(10)` | não |  |  | interna | ATIVO ou ENCERRADO |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.contrato_trabalho_prorrogacao`

A prorrogação legal do temporário; sua ausência com prazo estourado é irregularidade

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `contrato_trabalho_id` | `bigint unsigned` | não | FK → pessoas.contrato_trabalho |  | interna |  |
| `dt_assinatura` | `date` | não |  |  | interna |  |
| `dt_novo_termino` | `date` | não |  |  | interna |  |
| `dias_adicionais` | `smallint unsigned` | não |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.dependente`

Dependentes: salário-família e IR na folha

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `nome` | `varchar(160)` | não |  |  | pessoal |  |
| `parentesco` | `varchar(10)` | não |  |  | interna | FILHO, CONJUGE, ENTEADO, PAI ou MAE |
| `dt_nascimento` | `date` | não |  |  | pessoal |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `pessoas.desligamento`

Turnover por tipo; a efetivação pelo cliente é receita e perda ao mesmo tempo

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `contrato_trabalho_id` | `bigint unsigned` | não | FK → pessoas.contrato_trabalho, único |  | interna |  |
| `dt_desligamento` | `date` | não |  |  | interna |  |
| `tipo` | `varchar(20)` | não |  |  | interna | VOLUNTARIO, INVOLUNTARIO, FIM_CONTRATO ou EFETIVACAO_CLIENTE |
| `motivo_id` | `bigint unsigned` | não | FK → cadastro.motivo |  | interna |  |
| `dias_aviso_previo` | `smallint unsigned` | não |  | 0 | interna |  |
| `valor_rescisao` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `dt_homologacao` | `date` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="ponto"></a>

## `ponto`

### `ponto.apontamento`

Cerca de 1,1 milhão: o dia consolidado a partir das marcações; é o que a folha consome

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador, único |  | interna |  |
| `alocacao_id` | `bigint unsigned` | sim | FK → pessoas.alocacao |  | interna | NULL quando o dia não tem posto (retaguarda, entre alocações) |
| `data` | `date` | não | único |  | interna |  |
| `horas_trabalhadas` | `decimal(5,2)` | não |  | 0.00 | interna |  |
| `horas_extras` | `decimal(5,2)` | não |  | 0.00 | interna |  |
| `horas_noturnas` | `decimal(5,2)` | não |  | 0.00 | interna |  |
| `status` | `varchar(8)` | não |  |  | interna | NORMAL, FALTA, ATESTADO, FERIADO ou FOLGA |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ponto.banco_horas`

Passivo que ninguém enxerga até a rescisão

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador, único |  | interna |  |
| `competencia` | `date` | não | único |  | interna | primeiro dia do mês |
| `saldo_anterior` | `decimal(7,2)` | não |  | 0.00 | interna |  |
| `creditos` | `decimal(7,2)` | não |  | 0.00 | interna |  |
| `debitos` | `decimal(7,2)` | não |  | 0.00 | interna |  |
| `saldo_final` | `decimal(7,2)` | não |  | 0.00 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ponto.escala_colaborador`

A jornada esperada muda quando a pessoa troca de posto

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `escala_id` | `bigint unsigned` | não | FK → cadastro.escala |  | interna |  |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ponto.marcacao`

Cerca de 4,4 milhões: o registro bruto do relógio, 4 por dia. Sem UNIQUE de propósito: batida duplicada é sujeira de origem

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `data` | `date` | não |  |  | interna |  |
| `hora` | `time` | não |  |  | interna |  |
| `tipo` | `varchar(20)` | não |  |  | interna | ENTRADA, SAIDA_INTERVALO, RETORNO_INTERVALO ou SAIDA |
| `origem` | `varchar(8)` | não |  |  | interna | RELOGIO, APP ou MANUAL |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `ponto.ocorrencia_ponto`

Absenteísmo por posto, que é o que o cliente sente

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `apontamento_id` | `bigint unsigned` | não | FK → ponto.apontamento |  | interna |  |
| `tipo` | `varchar(20)` | não |  |  | interna | FALTA_JUSTIFICADA, FALTA_INJUSTIFICADA, ATRASO ou SAIDA_ANTECIPADA |
| `minutos` | `smallint unsigned` | não |  | 0 | interna |  |
| `justificativa` | `varchar(300)` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="folha"></a>

## `folha`

### `folha.beneficio`

Benefícios por convenção

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(10)` | não | único |  | interna |  |
| `nome` | `varchar(80)` | não |  |  | interna |  |
| `tipo` | `varchar(6)` | não |  |  | interna | VT, VR, VA ou PLANO |
| `valor_padrao` | `decimal(14,2)` | não |  |  | interna |  |
| `desconto_pct` | `decimal(7,4)` | não |  | 0.0000 | interna | parte descontada do colaborador |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `folha.colaborador_beneficio`

Quem recebe o quê, e desde quando

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `beneficio_id` | `bigint unsigned` | não | FK → folha.beneficio |  | interna |  |
| `valor` | `decimal(14,2)` | não |  |  | interna |  |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `folha.evento_folha`

Cerca de 30 eventos: salário, adicional noturno, HE 50 e 100, DSR, INSS, FGTS, VT, VR

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(10)` | não | único |  | interna |  |
| `descricao` | `varchar(100)` | não |  |  | interna |  |
| `tipo` | `varchar(10)` | não |  |  | interna | PROVENTO, DESCONTO, ENCARGO ou PROVISAO |
| `fl_incide_inss` | `tinyint(1)` | não |  | 0 | interna |  |
| `fl_incide_fgts` | `tinyint(1)` | não |  | 0 | interna |  |
| `fl_incide_ir` | `tinyint(1)` | não |  | 0 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `folha.folha_competencia`

O fechamento mensal da folha por filial

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `competencia` | `date` | não | único |  | interna | primeiro dia do mês |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial, único |  | interna |  |
| `dt_fechamento` | `date` | sim |  |  | interna |  |
| `status` | `varchar(8)` | não |  |  | interna | ABERTA, FECHADA ou REABERTA |
| `total_proventos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `total_descontos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `total_encargos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `folha.folha_item`

Cerca de 860 mil: uma linha por pessoa e evento em cada competência

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `folha_competencia_id` | `bigint unsigned` | não | FK → folha.folha_competencia |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `contrato_trabalho_id` | `bigint unsigned` | não | FK → pessoas.contrato_trabalho |  | interna |  |
| `evento_id` | `bigint unsigned` | não | FK → folha.evento_folha |  | interna |  |
| `referencia` | `decimal(10,2)` | sim |  |  | interna | base do evento: horas, dias, percentual |
| `valor` | `decimal(14,2)` | não |  |  | pessoal | remuneração individual |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `folha.provisao`

Cerca de 114 mil: a provisão aperta a margem exatamente no mês de maior receita

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `competencia` | `date` | não | único |  | interna | primeiro dia do mês |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador, único |  | interna |  |
| `tipo` | `varchar(16)` | não | único |  | interna | DECIMO_TERCEIRO, FERIAS ou ENCARGOS |
| `valor_mes` | `decimal(14,2)` | não |  |  | interna |  |
| `saldo_acumulado` | `decimal(14,2)` | não |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `folha.rateio_custo`

A tabela que torna a margem por cliente possível: leva o custo de cada pessoa até o posto onde ela trabalhou

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `competencia` | `date` | não |  |  | interna | primeiro dia do mês |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `alocacao_id` | `bigint unsigned` | não | FK → pessoas.alocacao |  | interna |  |
| `centro_custo_id` | `bigint unsigned` | não | FK → cadastro.centro_custo |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato |  | interna |  |
| `posto_id` | `bigint unsigned` | não | FK → comercial.posto |  | interna |  |
| `valor_salario` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_encargos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_provisoes` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_beneficios` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `custo_total` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="financeiro"></a>

## `financeiro`

### `financeiro.aliquota` · referência pública

Alíquota por tributo, município e vigência: ISS de Atibaia e Bragança difere do de Extrema

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `tributo_id` | `bigint unsigned` | não | FK → financeiro.tributo |  | pública |  |
| `municipio_id` | `bigint unsigned` | sim | FK → cadastro.municipio |  | pública | só para ISS, que muda por município |
| `aliquota` | `decimal(7,4)` | não |  |  | pública |  |
| `base_presumida_pct` | `decimal(7,4)` | sim |  |  | pública | base de presunção no lucro presumido |
| `vigencia_inicio` | `date` | não |  |  | pública |  |
| `vigencia_fim` | `date` | sim |  |  | pública | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |

### `financeiro.consolidado_gerencial`

A planilha gerencial carregada no sistema: diverge da operação a partir de 2022 e é o achado central da auditoria

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `competencia` | `date` | não | único |  | interna | primeiro dia do mês |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial, único |  | interna |  |
| `headcount_informado` | `int unsigned` | não |  |  | interna |  |
| `vagas_abertas_informado` | `int unsigned` | não |  |  | interna |  |
| `faturamento_informado` | `decimal(14,2)` | não |  |  | interna |  |
| `custo_informado` | `decimal(14,2)` | não |  |  | interna |  |
| `dt_lancamento` | `date` | não |  |  | interna |  |
| `origem` | `varchar(10)` | não |  | PLANILHA | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.fatura`

A nota de serviço do mês

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `numero` | `varchar(20)` | não | único |  | interna |  |
| `cliente_id` | `bigint unsigned` | não | FK → comercial.cliente |  | interna |  |
| `contrato_id` | `bigint unsigned` | não | FK → comercial.contrato |  | interna |  |
| `competencia` | `date` | não |  |  | interna | primeiro dia do mês medido |
| `dt_emissao` | `date` | não |  |  | interna |  |
| `valor_bruto` | `decimal(14,2)` | não |  |  | interna |  |
| `valor_impostos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_liquido` | `decimal(14,2)` | não |  |  | interna |  |
| `status` | `varchar(10)` | não |  |  | interna | EMITIDA, EM_ABERTO, QUITADA ou CANCELADA |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.fatura_item`

Cerca de 52 mil: a medição do mês, posto a posto

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `fatura_id` | `bigint unsigned` | não | FK → financeiro.fatura |  | interna |  |
| `posto_id` | `bigint unsigned` | não | FK → comercial.posto |  | interna |  |
| `qtd_dias_trabalhados` | `smallint unsigned` | não |  | 0 | interna |  |
| `qtd_faltas` | `smallint unsigned` | não |  | 0 | interna |  |
| `valor_postos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_horas_extras` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_descontos` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `valor_total` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.fornecedor`

A outra ponta do contas a pagar

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `razao_social` | `varchar(160)` | não |  |  | interna |  |
| `cnpj` | `char(14)` | não | único |  | interna |  |
| `tipo` | `varchar(12)` | não |  |  | interna | EXAMES, TREINAMENTO, BENEFICIOS ou SERVICOS |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.imposto_apurado`

Apuração mês a mês conforme o regime vigente

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `competencia` | `date` | não |  |  | interna | primeiro dia do mês |
| `tributo_id` | `bigint unsigned` | não | FK → financeiro.tributo |  | interna |  |
| `municipio_id` | `bigint unsigned` | sim | FK → cadastro.municipio |  | interna | só para ISS |
| `base_calculo` | `decimal(14,2)` | não |  |  | interna |  |
| `aliquota` | `decimal(7,4)` | não |  |  | interna |  |
| `valor_devido` | `decimal(14,2)` | não |  |  | interna |  |
| `titulo_pagar_id` | `bigint unsigned` | sim | FK → financeiro.titulo_pagar |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.regime_tributario`

O regime tributário é parâmetro por competência

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `regime` | `varchar(16)` | não |  |  | interna | LUCRO_PRESUMIDO ou LUCRO_REAL. Simples é vedado para cessão de mão de obra |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.titulo_pagar`

O que sai

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `tipo` | `varchar(12)` | não |  |  | interna | FOLHA, ENCARGOS, IMPOSTOS, FORNECEDOR ou BENEFICIOS |
| `fornecedor_id` | `bigint unsigned` | sim | FK → financeiro.fornecedor |  | interna |  |
| `centro_custo_id` | `bigint unsigned` | não | FK → cadastro.centro_custo |  | interna |  |
| `competencia` | `date` | não |  |  | interna | primeiro dia do mês |
| `dt_vencimento` | `date` | não |  |  | interna |  |
| `valor` | `decimal(14,2)` | não |  |  | interna |  |
| `status` | `varchar(10)` | não |  |  | interna | ABERTO, PAGO, ATRASADO ou CANCELADO |
| `dt_pagamento` | `date` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.titulo_receber`

Inadimplência e prazo médio de recebimento

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `fatura_id` | `bigint unsigned` | não | FK → financeiro.fatura, único |  | interna |  |
| `cliente_id` | `bigint unsigned` | não | FK → comercial.cliente |  | interna |  |
| `numero_parcela` | `tinyint unsigned` | não | único | 1 | interna |  |
| `dt_vencimento` | `date` | não |  |  | interna |  |
| `valor` | `decimal(14,2)` | não |  |  | interna |  |
| `status` | `varchar(10)` | não |  |  | interna | ABERTO, PAGO, ATRASADO ou CANCELADO |
| `dt_pagamento` | `date` | sim |  |  | interna |  |
| `valor_pago` | `decimal(14,2)` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `financeiro.tributo` · referência pública

Catálogo de tributos

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `codigo` | `varchar(10)` | não | único |  | pública | ISS, PIS, COFINS, IRPJ, CSLL |
| `descricao` | `varchar(80)` | não |  |  | pública |  |
| `esfera` | `varchar(10)` | não |  |  | pública | FEDERAL, ESTADUAL ou MUNICIPAL |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |


<a id="treinamento"></a>

## `treinamento`

### `treinamento.certificado`

O documento com prazo, que é o que vira alerta

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `turma_participante_id` | `bigint unsigned` | não | FK → treinamento.turma_participante, único |  | interna |  |
| `numero` | `varchar(30)` | não | único |  | interna |  |
| `dt_emissao` | `date` | não |  |  | interna |  |
| `dt_validade` | `date` | sim |  |  | interna | NULL = não vence |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `treinamento.curso`

Catálogo de cursos, com validade quando a norma exige reciclagem

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(10)` | não | único |  | interna |  |
| `nome` | `varchar(120)` | não |  |  | interna |  |
| `tipo` | `varchar(15)` | não |  |  | interna | NR, TECNICO ou COMPORTAMENTAL |
| `carga_horaria` | `decimal(5,1)` | não |  |  | interna |  |
| `validade_meses` | `smallint unsigned` | sim |  |  | interna | NULL = não vence |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `treinamento.curso_funcao`

Quais treinamentos são exigidos para qual função

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `curso_id` | `bigint unsigned` | não | FK → treinamento.curso, único |  | interna |  |
| `funcao_id` | `bigint unsigned` | não | FK → cadastro.funcao, único |  | interna |  |
| `fl_obrigatorio` | `tinyint(1)` | não |  | 1 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `treinamento.turma`

Turma interna ou treinamento vendido ao cliente

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `curso_id` | `bigint unsigned` | não | FK → treinamento.curso |  | interna |  |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial |  | interna |  |
| `cliente_id` | `bigint unsigned` | sim | FK → comercial.cliente |  | interna | preenchido quando o treinamento é vendido ao cliente |
| `dt_inicio` | `date` | não |  |  | interna |  |
| `dt_fim` | `date` | não |  |  | interna |  |
| `instrutor` | `varchar(120)` | sim |  |  | interna |  |
| `custo_total` | `decimal(14,2)` | não |  | 0.00 | interna |  |
| `fornecedor_id` | `bigint unsigned` | sim | FK → financeiro.fornecedor |  | interna | quando a turma é comprada de terceiro |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `treinamento.turma_participante`

Quem fez a turma

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `turma_id` | `bigint unsigned` | não | FK → treinamento.turma, único |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador, único |  | interna |  |
| `presenca_pct` | `decimal(5,2)` | não |  | 0.00 | interna |  |
| `fl_aprovado` | `tinyint(1)` | não |  | 0 | interna |  |
| `nota` | `decimal(4,1)` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="sst"></a>

## `sst`

### `sst.acidente`

Cerca de 2 acidentes por 100 alocados por ano

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `alocacao_id` | `bigint unsigned` | sim | FK → pessoas.alocacao |  | interna |  |
| `dt_acidente` | `date` | não |  |  | interna |  |
| `tipo` | `varchar(8)` | não |  |  | pessoal sensível | TIPICO, TRAJETO ou DOENCA |
| `gravidade` | `varchar(8)` | não |  |  | pessoal sensível | LEVE, MODERADA, GRAVE ou FATAL |
| `dias_afastamento` | `smallint unsigned` | não |  | 0 | interna |  |
| `afastamento_id` | `bigint unsigned` | sim | FK → pessoas.afastamento |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `sst.aso`

Cerca de 40 mil: ASO vencido com pessoa alocada é o alerta mais caro do painel

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `colaborador_id` | `bigint unsigned` | não | FK → pessoas.colaborador |  | interna |  |
| `tipo_exame_id` | `bigint unsigned` | não | FK → sst.tipo_exame |  | interna |  |
| `dt_exame` | `date` | não |  |  | interna |  |
| `dt_validade` | `date` | sim |  |  | interna |  |
| `resultado` | `varchar(15)` | não |  |  | pessoal sensível | APTO, INAPTO ou APTO_RESTRICAO, dado de saúde |
| `medico_crm` | `varchar(20)` | sim |  |  | interna |  |
| `fornecedor_id` | `bigint unsigned` | sim | FK → financeiro.fornecedor |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `sst.cat`

A Comunicação de Acidente de Trabalho, obrigatória

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `acidente_id` | `bigint unsigned` | não | FK → sst.acidente |  | interna |  |
| `numero` | `varchar(30)` | não | único |  | interna |  |
| `dt_emissao` | `date` | não |  |  | interna |  |
| `tipo_cat` | `varchar(10)` | não |  |  | interna | INICIAL, REABERTURA ou OBITO |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `sst.programa_sst`

Obrigação legal por cliente e contrato, com validade

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `tipo` | `varchar(6)` | não |  |  | interna | PGR, PCMSO ou LTCAT |
| `cliente_id` | `bigint unsigned` | não | FK → comercial.cliente |  | interna |  |
| `contrato_id` | `bigint unsigned` | sim | FK → comercial.contrato |  | interna |  |
| `dt_elaboracao` | `date` | não |  |  | interna |  |
| `dt_validade` | `date` | não |  |  | interna |  |
| `responsavel` | `varchar(120)` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `sst.risco_posto`

O adicional que entra na folha vem daqui

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `posto_id` | `bigint unsigned` | não | FK → comercial.posto |  | interna |  |
| `programa_sst_id` | `bigint unsigned` | não | FK → sst.programa_sst |  | interna |  |
| `agente_risco` | `varchar(80)` | não |  |  | interna | RUIDO, POEIRA, ERGONOMICO, QUIMICO, ALTURA |
| `grau` | `varchar(6)` | não |  |  | interna | BAIXO, MEDIO ou ALTO |
| `insalubridade_pct` | `decimal(7,4)` | não |  | 0.0000 | interna |  |
| `fl_periculosidade` | `tinyint(1)` | não |  | 0 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `sst.tipo_exame` · referência pública

Catálogo de tipos de exame ocupacional

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | pública |  |
| `codigo` | `varchar(15)` | não | único |  | pública | ADMISSIONAL, PERIODICO, MUDANCA_FUNCAO, RETORNO ou DEMISSIONAL |
| `periodicidade_meses` | `smallint unsigned` | sim |  |  | pública | só para periódico |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | pública |  |


<a id="seguranca"></a>

## `seguranca`

### `seguranca.log_auditoria`

Quem alterou o quê, com data: a trilha que o sistema futuro vai usar

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `usuario_id` | `bigint unsigned` | não | FK → seguranca.usuario |  | interna |  |
| `dt_evento` | `datetime(6)` | não |  |  | interna |  |
| `modulo` | `varchar(20)` | não |  |  | interna |  |
| `tabela` | `varchar(60)` | não |  |  | interna |  |
| `registro_id` | `bigint unsigned` | sim |  |  | interna | [sem FK] aponta para a tabela indicada na coluna tabela |
| `acao` | `varchar(10)` | não |  |  | interna | CRIAR, EDITAR, EXCLUIR, EXPORTAR ou LOGIN |
| `valor_anterior` | `json` | sim |  |  | pessoal | pode carregar o dado alterado |
| `valor_novo` | `json` | sim |  |  | pessoal | pode carregar o dado alterado |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `seguranca.perfil`

Os níveis do autoatendimento

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `codigo` | `varchar(12)` | não | único |  | interna | SOCIO, GERENTE, COORDENADOR, ASSISTENTE, FINANCEIRO ou TI |
| `nome` | `varchar(60)` | não |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `seguranca.permissao`

Matriz de permissão por módulo

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `perfil_id` | `bigint unsigned` | não | FK → seguranca.perfil, único |  | interna |  |
| `modulo` | `varchar(20)` | não | único |  | interna | nome do módulo (cadastro, comercial, ats, ...) |
| `acao` | `varchar(10)` | não | único |  | interna | LER, CRIAR, EDITAR, EXCLUIR ou EXPORTAR |
| `fl_permitido` | `tinyint(1)` | não |  | 0 | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `seguranca.usuario`

Cerca de 40 usuários internos ao longo do arco

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `login` | `varchar(40)` | não | único |  | interna |  |
| `nome` | `varchar(120)` | não |  |  | pessoal |  |
| `email` | `varchar(160)` | não |  |  | pessoal |  |
| `colaborador_id` | `bigint unsigned` | sim | FK → pessoas.colaborador |  | interna | quando o usuário também é colaborador |
| `filial_id` | `bigint unsigned` | não | FK → cadastro.filial |  | interna |  |
| `ativo` | `tinyint(1)` | não |  | 1 | interna |  |
| `dt_criacao` | `date` | não |  |  | interna |  |
| `ultimo_acesso` | `datetime(6)` | sim |  |  | interna |  |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

### `seguranca.usuario_perfil`

O escopo: a assistente vê a filial dela, a coordenadora vê o setor

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `usuario_id` | `bigint unsigned` | não | FK → seguranca.usuario |  | interna |  |
| `perfil_id` | `bigint unsigned` | não | FK → seguranca.perfil |  | interna |  |
| `filial_id` | `bigint unsigned` | sim | FK → cadastro.filial |  | interna | escopo: NULL = todas as filiais |
| `vigencia_inicio` | `date` | não |  |  | interna |  |
| `vigencia_fim` | `date` | sim |  |  | interna | NULL = vigente |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `atualizado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |


<a id="meta"></a>

## `meta`

### `meta.exclusao_auditoria`

Captura o DELETE que a marca d agua não veria; só insere, nunca atualiza

| coluna | tipo | nulo | chave | padrão | classe | descrição |
|---|---|---|---|---|---|---|
| `id` | `bigint unsigned` | não | PK |  | interna |  |
| `banco` | `varchar(30)` | não |  |  | interna | database da linha apagada |
| `tabela` | `varchar(60)` | não |  |  | interna |  |
| `registro_id` | `bigint unsigned` | não |  |  | interna | [sem FK] o id da linha apagada, que já não existe |
| `dt_exclusao` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |
| `usuario_banco` | `varchar(100)` | sim |  |  | interna | usuário de banco que executou o DELETE |
| `criado_em` | `datetime(6)` | não |  | CURRENT_TIMESTAMP(6) | interna |  |

---

[Início](#topo)
