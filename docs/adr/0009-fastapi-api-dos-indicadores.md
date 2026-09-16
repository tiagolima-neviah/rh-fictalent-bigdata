# ADR-0009 · FastAPI para servir os indicadores

**Situação:** aceito em 16/09/2026. Entra na v1.0.0.

## Contexto

Os indicadores da gold precisam ser consumidos por mais de um cliente (o painel web, um terceiro, um teste automatizado) com **contrato** (o que cada campo é), **versão** (mudar sem quebrar quem já consome), **autenticação** (quem pode ler o quê) e **saúde** (um endereço que diz se o serviço está vivo). Expor o banco direto não dá nada disso.

## Decisão

FastAPI: tipagem com pydantic, documentação OpenAPI gerada do código, `/v1` como prefixo de versão, token por consumidor, `/saude` para o healthcheck. Lê a gold (parquet via DuckDB) ou o warehouse, conforme o indicador.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| Flask | sem tipagem, validação nem OpenAPI nativos; tudo isso viraria código a mais |
| Django REST Framework | ORM e admin não servem a uma API só de leitura sobre parquet; peso sem uso |
| expor o Postgres do warehouse direto | sem contrato, sem versão, sem token por consumidor; cada cliente vira um usuário de banco |
| GraphQL | não há demanda de consulta flexível; os indicadores são poucos e conhecidos |

## Consequências

- Mesma família de ferramentas do painel web da série (FastAPI, HTMX, ECharts), o que reduz o que há para aprender.
- Testes da API incluem acesso negado (token errado, token sem direito ao indicador).
