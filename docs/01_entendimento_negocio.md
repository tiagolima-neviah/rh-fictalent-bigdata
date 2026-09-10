<a id="topo"></a>

# Entendimento do Negócio · Fictalent RH

<!-- nav:start -->
[Home](../README.md) | [Entendimento dos Dados →](02_entendimento_dados.md)
<!-- nav:end -->

> O documento que qualquer pessoa deveria ler antes de olhar uma tabela deste projeto: quem é a empresa, como o dinheiro entra, o que ela mede, e a história que os dados sintéticos precisam contar. Sem entender isto, os números das camadas seguintes são só números.

## 1. A empresa

A **Fictalent RH** é uma empresa fictícia de **gestão de mão de obra**, fundada em **2018** com matriz em **Atibaia** e filiais em **Bragança Paulista** e **Extrema**, no eixo da rodovia Fernão Dias. Ela atende indústrias, transportadoras, galpões de armazenagem e varejo da região, empresas que têm entre mil e três mil funcionários e uma demanda que sobe e desce com o calendário.

**A distinção que muda tudo no dado:** ela não é uma consultoria de RH no sentido estratégico (clima, cargos e salários, desenvolvimento de liderança). Ela **coloca e administra pessoas**. Enquanto um RH interno administra o ciclo de vida de um quadro fixo, a Fictalent administra **um fluxo de colocação e uma carteira de contratos**. A pessoa alocada é três coisas ao mesmo tempo:

1. o **produto** entregue ao cliente,
2. a **unidade de receita** do contrato,
3. um **empregado CLT** da própria Fictalent, com folha, encargos, exames e prazo legal.

É por isso que o BI dela é híbrido: tem funil comercial, tem folha, tem margem por unidade e tem compliance. Quatro naturezas de dado que quase nunca se encontram na mesma tela.

**Os quatro serviços, e onde cada um termina:**

| serviço | quando termina | como a receita entra |
|---|---|---|
| **Recrutamento e Seleção** | na entrega do candidato admitido, com garantia de reposição (90 dias) | taxa pontual, um múltiplo do salário |
| **Trabalho temporário** | não termina na entrega, **começa nela**: a Fictalent é a empregadora legal durante todo o contrato (Lei 6.019/74, até 180 dias prorrogáveis por mais 90) | mensal, enquanto a pessoa estiver alocada |
| **Terceirização de serviços** | contínuo, com gestão do posto e reposição de faltas | mensal, por posto contratado |
| **Treinamentos** | no fim da turma | pontual, por turma ou por participante |

**As pessoas do caso** (fictícias, e cada uma existe porque representa um papel no dado):

| pessoa | papel | relação com a informação |
|---|---|---|
| **Romeu** | sócio-proprietário | decide contratar, demitir e investir. Hoje decide por intuição |
| **Janaína** | sócia-proprietária | acompanha resultado nas reuniões formais |
| **Sabrina** | gerente-geral | consolida os relatórios de todos os setores e apresenta aos sócios. É o gargalo humano da informação |
| **Coordenadoras** | uma por setor | deveriam ser a camada analítica; foram absorvidas pelo operacional |
| **Assistentes** | duas a três por setor | exportam planilhas dos sistemas e cruzam à mão, todo dia |

## 2. Como um pedido de vaga vira pessoa alocada e receita

O ciclo operacional inteiro, que é o que o modelo de dados precisa reproduzir:

```
requisição do cliente
   → divulgação da vaga
      → triagem de currículos
         → entrevista interna
            → encaminhamento ao cliente
               → entrevista do cliente
                  → aprovação
                     → exames admissionais (ASO)
                        → documentação e admissão
                           → ALOCAÇÃO no posto
                              → acompanhamento (ponto, faltas, horas extras, ocorrências)
                                 → desfecho
```

O **desfecho** é o que fecha a conta de cada colocação, e são quatro:

- **efetivação pelo cliente**: o cliente contrata a pessoa. Para a Fictalent é receita de taxa e perda de receita recorrente;
- **fim de contrato**: o temporário chega ao termo. É o desfecho saudável;
- **desligamento**: a pessoa sai antes, por iniciativa dela ou do cliente. Se for nos primeiros 90 dias, é o desfecho mais caro, porque queima a garantia e obriga a repor;
- **substituição**: troca da pessoa no mesmo posto, mantendo o contrato.

Entre a aprovação e a alocação existe um intervalo que quase ninguém mede e que custa dinheiro: enquanto o posto está descoberto, **não há receita naquele posto**, mas o contrato e o SLA continuam correndo.

## 3. O que a empresa mede (ou deveria)

Cinco famílias de indicadores, e a tese do projeto é que ninguém na Fictalent vê as cinco na mesma tela:

**Funil de colocação (o comercial dela):** vagas abertas, preenchidas e canceladas; **fill rate**; **time to fill** por vaga, cliente e filial; conversão de cada etapa (triados, entrevistados, encaminhados, aprovados, admitidos); no-show de entrevista e de primeiro dia; fonte do candidato; custo por contratação.

**Carteira alocada (a receita viva):** headcount alocado por cliente, posto e filial; entradas e saídas; **taxa de ocupação dos postos**, porque posto vago é receita que não entra; dias de posto descoberto; efetivações pelo cliente.

**Rotatividade e absenteísmo:** turnover total, voluntário e involuntário; **turnover nos primeiros 90 dias**; absenteísmo por posto; horas extras e banco de horas.

**Financeiro por unidade:** faturamento por cliente, posto e filial; custo por cabeça (salário, encargos, provisões e benefícios); **margem por posto e por contrato**; inadimplência; ticket médio de R&S.

