<a id="topo"></a>

# Warehouse Postgres · a gold servida num banco, com quem lê o quê provado por teste

<!-- nav:start -->
[Home](../README.md) | [← Gold](16_gold.md) | [Bibliografia →](bibliografia.md)
<!-- nav:end -->

> O parquet no lake é a [Gold](16_gold.md); o Postgres é onde ela é consultada, pela API, pelo Power BI e por quem abrir um cliente de banco. Este documento explica como a DDL sai do modelo em vez de ser escrita à mão, como a carga é feita por partição e conferida contra o parquet, quem lê o quê (os perfis de negócio, sem atributo de pessoa fora da necessidade), como cada filial enxerga só as próprias linhas no próprio banco, quais índices existem e por que só esses, e como o warehouse se liga ao resto no Dagster. Todo número foi medido na base completa em 06/10/2026.

## 1. O que o warehouse é

É um Postgres 16 ([ADR-0001](adr/0001-mysql-no-staging-postgres-no-olap.md)), o banco `dw_fictalent`, com dois schemas de negócio: `dim`, com as 11 dimensões, e `fato`, com os 14 fatos. `dim_cliente` da gold é `dim.cliente`; `fato_posto_mes` é `fato.posto_mes`. O mesmo banco já guardava, desde a v0.3.0, as métricas de execução (`observabilidade`) e, desde a v0.6.0, o registro dos descartes (`lgpd`); agora guarda o dado que o painel lê. Para este volume, 1,68 milhão de linhas e 355 MB entre tabelas e índices, um banco de linhas serve como warehouse, e o que o Postgres traz de graça é o que o caso pede: partição declarativa, chave estrangeira, *row level security* nativa e papéis com concessão por coluna.

Quem escreve no warehouse é só o administrador (`fictalent_admin`), pela carga. Todo mundo que lê entra por um perfil (seção 4). O lake continua sendo a verdade: o warehouse é refeito dele a cada carga, e a conferência garante que os dois dizem o mesmo.

## 2. A DDL sai do modelo

Nenhuma tabela do warehouse foi escrita à mão. A DDL é gerada do modelo da gold (`gold.modelo`) e dos tipos que o DuckDB deu a cada coluna ao construir a tabela, traduzidos para o Postgres: `DECIMAL(p, s)` vira `numeric(p, s)`, `VARCHAR` vira `text`, `DOUBLE` vira `double precision`, `BIGINT`, `INTEGER`, `BOOLEAN` e `DATE` ficam como são. O que o modelo declara vira restrição no banco:

- o **grão** vira chave primária; no fato, o ano entra nela, porque o Postgres exige a coluna de partição na chave;
- cada **referência** vira chave estrangeira para a dimensão, o que obriga a carregar as dimensões antes dos fatos;
- a **partição** vira partição declarativa por intervalo de ano, uma tabela filha por ano (`fato.posto_mes_2024`), criada quando o ano aparece no parquet;
- a descrição da [Matriz de barramento](15_matriz_de_barramento.md) (o grão e o processo do fato, o que a dimensão é) vira o comentário da tabela, que o cliente de banco mostra.

A DDL de um fato, como sai de `python -m rh_fictalent.gold --ddl`:

```sql
CREATE TABLE IF NOT EXISTS fato.posto_mes (
  mes_id integer,
  posto_id bigint,
  contrato_id bigint,
  cliente_id bigint,
  filial_id bigint,
  funcao_id bigint,
  mes_parcial boolean,
  ...
  receita numeric(38, 2),
  custo_pessoal numeric(38, 2),
  margem numeric(38, 2),
  margem_pct double precision,
  ano integer,
  PRIMARY KEY (posto_id, mes_id, ano),
  FOREIGN KEY (mes_id) REFERENCES dim.mes (id),
  FOREIGN KEY (posto_id) REFERENCES dim.posto (id),
  FOREIGN KEY (contrato_id) REFERENCES dim.contrato (id),
  FOREIGN KEY (cliente_id) REFERENCES dim.cliente (id),
  FOREIGN KEY (filial_id) REFERENCES dim.filial (id),
  FOREIGN KEY (funcao_id) REFERENCES dim.funcao (id)
)
PARTITION BY RANGE (ano);
COMMENT ON TABLE fato.posto_mes IS 'um posto num mês da vigência dele; o processo: ocupar o posto, faturar e custear';
```

