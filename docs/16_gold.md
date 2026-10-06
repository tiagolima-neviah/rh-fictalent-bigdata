<a id="topo"></a>

# Gold · o modelo dimensional, construído da silver e provado antes de publicar

<!-- nav:start -->
[Home](../README.md) | [← Matriz de barramento](15_matriz_de_barramento.md) | [Warehouse Postgres →](17_warehouse_postgres.md)
<!-- nav:end -->

> A gold é a [Matriz de barramento](15_matriz_de_barramento.md) tornada tabela: as 11 dimensões e os 14 fatos de prioridade 1, em parquet no lake, construídos da [Silver](14_silver.md) por SQL declarado em código e publicados só depois de cinco provas. É a camada que o [Warehouse Postgres](17_warehouse_postgres.md) carrega e que os painéis vão ler. Este documento explica o que a gold é e o que ela nunca faz, como cada tabela se prova sozinha, o que o horizonte e o calendário significam, as decisões de modelagem que a matriz não tinha, o que a régua da gold mede e onde ela diverge do contrato de aceite, e o SQL analítico que responde às perguntas do [Entendimento do Negócio](01_entendimento_negocio.md). Todo número foi medido na base completa em 06/10/2026.

## 1. O que a gold é, e o que ela nunca faz

A silver tem o grão da réplica: uma linha do sistema do cliente, uma linha da silver. A gold tem o **grão do negócio**: uma linha é um posto num mês, um dia de ponto de uma pessoa, uma candidatura com todos os seus marcos, o resultado de uma filial num mês. É o modelo em estrela de Kimball, desenhado e aprovado na matriz antes de existir: cada fato é cortado pelas dimensões que a matriz marcou, e duas tabelas que dividem uma dimensão (o cliente, o mês, a filial) podem ser postas lado a lado por ela.

Cada tabela é uma `Tabela` em `src/rh_fictalent/gold/modelo.py`: o SQL sobre a silver e quatro declarações que a construção confere antes de publicar. O **grão** (`chave`) são as colunas que identificam uma linha, e repetição é reprovação. As **referências** (`referencias`) dizem que coluna aponta para que dimensão, e chave que não existe na dimensão é reprovação. As **conservações** (`conservacoes`) são totais que a gold tem de reproduzir da silver ao centavo: o faturamento bruto, o custo rateado, os dias de ponto, as linhas do CAGED. É o que impede um join de multiplicar ou perder dinheiro sem ninguém ver. E a **partição** é a coluna com o ano da data de negócio, que é como o fato é gravado no lake e carregado no warehouse.

Cinco convenções valem para todas as tabelas. A gold lê a silver pelas views de `lake.consulta.abrir_silver`, que só têm linhas vivas: a linha excluída na origem e a descartada por retenção não entram. A chave de uma dimensão é o `id` do sistema do cliente, e **toda dimensão tem a linha 0, "não se aplica"**, para o fato que não tem a dimensão (a vaga de recrutamento sem posto, o contrato sem motivo de encerramento) apontar para uma linha que existe em vez de para um nulo. A data vira `AAAAMMDD` e o mês vira `AAAAMM`, inteiros, para o join com `dim_data` e `dim_mes`. Dinheiro é decimal do começo ao fim, e onde um valor é repartido entre itens o arredondamento fica no último, para a soma fechar. E **a gold conta pessoas, não as identifica**: as dimensões de pessoa (`dim_colaborador`, `dim_candidato`) não têm nome, documento, chave pseudonimizada, matrícula, telefone, e-mail nem login, e um teste reprova a dimensão que ganhar uma dessas colunas. O que sobra são atributos (ano de nascimento, sexo, escolaridade, município, fonte) que servem ao agregado e que o warehouse concede coluna a coluna, por necessidade ([Warehouse, seção 4](17_warehouse_postgres.md)).

O que a gold nunca faz vem das camadas anteriores e da auditoria às cegas:

- **não lê a bronze nem a réplica**: só a silver e as fontes públicas no lake;
- **não corrige a silver**: a marca de achado vem junto (`q_fin_06` no posto do mês, `q_ats_01` no candidato), e a decisão de contar ou descontar é da pergunta, não da tabela;
- **não consulta o gerador nem a régua do dado sintético** para montar tabela nenhuma; a única exceção é deliberada e está na seção 6, a régua da gold, que lê as bandas do contrato para provar o caminho de ponta a ponta;
- **não é ajustada para caber numa banda**: onde a medida da gold sai do contrato de aceite, o laudo relata e este documento registra o porquê.

