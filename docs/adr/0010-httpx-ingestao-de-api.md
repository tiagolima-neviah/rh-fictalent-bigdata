# ADR-0010 · httpx para a ingestão por API, com retry e limite de taxa próprios

**Situação:** aceito em 17/09/2026. Entra na v0.4.0.

## Contexto

Duas tabelas do caso vêm de APIs públicas: os municípios (IBGE, com o código de 7 dígitos que a réplica usa como chave) e os feriados nacionais (BrasilAPI, porque quase todo indicador da Fictalent é medido em dias úteis). São APIs de todos, sem contrato com o projeto: podem demorar, responder 429 ou 5xx num minuto e voltar no seguinte. Uma ingestão que não trata isso ou trava o pipeline num pedido que nunca responde, ou martela a API até ser bloqueada.

## Decisão

Um cliente HTTP só, em `rh_fictalent.fontes.apis`, sobre **httpx**, com três cuidados que valem para qualquer fonte de API: timeout em todo pedido; retry com recuo exponencial em falha de rede, 429 e 5xx, respeitando o `Retry-After` quando a API o manda, e nunca em erro de cliente (um 404 repetido continua 404); e limite de taxa por intervalo mínimo entre pedidos. O retry e o limite de taxa são escritos no projeto (cerca de 30 linhas) em vez de vir de uma biblioteca, para que o mecanismo fique legível e testável com relógio de mentira. Os assets do Dagster que chamam o cliente gravam o resultado em parquet no lake, sob `fontes/`, e as mesmas funções geram as tabelas versionadas em `dados/publicos/`, que o gerador usa para ser reprodutível sem rede.

## Alternativas consideradas

| alternativa | por que não |
|---|---|
| `requests` | sem timeout por padrão e sem cliente assíncrono; o httpx tem a mesma API com os dois |
| `urllib` da biblioteca padrão | serve para um download (é o que o CAGED usa, num FTP), mas sem sessão, cabeçalhos por cliente nem tratamento de status legível |
| `tenacity` para o retry | resolve, mas esconde o recuo numa configuração por decorador; o recuo escrito à mão é o que se quer ler num projeto de estudo |
| chamar as APIs de dentro do gerador, sem tabela versionada | o gerador passaria a depender de rede e do estado das APIs no dia; a reprodução deixaria de ser determinística |

## Consequências

- Toda fonte de API futura usa o mesmo cliente; a paginação entra nele quando uma fonte precisar (o IBGE e a BrasilAPI devolvem a lista inteira).
- Os testes do cliente não tocam a rede: `httpx.MockTransport` responde 503, 429 e queda de conexão, e um relógio de mentira mede as esperas.
- A imagem do Dagster precisa do `httpx` (dependência de runtime), então cada versão que muda dependências reconstrói a imagem (`docker compose up -d --build`).