A DDL é idempotente (`IF NOT EXISTS`): a carga a aplica toda vez, e coluna nova no modelo é um caso que a carga não resolve sozinha, deliberadamente (seção 10). As chaves estrangeiras valem: um teste muda o posto de uma linha para um `id` que não existe e o Postgres recusa.

## 3. A carga: por partição, idempotente, conferida

A carga lê o parquet da gold pelo DuckDB e escreve no Postgres pelo `COPY`, em lotes de 50 mil linhas. **O fato é carregado por partição**: o ano que chega do parquet substitui a partição inteira (`TRUNCATE` da filha e `COPY`), e a partição de um ano que sumiu do parquet é esvaziada. Repetir a carga dá o mesmo resultado. **A dimensão** é pequena e tipo 1: entra por upsert pelo `id`, numa tabela temporária e um `INSERT ... ON CONFLICT DO UPDATE`, e a linha que deixou de existir no parquet sai. A chave estrangeira obriga a dimensão antes do fato, e é a linhagem do Dagster que garante a ordem.

Depois de carregar, a **conferência** lê o parquet e o Postgres com as mesmas expressões: a contagem por ano e cada total de conservação do modelo (os mesmos da [Gold, seção 3](16_gold.md)), exceto os que dependem do horizonte, que é uma variável da sessão do DuckDB e o Postgres não tem. O que não bater reprova a tabela, e o asset falha dizendo o quê: um teste altera uma receita no Postgres e a conferência responde `receita dos postos em 2024: parquet 100.0000, postgres 101.0000`.

Pela linha de comando, o warehouse inteiro, dimensões antes dos fatos:

```bash
.venv/bin/python -m rh_fictalent.gold --warehouse
```

Na base completa são 25 tabelas, 120 partições e 1,68 milhão de linhas, tudo conferido. O fato de ponto (1.166.361 linhas) é o que mais demora, 91 s: o gargalo é a conversão linha a linha do Arrow para o `COPY`, e o driver ADBC, que já está nas dependências, resolve isso quando o volume pedir (seção 10).

## 4. Quem lê o quê: o DCL por perfil de negócio

Na réplica os papéis são por função técnica (`pipeline`, `relatorios_cliente`, `replicador`). No warehouse são **por perfil de negócio**, os de quem lê o painel no [Entendimento dos Dados](02_entendimento_dados.md): o sócio, a gerência, a coordenação da operação, a assistente do funil e o financeiro. Cada perfil é um papel do Postgres sem login (`perfil_<nome>`), e a pessoa que entra recebe o perfil e herda só o que ele pode. O que cada perfil pode é declarado em `src/rh_fictalent/gold/dcl.py`, o SQL é gerado dali e é idempotente: revoga e reconcede a cada aplicação, para o banco refletir a declaração e não a história.

| perfil | lê | atributos de pessoa | alcance |
|---|---|---|---|
| `perfil_socio` | todos os 14 fatos | nenhum | a empresa inteira |
| `perfil_gerencia` | todos os 14 fatos | nenhum | a empresa inteira |
| `perfil_coordenacao` | posto_mes, alocacao, vinculo, ponto_dia, conformidade_mes, ocorrencia, contrato, vaga | do colaborador | só as suas filiais |
| `perfil_assistente` | vaga, candidatura, vinculo, alocacao, mercado_mes | do candidato | só as suas filiais |
| `perfil_financeiro` | faturamento, recebimento, custo_pessoal, resultado_mes, posto_mes, contrato | nenhum | a empresa inteira |