**Compliance e risco:** vencimento do **prazo legal do temporário** (180 dias, prorrogáveis por 90); ASO e exames vencidos; treinamentos obrigatórios (NR) vencidos; acidentes e CAT; reclamações por posto.

## 4. A história nos números, de 2018 a 2026

Os dados sintéticos deste projeto não são aleatórios com cara de real: eles contam uma história com cinco atos, e cada ato tem consequência mensurável. Quem abrir o banco e olhar a série mensal precisa **ver a história acontecer**.

**Ato 1, 2018 e 2019: a fundação.** Volume baixo e processo artesanal que funciona bem. Cada setor exporta sua planilha, cruza e entrega à coordenadora; a coordenadora entrega à Sabrina; Sabrina consolida e apresenta aos sócios. Existe ritual: reunião mensal, trimestral, semestral e anual, e uma reunião curta toda sexta-feira entre a Sabrina e as coordenadoras.

**Ato 2, 2020 e 2021: a pandemia.** A operação industrial da região reduz e o volume cai forte. O processo em Excel aguenta justamente porque encolheu. A empresa sobrevive enxuta e não perde os clientes âncora.

**Ato 3, de 2022 a 2024: o crescimento que quebrou o processo.** A retomada vem em massa. Concorrentes não dão conta e a Fictalent cresce em clientes, em pessoas alocadas e em receita. O que era virtude vira gargalo: as assistentes não conseguem mais operar e alimentar as bases ao mesmo tempo, a informação quebra na ponta, e as coordenadoras abandonam a análise para socorrer o operacional. **A empresa cresce sem saber se tem lucro.** A partir de 2023 a qualidade do serviço começa a ceder: o tempo para preencher uma vaga sobe, o no-show de primeiro dia aumenta, a rotatividade nos primeiros 90 dias piora. Ninguém mede isso, então ninguém vê.

**Ato 4, de 2025 a setembro de 2026: a virada de maré.** Elogios de clientes viram reclamações, e as reclamações viram quebras de contrato. Clientes saem, a receita cai e a despesa demora a acompanhar. Romeu demite por intuição, contrata auxiliares que são imediatamente absorvidas pelo operacional, e consegue extrair relatório suficiente apenas para concluir que não pode contratar nem demitir mais. **A empresa continua dando lucro, mas com margem apertada, e sem saber de onde ele vem.**

**Ato 5, setembro de 2026: a decisão.** Romeu conclui que o problema é de informação, não de mercado, e busca ajuda. É o instante em que este projeto começa, e é o relógio dos dados: a base vai de 2018 até **10 de setembro de 2026**.

**A defasagem que explica tudo, e que só o dado mostra:** a degradação da qualidade começa em 2023, mas a perda de contratos só aparece no fim de 2025. Um cliente não rompe no primeiro problema; ele aguenta um ciclo sazonal ruim e não renova no seguinte. Entre a causa e o efeito existem de seis a nove meses, e é por isso que, para quem olha só o mês corrente, a queda parece ter vindo do nada.

## 5. As perguntas que este projeto precisa responder

Sete afirmações feitas pelos donos na primeira reunião. Elas são o **contrato da análise**: cada uma vira uma verificação nas camadas seguintes, e a resposta pode ser "confirma" ou "contradiz".

| # | afirmação | quem disse | o que a análise precisa checar |
|---|---|---|---|
| D1 | "A gente cresceu muito de 2022 a 2025." | Romeu | cresceu em quê? receita, headcount, clientes ou volume de trabalho? |
| D2 | "Não sei se tenho lucro ou prejuízo." | Romeu | margem por cliente, posto e filial ao longo do arco |
| D3 | "Os clientes começaram a sair no fim de 2025." | Romeu | quando começou de fato, e em quais clientes e postos |
| D4 | "A queda é do mercado." | Romeu | é mercado ou é qualidade de serviço? (a comparação com o CAGED da região responde) |
| D5 | "Contratar mais assistente resolveria." | Romeu | as contratações de 2026 melhoraram algum indicador? |
| D6 | "Depois de 2022 os relatórios pararam de bater." | Sabrina | divergência entre o consolidado dela e a operação |
| A1 | "Cliente grande é sempre melhor." | Janaína | margem por porte de cliente |

## 6. As dores, na linguagem deles

Retrabalho diário de exportar e cruzar planilhas. Informação que quebra na ponta quando o volume sobe. Coordenação presa no operacional. Ausência de visão de lucro por cliente. Decisão de contratar e demitir por intuição. Perda de contrato sem causa identificada. Reuniões que existiam e acabaram.

## 7. O que este projeto entrega

Três coisas, nesta ordem, e cada uma resolve uma das dores acima:

1. **Um banco relacional modular** que funciona como o sistema que a empresa não tem, com **carga histórica retroativa desde 2018** (o cliente não recomeça do zero: a história dele já está no sistema dele) e **carga incremental diária** que substitui o trabalho manual das assistentes.
2. **Um pipeline analítico** (bronze, silver e gold) que reconstrói os indicadores de uma única fonte da verdade, documentando cada limpeza feita e cada divergência encontrada, incluindo a da declaração D6.
3. **Um modelo multidimensional** pronto para o painel web e para o Power BI, organizado pelos mesmos módulos do negócio, com **autoatendimento em três níveis**: a assistente extrai o detalhe, a Sabrina consolida sem montar planilha, e os sócios abrem o painel sozinhos.

O sistema com telas transacionais (o que substituiria o operacional) é projeto futuro. O modelo relacional deste projeto já nasce preparado para ele, inclusive com o módulo de permissões.

---

[Início](#topo) | [Entendimento dos Dados →](02_entendimento_dados.md)
