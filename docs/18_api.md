<a id="topo"></a>

# API dos indicadores · a gold servida do warehouse, com o banco decidindo quem vê o quê

<!-- nav:start -->
[Home](../README.md) | [← Warehouse Postgres](17_warehouse_postgres.md) | [Bibliografia →](bibliografia.md)
<!-- nav:end -->

> A API REST (`rh_fictalent.api`, FastAPI) é a porta pela qual o painel, um terceiro ou um teste leem os indicadores da [Gold](16_gold.md), servidos do [Warehouse Postgres](17_warehouse_postgres.md). Ela tem contrato (cada campo descrito, OpenAPI gerada do código), versão (`/v1`), um token por consumidor e um `/saude`. O que a diferencia de uma API comum é que **ela não decide quem vê o quê**: cada consumidor é um papel do Postgres, e a API assume esse papel a cada pedido, de modo que o controle de acesso por área e o isolamento por filial da v0.7.0 valem na porta HTTP sem uma linha de permissão no código. Este documento explica o desenho, o contrato, o rito de cadastrar um consumidor, como testar com `curl`, os erros, a operação e o que ainda não existe. Dado 100 % sintético; não usar em produção.

## 1. O desenho, em quatro decisões

**O banco decide quem vê o quê.** A API conecta ao warehouse como o usuário `api`, que não lê tabela nenhuma. Cada consumidor é um papel sem login do Postgres dentro de um perfil de negócio (`perfil_socio`, `perfil_coordenacao`, ...), com as filiais dele em `acesso.filial_do_papel` quando o perfil é de filial, e o `api` é membro desse papel. A cada pedido, a API abre uma transação, faz `SET LOCAL ROLE <papel do consumidor>` e roda a consulta: o DCL ([Warehouse, seção 4](17_warehouse_postgres.md)) e o RLS ([seção 5](17_warehouse_postgres.md)) são aplicados pelo Postgres. O que o banco recusa vira 403 com o motivo; o que o RLS esconde simplesmente não vem, e a coordenação de uma filial recebe o ponto da filial dela como se fosse o todo.

**Token guardado como senha.** `acesso.token` guarda o hash SHA-256 do token, o papel, a validade e uma descrição; só o administrador lê e escreve. A API só pergunta "de quem é este hash" por uma função `SECURITY DEFINER` (`acesso.papel_do_token`). O token tem 32 bytes aleatórios, então o hash puro basta: a entropia está no token, não numa senha escolhida por alguém. Sem token, ou com token desconhecido ou vencido, a resposta é 401 antes de tocar no banco.

**O contrato `/v1`, poucos e conhecidos.** Oito caminhos, um por pergunta que o painel faz (seção 2), modelos pydantic com cada campo descrito, OpenAPI em `/v1/openapi.json` e a interface em `/v1/docs`. Dinheiro sai como número JSON com duas casas: o JSON não tem decimal, e a gold e o warehouse continuam decimais.

**Um serviço `api` no Compose**, na mesma imagem do Dagster, só em `127.0.0.1:8010`, com healthcheck em `/saude` e a própria senha (`API_DB_PASSWORD`), nunca a do administrador.

A alternativa de a API ler o parquet da gold pelo DuckDB, que o [ADR-0009](adr/0009-fastapi-api-dos-indicadores.md) também admitia, foi descartada em 06/10/2026 porque a permissão por filial teria de viver na API, e não no banco.

## 2. O contrato

| caminho | pergunta | parâmetros | quem lê |
|---|---|---|---|
| `GET /saude` | o serviço está vivo e alcança o warehouse? | nenhum, sem token | todos |
| `GET /v1/filiais` | as filiais | | todos os perfis |
| `GET /v1/filiais/{filial_id}/resultado` | o resultado de uma filial, mês a mês | `de`, `ate` (AAAAMM) | sócio, gerência, financeiro |
| `GET /v1/clientes` | o Pareto dos clientes de um ano: receita, margem, posição, participação acumulada | `ano` | sócio, gerência, financeiro, coordenação |
| `GET /v1/postos/{posto_id}/ponto` | o ponto de um posto num mês, por situação do dia | `mes` (AAAAMM) | sócio, gerência, coordenação (as suas filiais) |
| `GET /v1/funil` | o funil de um ano, trimestre a trimestre | `ano` | sócio, gerência, assistente (as suas filiais) |
| `GET /v1/mercado/escopos` | os recortes do Novo CAGED | | sócio, gerência, assistente |
| `GET /v1/mercado` | o mercado formal de um escopo, mês a mês | `escopo` | sócio, gerência, assistente |