As dimensões vêm das referências dos fatos de cada perfil, mais a data e o mês. A gold não identifica ninguém por construção; o que sobra nas dimensões de pessoa são **atributos** (ano de nascimento, sexo, escolaridade, município, fonte de recrutamento) que não identificam sozinhos mas, cruzados, aproximam. Por isso o acesso a eles é coluna a coluna, pelo princípio da necessidade: a assistente lê o candidato inteiro, porque é o trabalho dela; a coordenação lê o colaborador inteiro; o sócio, a gerência e o financeiro leem só o `id` e o operacional (`ativo`, datas, marcas), e `SELECT *` numa dimensão de pessoa falha para eles, de propósito. Ninguém escreve, cria nem concede.

O trecho do financeiro, como sai de `python -m rh_fictalent.gold --dcl`:

```sql
CREATE ROLE perfil_financeiro NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
COMMENT ON ROLE perfil_financeiro IS 'o financeiro: faturar, receber, custear e fechar o mês';
GRANT USAGE ON SCHEMA dim, fato TO perfil_financeiro;
REVOKE ALL ON ALL TABLES IN SCHEMA dim, fato FROM perfil_financeiro;
GRANT SELECT ON fato.faturamento TO perfil_financeiro;
GRANT SELECT ON fato.recebimento TO perfil_financeiro;
...
GRANT SELECT (id, ativo, ...) ON dim.colaborador TO perfil_financeiro;
```

O teste roda no banco de verdade: o cenário vai para schemas de teste, o DCL é aplicado neles e cada perfil é exercido por `SET ROLE`. O financeiro soma o faturamento, a assistente lê sexo e escolaridade do candidato, a coordenação conta o ponto, e nove acessos indevidos falham com erro de privilégio: a coluna vedada, o asterisco, o fato de outra área, o `INSERT`, o `DELETE`, o `CREATE TABLE`. É a regra da [Arquitetura](03_arquitetura.md): o teste passa quando o acesso indevido falha.

## 5. Cada filial enxerga só as próprias linhas

O DCL decide tabela e coluna; não decide linha. É o *row level security* do Postgres que faz a coordenadora de Extrema enxergar só as linhas de Extrema, **no próprio banco, sem depender da aplicação**: a política fica na tabela e vale para qualquer cliente que se conecte, o painel, o notebook ou o `psql`. O alcance de cada perfil é um campo da declaração (`EMPRESA` ou `FILIAL`), e o SQL é gerado dela (`src/rh_fictalent/gold/rls.py`).

Em toda tabela com `filial_id` (os 13 fatos que têm filial e a dimensão de contrato; o mercado do CAGED é público e fica fora) há duas políticas. `empresa_inteira` deixa tudo passar para sócio, gerência e financeiro. `por_filial` só deixa passar a linha cuja filial está entre as do papel, para coordenação e assistente, e a linha 0 das dimensões, que é de todos:

```sql
ALTER TABLE fato.posto_mes ENABLE ROW LEVEL SECURITY;
CREATE POLICY empresa_inteira ON fato.posto_mes FOR SELECT
  TO perfil_socio, perfil_gerencia, perfil_financeiro USING (true);
CREATE POLICY por_filial ON fato.posto_mes FOR SELECT
  TO perfil_coordenacao, perfil_assistente
  USING (filial_id = 0 OR filial_id IN (SELECT acesso.filiais_do_papel(current_user)));
```

**Quem vê qual filial** fica em `acesso.filial_do_papel` (papel de login, filial), com chave estrangeira para `dim.filial`, que **só o administrador lê e escreve**. A política a consulta por uma função `SECURITY DEFINER`, que roda como o dono e recebe o papel como argumento, porque dentro dela `current_user` seria o dono. A alternativa de guardar a filial numa variável de sessão foi descartada: qualquer usuário pode fazer `SET` numa variável própria e trocar de filial. **Papel sem linha na tabela não vê linha nenhuma**: fecha por padrão. O administrador, dono das tabelas e da carga, não passa pela política. E a partição de um fato não é concedida a ninguém (o `GRANT` na tabela-mãe não desce), então não há como ler o ano inteiro por baixo da política; o teste prova que `SELECT` em `fato.posto_mes_2024` falha para qualquer perfil.

O rito do administrador para dar acesso a uma pessoa, a senha pelo `\password` e nunca em texto:

