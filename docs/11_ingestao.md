<a id="topo"></a>

# Ingestão · da réplica, da API e do arquivo até a bronze

<!-- nav:start -->
[Home](../README.md) | [← Monitoramento e Healthcheck](09_monitoramento_e_healthcheck.md)
<!-- nav:end -->

> Como o dado entra no pipeline, pelas três portas que o caso tem: o banco do cliente (a réplica), as APIs públicas e a planilha da gerência. O documento explica o que cada carga faz, por que faz assim e quanto custa, com todo número medido na base completa. Estado atual: a bronze tem as 76 tabelas da réplica, as duas fontes de API e as nove planilhas; a carga diária roda sozinha às 5h e traz só o que mudou.

## 1. As três naturezas de fonte

A Fictalent não tem um lugar onde o dado mora. Tem um sistema (que o projeto representa pela réplica), tem o que vem de fora por API (municípios do IBGE, feriados da BrasilAPI) e tem a planilha que a gerente-geral fecha à mão todo mês. As três entram por caminhos diferentes, porque têm naturezas diferentes, e desembocam no mesmo lugar: a **bronze**, a primeira camada do lake, em parquet.

| natureza | fonte | como entra | onde fica no lake | desde |
|---|---|---|---|---|
| relacional | a réplica MySQL, 76 tabelas | backfill uma vez, depois carga incremental diária por marca d'água | `bronze/<modulo>/<tabela>/ano=AAAA.parquet` | v0.5.0 |
| API REST | IBGE e BrasilAPI | assets do Dagster com cliente HTTP próprio ([ADR-0010](adr/0010-httpx-ingestao-de-api.md)) | `fontes/<provedor>/...` | v0.4.0 |
| arquivo | nove planilhas Excel do consolidado gerencial | asset por ano, com esquema pandera ([ADR-0006](adr/0006-pandera-e-regua.md)) | `bronze/arquivo/consolidado_gerencial/ano=AAAA.parquet` | v0.5.0 |

A regra que vale para as três: **a bronze não corrige nada**. O que a fonte disse entra igual, com o tipo declarado e a proveniência guardada. Corrigir é trabalho da silver, com prestação de contas, e uma correção feita na entrada seria uma correção que ninguém consegue auditar.

## 2. A bronze: o que ela é

A bronze é o **espelho fiel** da réplica, com três coisas que a réplica não tem: arquivo colunar comprimido, partição por ano e linhagem no Dagster (`replica/<modulo>/<tabela>` é a origem, `bronze/<modulo>/<tabela>` é o parquet).

**Partição pelo ano de `criado_em`.** É a data que não muda: uma linha nasce num ano e fica nele para sempre, então a partição de uma linha nunca se move. Particionar por `atualizado_em` faria a linha migrar de arquivo a cada alteração. A consequência, que precisa estar dita, é que a partição é técnica, não de negócio: a marcação de ponto da noite de 31/12 é gravada em 01/01 e mora na partição do ano seguinte. Quem quiser fato por ano usa a data de negócio, na silver.

**Esquema declarado, nunca inferido.** O tipo de cada coluna vem do `information_schema` da réplica e vira tipo Arrow explícito. Sem isso, uma coluna toda nula num ano viraria um tipo diferente do mesmo campo em outro ano, e a tabela deixaria de ser legível como um conjunto só.

**Uma coluna a mais, e só uma.** `excluido_em`, no fim, depois de todas as colunas da DDL. Fica nula enquanto a linha existe na réplica e ganha o instante do `DELETE` quando a trilha de exclusões diz que ela morreu (seção 5).

O que sai: 8.410.929 linhas em **162 MB** de parquet, contra 1,5 GB da réplica em disco. A compressão colunar com zstd não é detalhe: é o que faz 8 milhões de linhas caberem numa leitura.

## 3. O backfill: tudo, uma vez

O backfill traz da réplica para a bronze tudo o que existe desde 2018. É a resposta à pergunta do dono do caso: não, ele não recomeça do zero. São 76 assets no Dagster (um por tabela, incluindo a trilha de exclusões), cada um com nove partições, uma por ano.

Cada partição é copiada com três cuidados. A leitura é **em lote, por cursor de streaming**: `ponto.marcacao` tem 4,3 milhões de linhas, e um `fetchall` traria tudo para a memória. A contagem e a leitura acontecem **na mesma transação**, aberta com `START TRANSACTION WITH CONSISTENT SNAPSHOT`: assim o `COUNT(*)` e o `SELECT` enxergam exatamente o mesmo banco, e a conferência "gravei o que existia" compara duas leituras da mesma foto. E a **conferência é obrigatória**: partição com contagem diferente da réplica falha, em vez de ficar gravada errada.

Pela interface do Dagster: *Jobs* → `backfill_bronze` → *Materialize all* → backfill das nove partições. Por linha de comando, uma partição de um asset:

```bash
.venv/bin/dagster asset materialize -m rh_fictalent.orquestracao.definicoes --select "bronze/cadastro/filial" --partition 2019
```