A coluna "quem lê" é a consequência do DCL, não uma regra da API: mudar quem lê é mudar a declaração em `gold/dcl.py`, com teste. Os campos de cada resposta e a descrição deles estão em `/v1/docs`; o SQL de cada caminho está em `src/rh_fictalent/api/consultas.py`, composto com `psycopg.sql` (o schema como identificador, os valores como parâmetro).

## 3. Quem consome: o rito do administrador

Tudo abaixo roda na raiz do projeto, com a plataforma de pé e o `.env` preenchido, pelo administrador (`DW_ADMIN_PASSWORD`). O serviço nunca tem essa senha.

**1. O preparo, uma vez** (e de novo quando `API_DB_PASSWORD` mudar): cria o usuário `api`, a tabela de tokens e a função:

```bash
.venv/bin/python -m rh_fictalent.api --preparar
```

**2. O consumidor**: um papel no perfil, com as filiais quando o perfil é de filial (o perfil da empresa inteira não aceita filial; o de filial exige ao menos uma):

```bash
.venv/bin/python -m rh_fictalent.api --consumidor ana --perfil coordenacao --filial 3
```

```bash
.venv/bin/python -m rh_fictalent.api --consumidor paulo --perfil socio
```

O SQL que isso aplica (`CREATE ROLE ... NOLOGIN`, `GRANT perfil_... TO ana`, as filiais, `GRANT ana TO api`) pode ser visto sem aplicar com `--sql-consumidor ana --perfil coordenacao --filial 3`. Repetir o comando com outro perfil troca o perfil e revoga o anterior.

**3. O token.** Gere com `openssl rand -hex 32` e guarde onde guarda senha. O cadastro pede o token escondido, para ele não ficar no histórico do terminal, e guarda só o hash:

```bash
.venv/bin/python -m rh_fictalent.api --token ana --descricao "o painel da coordenação" --valido-ate 2027-12-31
```

Sem `--valido-ate`, o token não vence. Um papel pode ter mais de um token (um por aplicação, por exemplo).

**4. Revogar**: apaga todos os tokens do papel; o papel e as filiais ficam, para um token novo:

```bash
.venv/bin/python -m rh_fictalent.api --revogar ana
```

O mesmo papel vale para o `psql` e para o Power BI se receber `LOGIN` e uma senha pelo rito do [Warehouse, seção 5](17_warehouse_postgres.md): a API e o banco veem a mesma pessoa.

## 4. Testar com `curl`

O `curl` é a ferramenta certa, e o hábito vale para qualquer API. Do terminal do WSL, na raiz do projeto, com um token cadastrado.

**O token na mão, sem deixar rastro.** Nunca cole o token na linha de comando: ele ficaria no histórico do shell. Leia escondido para uma variável da sessão:

```bash
read -rsp 'cole o token: ' TOKEN; echo
```

**Sem token, a porta fecha.** O `-i` mostra os cabeçalhos da resposta, que é onde se lê o código:

```bash
curl -si http://127.0.0.1:8010/v1/filiais | head -5
```

Esperado: `HTTP/1.1 401 Unauthorized` e o corpo `{"detalhe":"token ausente: envie Authorization: Bearer <token>"}`.

**Com o token, o cabeçalho `Authorization`.** O `-H` acrescenta um cabeçalho; o `python3 -m json.tool` indenta o JSON:

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8010/v1/filiais | python3 -m json.tool
```

**Parâmetros na URL**, entre aspas, porque o `&` sem aspas manda o comando para segundo plano:

```bash
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8010/v1/filiais/3/resultado?de=202501&ate=202509" | python3 -m json.tool
```

A filial 3 é Extrema. Os outros caminhos seguem o mesmo molde: `/v1/clientes?ano=2024`, `/v1/postos/1/ponto?mes=202409`, `/v1/funil?ano=2024`, `/v1/mercado/escopos`, `/v1/mercado?escopo=1`.

**Só o código, sem o corpo.** O `-o /dev/null` descarta o corpo e o `-w` imprime o que se pedir; é como se testa acesso negado em lote:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8010/v1/funil?ano=2024"
```

Um sócio vê `200` em tudo. Para ver um `403` de verdade, cadastre um consumidor de filial (`--consumidor ana --perfil coordenacao --filial 3` e o token dele) e repita o pedido do resultado da filial: responde `403` com o nome da tabela no motivo; e o ponto de um posto da matriz responde `200` com lista vazia, que é o RLS escondendo em silêncio. Um parâmetro fora do contrato (`?ano=1999`) responde `422` com o que era esperado: é o pydantic validando antes de tocar no banco.

