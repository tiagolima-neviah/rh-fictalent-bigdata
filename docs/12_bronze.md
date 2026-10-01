<a id="topo"></a>

# Bronze · o que o lake guarda, como se lê e como se confere

<!-- nav:start -->
[Home](../README.md) | [← Ingestão](11_ingestao.md) | [Catálogo de achados →](13_catalogo_de_achados.md)
<!-- nav:end -->

> A [Ingestão](11_ingestao.md) conta como o dado entra. Este documento conta o que existe depois que ele entrou: o que a bronze promete, onde cada arquivo mora, como os tipos atravessam do MySQL ao parquet, como se lê a camada inteira com SQL, como se prova que ela ainda é o espelho da réplica e como ela foi auditada. Traz também dois defeitos que o próprio projeto cometeu e achou, porque é neles que está o que vale a pena aprender. Todo número foi medido na base completa em 01/10/2026.

## 1. O que a bronze promete

A bronze é o **espelho fiel** da réplica: mesma tabela, mesma coluna, mesmo tipo, mesmo valor, sem regra de negócio nenhuma. Quem lê a bronze lê o que o sistema do cliente disse, inclusive o que ele disse errado. Corrigir é trabalho da [Silver](14_silver.md), com prestação de contas; uma correção feita na entrada seria uma correção que ninguém consegue auditar.

O espelho tem quatro diferenças em relação à réplica, todas de propósito e todas escritas:

| diferença | o que é | por quê |
|---|---|---|
| partição | um parquet por ano de `criado_em` | a data que não muda: a linha nunca troca de arquivo |
| `excluido_em` | uma coluna a mais, no fim | a linha apagada na origem fica, marcada: o histórico responde "o que sumiu, e quando" |
| nulo permitido | coluna etiquetada como dado pessoal aceita nulo, mesmo obrigatória na réplica | o descarte por eliminação ou retenção a apaga (seção 7) |
| dado pessoal vencido | apagado nas linhas excluídas e nos candidatos com retenção vencida | a LGPD manda; a linha fica, o dado pessoal não |

Fora disso, qualquer diferença entre a bronze e a réplica é defeito, e há um job que procura por ela (seção 5).

## 2. Onde cada arquivo mora

```
s3://fictalent-lake/
├── bronze/
│   ├── <modulo>/<tabela>/ano=AAAA.parquet     75 tabelas de negócio, 9 anos cada
│   ├── meta/exclusao_auditoria/ano=AAAA.parquet   a trilha do que foi apagado na origem
│   ├── arquivo/consolidado_gerencial/ano=AAAA.parquet   a planilha da gerência
│   └── _em_descarte/                           área de conferência do descarte (vazia em regime)
├── fontes/
│   ├── ibge/municipios.parquet
│   └── brasilapi/feriados/ano=AAAA.parquet
└── silver/                                     a camada seguinte
```

São **693 arquivos em 77 conjuntos** (as 75 tabelas, a trilha e a planilha), **170 MB** para 8.411.167 linhas: 8.410.930 de negócio, todas vivas hoje, e 237 da planilha. A réplica ocupa 1,5 GB em disco para o mesmo dado. Partição vazia é gravada como parquet vazio com o esquema certo, para a leitura do conjunto ser uniforme.

O nome do arquivo é a única coisa que diz o ano. Dentro dele não há coluna de partição: quem precisa do ano técnico o tira do nome (`filename = true` no DuckDB), e quem precisa do ano de negócio usa a data de negócio da tabela, que é outra coisa (a batida da noite de 31/12 é gravada em 01/01 e mora no arquivo do ano seguinte).

## 3. Os tipos: do MySQL ao parquet

O tipo de cada coluna vem do `information_schema` da réplica e vira tipo Arrow declarado, nunca inferido do lote. A tabela inteira do mapeamento (`src/rh_fictalent/ingestao/backfill.py`):