Medido na base completa: **8.410.929 linhas em 124 segundos**, 675 partições (160 vazias, gravadas como parquet vazio com o esquema certo, para a leitura do conjunto ser uniforme), nenhuma divergência de contagem. A maior partição, `ponto.marcacao` de 2024, tem 940.725 linhas e leva 10,7 segundos.

## 4. A carga incremental: só o que mudou

Rodar o backfill todo dia custaria 124 segundos e transferiria 8,4 milhões de linhas para reescrever o que já estava igual. A carga incremental pede à réplica só as linhas com `atualizado_em` acima da **marca d'água**, descobre em que partições elas caem (pelo ano de `criado_em`) e reescreve só essas, por merge de id: o que já estava, menos os ids que voltaram, mais as versões novas.

A decisão entre marca d'água e captura pelo binlog está no [ADR-0011](adr/0011-marca-dagua-nao-binlog.md). O que decide não é preferência técnica: a réplica é do cliente, então não se configura `log_bin` nem se cria usuário de replicação nela, e o projeto precisa subir com `docker compose up` numa máquina limpa.

Três armadilhas desta carga, e o que o pipeline faz com cada uma:

- **O relógio.** A marca é comparada com `atualizado_em`, que o MySQL grava. O corte de cada carga é pedido à própria réplica (`SELECT NOW(6)`), não ao relógio de quem roda o pipeline: máquinas diferentes têm relógios diferentes, e a diferença viraria linha perdida.
- **A transação que commita tarde.** `atualizado_em` é gravado quando o `UPDATE` roda, mas a linha só fica visível no commit. Uma transação que grava 10:00:00 e commita 10:00:05 é invisível para a carga das 10:00:02 e ficaria abaixo da marca nova para sempre. A carga volta **uma hora** no tempo e relê. Reler é inofensivo porque a aplicação é por id.
- **A foto presa.** Em REPEATABLE READ, que é o padrão do InnoDB, a transação que o driver abre sozinho na primeira leitura congela o que a conexão enxerga até o fim dela. A carga renova a foto a cada tabela. Isso não é hipótese: na primeira prova contra a réplica, o `UPDATE` estava commitado e a carga via zero linhas alteradas.

**Onde a marca mora.** No warehouse (`ingestao.marca_dagua`), ao lado das métricas de execução. A réplica é do cliente: o pipeline lê e não escreve nela, nem para anotar o próprio progresso. Tabela sem marca não é erro: a marca inicial é derivada do maior `atualizado_em` que a bronze já tem, e só sem marca e sem bronze a tabela pede backfill.

**A conferência.** Depois de reescrever, cada partição tocada é contada na réplica (linhas criadas até o corte) e comparada com as linhas vivas da bronze. Diferença é falha, com a mensagem dizendo tabela, ano e o tamanho do buraco.

A carga é um job, `carga_incremental`, com agenda diária às 5h (fuso de São Paulo), **ligada por padrão**. Rodar à mão:

```bash
.venv/bin/dagster job execute -m rh_fictalent.orquestracao.definicoes -j carga_incremental
```

Medido: carga sem nada a fazer em **845 ms**; a primeira carga depois do backfill, quando as marcas são derivadas da bronze e a sobreposição relê a última hora de cada tabela, 22 segundos para as 76 tabelas.

Quando a bronze não tem conserto (uma partição corrompida, uma divergência que a carga não sabe fechar), a saída de emergência é recopiar a tabela inteira: o job aceita `refazer_tudo: true` na configuração, e `tabelas: ["modulo.tabela"]` limita a uma tabela.

## 5. As exclusões: marcar, não apagar

Uma linha apagada não tem `atualizado_em` para ser encontrada. Quem a vê é a trilha `meta.exclusao_auditoria`, que os gatilhos `BEFORE DELETE` da v0.2.0 alimentam com banco, tabela, id e usuário, na mesma transação do `DELETE`. A carga lê a trilha na mesma janela da marca d'água, procura cada id apagado nas partições da tabela e carimba `excluido_em`.

A linha **continua na bronze**. Quem pergunta "quantos contratos existem" filtra as vivas; quem pergunta "o que sumiu, quando e por quem" tem resposta. Apagar responderia a primeira pergunta e destruiria a segunda, que é a da auditoria.

Duas consequências, ditas porque custam algo. A conferência de contagem passa a contar só as vivas, e vale também para a partição que só teve exclusão (um `DELETE` não gera alteração nenhuma, então a partição dele não é tocada pelo merge; a conferência é chamada explicitamente depois da marcação). E a bronze com marcação **não é reconstruível só a partir da réplica**: a linha apagada não existe mais lá, e recopiar a tabela traz o presente e esquece quem morreu. Por isso a própria trilha é copiada para a bronze, como a 76ª tabela: o registro do que foi apagado sobrevive mesmo quando a marcação não sobrevive.

## 6. A planilha: com esquema, ou não entra