## 2. As tabelas

Vinte e cinco tabelas, 131 arquivos, 11,9 MB de parquet. A dimensão é um arquivo (`gold/dim_cliente/dim_cliente.parquet`); o fato é um arquivo por ano da data de negócio (`gold/fato_ponto_dia/ano=2024.parquet`), nove anos de 2018 a 2026, três para o mercado, que começa em 2023 com o Novo CAGED.

| tabela | uma linha é | linhas |
|---|---|---:|
| `dim_data` | um dia do calendário, de 01/01/2018 a 31/12/2027 | 3.653 |
| `dim_mes` | um mês do calendário | 121 |
| `dim_filial` | uma filial | 4 |
| `dim_cliente` | um cliente | 101 |
| `dim_funcao` | uma função, com o código de ocupação | 46 |
| `dim_motivo` | um motivo de encerramento, desligamento, reprovação ou ocorrência | 46 |
| `dim_contrato` | um contrato comercial | 129 |
| `dim_posto` | um posto de trabalho | 695 |
| `dim_colaborador` | uma pessoa que teve contrato de trabalho | 15.559 |
| `dim_candidato` | uma pessoa que se candidatou | 60.295 |
| `dim_escopo_mercado` | um escopo do CAGED: município ou estado por grupo de atividade | 64 |
| `fato_faturamento` | um item de fatura | 9.934 |
| `fato_custo_pessoal` | o custo de uma pessoa num posto numa competência | 63.470 |
| `fato_posto_mes` | um posto num mês da vigência dele | 9.355 |
| `fato_contrato` | um contrato, com os seus marcos | 128 |
| `fato_vaga` | uma vaga, da abertura ao fechamento | 18.932 |
| `fato_candidatura` | uma candidatura, da inscrição ao desfecho | 282.605 |
| `fato_alocacao` | uma alocação de pessoa em posto | 16.992 |
| `fato_vinculo` | um contrato de trabalho, da admissão à rescisão | 16.992 |
| `fato_ponto_dia` | um dia de ponto de uma pessoa alocada | 1.166.361 |
| `fato_recebimento` | um título a receber | 3.459 |
| `fato_ocorrencia` | uma ocorrência de contrato | 1.321 |
| `fato_conformidade_mes` | um posto num mês, com a foto do ASO e dos cursos | 9.355 |
| `fato_resultado_mes` | uma filial num mês: receita, custo, impostos, despesa, resultado | 240 |
| `fato_mercado_mes` | um escopo do CAGED num mês: admissões, desligamentos, saldo | 2.137 |

Cada linha e cada coluna têm a descrição na matriz (grão, processo, o que a dimensão é), e essa descrição vira o comentário da tabela no warehouse. Os seis fatos de prioridade 2 da matriz (folha, treinamento, acesso, entre outros) não existem ainda; estão na seção 11.

## 3. Como uma tabela é construída, e provada

É o mesmo padrão da silver, auditar antes de publicar, com as provas que cabem a um modelo dimensional. A tabela é montada da silver, gravada em `gold/_em_conferencia/`, lida de volta do lake e conferida; só a aprovada é movida para `gold/<tabela>/`, e a reprovada fica na área de conferência com a versão publicada antes intacta. A conferência são **cinco provas**, e qualquer uma reprova:

| prova | o que exige | o que pega |
|---|---|---|
| grão | a chave declarada não se repete nem vem vazia | join que duplicou o posto do mês |
| referências | toda chave de dimensão do fato existe na dimensão publicada, inclusive a linha 0 | função que a vaga cita e o cadastro não tem |
| conservação | cada total declarado dá, na gold, o mesmo número que na silver, sem tolerância | o item de fatura que o join perdeu, o centavo que o rateio inventou |
| pessoa | a dimensão de pessoa não tem coluna de identidade; toda dimensão tem a linha 0 | a coluna de nome que entrou por engano |
| partição | nenhuma linha sem ano; o que foi lido de volta tem as linhas que foram montadas | o arquivo que não gravou inteiro |

As dimensões são construídas antes dos fatos, porque a prova de referência precisa da dimensão publicada. São 55 conservações declaradas no modelo; a mais importante é a do faturamento bruto, que atravessa `fato_faturamento`, `fato_posto_mes` e `fato_resultado_mes` e dá o mesmo total nas três.

Pela linha de comando, a gold inteira:

```bash
.venv/bin/python -m rh_fictalent.gold --publicar
```