| MySQL | parquet (Arrow) | o DuckDB lê como | cuidado |
|---|---|---|---|
| `TINYINT(1)`, `BOOLEAN` | `bool` | `BOOLEAN` | só a largura 1 é booleano |
| `TINYINT`, `SMALLINT`, `INT`, `BIGINT` | `int64` | `BIGINT` | um tipo só: a soma nunca estoura |
| `DECIMAL(p, s)` | `decimal128(p, s)` | `DECIMAL(p, s)` | dinheiro nunca vira ponto flutuante |
| `DATE` | `date32` | `DATE` | |
| `DATETIME`, `TIMESTAMP` | `timestamp[us]` | `TIMESTAMP` | sem fuso: é o relógio da réplica |
| `TIME` | `time64[us]` | `TIME` | hora do dia, não duração |
| `CHAR`, `VARCHAR`, `TEXT`, `JSON`, `ENUM` | `string` | `VARCHAR` | |

**Dois defeitos nossos, e o que eles ensinam.** A primeira linha da tabela e a do `TIME` são as que o projeto errou na v0.5.0 e achou na auditoria da v0.6.0.

O primeiro: o mapeamento tratava todo `TINYINT` como booleano. Quatro colunas inteiras, que guardam contagens pequenas, foram gravadas como `true` em toda linha diferente de zero. O MySQL guarda o `BOOLEAN` da DDL como `tinyint(1)`, e o único lugar onde ele distingue um do outro é o `column_type`, que o código não lia.

O segundo: o driver devolve `TIME` como duração (`timedelta`), e a hora da batida de ponto foi gravada como duração. O DuckDB lê duração de parquet como inteiro de microssegundos, e nenhuma pergunta sobre a ordem das batidas podia ser feita em SQL.

Os dois passaram por todos os testes e pela conferência de contagem, porque **contar linhas não acusa tipo errado**: a tabela tinha exatamente as linhas certas, com o conteúdo errado. Quem achou foi a primeira seção de cada notebook de auditoria, que compara o tipo que a DDL declara com o tipo que a bronze gravou. Corrigido o mapeamento, cinco tabelas foram recopiadas, e a comparação de tipos passou a fazer parte de toda auditoria (`checagens.tipos`). A lição vale para qualquer pipeline: conservação de linhas e conservação de tipo são duas provas diferentes, e é preciso ter as duas.

## 4. Ler a bronze: SQL, com os nomes da réplica

A bronze é lida como um banco. `rh_fictalent.lake.consulta.abrir` devolve uma conexão DuckDB em memória com **79 views**, uma por conjunto, com o nome que a tabela tem na réplica: `ats.candidato`, `pessoas.alocacao`, `financeiro.fatura`, mais `meta.exclusao_auditoria`, `arquivo.consolidado_gerencial`, `fontes.municipios` e `fontes.feriados`. O SQL escrito para o MySQL roda aqui quase sem mexer. Da raiz do repositório, com a plataforma de pé:

```python
from dotenv import load_dotenv

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.recursos import lake_do_ambiente

load_dotenv(".env")
con = consulta.abrir(lake_do_ambiente())
consulta.sql(
    con,
    """
    SELECT k.tipo_servico, count(*) AS alocacoes
    FROM pessoas.alocacao a
    JOIN comercial.posto p ON p.id = a.posto_id
    JOIN comercial.contrato k ON k.id = p.contrato_id
    WHERE a.excluido_em IS NULL
    GROUP BY 1 ORDER BY 2 DESC
""",
)
```

O resultado é um DataFrame. Três escolhas sustentam essa leitura, e as três estão no topo de `src/rh_fictalent/lake/consulta.py` com as medições:

**As views são cruas.** Toda linha aparece, inclusive a marcada como excluída. Filtrar é de quem consulta: `WHERE excluido_em IS NULL`. Esconder a linha morta na view seria a silver começando cedo demais.

**O DuckDB fala com o lake pela extensão `httpfs` dele**, e não pelo `fsspec` do Python. Contar as linhas vivas das 76 tabelas levou 0,3 s pelo `httpfs` e 14 s pelo `fsspec`, porque no segundo cada arquivo é uma ida ao Python ([ADR-0005](adr/0005-duckdb-parquet-medalhao.md), nota de 23/09).