As nove planilhas do consolidado gerencial (`dados/gerencial`, uma por ano) são a terceira natureza de fonte e a mais frágil: não têm contrato nenhum. Título na primeira linha, uma linha em branco, cabeçalho na terceira, os dados e um **TOTAL** no fim que não é observação, é soma. Lida crua, a coluna de competência chega como texto (porque a palavra "TOTAL" está nela) e o headcount chega como decimal (porque a célula do total está vazia). Quem faz `read_excel` e segue em frente carrega os dois defeitos adiante, e o erro aparece num painel três camadas depois.

A ingestão de arquivo tem duas etapas separadas de propósito. **Preparar** descarta o título e o total, renomeia as colunas para nomes de coluna (sem acento, sem unidade entre parênteses) e converte os tipos que a planilha misturou; é trabalho declarado e revisável. **Validar** aplica o esquema pandera, e é o portão: `strict=True` (coluna a mais é erro, não curiosidade), unicidade de competência e filial (linha repetida dobra o faturamento do mês sem ninguém ver), competência no primeiro dia do mês, lançamento nunca anterior à competência, e a pasta de trabalho do ano só com competências daquele ano. Esquema reprovado, asset reprovado.

O total descartado não é ignorado: a soma das linhas é comparada com ele, e as nove batem. Quando uma não bater, é sinal de que alguém editou a planilha depois de fechada. Cada linha na bronze guarda o nome do arquivo de onde veio: quando a planilha e a operação discordarem (e elas discordam a partir de 2022, de propósito), é preciso poder apontar de qual arquivo veio o número.

Medido: 237 linhas, uma partição por ano, abaixo de um segundo por arquivo.

## 7. Dias correntes: a réplica se mexe

A base sintética termina em 10/09/2026. Um pipeline que só lê uma base parada nunca exercita o que foi construído aqui: a marca nunca avança, a sobreposição nunca serve para nada, a trilha nunca tem o que contar. O job `simular_dias` escreve na réplica o dia de operação que falta, como o sistema do cliente escreveria: ponto de quem está em campo pela escala, faltas e atestados, os defeitos de marcação do catálogo, vagas fechando, alocações terminando e, de vez em quando, uma batida apagada que vai para a trilha. Cada dia é determinístico pela data, entra numa transação só e não é escrito duas vezes.

**O que isso é, e o que não é.** É a operação continuando. **Não é** uma continuação do gerador: a fidelidade é menor e está declarada no módulo (a escala vira regra de dia da semana; ninguém é admitido nem alocado; folha e faturamento não fecham no dia). A régua de validação vale para a base gerada até 10/09/2026, não para o que a operação acrescentou depois.

Por isso a agenda dele (4h, uma hora antes da carga) nasce **desligada**. Ligar é decisão consciente: a partir daí a réplica deixa de ser exatamente a base que a régua aprovou. Para que a conferência continue possível mesmo assim, `ingestao.dia_simulado` registra o que cada dia acrescentou, e basta descontar. Rodar à mão, até ontem:

```bash
.venv/bin/dagster job execute -m rh_fictalent.orquestracao.definicoes -j simular_dias
```

Medido: um dia escreve 3.816 linhas e altera 4 registros, em menos de um segundo. Há uma trava de 30 dias por execução: escrever um mês inteiro sem olhar é como rodar um backfill sem conferir.

## 8. Os tempos, lado a lado

| operação | volume | tempo medido |
|---|---|---|
| backfill da réplica inteira | 8.410.929 linhas, 675 partições, 162 MB | 124 s |
| maior partição (`ponto.marcacao`, 2024) | 940.725 linhas, 20 MB | 10,7 s |
| carga incremental sem nada a fazer | 76 tabelas conferidas | 845 ms |
| primeira carga depois do backfill | marcas derivadas da bronze, 82 partições relidas | 22 s |
| aplicar uma exclusão | procura em 9 partições e reescreve uma | abaixo de 1 s |
| uma planilha do consolidado | 12 a 36 linhas | abaixo de 1 s |
| um dia de operação simulado | 3.816 linhas novas, 4 alteradas | abaixo de 1 s |

Máquina de referência: a estação de 16 núcleos descrita em [Instalação e Reprodução](07_instalacao_e_reproducao.md), com a plataforma inteira em containers na mesma máquina.

## 9. O que ainda não existe

- **Latência de segundos.** A carga é diária, e isso é a latência. Captura pelo binlog daria segundos, ao custo de configurar o servidor do cliente e operar mais um processo; o ADR-0011 registra que a escolha é reversível.
- **Folha e faturamento nos dias correntes.** A simulação escreve o dia; o fechamento mensal (folha, fatura, provisão) é assunto da fase 6, quando a silver e a gold existirem para consumi-lo.
- **Auditoria de qualidade e silver.** A bronze é a entrada. O catálogo de achados (candidato duplicado, CPF inválido, ASO vencido e os outros do caso) e as regras aprovadas de correção vêm na v0.6.0, com prestação de contas.
- **Ingestão de arquivo além do consolidado.** O índice sazonal do CAGED é lido como tabela versionada pelo gerador e pela régua; entrar no lake como asset, com esquema, fica para quando a gold precisar dele.

---

[Início](#topo)
