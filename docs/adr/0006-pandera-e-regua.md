# ADR-0006 · pandera para esquema, régua própria para a história

**Situação:** aceito em 16/09/2026. Entra na v0.4.0 (régua) e v0.5.0 (pandera nos arquivos).

## Contexto

Dois tipos de validação diferentes. O primeiro é **de esquema**: o consolidado gerencial chega em Excel, os índices do CAGED em CSV, e cada camada do lake tem colunas, tipos, nulos e domínios que precisam ser declarados e conferidos. O segundo é **de negócio**: o dado sintético precisa contar a história certa (crescimento até 2024, queda sem prejuízo até 2026, defasagem de 6 a 9 meses entre reclamação e perda de contrato), e isso é uma banda, não um tipo.

## Decisão

**pandera** declara e confere esquema (arquivo e camada), dentro dos assets do Dagster: esquema reprovado, asset reprovado. A **régua própria** (`validacao/`) confere as bandas da história e os invariantes de conservação entre camadas; "reprovou, regenera".

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| Great Expectations | poderoso, mas traz contexto de dados, armazenamento de expectativas e interface que o caso não pede; o custo de operar não paga |
| Soda | validação por YAML e serviço; menos integrada ao Python dos assets |
| só régua própria | não fala a língua do mercado (esquema declarado) nem ganha os tipos e domínios de graça |
| só pandera | esquema não sabe se a empresa nunca deu prejuízo; a história é do caso, não da ferramenta |

## Consequências

- Todo arquivo que entra tem um esquema versionado no repositório.
- A régua é o contrato do dado sintético com o dossiê: as bandas são documentadas (`docs/06`, v0.4.0).
- Primeiro uso do pandera na v0.5.0 (card 5.4): o esquema do consolidado gerencial em `ingestao/planilhas.py`, com `strict=True` (coluna a mais é erro), unicidade de competência e filial, e checks de negócio no nível do quadro (competência é o primeiro do mês, lançamento não é anterior à competência, a pasta de trabalho do ano só tem competências daquele ano).