**As conexões com o lake são reaproveitadas.** Esta custou uma investigação, contada na seção 8.

Abrir as 79 views leva 0,6 s. As views não guardam dado: cada consulta lê os parquets onde eles estão.

## 5. Conferir a bronze: ela ainda é o espelho?

Três conferências, em três momentos.

**Na carga, por partição.** Cada partição que a carga reescreve é contada na réplica e comparada com as linhas vivas gravadas. Diferença é falha, com tabela, ano e o tamanho do buraco ([Ingestão, seção 4](11_ingestao.md)).

**A qualquer hora, a camada inteira.** O job `conferir_bronze` conta as linhas vivas das 76 tabelas na bronze e as compara com a contagem na réplica. Divergência é falha nominando as tabelas.

```bash
docker compose exec dagster-web dagster job execute -m rh_fictalent.orquestracao.definicoes -j conferir_bronze
```

**No aceite, como check da régua.** A mesma medida é o check C-06 da [Régua de Validação](06_regua_de_validacao.md), calculado por `python -m rh_fictalent.gerador --aceite --replica`.

As três contam linhas. Nenhuma delas veria um tipo errado (seção 3) nem um valor trocado: para isso existe a auditoria.

## 6. A auditoria: às cegas

Antes de transformar qualquer coisa, a bronze foi auditada: dez notebooks em [`notebooks/auditoria`](../notebooks/auditoria/README.md), um por domínio e um de fechamento, executados e versionados com as saídas.

**Às cegas** quer dizer que os notebooks têm só duas referências: a DDL (o que o sistema promete) e o [Entendimento dos Dados](02_entendimento_dados.md) (o que o cliente declarou). Eles não consultam o gerador nem a régua, que sabem quais defeitos foram plantados; um teste reprova a célula que tentar. Quem sabe o que foi plantado enxerga o que espera, e o valor da auditoria é enxergar o que ninguém esperava. As seis declarações do cliente entram como hipóteses a testar, não como fatos.

Cada domínio passa pelo mesmo roteiro, escrito uma vez em `src/rh_fictalent/auditoria/checagens.py`: tipo contra a DDL, completude, unicidade por chave e por conteúdo (sem acento, caixa e espaço sobrando), domínios declarados, grafia, cronologia, integridade referencial com a linha excluída contando como ausente, e as regras de negócio do domínio. Cada seção fecha com uma Nota Técnica: o observado, por que importa, a ação.

O resultado, gravado em [`dados/auditoria`](../dados/auditoria/): **61 achados**, 4 altos, 17 médios, 19 baixos e 21 registros de severidade nenhuma (hipótese refutada, regra que parecia defeito, ponto forte). As seis declarações do cliente foram confirmadas com número. Doze achados médios ninguém tinha declarado. E os dois defeitos de tipo da seção 3 eram nossos.

O que se faz com cada achado é assunto do [Catálogo de achados](13_catalogo_de_achados.md), aprovado entrada a entrada antes de a silver existir.

## 7. Dado pessoal na bronze

A bronze é a única camada do lake com dado pessoal em claro: nome, CPF, telefone, e-mail. Ela precisa dele por um motivo só, as regras de qualidade da silver (o dígito verificador do CPF, a duplicidade por documento), e a silver já sai pseudonimizada. As 28 colunas alcançadas pela LGPD estão etiquetadas na DDL e listadas no [dicionário](dicionario/README.md).

Dois descartes apagam dado pessoal da bronze, pelo job `aplicar_descarte`, que roda depois de toda carga ([Segurança e LGPD, seção 4](05_seguranca_e_lgpd.md)):

- **Eliminação.** A linha apagada na origem fica marcada, e as colunas pessoais dela são apagadas. O histórico continua contando a linha; ela só não diz mais de quem era.
- **Retenção.** O candidato que nunca foi contratado e está sem atividade há mais de 730 dias (prazo declarado pelo cliente em `cadastro.parametro`) tem as colunas pessoais apagadas. Em 01/10/2026 foram 19.119 dos 60.294 candidatos.

