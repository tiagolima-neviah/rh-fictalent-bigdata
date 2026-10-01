"""A silver: a bronze conformada pelo que o catálogo de achados aprovou, e nada além.

- `regras`: as entradas aprovadas do catálogo como SQL sobre a bronze.
- `construcao`: a tabela da silver (a bronze mais as colunas das regras), gravada no lake e
  conferida contra a bronze.
- `contas`: a prestação de contas, cada regra contra o número que a auditoria gravou.
"""