**O contrato inteiro pelo navegador**: `http://127.0.0.1:8010/v1/docs`. O botão *Authorize* aceita o token, e o *Try it out* monta o `curl` equivalente de cada pedido.

Dois hábitos: `-v` em vez de `-i` mostra também o que o `curl` enviou (útil para conferir que o cabeçalho foi mesmo); e `unset TOKEN` ao terminar, porque variável de ambiente é herdada por todo processo filho.

## 5. Os erros

| código | quando | o que fazer |
|---|---|---|
| 401 | sem token, token desconhecido, vencido ou revogado | cadastrar ou renovar o token (seção 3) |
| 403 | o perfil do consumidor não lê a tabela; ou a API não pode assumir o papel (faltou `GRANT ... TO api`) | o motivo diz a tabela; se o perfil precisa dela, a declaração é `gold/dcl.py`, com teste; se faltou o `GRANT`, repita `--consumidor` |
| 422 | parâmetro fora do contrato (ano antes de 2018, mês fora de AAAAMM) | o corpo diz o campo e o que era esperado |
| 200 com lista vazia | o RLS escondeu as linhas: a filial não é do consumidor, ou não há dado no recorte | nada: é o comportamento certo |
| 503 ou `/saude` degradada | o warehouse não responde | `bash scripts/saude.sh`; `docker compose logs api` |

Todo erro vem como `{"detalhe": "..."}`.

## 6. No Compose e na operação

O serviço `api` sobe com a plataforma (`docker compose up -d`), na mesma imagem do Dagster, com o comando `python -m rh_fictalent.api --servir`, só em `127.0.0.1:${API_PORT:-8010}`, 512 MB, healthcheck em `/saude`. As variáveis dele são `DW_HOST`, `DW_PORT`, `DW_DB`, `API_DB_USER` e `API_DB_PASSWORD`; a senha é gerada como as outras (`openssl rand -hex 24`) e entra na lista do [Manual de Operação, seção 2](08_manual_de_operacao.md). Depois de mudar código em `src/rh_fictalent/api`, reconstrua a imagem e recrie o serviço: `docker compose up -d --build api`.

O `saude.sh` confere três coisas da API: `/saude` ok alcançando o warehouse, `401` sem token e quantos tokens há cadastrados (sem nenhum, é aviso, não falha). Os logs saem por `docker compose logs api`, um pedido por linha com o código da resposta.

## 7. Os testes

`tests/test_api.py` prova o contrato sem o banco, com um leitor falso que faz o papel do warehouse e anota como quem cada consulta rodou: 401 sem token e com token desconhecido, a consulta rodando como o papel do token com o SQL e os parâmetros certos, 403 quando o banco recusa, 422 nos parâmetros, `/saude`, a OpenAPI com os oito caminhos, o hash e o SQL do consumidor.

`tests/test_api_viva.py` roda com a plataforma de pé e é o teste que a [Arquitetura](03_arquitetura.md) pede: passa quando o acesso indevido falha. Cadastra consumidores descartáveis (um por perfil, com as filiais do caso) e tokens gerados no processo, nunca impressos, e os apaga ao fim. Prova 401 sem token, com token inventado, vencido e revogado; 403 em oito combinações de perfil e tabela e no papel que a API não pode assumir; o RLS conferido contra o parquet da gold (a assistente de Bragança vê o funil de Bragança como se fosse o todo; a coordenação de Extrema não vê o ponto da matriz); o contrato com os números da gold; e o serviço do Compose.

## 8. O que ainda não existe

- **Auditoria de acesso.** Quem pediu o quê não é registrado além do log do serviço; as consultas de auditoria são o card 8.3.
- **Limite de taxa e paginação.** As respostas são listas inteiras (a maior, o Pareto, tem cerca de 60 linhas); não há limite de pedidos por consumidor.
- **TLS.** O serviço escuta só em `127.0.0.1`; em produção fica atrás de um proxy com TLS, como a tabela do [Segurança e LGPD, seção 5](05_seguranca_e_lgpd.md) diz.
- **Rotação de token sem janela.** Cadastrar o novo e revogar o antigo são dois passos; não há sobreposição automática.
- **`/v2`.** Mudar um campo do contrato é uma versão nova ao lado, nunca a troca da `/v1`.

---

[Início](#topo)
