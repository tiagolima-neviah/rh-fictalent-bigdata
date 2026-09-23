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

## Nota de 23/09/2026 (card 6.1): a leitura do lake é pelo `httpfs`, não pelo `fsspec`

A decisão dizia "via fsspec", e a escrita continua assim: os parquets da bronze são gravados pelo recurso `Lake`, que é um `fsspec` apontado para o S3. A **leitura pelo DuckDB** entrou na v0.6.0 pela extensão `httpfs` do próprio DuckDB, configurada a partir do mesmo recurso (endpoint, chave, segredo e bucket vêm de um lugar só). A primeira medição, com uma tabela, dava 270 ms de diferença e não justificava a extensão; a medição com o lake inteiro justificou: contar as linhas vivas das 76 tabelas leva 0,3 s pelo `httpfs` e 14,2 s pelo `fsspec` registrado no DuckDB (cada arquivo é uma ida ao Python), e um join de 4,3 milhões por 1,2 milhão de linhas leva 0,09 s contra 2,7 s. Abrir as 79 views leva 3,6 s contra 5,2 s. A extensão é instalada na imagem do Dagster em tempo de build (`DUCKDB_EXTENSION_DIRECTORY`), para o container não depender de rede na primeira consulta. O que muda para quem lê: nada; o SQL é o mesmo, com os nomes da réplica. O que muda para quem opera: a imagem precisa ser reconstruída quando a versão do DuckDB mudar, porque a extensão é compilada por versão.