Em 8,8 s, as 25 tabelas são montadas, gravadas, conferidas e publicadas. Uma tabela só, com o nome dela: `--publicar fato_posto_mes`.

## 4. O horizonte e o calendário

A gold precisa de um "hoje". A silver tem a data de referência, que é o dia da carga; a gold tem o **horizonte**: o último dia com movimento na operação, a maior data entre o apontamento de ponto e a alocação. Na base completa é 10/09/2026. O posto e a alocação em aberto são medidos até ele, a foto da conformidade é tirada nele, e o mês dele é marcado como **parcial** (`mes_parcial`) em todo fato mensal, porque ainda não tem fatura e entraria como queda falsa em qualquer série. O horizonte é uma variável da sessão do DuckDB (`SET VARIABLE horizonte`), definida por `modelo.preparar` a partir do dado, nunca digitada.

O **calendário** (`dim_data`, `dim_mes`) começa em 01/01/2018, o início do arco do caso, e termina no último dia do ano seguinte ao do horizonte ou na maior data futura que o dado tem (o fim de vigência de um contrato comercial, o término previsto de um contrato de trabalho), o que vier depois: 31/12/2027 na base completa. A regra existe porque a primeira versão terminava o calendário no ano do horizonte e uma data de 2027 que o contrato de trabalho previa ficou órfã, sem linha em `dim_data`, e a prova de referência reprovou. O fim do calendário vem do dado pelo mesmo motivo que o horizonte.

## 5. As decisões de modelagem que a matriz não tinha

A matriz desenhou o grão e as dimensões; quatro decisões só apareceram ao construir, e estão registradas aqui e no código.

**O resultado por filial.** O caso tem imposto e despesa que o sistema do cliente não atribui a filial nenhuma. A regra adotada: o ISS é da filial do município que o recolhe; o imposto federal e a despesa da retaguarda são rateados entre as filiais pelo faturamento do mês, com o resto do arredondamento na matriz. Entrou na matriz como proposta e foi **aprovada em 06/10/2026 pelo Tiago, no papel de cliente**; `fato_resultado_mes` a implementa, e a conservação garante que o rateio não cria nem perde um centavo.

**A conformidade é foto.** `fato_conformidade_mes` responde "no fim deste mês, quantas pessoas alocadas neste posto estavam com ASO vencido ou curso obrigatório sem certificado". A foto é tirada no último dia do mês ou no horizonte, o que vier antes, e por isso o mês parcial conta pessoas até o horizonte. É a série mensal do que a silver só marcava na data de referência ([Silver, seção 10](14_silver.md)).

**A candidatura carrega as etapas como colunas.** Em vez de uma linha por etapa do funil, `fato_candidatura` tem uma linha por candidatura com a data de cada etapa e os marcos (`aprovada`, `reprovada`, `desistiu`, `aprovada_sem_admissao`, `aguardando_admissao`). A conversão de uma etapa para a seguinte é a divisão entre duas colunas, e o funil por trimestre sai de um `GROUP BY`. O prazo de admissão (45 dias) separa a aprovada que ainda está dentro do prazo da que já deveria ter sido admitida e não foi.

**O mercado entra pelo lake.** A tabela derivada do Novo CAGED, versionada em `dados/publicos/caged` desde a v0.4.0, passou a ser um asset do grupo `fontes` (`fontes/caged/movimentacao`), lido pela gold como qualquer outra fonte. `dim_escopo_mercado` e `fato_mercado_mes` existem para a pergunta "a queda é do mercado?", e a conservação das linhas, admissões e desligamentos garante que a gold reproduz a tabela publicada.

## 6. A régua da gold

O [Régua de Validação](06_regua_de_validacao.md) prometeu que a régua, por não saber gerar dado nem ler banco, poderia um dia conferir as mesmas medidas tiradas do warehouse. `rh_fictalent.gold.regua` é esse dia: o mesmo motor (banda, check, laudo) com três famílias de checks.

A **conservação** (55 checks) é cada total declarado no modelo, medido na gold e na silver, com banda exatamente zero. É a mesma prova da construção, agora como contrato declarado e não só como conferência interna. A **integridade de chaves** (132 checks) é o grão que não se repete, toda chave de dimensão existindo na dimensão e toda dimensão com a linha 0. E a **coerência com as bandas** (59 medidas) são as medidas do contrato de aceite que a gold consegue reproduzir com a definição do próprio contrato (clientes ativos no fim do ano, headcount médio e de pico, vagas abertas, margem líquida, os invariantes C-01 a C-03 e C-05, a sujeira CAD-01, PES-02, SST-01, FIN-01 e GER-01), conferidas contra as mesmas bandas que aceitaram a base. É a prova de ponta a ponta: o que entrou pela réplica e atravessou bronze, silver e gold ainda conta a mesma história.

