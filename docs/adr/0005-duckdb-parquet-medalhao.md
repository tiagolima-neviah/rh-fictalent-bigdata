# ADR-0005 · DuckDB sobre parquet como motor do lake

**Situação:** aceito em 16/09/2026. Entra na v0.6.0.

## Contexto

Cerca de 8 milhões de linhas no total, com a maior tabela (marcações de ponto) em torno de 4,4 milhões; transformação em camadas (bronze, silver, gold) com regras de negócio em SQL; funções de janela na gold; execução na máquina do analista e em container.

## Decisão

DuckDB como motor SQL embarcado, lendo e escrevendo parquet (zstd, partição por ano) no lake via fsspec. Cada camada é parquet; DuckDB não guarda dado, só processa.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| Spark / PySpark | cluster para 8 milhões de linhas ensina a resolver o problema errado; o custo de operar supera o ganho. Entra como comparativo **medido** (P2), não como base |
| pandas puro | tudo em memória, sem SQL analítico, funções de janela verbosas; o SQL é a língua do caso e do mercado |
| Postgres como lake | banco não é lake: não separa storage de processamento, não versiona por arquivo, não escala leitura colunar |
| Polars | motor excelente; a diferença é a interface: SQL primeiro, para que a gold seja legível por quem só sabe SQL |

## Consequências

- Mesmo padrão da Fictitur, o que permite comparar as duas obras.
- Funções de janela explícitas e comentadas na gold (SQL analítico como evidência).
- Volume por partição por ano; a régua confere conservação de linhas entre camadas.
