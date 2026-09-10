<a id="topo"></a>

# Arquitetura · do banco de origem ao painel

<!-- nav:start -->
[Home](../README.md) | [← Entendimento dos Dados](02_entendimento_dados.md)
<!-- nav:end -->

> Como este pipeline é montado, peça por peça, e **por que** cada decisão foi tomada. Documento vivo: cada camada que entra atualiza a seção correspondente com o que foi medido de verdade, e o que ainda não existe está marcado como tal. Números sem medição não entram aqui.

## 1. O desenho inteiro numa página

```
┌─ ORIGEM (simulada) ──────────────────────────────────────────────┐
│  Postgres "db_fictalent": 10 schemas, o sistema que a empresa    │
│  não tem. Populado pelo gerador determinístico (2018 a 2026).    │
└───────────────┬──────────────────────────────────────────────────┘
                │  (1) backfill histórico: tudo, uma vez
                │  (2) carga incremental diária: só o que mudou
                ▼
┌─ STAGING ────────────────────────────────────────────────────────┐
│  Postgres "stg_fictalent": espelho da origem + colunas de        │
│  linhagem. É daqui que o pipeline lê, nunca da origem.           │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌─ LAKE (parquet, storage abstraído por fsspec) ───────────────────┐
│  BRONZE  espelho fiel do staging, sem regra de negócio           │
│  SILVER  regras aprovadas + prestação de contas de cada limpeza  │
│  GOLD    star schema: dimensões conformadas e fatos por módulo   │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
┌─ WAREHOUSE ──────────────────────────────────────────────────────┐
│  Postgres dimensional (container local e destino em nuvem),      │
│  carregado partição a partição, com conferência de contagem.     │
└───────────────┬──────────────────────────────────────────────────┘
                ▼
          Painel web (DuckDB sobre o parquet)  ·  Power BI (warehouse)
```

## 2. Por que uma origem simulada, e o que ela representa

Num cliente real, a origem é o sistema dele. Aqui a origem é **um Postgres que o projeto cria e popula**, com o modelo relacional completo dos 10 módulos. Ela existe por três motivos:

1. **O caso pede.** A Fictalent não tem um sistema único; tem quatro sistemas desconectados e planilhas. Modelar a origem como o sistema que ela deveria ter é o que permite mostrar o pipeline inteiro e, no futuro, o produto transacional.
2. **Ensina o que importa.** Quem estuda o repositório vê a diferença entre um banco **transacional normalizado** (a origem) e um banco **analítico dimensional** (o warehouse), com as mesmas informações e desenhos opostos. Essa é a lição central de modelagem de dados, e ela só fica clara quando os dois existem lado a lado.
3. **Não expõe ninguém.** Nenhum dado real de nenhuma empresa entra em qualquer etapa. A FORMA vem do dossiê do caso; o ritmo do ano vem de dado público agregado.

**Origem e staging são bancos separados** (dois serviços no mesmo Docker Compose), porque a separação é o que torna a carga incremental honesta: o pipeline nunca lê a origem, exatamente como num cliente onde tocar a produção é proibido.

## 3. Backfill e carga incremental: a decisão que define o caso

Este é o ponto onde este projeto se distingue dos dois anteriores da série, e vale entender a diferença entre as duas cargas.

**Backfill histórico (uma vez).** Traz tudo o que existe na origem desde 2018. É a resposta à pergunta do dono: *"vou ter que começar do zero?"*. Não: o histórico está no sistema e o pipeline vai buscá-lo. Sem backfill não existe comparação ano a ano, e sem comparação ano a ano não é possível responder por que a empresa perdeu contratos em 2025.

**Carga incremental (todo dia).** Traz só o que mudou desde a última carga. É o que substitui o trabalho manual das assistentes e o que mantém o painel vivo sem pesar na origem.

**Como o incremental sabe o que mudou.** Cada tabela da origem carrega `criado_em` e `atualizado_em` mantidos por gatilho, e o staging guarda, por tabela, a **marca d'água** da última carga (o maior `atualizado_em` já trazido). A carga seguinte pede apenas as linhas acima dessa marca. É o mesmo princípio do `rowversion` usado no caso em SQL Server desta série, escrito em Postgres.

**O problema que quase todo mundo esquece: exclusões.** Uma linha apagada na origem não tem `atualizado_em` para ser encontrada, e some do sistema sem avisar o staging. Por isso a origem mantém uma **trilha de exclusões** (tabela de auditoria alimentada por gatilho de `DELETE`), e a carga incremental aplica essas exclusões no staging como marcação lógica, nunca com `DELETE` físico: o dado apagado na origem continua existindo no histórico analítico, marcado como excluído e com a data. Quem já viu um faturamento sumir de um relatório porque alguém cancelou um lançamento no mês seguinte sabe por que isso importa.

**Estado atual:** projetado, ainda não implementado.

## 4. As três camadas do lake

