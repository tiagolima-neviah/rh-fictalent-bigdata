# ADR-0007 · Grafana só para observabilidade

**Situação:** aceito em 15/09/2026 (ratificação da direção com a condição 4). De pé desde a v0.2.0; painéis na v0.3.0.

## Contexto

O pipeline precisa mostrar execuções, duração, linhas movidas, falhas e frescor do dado, e alertar quando algo para. A casa já entrega três canais de **negócio** (painel web próprio, Power BI, Tableau Public); um quarto canal para os mesmos indicadores seria trabalho sem aprendizado novo.

## Decisão

Grafana OSS, provisionado como código (fontes e painéis versionados), lendo os metadados do Dagster e o warehouse com um papel só de leitura, sem acesso anônimo e sem cadastro. Escopo: **observabilidade e alerta**. Painel de negócio não entra.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| Metabase | a edição aberta não exporta painel como código, e não cabe no plano gratuito de hospedagem; o painel viraria configuração manual, invisível no git |
| só a interface do Dagster | mostra execuções, mas não alerta, não cruza com o warehouse e não mede frescor do dado |
| Prometheus + exportadores | métricas de infraestrutura que o caso não pede agora; o que importa é o dado, não a CPU |
| Grafana também para negócio | duplica o painel web e o Power BI; quarto canal do mesmo número (condição da direção) |

## Consequências

- `grafana_leitor` criado na inicialização dos dois Postgres; a réplica MySQL não é fonte do Grafana.
- Painéis de execução, frescor e falha, com alerta, entram na v0.3.0 como arquivos em `infra/grafana/provisioning`.