```sql
CREATE ROLE ana LOGIN IN ROLE perfil_coordenacao;
\password ana
INSERT INTO acesso.filial_do_papel VALUES ('ana', 3);   -- 3 é Extrema
```

O teste, no banco de verdade: um papel ligado à filial 2 lê só a filial 2 em `fato.contrato`, `fato.vaga`, `fato.posto_mes` e `dim.contrato`; uma assistente ligada às filiais 1 e 2 lê tudo o que a assistente pode; o sócio e o financeiro leem tudo; o `perfil_coordenacao` sem filial registrada lê zero linhas; e falham com erro de privilégio a leitura e a escrita da tabela de acesso e a leitura direta da partição. Na base completa são 14 tabelas com política, 28 políticas, e `acesso.filial_do_papel` está vazia, de propósito: ninguém foi cadastrado ainda.

## 6. Os índices, medidos

A DDL só cria o que o modelo exige: a chave primária, que vira índice, e a chave estrangeira, que no Postgres não vira. Então toda consulta do painel que filtra um fato por uma dimensão (o ponto de um posto, as candidaturas de uma pessoa) varre a tabela inteira, e no fato de ponto isso é 1,2 milhão de linhas por pergunta. A regra adotada é **nenhum índice por palpite**: há candidatos, cada um com a consulta do painel que o pede (`src/rh_fictalent/gold/indices.py`), e há a medida. A medida remove todos, roda cada consulta com `EXPLAIN (ANALYZE)`, cria todos, roda de novo e deixa no banco só os adotados; cada consulta roda três vezes e fica a mediana, e o valor usado é o mais frequente da coluna, o pior caso para o índice, porque é o que mais linhas devolve.

```bash
.venv/bin/python -m rh_fictalent.gold --indices --medir
```

| consulta do painel | linhas | sem índice | com índice | ganho | decisão |
|---|---:|---:|---:|---:|---|
| o ponto de um posto no mês | 3 | 22,9 ms | 0,5 ms | 43x | adotado `ponto_dia (posto_id, data_id)` |
| o ponto de uma pessoa | 84 | 20,4 ms | 1,7 ms | 12x | adotado `ponto_dia (colaborador_id)` |
| as candidaturas de uma pessoa | 3 | 8,6 ms | 0,1 ms | 66x | adotado `candidatura (candidato_id)` |
| o custo de uma pessoa | 83 | 2,3 ms | 0,2 ms | 14x | adotado `custo_pessoal (colaborador_id)` |
| as alocações de um posto | 609 | 0,7 ms | 0,6 ms | 1,1x | descartado: 17 mil linhas |
| a receita de um cliente | 49 | 0,6 ms | 0,5 ms | 1,3x | descartado: 9 mil linhas |
| as faturas de um cliente | 49 | 0,6 ms | 0,4 ms | 1,7x | descartado: 10 mil linhas |
| o ponto de uma filial no mês (controle) | 4 | 24,8 ms | 10,8 ms | 2,3x | descartado: o planejador ignorou o índice de filial, de três valores, e usou o composto de posto e data |

Quatro índices fazem diferença e foram adotados. Três são usados pelo planejador mas não fazem diferença, porque a tabela é pequena e a consulta fica abaixo de um milissegundo com ou sem eles; ficam declarados como descartados, com a medida, para ninguém os propor de novo sem medir, e voltam quando o volume pedir. O controle confirmou a lição clássica: índice em coluna de três valores não é usado nem quando existe. O índice criado na tabela-mãe desce a toda partição, inclusive às que a carga criar depois (36 índices de partição, 39 MB), e o asset que os garante também roda `ANALYZE` em todo fato, porque o planejador decide pelas estatísticas e a carga por partição as envelhece. O laudo fica no lake, em `gold/_indices.json`.

## 7. No Dagster

