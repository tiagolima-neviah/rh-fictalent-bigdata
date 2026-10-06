<a id="topo"></a>

# Matriz de barramento · os fatos, as dimensões e o grão da gold

<!-- nav:start -->
[Home](../README.md) | [← Silver](14_silver.md) | [Bibliografia →](bibliografia.md)
<!-- nav:end -->

> **Arquivo gerado** por `python -m rh_fictalent.gold --matriz` a partir de `src/rh_fictalent/gold/barramento.py`. Não edite à mão: mude a declaração e gere de novo. A matriz é o desenho do modelo dimensional, escrito antes de a gold existir: diz que tabelas de fatos haverá, o que é uma linha de cada uma e por quais dimensões cada uma pode ser cortada. É o documento que se aprova antes de construir, porque mudar o grão de um fato depois de pronto é refazer o fato.

Situação: **aprovada pelo Tiago em 05/10/2026, como proposta**. São **20 fatos** (14 de prioridade 1 e 6 de prioridade 2) e **14 dimensões**, cobrindo os 26 indicadores do [Entendimento do Negócio](01_entendimento_negocio.md) e as 7 afirmações dos donos.

## 1. Como ler

Um **fato** é uma tabela em que cada linha é algo que aconteceu ou uma medida tirada: uma vaga, um dia trabalhado, o mês de um posto. Uma **dimensão** é uma tabela pela qual o fato é cortado e descrito: o cliente, a filial, o mês. O **grão** é a frase que diz o que é uma linha do fato, e é a decisão mais importante do modelo: tudo o que o fato consegue responder sai dela.

Na matriz, cada linha é um fato e cada coluna é uma dimensão. Dois fatos com a marca na mesma coluna dividem aquela dimensão e podem ser postos lado a lado por ela: é assim que a margem, o tempo de preenchimento e as reclamações de um cliente cabem na mesma tela, vindos de três tabelas diferentes.

Os fatos são de quatro tipos:

| tipo | o que é |
|---|---|
| transação | uma linha por evento, que não muda depois de gravada |
| foto acumulada | uma linha por coisa que tem começo, meio e fim (a vaga, a candidatura, o contrato), atualizada a cada marco, com uma data por marco |
| foto periódica | uma linha por período (o mês), mesmo que nada tenha acontecido: é como se mede estoque, e headcount é estoque |
| consolidado | fatos de processos diferentes levados ao mesmo grão e postos lado a lado; é onde receita e custo se encontram |

## 2. A matriz