Só as duas primeiras famílias reprovam: elas são da gold. A terceira é relatada, porque o contrato foi escrito para o gerador e a gold mede o negócio como o [Modelo de Dados](04_modelo_dados_staging.md) manda. Na base completa:

```bash
.venv/bin/python -m rh_fictalent.gold --regua --so-problemas
```

Termina em **`RÉGUA DA GOLD APROVADA: 187 de 187 checks de conservação e integridade aprovados; 50 de 59 medidas do contrato de aceite dentro da banda`**, em 3,2 s. As nove fora da banda são duas diferenças de definição, e as duas estão entendidas:

| medida | na gold | banda do contrato | por quê |
|---|---:|---|---|
| H-10, margem líquida, 2018 a 2025 | de 0,2 % a 8,9 %, conforme o ano | de 0,8 a 2,3 pontos acima, em todo ano | o contrato mede pelos títulos a pagar lançados no ano, em regime de caixa: a provisão só vira título quando é baixada, na rescisão e no 13º. A gold mede pelo custo rateado ao posto, em regime de competência: a provisão entra no mês em que é constituída, e o imposto e a despesa são atribuídos à filial pela regra da seção 5. A margem da gold é a do negócio em competência, e fica sistematicamente abaixo da do contrato |
| CAD-01, candidatos duplicados | 1,4 % | de 2,8 % a 4,2 % | o descarte por retenção apagou o CPF de 19.119 candidatos vencidos e os grupos de cadastro repetido caíram de 2.735 para 859 ([Silver, seção 6](14_silver.md)). A gold conta o que a silver marcou depois do descarte; a banda foi escrita para a base antes dele |

A decisão de qual margem é a do painel (a de caixa do contrato ou a de competência da gold) é do cliente; até lá a gold mantém a de competência e o laudo continua relatando a diferença. O laudo fica no lake, em `gold/_regua.json`, e é o último passo do job `construir_gold`: conservação ou chave reprovada falha o job.

## 7. O SQL analítico

Nove consultas em `src/rh_fictalent/gold/analitico.py` respondem às perguntas do [Entendimento do Negócio](01_entendimento_negocio.md) com funções de janela, e cada uma declara a pergunta, a afirmação ou o indicador de origem, o SQL e as janelas que usa, uma a uma: onde a janela recomeça (`PARTITION BY`), a ordem dentro dela (`ORDER BY`) e o quadro (`ROWS BETWEEN`). O texto explica o porquê de cada escolha, porque é o que quem lê SQL analítico mais erra: a diferença entre `ROWS` e `RANGE` no acumulado, o `LAG` de doze linhas que só é o mesmo mês do ano anterior porque a série não tem buraco, o `RANK` que repete e pula.

| consulta | pergunta | origem |
|---|---|---|
| `serie_da_filial` | como cada filial cresceu mês a mês, em receita, pessoas, clientes e vagas, e quando parou | D1 |
| `pareto_de_clientes` | quais clientes carregam a receita de cada ano, com que margem, e quantos fazem 80 % dela | D2, A1 |
| `o_aviso_e_o_fim` | em cada contrato encerrado, quando veio o primeiro aviso, quantas reclamações houve nos seis meses finais, e a ocupação | D3 |
| `mercado_e_servico` | mês a mês, o que o mercado da região fez (CAGED) e o que a Fictalent fez ao mesmo tempo | D4 |
| `defasagem_do_mercado` | com que defasagem a reclamação e a perda de contrato seguem o mercado | D4 |
| `funil_por_trimestre` | a conversão de cada etapa do funil, trimestre a trimestre | D5 |
| `informado_contra_apurado` | o que a gerência informou e o que a operação apurou, mês a mês, e a divergência | D6 |
| `coorte_de_90_dias` | de cada coorte de admitidos, quantos saíram antes de 90 dias, e por quê | rotatividade |
| `postos_descobertos_em_sequencia` | os postos que ficaram descobertos meses seguidos, e por quanto tempo | carteira alocada |