| o quê | nome | o que faz |
|---|---|---|
| 25 assets | `warehouse/dim/<tabela>`, `warehouse/fato/<tabela>` | a DDL, a carga por partição ou upsert, a conferência contra o parquet |
| asset | `warehouse/indices` | os índices adotados e o `ANALYZE` de todo fato |
| asset | `warehouse/dcl` | os perfis e as concessões, reaplicados |
| asset | `warehouse/rls` | as políticas por filial e a tabela de acesso, depois do DCL |
| job | `carregar_warehouse` | tudo acima, dimensões antes dos fatos: 28 passos |
| sensor | `warehouse_depois_da_gold` | dispara `carregar_warehouse` depois de todo `construir_gold` que termina bem |

`warehouse/fato/posto_mes` depende de `gold/fato_posto_mes` e das dimensões que referencia já no warehouse, porque a chave estrangeira exige a dimensão carregada antes. Fato que não confere falha o asset e o que estava carregado antes continua como estava. O DCL vem depois das tabelas porque o `GRANT` precisa da tabela, e o RLS depois do DCL porque a política cita os perfis. Com o sensor, a cadeia do dia fecha de ponta a ponta: a carga incremental das 5h, a silver, a gold e o warehouse, cada camada disparada pelo fim da anterior, sem agenda nova.

## 8. Ler o warehouse

Com a plataforma de pé, o administrador entra pelo container:

```bash
docker exec -it -e PGPASSWORD="$(grep -E '^DW_ADMIN_PASSWORD=' .env | cut -d= -f2-)" fictalent_pg_dw psql -U fictalent_admin -d dw_fictalent
```

O administrador não passa pela política nem pela concessão; para ver o banco como um perfil o vê, `SET ROLE`:

```sql
SET ROLE perfil_financeiro;
SELECT f.nome AS filial, r.mes_id, r.faturamento, r.resultado
FROM fato.resultado_mes r JOIN dim.filial f ON f.id = r.filial_id
WHERE NOT r.mes_parcial AND r.mes_id >= 202501 ORDER BY 1, 2;
SELECT sexo FROM dim.candidato LIMIT 1;   -- ERROR: permission denied for table candidato
RESET ROLE;
```

Um cliente de banco (DBeaver, o Power BI) entra em `127.0.0.1:5441`, banco `dw_fictalent`, com o papel de login que o administrador criou pelo rito da seção 5 ([Instalação, seção 8](07_instalacao_e_reproducao.md)). O que ele enxerga é o que o perfil e a filial dele permitem, sem a aplicação precisar saber disso.

## 9. Os tempos, lado a lado

| operação | volume | tempo medido |
|---|---|---|
| o warehouse inteiro, pela linha de comando | 25 tabelas, 120 partições, 1,68 milhão de linhas, com a conferência | 115 s |
| o fato de ponto | 1.166.361 linhas, por `COPY` em lotes de 50 mil | 91 s |
| o DCL | 5 perfis, 124 comandos | 1,5 s |
| o RLS | 14 tabelas, 28 políticas, 79 comandos | 1,3 s |
| a medida dos índices | 8 consultas, três vezes cada, sem e com índice | 8,9 s |
| job `carregar_warehouse`, no container | 28 passos, dois por vez | 140 s, disparado pelo sensor |

## 10. O que ainda não existe

- **Coluna nova no modelo.** A DDL é `IF NOT EXISTS`: uma coluna acrescentada a uma tabela da gold não entra no warehouse sozinha. O caminho hoje é apagar a tabela no Postgres e deixar a carga recriá-la; uma migração de esquema é trabalho futuro.
- **Carga pelo ADBC.** Os 91 s do fato de ponto são a conversão linha a linha para o `COPY`; o `adbc_ingest` do Arrow já está nas dependências e entra quando o volume pedir.
- **Pessoas cadastradas.** Os perfis existem e a tabela de acesso está vazia; o rito da seção 5 é do administrador, por pessoa.
- **O destino em nuvem.** O warehouse roda no Compose; um Postgres gratuito em nuvem como destino, previsto na [Arquitetura](03_arquitetura.md), é da v1.0.0, junto com a API.
- **Auditoria de acesso.** O que cada perfil consultou não é registrado; as consultas de auditoria são da v1.0.0.

---

[Início](#topo)