| fato | P | data | mês | filial | cliente | contrato | posto | função | colaborador | candidato | motivo | escopo mercado | evento folha | curso | usuário |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| [vaga](#fato_vaga) | 1 | ● |   | ● | ● | ● | ● | ● |   |   |   |   |   |   |   |
| [candidatura](#fato_candidatura) | 1 | ● |   | ● | ● |   |   | ● |   | ● | ● |   |   |   |   |
| [alocação](#fato_alocacao) | 1 | ● |   | ● | ● | ● | ● | ● | ● |   | ● |   |   |   |   |
| [posto mês](#fato_posto_mes) | 1 |   | ● | ● | ● | ● | ● | ● |   |   |   |   |   |   |   |
| [contrato](#fato_contrato) | 1 | ● |   | ● | ● | ● |   |   |   |   | ● |   |   |   |   |
| [vínculo](#fato_vinculo) | 1 | ● |   | ● |   |   |   | ● | ● |   | ● |   |   |   |   |
| [ponto dia](#fato_ponto_dia) | 1 | ● |   | ● | ● | ● | ● | ● | ● |   |   |   |   |   |   |
| [faturamento](#fato_faturamento) | 1 | ● | ● | ● | ● | ● | ● | ● |   |   |   |   |   |   |   |
| [recebimento](#fato_recebimento) | 1 | ● | ● | ● | ● | ● |   |   |   |   |   |   |   |   |   |
| [custo pessoal](#fato_custo_pessoal) | 1 |   | ● | ● | ● | ● | ● | ● | ● |   |   |   |   |   |   |
| [resultado mês](#fato_resultado_mes) | 1 |   | ● | ● |   |   |   |   |   |   |   |   |   |   |   |
| [ocorrência](#fato_ocorrencia) | 1 | ● |   | ● | ● | ● | ● |   |   |   | ● |   |   |   |   |
| [conformidade mês](#fato_conformidade_mes) | 1 |   | ● | ● | ● | ● | ● | ● |   |   |   |   |   |   |   |
| [mercado mês](#fato_mercado_mes) | 1 |   | ● |   |   |   |   |   |   |   |   | ● |   |   |   |
| [folha](#fato_folha) | 2 |   | ● | ● |   |   |   |   | ● |   |   |   | ● |   |   |
| [despesa](#fato_despesa) | 2 | ● | ● | ● |   |   |   |   |   |   |   |   |   |   |   |
| [afastamento](#fato_afastamento) | 2 | ● |   | ● | ● |   |   | ● |   |   | ● |   |   |   |   |
| [saúde ocupacional](#fato_saude_ocupacional) | 2 | ● |   | ● | ● |   |   | ● |   |   |   |   |   |   |   |
| [treinamento](#fato_treinamento) | 2 | ● |   | ● | ● |   |   |   | ● |   |   |   |   | ● |   |
| [acesso](#fato_acesso) | 2 | ● |   | ● |   |   |   |   |   |   |   |   |   |   | ● |

A coluna P é a prioridade (seção 7). O nome de cada fato leva ao detalhe dele.

## 3. Os fatos, um a um

### Funil de colocação

<a id="fato_vaga"></a>

**`fato_vaga`** · abrir e preencher uma vaga · foto acumulada · prioridade 1

- **Grão:** uma vaga.
- **Dimensões:** `dim_data` (abertura, fechamento), `dim_filial`, `dim_cliente`, `dim_contrato`, `dim_posto`, `dim_funcao`.
- **Medidas:** posições; candidaturas recebidas; aprovados; dias até fechar; preenchida; cancelada; dias em aberto.
- **Vem de:** `ats.vaga`, `ats.requisicao`, `ats.candidatura`.

<a id="fato_candidatura"></a>

**`fato_candidatura`** · levar um candidato pelo funil · foto acumulada · prioridade 1

- **Grão:** uma candidatura.
- **Dimensões:** `dim_data` (inscrição, conclusão), `dim_candidato`, `dim_filial`, `dim_cliente`, `dim_funcao`, `dim_motivo` (reprovação ou desistência).
- **Medidas:** chegou a cada etapa (uma coluna por etapa); entrevistas; faltou à entrevista; aprovada; admitida; aprovada que não começou (no-show do primeiro dia); dias no funil; custo médio da fonte.
- **Vem de:** `ats.candidatura`, `ats.candidatura_etapa`, `ats.entrevista`, `ats.vaga`, `ats.requisicao`, `ats.etapa_funil`, `ats.candidato`, `ats.fonte_candidato`, `pessoas.colaborador`, `pessoas.contrato_trabalho`.
- **Marcas de qualidade que carrega:** `q_ats_01`.
- **Nota:** as etapas viram colunas, não linhas: a conversão de cada etapa é uma divisão entre duas colunas.

<a id="fato_mercado_mes"></a>

**`fato_mercado_mes`** · o mercado de trabalho da região · foto periódica · prioridade 1

- **Grão:** um território e um grupo de atividade num mês.
- **Dimensões:** `dim_mes`, `dim_escopo_mercado`.
- **Medidas:** admissões; desligamentos; saldo.
- **Vem de:** `fontes.caged_movimentacao`.
- **Nota:** não é dado do cliente: é a régua de fora, para separar o que é mercado do que é serviço.

### Carteira alocada

<a id="fato_alocacao"></a>

**`fato_alocacao`** · alocar uma pessoa num posto · foto acumulada · prioridade 1

- **Grão:** uma alocação.
- **Dimensões:** `dim_data` (início, fim), `dim_colaborador`, `dim_posto`, `dim_contrato`, `dim_cliente`, `dim_filial`, `dim_funcao`, `dim_motivo` (fim da alocação).
- **Medidas:** dias alocado; em substituição de outra alocação; terminou em efetivação pelo cliente.
- **Vem de:** `pessoas.alocacao`, `pessoas.contrato_trabalho`, `pessoas.desligamento`, `comercial.posto`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_fin_06`, `q_tss_01`, `q_tss_06`.

<a id="fato_posto_mes"></a>

**`fato_posto_mes`** · ocupar o posto, faturar e custear · consolidado · prioridade 1

- **Grão:** um posto num mês da vigência dele.
- **Dimensões:** `dim_mes`, `dim_posto`, `dim_contrato`, `dim_cliente`, `dim_filial`, `dim_funcao`.
- **Medidas:** posições contratadas; pessoas no fim do mês; pessoa-dias alocados; posição-dias descobertos; taxa de ocupação; entradas; saídas; preço mensal vigente; receita; custo de pessoal; margem; margem percentual.
- **Vem de:** `comercial.posto`, `comercial.posto_preco`, `comercial.contrato`, `pessoas.alocacao`, `financeiro.fatura_item`, `financeiro.fatura`, `folha.rateio_custo`, `ponto.apontamento`.
- **Marcas de qualidade que carrega:** `q_fin_06`, `q_fol_01`.
- **Nota:** é a espinha da margem (`docs/04`, seção 4): o único lugar onde receita e custo estão no mesmo grão.

<a id="fato_contrato"></a>

**`fato_contrato`** · ganhar, manter e perder um contrato · foto acumulada · prioridade 1

- **Grão:** um contrato comercial.
- **Dimensões:** `dim_data` (assinatura, início, fim da vigência, encerramento), `dim_contrato`, `dim_cliente`, `dim_filial`, `dim_motivo` (encerramento).
- **Medidas:** meses de vida; encerrado; prorrogações; postos; reclamações; elogios; avisos de rescisão; receita total.
- **Vem de:** `comercial.contrato`, `comercial.contrato_aditivo`, `comercial.contrato_ocorrencia`, `comercial.posto`, `financeiro.fatura`.
- **Marcas de qualidade que carrega:** `q_com_01`.

### Rotatividade e absenteísmo

<a id="fato_vinculo"></a>

**`fato_vinculo`** · admitir e desligar · foto acumulada · prioridade 1

- **Grão:** um contrato de trabalho.
- **Dimensões:** `dim_data` (admissão, término previsto, rescisão), `dim_colaborador`, `dim_filial`, `dim_funcao`, `dim_motivo` (desligamento).
- **Medidas:** dias de vínculo; desligado; tipo de desligamento; saiu em até 90 dias; dias além do prazo legal; dias de atraso do lançamento; salário base; valor da rescisão.
- **Vem de:** `pessoas.contrato_trabalho`, `pessoas.desligamento`, `pessoas.contrato_trabalho_prorrogacao`.
- **Marcas de qualidade que carrega:** `q_pes_01`, `q_pes_02`, `q_pes_03`.

<a id="fato_ponto_dia"></a>

**`fato_ponto_dia`** · trabalhar o dia · transação · prioridade 1

- **Grão:** um colaborador num dia (um apontamento).
- **Dimensões:** `dim_data`, `dim_colaborador`, `dim_posto`, `dim_contrato`, `dim_cliente`, `dim_filial`, `dim_funcao`.
- **Medidas:** horas trabalhadas; horas extras; horas noturnas; dia previsto; falta; falta injustificada; atestado; minutos de atraso.
- **Vem de:** `ponto.apontamento`, `ponto.ocorrencia_ponto`, `pessoas.alocacao`, `comercial.posto`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_pon_01`, `q_pon_03`.
- **Nota:** as batidas (4,3 milhões) ficam na silver: o fato é o dia, e a batida é evidência dele.

<a id="fato_afastamento"></a>

**`fato_afastamento`** · afastar-se do trabalho · foto acumulada · prioridade 2

- **Grão:** um afastamento, sem chave de pessoa.
- **Dimensões:** `dim_data` (início, fim), `dim_cliente`, `dim_filial`, `dim_funcao`, `dim_motivo` (afastamento).
- **Medidas:** dias afastado; tipo; grupo da CID.
- **Vem de:** `pessoas.afastamento`, `pessoas.alocacao`, `pessoas.contrato_trabalho`, `comercial.posto`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_pes_04`.
- **Nota:** dado de saúde: entra para o agregado, sem a dimensão de colaborador.

### Financeiro por unidade

<a id="fato_faturamento"></a>

**`fato_faturamento`** · faturar o cliente · transação · prioridade 1

- **Grão:** um item de fatura (a fatura de um posto num mês); fatura de recrutamento, sem posto, entra numa linha só.
- **Dimensões:** `dim_mes` (competência), `dim_data` (emissão), `dim_cliente`, `dim_contrato`, `dim_posto`, `dim_filial`, `dim_funcao`.
- **Medidas:** valor dos postos; valor de horas extras; descontos; valor bruto; impostos; valor líquido; dias trabalhados; faltas.
- **Vem de:** `financeiro.fatura`, `financeiro.fatura_item`, `comercial.posto`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_fin_03`, `q_fin_07`.

<a id="fato_recebimento"></a>

**`fato_recebimento`** · receber do cliente · foto acumulada · prioridade 1

- **Grão:** um título a receber.
- **Dimensões:** `dim_data` (vencimento, pagamento), `dim_mes` (competência da fatura), `dim_cliente`, `dim_contrato`, `dim_filial`.
- **Medidas:** valor; valor pago; dias de atraso; vencido e não pago; diferença entre pago e devido.
- **Vem de:** `financeiro.titulo_receber`, `financeiro.fatura`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_fin_05`.
- **Nota:** a situação vem das datas (FIN-04), não do status do sistema.

<a id="fato_custo_pessoal"></a>

**`fato_custo_pessoal`** · custear a pessoa alocada · transação · prioridade 1

- **Grão:** o rateio do custo de um colaborador numa alocação num mês.
- **Dimensões:** `dim_mes`, `dim_colaborador`, `dim_posto`, `dim_contrato`, `dim_cliente`, `dim_filial`, `dim_funcao`.
- **Medidas:** salário; encargos; provisões; benefícios; custo total; diferença entre o rateio e a folha.
- **Vem de:** `folha.rateio_custo`, `comercial.posto`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_fol_01`, `q_fol_03`.

<a id="fato_resultado_mes"></a>

**`fato_resultado_mes`** · fechar o mês da filial · consolidado · prioridade 1

- **Grão:** uma filial num mês.
- **Dimensões:** `dim_mes`, `dim_filial`.
- **Medidas:** faturamento; custo de pessoal; impostos; despesas; resultado; margem líquida; pessoas alocadas; vagas abertas; clientes ativos; faturamento informado; custo informado; headcount informado; vagas abertas informadas; diferença de cada par.
- **Vem de:** `financeiro.fatura`, `folha.rateio_custo`, `financeiro.imposto_apurado`, `financeiro.titulo_pagar`, `financeiro.consolidado_gerencial`, `pessoas.alocacao`, `pessoas.contrato_trabalho`, `ats.vaga`, `comercial.contrato`, `cadastro.centro_custo`.
- **Nota:** a operação é a fonte da verdade e o consolidado da gerência fica ao lado, como série informada (FIN-01 e FIN-02); como imposto e despesa chegam à filial é regra a escrever e aprovar no card 7.2.

<a id="fato_folha"></a>

**`fato_folha`** · pagar a folha · transação · prioridade 2

- **Grão:** um colaborador, um mês, um evento da folha.
- **Dimensões:** `dim_mes`, `dim_colaborador`, `dim_filial`, `dim_evento_folha`.
- **Medidas:** valor; referência.
- **Vem de:** `folha.folha_item`, `folha.folha_competencia`, `folha.evento_folha`.

<a id="fato_despesa"></a>

**`fato_despesa`** · pagar fornecedor, encargo e imposto · foto acumulada · prioridade 2

- **Grão:** um título a pagar.
- **Dimensões:** `dim_mes` (competência), `dim_data` (vencimento, pagamento), `dim_filial`.
- **Medidas:** valor; tipo; dias de atraso.
- **Vem de:** `financeiro.titulo_pagar`, `financeiro.fornecedor`, `cadastro.centro_custo`.

### Compliance e risco

<a id="fato_ocorrencia"></a>

**`fato_ocorrencia`** · ouvir o cliente · transação · prioridade 1

- **Grão:** uma ocorrência de contrato (reclamação, elogio, advertência, aviso de rescisão).
- **Dimensões:** `dim_data`, `dim_cliente`, `dim_contrato`, `dim_posto`, `dim_filial`, `dim_motivo` (ocorrência).
- **Medidas:** ocorrência; tipo.
- **Vem de:** `comercial.contrato_ocorrencia`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_com_03`.

<a id="fato_conformidade_mes"></a>

**`fato_conformidade_mes`** · manter a operação regular · foto periódica · prioridade 1

- **Grão:** um posto no último dia de cada mês.
- **Dimensões:** `dim_mes`, `dim_posto`, `dim_contrato`, `dim_cliente`, `dim_filial`, `dim_funcao`.
- **Medidas:** pessoas alocadas; com ASO vencido; com ASO a vencer em 30 dias; com curso obrigatório faltando; temporários além do prazo legal; temporários a 30 dias do prazo; programas legais vencidos.
- **Vem de:** `pessoas.alocacao`, `pessoas.contrato_trabalho`, `pessoas.contrato_trabalho_prorrogacao`, `sst.aso`, `sst.programa_sst`, `treinamento.certificado`, `treinamento.turma_participante`, `treinamento.turma`, `treinamento.curso_funcao`, `comercial.posto`, `comercial.contrato`.
- **Nota:** é a série mensal das marcas com prazo, que na silver só valem na data de referência; conta pessoas por posto e não leva chave de pessoa.

<a id="fato_saude_ocupacional"></a>

**`fato_saude_ocupacional`** · examinar e registrar acidente · transação · prioridade 2

- **Grão:** um exame (ASO) ou um acidente, sem chave de pessoa.
- **Dimensões:** `dim_data`, `dim_cliente`, `dim_filial`, `dim_funcao`.
- **Medidas:** exame; dias de atraso do admissional; acidente; gravidade; dias de afastamento; dias além do prazo da CAT.
- **Vem de:** `sst.aso`, `sst.tipo_exame`, `sst.acidente`, `sst.cat`, `pessoas.alocacao`, `pessoas.contrato_trabalho`, `comercial.posto`, `comercial.contrato`.
- **Marcas de qualidade que carrega:** `q_tss_02`, `q_tss_03`.
- **Nota:** dado de saúde: entra para o agregado, sem a dimensão de colaborador.

<a id="fato_treinamento"></a>

**`fato_treinamento`** · treinar e certificar · transação · prioridade 2

- **Grão:** a participação de um colaborador numa turma.
- **Dimensões:** `dim_data` (início da turma), `dim_colaborador`, `dim_filial`, `dim_cliente`, `dim_curso`.
- **Medidas:** presença; aprovado; certificado emitido; custo da turma rateado por participante.
- **Vem de:** `treinamento.turma_participante`, `treinamento.turma`, `treinamento.certificado`, `treinamento.curso`.
- **Marcas de qualidade que carrega:** `q_tss_05`.

### Acesso ao sistema

<a id="fato_acesso"></a>

**`fato_acesso`** · usar o sistema · transação · prioridade 2

- **Grão:** um evento da trilha de auditoria do sistema.
- **Dimensões:** `dim_data`, `dim_usuario`, `dim_filial`.
- **Medidas:** evento; módulo; ação; sem permissão vigente.
- **Vem de:** `seguranca.log_auditoria`, `seguranca.usuario`.
- **Marcas de qualidade que carrega:** `q_seg_01`.
- **Nota:** serve às consultas de auditoria da v1.0.0.

## 4. As dimensões

| dimensão | o que é | uma linha é | atributos | P |
|---|---|---|---|:-:|
| `dim_data` | o calendário, dia a dia | um dia, de 01/01/2018 a 31/12/2026 | ano, trimestre, mês, dia da semana, dia útil, feriado nacional | 1 |
| `dim_mes` | o mês de competência | um mês; é a `dim_data` enrolada no primeiro dia do mês | ano, trimestre, mês, dias úteis do mês | 1 |
| `dim_filial` | as unidades da Fictalent | uma filial | código, nome, matriz ou filial, município, região, data de abertura | 1 |
| `dim_cliente` | quem contrata a Fictalent | um cliente | razão social, nome fantasia, porte, setor, origem, município, região, primeiro contrato, ativo | 1 |
| `dim_contrato` | o contrato comercial | um contrato | número, tipo de serviço, status informado, situação derivada, vigência, prazo de pagamento, índice de reajuste | 1 |
| `dim_posto` | o posto de trabalho contratado | um posto | turno, escala, posições contratadas, vigência, município do local de trabalho | 1 |
| `dim_funcao` | a função exercida | uma função | código, nome, família, nível, CBO, insalubre, periculosidade | 1 |
| `dim_colaborador` | a pessoa contratada, sem identidade | um colaborador | ano de nascimento, sexo, escolaridade, fonte de recrutamento, município de residência, primeira admissão | 1 |
| `dim_candidato` | quem se candidatou, sem identidade | um cadastro de candidato | fonte, sexo, escolaridade, ano de nascimento, município, cadastro repetido, cadastro canônico, dado pessoal descartado | 1 |
| `dim_motivo` | os motivos do cadastro | um motivo | tipo, código, descrição, grupo | 1 |
| `dim_escopo_mercado` | o recorte do mercado de trabalho público | um território (UF ou município) e um grupo de atividade | território, UF ou município, grupo de atividade | 1 |
| `dim_evento_folha` | as rubricas da folha | um evento | código, descrição, tipo, incidências | 2 |
| `dim_curso` | os cursos e treinamentos | um curso | código, nome, tipo, carga horária, validade | 2 |
| `dim_usuario` | quem acessa o sistema, sem identidade | um usuário | chave do login, perfil vigente, filial, ativo | 2 |

- **`dim_data`:** tem vários papéis no mesmo fato (abertura e fechamento da vaga, admissão e rescisão); o feriado é o nacional, porque o municipal depende de onde o posto está.
- **`dim_filial`:** é a dimensão do isolamento por filial no warehouse (card 7.8).
- **`dim_contrato`:** carrega o status do sistema e a situação derivada das datas, lado a lado (COM-01).
- **`dim_posto`:** hierarquia natural cliente, contrato, posto; receita e custo se encontram aqui.
- **`dim_colaborador`:** sem nome, documento, chave de documento nem matrícula: a gold conta pessoas, não as identifica.
- **`dim_candidato`:** o cadastro repetido (ATS-01) aponta o canônico: quem lê escolhe contar cadastros ou pessoas.
- **`dim_motivo`:** um papel por fato: de desligamento, de reprovação, de perda de contrato, de fim de alocação, de ocorrência.
- **`dim_escopo_mercado`:** vem do Novo CAGED, não do cliente.

## 5. Dos indicadores aos fatos

Cada indicador da seção 3 do [Entendimento do Negócio](01_entendimento_negocio.md), o fato de onde sai e como se calcula. Um teste reprova a matriz se um indicador ficar sem fato.

| família | indicador | fato | como |
|---|---|---|---|
| Funil de colocação | vagas abertas, preenchidas e canceladas | `fato_vaga` | contagem por situação |
| Funil de colocação | fill rate | `fato_vaga` | posições preenchidas sobre posições abertas |
| Funil de colocação | time to fill por vaga, cliente e filial | `fato_vaga` | dias entre a abertura e o fechamento das vagas preenchidas |
| Funil de colocação | conversão de cada etapa | `fato_candidatura` | quem chegou à etapa seguinte sobre quem chegou à etapa |
| Funil de colocação | no-show de entrevista e de primeiro dia | `fato_candidatura` | faltou à entrevista; aprovada que não começou |
| Funil de colocação | fonte do candidato | `fato_candidatura` | conversão por fonte, pela `dim_candidato` |
| Funil de colocação | custo por contratação | `fato_candidatura` | custo médio da fonte somado nas candidaturas, sobre as admitidas |
| Carteira alocada | headcount alocado por cliente, posto e filial | `fato_posto_mes` | pessoas no fim do mês |
| Carteira alocada | entradas e saídas | `fato_posto_mes`, `fato_alocacao` | alocações que começam e terminam no mês |
| Carteira alocada | taxa de ocupação dos postos | `fato_posto_mes` | pessoa-dias alocados sobre posição-dias contratados |
| Carteira alocada | dias de posto descoberto | `fato_posto_mes` | posição-dias sem ninguém alocado |
| Carteira alocada | efetivações pelo cliente | `fato_alocacao` | alocações que terminaram em efetivação |
| Rotatividade e absenteísmo | turnover total, voluntário e involuntário | `fato_vinculo`, `fato_posto_mes` | desligamentos do mês, por tipo, sobre o headcount médio |
| Rotatividade e absenteísmo | turnover nos primeiros 90 dias | `fato_vinculo` | admitidos no mês que saíram em até 90 dias, sobre os admitidos |
| Rotatividade e absenteísmo | absenteísmo por posto | `fato_ponto_dia` | faltas e atestados sobre os dias previstos |
| Rotatividade e absenteísmo | horas extras e banco de horas | `fato_ponto_dia` | horas extras sobre horas trabalhadas; o saldo do banco de horas fica na silver até o painel pedir |
| Financeiro por unidade | faturamento por cliente, posto e filial | `fato_faturamento` | valor bruto por competência |
| Financeiro por unidade | custo por cabeça | `fato_custo_pessoal` | salário, encargos, provisões e benefícios sobre as pessoas do mês |
| Financeiro por unidade | margem por posto e por contrato | `fato_posto_mes` | receita menos custo de pessoal, no posto e no mês |
| Financeiro por unidade | inadimplência | `fato_recebimento` | valor vencido e não pago sobre o valor vencido |
| Financeiro por unidade | ticket médio de recrutamento e seleção | `fato_faturamento` | valor das faturas sem posto sobre a quantidade delas |
| Compliance e risco | vencimento do prazo legal do temporário | `fato_conformidade_mes`, `fato_vinculo` | temporários além do prazo e a 30 dias dele, mês a mês |
| Compliance e risco | ASO e exames vencidos | `fato_conformidade_mes` | pessoas alocadas com ASO vencido no fim do mês |
| Compliance e risco | treinamentos obrigatórios vencidos | `fato_conformidade_mes` | pessoas alocadas sem certificado válido de curso obrigatório |
| Compliance e risco | acidentes e CAT | `fato_saude_ocupacional` | acidentes por gravidade e CAT fora do prazo |
| Compliance e risco | reclamações por posto | `fato_ocorrencia` | ocorrências do tipo reclamação |

## 6. As sete afirmações dos donos

As afirmações da primeira reunião são o contrato da análise. Cada uma tem os fatos que a respondem; a resposta pode ser "confirma" ou "contradiz", e sai dos números, não da matriz.

| # | afirmação | quem | fatos | como se responde |
|---|---|---|---|---|
| D1 | "A gente cresceu muito de 2022 a 2025." | Romeu | `fato_resultado_mes`, `fato_posto_mes`, `fato_vaga` | a mesma série mensal em quatro medidas (receita, pessoas, clientes ativos, vagas): cresceu em quê, e até quando |
| D2 | "Não sei se tenho lucro ou prejuízo." | Romeu | `fato_posto_mes`, `fato_resultado_mes` | margem por posto, contrato, cliente e filial ao longo do arco, e o resultado do mês por filial |
| D3 | "Os clientes começaram a sair no fim de 2025." | Romeu | `fato_contrato`, `fato_ocorrencia` | a data de encerramento de cada contrato e a do primeiro aviso de rescisão: quando começou de fato, e em quais clientes |
| D4 | "A queda é do mercado." | Romeu | `fato_mercado_mes`, `fato_vaga`, `fato_vinculo`, `fato_ocorrencia`, `fato_contrato` | a série do mercado da região ao lado da série de qualidade (time to fill, turnover em 90 dias, reclamações) e da série de perda de contratos, com a defasagem medida em meses |
| D5 | "Contratar mais assistente resolveria." | Romeu | `fato_vaga`, `fato_candidatura`, `fato_vinculo` | os indicadores do funil antes e depois das contratações de 2026 |
| D6 | "Depois de 2022 os relatórios pararam de bater." | Sabrina | `fato_resultado_mes` | o informado e o apurado lado a lado, por mês e filial, com a diferença de cada par |
| A1 | "Cliente grande é sempre melhor." | Janaína | `fato_posto_mes`, `fato_recebimento` | margem e inadimplência pelo porte do cliente |

## 7. Decisões de modelagem

**1. A chave é o `id` da réplica.** Há uma fonte só, e as dimensões não guardam versões: o `id` do sistema do cliente já é estável e único. Chave substituta só onde não há `id` (a data, como AAAAMMDD, e o mês, como AAAAMM). Cada dimensão ganha a linha 0, "não se aplica", para o fato que não tem aquela dimensão (a fatura de recrutamento não tem posto).

**2. Dimensão guarda o estado atual; a história mora no fato.** O sistema do cliente não versiona o cadastro do cliente nem da função, então a dimensão é do tipo 1. O que tem vigência de verdade (o preço do posto, o piso salarial, o perfil do usuário) entra no fato como medida do período, que é onde a pergunta acontece.

**3. A gold conta pessoas e não as identifica.** As dimensões de pessoa não têm nome, documento, chave de documento nem matrícula. Os fatos de saúde (afastamento, exame, acidente) não têm dimensão de pessoa nenhuma: servem ao agregado por cliente, filial e função. É o que o `docs/05` promete.

**4. A marca de qualidade viaja com o fato.** A silver marcou e não corrigiu; a gold leva a marca como coluna do fato. Quem lê decide contar com ou sem a linha marcada, e o painel pode mostrar os dois números. A gold não apaga o que a silver marcou.

**5. A linha excluída fica na silver; a descartada entra.** A linha apagada no sistema do cliente não existe para o negócio e não vira fato. O candidato com dado pessoal descartado continua contando no funil, com os atributos de pessoa como "não informado".

**6. O ano do arquivo é o da data de negócio.** Na bronze e na silver o arquivo é do ano em que a linha foi criada no sistema. Na gold o fato é particionado pelo ano da data principal dele (a competência, a admissão, o dia trabalhado), que é o que a pergunta usa.

**7. Foto periódica vale no último dia do mês.** Headcount, ocupação e conformidade são estoque: a medida é a do último dia do mês. O mês corrente, incompleto, é medido na data de referência da carga e identificado como parcial.

**8. Dois níveis de prioridade.** Os fatos de prioridade 1 respondem às sete afirmações e aos indicadores em destaque do `docs/01`, e são construídos no card 7.2. Os de prioridade 2 completam os módulos do painel e entram depois, na ordem em que o painel pedir.

## 8. O que fica fora

- As batidas de ponto, uma a uma, e o saldo do banco de horas: ficam na silver, que já as tem conferidas.
- Dimensão com história (tipo 2): só faria sentido se o cliente passasse a versionar o cadastro, o que o sistema dele não faz.
- Indicador pré-calculado por tela: a gold entrega fatos e dimensões; a conta de cada indicador é do SQL analítico (card 7.3) e do painel.
- Previsão e modelo: risco de desistência, projeção de receita. São da trilha prevista (P.3), depois do painel.

Fontes que ainda não estão no lake e entram no card 7.2, com esquema:

- `fontes.caged_movimentacao`: movimentação mensal do Novo CAGED (hoje em `dados/publicos/caged/movimentacao_mensal.csv`).

---

[Início](#topo)