O lake é feito de arquivos **parquet**, com o caminho abstraído por **fsspec**: o mesmo código escreve em `file://` no disco do analista e em `s3://` num MinIO ou numa nuvem, sem uma linha de diferença. O motor de transformação é o **DuckDB**, que lê e escreve parquet com SQL, sem servidor.

**Bronze: espelho fiel.** Uma cópia do staging em parquet, sem nenhuma regra de negócio, com colunas de linhagem (quando foi extraída, de onde veio). O bronze é intocável: nenhuma camada posterior o reescreve. É a rede de segurança que permite refazer tudo se uma regra da silver estiver errada.

**Silver: conformada, com prestação de contas.** Aqui as regras aprovadas na auditoria de qualidade são aplicadas, e cada uma presta contas: quantas linhas leu, quantas marcou, quantas células anulou. A regra da casa é que a silver **se reprova sozinha** se o que ela fez diferir do que o catálogo de achados prometeu. Cinco princípios governam qualquer limpeza: ausência não se preenche, duplicidade se marca (não se funde), valor impossível se anula mas o original se preserva, toda limpeza presta contas, e rodar duas vezes dá o mesmo resultado.

**Gold: o star schema.** Dimensões conformadas (calendário, cliente, colaborador, função, filial, posto, contrato) e fatos por módulo, no grão que cada pergunta exige. As fatos são particionadas por ano, e a partição é a unidade de carga e de auditoria: dá para reprocessar 2023 sem tocar em 2024. A gold só carrega **medidas-base**; comparações e percentuais são trabalho da camada de apresentação.

**Estado atual:** projetadas, ainda não implementadas.

## 5. O warehouse e os destinos

A gold em parquet serve muito bem a quem programa, mas as ferramentas de mercado esperam um banco. Por isso o mesmo star schema é carregado num **Postgres dimensional**, com schemas separados para dimensões e fatos. A carga é feita **partição a partição**, de forma idempotente, e cada partição confere a contagem no parquet contra a contagem no banco antes de aprovar.

O destino é configurável por variáveis de ambiente: o container local durante o desenvolvimento, um Postgres gratuito na nuvem para a demonstração pública. O carregador não sabe onde o banco mora, e é isso que torna o pipeline portável.

**Estado atual:** projetado, ainda não implementado.

## 6. As duas pontas de consumo

**Painel web** (projeto separado): lê o **parquet da gold** com DuckDB embutido no próprio serviço, sem banco no ar. Isso o torna barato de hospedar e rápido, e é a escolha que sustenta a vitrine pública.

**Power BI** (projeto separado): lê o **warehouse**, em modo de importação. As duas pontas consomem o mesmo modelo dimensional, e é por isso que o número é o mesmo nas duas: a conta foi feita uma vez, na gold.

## 7. Qualidade: a régua, e por que ela vem antes

Dado sintético sem régua é dado inventado. Antes de o gerador escrever uma linha, existe uma **régua de validação**: um conjunto de bandas (mínimo e máximo aceitáveis) para cada grandeza que a história exige, derivadas do dossiê do caso e, no que diz respeito à sazonalidade, dos microdados públicos do Novo CAGED.

O gerador roda, a régua confere, e se algum indicador cair fora da banda a base é **regenerada**, não remendada. A régua também protege contra o erro mais comum em base sintética, que é a grandeza plausível na média e absurda no total.

A mesma disciplina se repete na gold, com uma régua própria de consistência: conservação de contagens entre camadas, integridade das chaves dimensionais e coerência dos indicadores com as bandas do início.

**Estado atual:** projetada, ainda não implementada.

## 8. Ferramentas, e o porquê de cada uma

| peça | escolha | por quê |
|---|---|---|
| banco de origem e staging | **Postgres 16** em Docker | é o banco livre mais comum em PME; roda em qualquer máquina |
| transformação | **DuckDB** | SQL sobre parquet, sem servidor, rápido no laptop |
| formato do lake | **parquet** com compressão zstd | colunar, comprime bem, lido por qualquer ferramenta |
| storage | **fsspec** | o mesmo código no disco local, em MinIO ou em nuvem |
| extração | **ADBC** (Arrow) | traz os dados do Postgres em lotes, sem estourar a memória |
| warehouse | **Postgres** dimensional | mesma tecnologia da origem, para o estudo comparar os dois desenhos |
| linguagem e dependências | **Python 3.12** com uv | reprodutível: quem clona instala exatamente as mesmas versões |
| qualidade | **ruff, mypy, pytest** em CI | a esteira roda desde o primeiro commit, não no fim |

## 9. O que este projeto deliberadamente não faz

Não tem orquestrador (Airflow, Dagster): a cadeia é uma sequência de comandos, e introduzir orquestração antes de a cadeia estar estável só esconderia problemas. Não tem processamento distribuído: 12 milhões de linhas cabem num laptop, e usar cluster aqui seria ensinar a resolver o problema errado. Não tem telas transacionais: isso é projeto futuro, e o modelo relacional já nasce preparado. Não tem hardening de segurança, pelo motivo declarado no aviso do README: é material de estudo, e a implementação real é outra conversa.

---

[Início](#topo)