O arquivo descartado só substitui o original depois de conferido em `bronze/_em_descarte/`: mesmas linhas, as linhas que não eram alvo idênticas, nas linhas-alvo só as colunas pessoais mudaram.

Isso tem um custo, dito porque é real: **depois de um descarte, a bronze deixa de reproduzir a medida da auditoria**. Apagar 19 mil CPFs muda quantos CPFs repetidos existem. O projeto não esconde a mudança nem refaz a auditoria às pressas: cada descarte registra, no warehouse, o número de cada regra antes e depois, e a prestação de contas da silver segue essa cadeia ([Silver, seção 6](14_silver.md)).

## 8. O dia em que o lake recusava pedidos

Em 24/09/2026 a conexão com o lake caiu duas vezes, com `Failure when receiving data from the peer`, sem nenhum erro no log do armazenamento. Parecia aleatório. Não era, e a investigação de 01/10 vale como roteiro.

**Reproduzir primeiro.** Abrir as 79 views em sequência reproduziu a falha em toda tentativa, sempre por volta da 37ª abertura, uns 23 segundos depois do início. Falha que se reproduz no mesmo ponto não é acaso.

**Duas hipóteses erradas, descartadas com medida.** A primeira era o teto de memória do container, que estava no limite: dobrar o teto, sem reiniciar, não mudou nada. A segunda era um evento periódico do armazenamento, porque as falhas pareciam cair em cima de uma linha do log que se repete a cada cinco minutos: uma sonda leve atravessou o ciclo com 2.606 pedidos e nenhuma falha. A coincidência tinha sido fabricada pelo próprio teste, que alinhava a carga com o ciclo.

**A causa.** Criar as 79 views lê a lista e o rodapé de cerca de 700 arquivos, e por padrão o `httpfs` abre uma conexão TCP nova para cada pedido. Toda conexão fechada fica um minuto em espera no sistema operacional (`TIME_WAIT`), segurando uma porta, e o sistema tem cerca de 28 mil portas para isso. Medido: 1.421 sockets em espera por abertura. Umas 37 aberturas em menos de um minuto esgotam as portas, e os pedidos seguintes são recusados até a fila esvaziar, 60 segundos depois.

**A correção** é uma linha, `SET httpfs_connection_caching = true`, que faz o DuckDB reaproveitar a conexão: 18 sockets em espera por abertura. O teste que falhava em 37 aberturas passou com 150, sem falha. Um teste de integração garante que a configuração não se perde, e a política de nova tentativa dos assets ficou, como rede de segurança para falha de infraestrutura de verdade.

O que fica de lição: o erro apareceu no cliente e a causa estava no sistema operacional, entre os dois; o log do servidor estava limpo porque o servidor não tinha nada a ver com isso. E uma hipótese plausível (memória no teto) sobreviveu até ser medida.

## 9. O que ainda não existe

- **Feriados de todos os anos.** `fontes.feriados` tem só 2024 no lake; os outros anos estão versionados em `dados/publicos` e entram com um backfill do job `carregar_feriados`. A auditoria do cadastro repete a conferência quando eles entrarem.
- **Evolução de esquema.** Nunca foi exercitada: a DDL da réplica não mudou desde que a bronze existe. A leitura usa `union_by_name`, que junta arquivos de esquemas diferentes, mas o comportamento da carga diante de coluna nova, coluna que some ou tipo trocado não está testado nem decidido.
- **Reauditoria agendada.** A auditoria foi feita uma vez, sobre a base de 24/09/2026. Refazê-la é um comando (`python -m rh_fictalent.auditoria --executar`), mas não há agenda nem critério escrito para quando refazer.
- **Retenção além do candidato.** O único prazo de retenção declarado pelo cliente é o do candidato não contratado. Ex-colaboradores, dependentes e a trilha de auditoria de acesso têm prazos legais próprios, que entram quando o cliente os declarar.

---

[Início](#topo)