Pela linha de comando, `python -m rh_fictalent.gold --analitico` lista as consultas e `--analitico pareto_de_clientes` roda uma sobre a gold publicada (1,3 s). O notebook `notebooks/gold/01_sql_analitico.ipynb` é a projeção das nove sobre o dado inteiro, executado e versionado, com uma Nota Técnica por seção ([os notebooks da gold](../notebooks/gold/README.md)). A semântica de cada janela é provada em teste num cenário pequeno, onde o resultado se confere à mão. A conclusão sobre as sete afirmações dos donos não está aqui: é outro notebook, de análise, escrito pelo Tiago com apoio do Code sobre o warehouse.

## 8. No Dagster

| o quê | nome | o que faz |
|---|---|---|
| 25 assets | `gold/<tabela>` | monta, grava, confere e publica a tabela; reprova a si mesmo |
| asset | `gold/regua` | o laudo da régua da gold; grava `gold/_regua.json`; falha por conservação ou chave |
| job | `construir_gold` | as dimensões, os fatos e a régua: 26 passos |
| sensor | `gold_depois_da_silver` | dispara `construir_gold` depois de todo `construir_silver` que termina bem |

A linhagem é a do modelo: `gold/fato_posto_mes` depende das tabelas da silver que o SQL dele lê e das dimensões que ele referencia, já publicadas na gold; `gold/fato_mercado_mes` depende do asset do CAGED. A gold é refeita inteira depois de toda silver, e a silver depois de toda carga incremental, então a cadeia do dia é: a carga das 5h, a silver em cerca de 3 minutos, a gold em cerca de 1 e o warehouse em pouco mais de 2 ([Warehouse, seção 7](17_warehouse_postgres.md)). O sensor não reage ao `aplicar_descarte`, que é o caminho curto feito à mão, nem a silver nenhuma que falhe.

## 9. Ler a gold

A gold é parquet no lake, lida com o mesmo DuckDB. `abrir_gold` devolve uma conexão com uma view por tabela, `gold.<tabela>`, sobre o parquet publicado:

```python
from dotenv import load_dotenv

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.recursos import lake_do_ambiente

load_dotenv(".env")
con = consulta.abrir_gold(lake_do_ambiente())
con.sql(
    """
    SELECT f.nome AS filial, r.mes_id, r.faturamento, r.custo_pessoal, r.resultado, r.margem_liquida
    FROM gold.fato_resultado_mes r JOIN gold.dim_filial f ON f.id = r.filial_id
    WHERE NOT r.mes_parcial AND r.mes_id >= 202501
    ORDER BY 1, 2
    """
).show()
```

A mesma conexão tem as views da silver (`silver.<modulo>.<tabela>`) e das fontes (`fontes.<nome>`), que é como a régua compara os dois lados. Quem precisa do warehouse, e não do lake, lê o Postgres ([Warehouse, seção 8](17_warehouse_postgres.md)).

## 10. Os tempos, lado a lado

| operação | volume | tempo medido |
|---|---|---|
| a gold inteira, pela linha de comando | 25 tabelas, 1,68 milhão de linhas, com as cinco provas | 8,8 s |
| a régua da gold | 187 checks e 59 medidas do contrato, gold e silver | 3,2 s |
| uma consulta analítica (`pareto_de_clientes`) | sobre a gold publicada | 1,3 s |
| job `construir_gold`, no container | 26 passos, dois por vez | 56 s |
| job `carregar_caged` | a tabela do CAGED para o lake | 2,7 s |

A gold é mais rápida que a silver (31 s) porque produz 1,68 milhão de linhas a partir de 8,4 milhões: o grão do negócio é menor que o grão do sistema. Os 56 s do job contra os 8,8 s da linha de comando são o mesmo custo visto na silver, cada passo do Dagster como um processo novo com registro e linhagem.

## 11. O que ainda não existe

- **Os fatos de prioridade 2.** A matriz tem 20 fatos; a gold tem os 14 de prioridade 1. Folha detalhada, treinamento, acesso ao sistema e os demais entram quando uma pergunta os pedir.
- **A gold incremental.** Cada tabela é refeita inteira; com 8,8 s para a camada toda, refazer é mais barato que não refazer. A conta muda com o volume.
- **A margem do painel.** Qual das duas definições (seção 6) é a do painel é decisão do cliente, ainda em aberto.
- **O notebook de conclusões.** Os números das sete afirmações estão nas consultas; a análise é o próximo notebook, com o olhar de quem conhece o caso.
- **Frescor por tabela.** O painel de monitoramento mede o frescor por execução; a idade de cada tabela da gold ainda não aparece ([Monitoramento](09_monitoramento_e_healthcheck.md)).

---

[Início](#topo)
