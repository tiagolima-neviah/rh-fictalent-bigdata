<a id="topo"></a>

# Entendimento dos Dados · o banco relacional da Fictalent

<!-- nav:start -->
[Home](../README.md) | [← Entendimento do Negócio](01_entendimento_negocio.md) | [Arquitetura →](03_arquitetura.md)
<!-- nav:end -->

> O banco deste projeto foi desenhado como **o sistema que a Fictalent não tem**: um único banco relacional normalizado que cobre o que hoje mora em quatro lugares desconectados (recrutamento, folha, financeiro e planilhas). Ele existe para servir hoje ao BI e amanhã a um sistema com telas. Este documento explica o que cada módulo guarda e por quê; o detalhe coluna a coluna entra no Modelo de Dados (`docs/04`, versão v0.2.0).

## 1. Visão geral

O banco é organizado em **10 módulos**, um por schema do Postgres. A escolha não é estética: **os módulos são o vocabulário do negócio**, são as fronteiras de responsabilidade dentro da empresa (cada coordenadora é dona de um pedaço) e, mais adiante, serão o **menu do painel**. Quem entende os dez módulos entende a empresa.

| # | schema | o que guarda | quem é dono na empresa |
|---|---|---|---|
| 1 | `cadastro` | filiais, centros de custo, funções, convenções coletivas, calendário, catálogos de motivo | retaguarda |
| 2 | `comercial` | clientes, contratos, postos contratados, tabela de preço, SLA, aditivos | Romeu e a coordenação comercial |
| 3 | `ats` | requisições, vagas, candidatos, funil, entrevistas, encaminhamentos | coordenadora de R&S |
| 4 | `pessoas` | colaboradores, contratos de trabalho, alocações, afastamentos, desligamentos | coordenadora de administração de pessoal |
| 5 | `ponto` | apontamento diário, faltas, horas extras, banco de horas, escalas | coordenadora de administração de pessoal |
| 6 | `folha` | eventos de folha, provisões, benefícios, rateio por centro de custo | retaguarda |
| 7 | `financeiro` | faturamento, contas a receber e a pagar, impostos, inadimplência | Romeu |
| 8 | `treinamento` | cursos, turmas, participantes, certificados e validade | coordenadora de treinamentos |
| 9 | `sst` | ASO e exames, programas legais, acidentes, CAT | SST |
| 10 | `seguranca` | usuários, perfis, permissões por módulo e filial, log de auditoria | TI |

**Três decisões de modelagem que atravessam o banco inteiro:**

**A pessoa aparece em dois papéis, e eles são tabelas diferentes.** No `ats` existe o **candidato**, alguém que se inscreveu em uma ou mais vagas e pode nunca ter sido contratado. Em `pessoas` existe o **colaborador**, que é o candidato depois de admitido. A ligação entre os dois é explícita, e é ela que permite responder quanto custa converter um candidato em uma pessoa alocada. Separar os dois papéis também é o que torna honesta a contagem de funil: candidato que aparece em cinco vagas é uma pessoa e cinco candidaturas.

**O posto é a unidade de receita, não a pessoa.** O cliente contrata **postos** (por exemplo, doze auxiliares de produção no turno da noite em Extrema), e é o posto que tem preço, SLA e margem. A pessoa ocupa o posto por um período. Quando ela sai e outra entra, o posto continua o mesmo, e a receita nunca deixou de existir; quando ninguém ocupa, existe **posto descoberto**, que é receita que não entra. Modelar assim é o que permite medir ocupação, que é o indicador que a empresa não tem hoje.

**Toda relação que muda no tempo tem período, não estado.** Alocação, preço, contrato de trabalho, convenção coletiva e regime tributário são vigências com início e fim. É o que permite reconstruir a foto de qualquer dia do passado, e sem isso o backfill desde 2018 não faria sentido.

## 2. `cadastro`: as regras do jogo

As tabelas que quase não mudam e que todo o resto referencia. **Filial** (matriz em Atibaia, filiais em Bragança Paulista e Extrema) e **centro de custo**, que é como o financeiro divide o resultado (um por filial, um para a retaguarda e um para cada contrato grande). A geografia (município, UF, região) usada por cliente, posto e colaborador.

A **função** é o cargo operacional que a Fictalent coloca em campo (auxiliar de produção, operador de empilhadeira, conferente, repositor, auxiliar de limpeza), ligada ao código da CBO e a uma faixa salarial. A **convenção coletiva** guarda o sindicato, a data-base e o piso por função e município, e é ela que explica por que o mesmo cargo custa diferente em Extrema e em Atibaia.

O **calendário** e os **feriados** existem porque quase todo indicador desta empresa é medido em dias úteis: tempo para preencher uma vaga, dias de posto descoberto, apontamento de ponto. Os **catálogos de motivo** (desligamento, reprovação em etapa, cancelamento de vaga, perda de contrato) são o que transforma "o cliente saiu" em uma causa analisável.

## 3. `comercial`: a carteira que gera receita

O **cliente** é a empresa tomadora, com porte, setor e a data em que virou cliente. O **contrato** liga cliente e tipo de serviço com vigência, e é onde ficam as condições comerciais: prazo de pagamento, índice de reajuste, garantia de reposição. Os **aditivos** registram prorrogações, mudanças de escopo e reajustes, cada um com sua data, porque a linha do tempo do contrato é parte da história.

O **posto contratado** é o coração: contrato, função, quantidade de vagas, turno, local de trabalho e vigência. A **tabela de preço** dá o valor faturado por posto por mês (ou por hora, conforme o contrato) com vigência própria, e é comparada ao custo por cabeça para produzir a **margem por posto**, que é a resposta da declaração D2.

O **SLA acordado** guarda, por contrato, as metas que o cliente cobra: prazo para preencher uma vaga, prazo para repor uma falta, percentual máximo de absenteísmo. Ter isso no banco é o que permite dizer se um cliente saiu porque o mercado caiu ou porque a Fictalent parou de cumprir o que prometeu.

## 4. `ats`: o funil de colocação

A **requisição** é o pedido do cliente; a **vaga** é o que a Fictalent abre a partir dela (uma requisição de doze pessoas pode virar uma vaga com doze posições). O **candidato** tem documentos, fonte (indicação, portal, redes, banco interno) e histórico.

A **candidatura** liga candidato e vaga, e é a linha do funil. Cada passagem de etapa (triagem, entrevista interna, encaminhamento, entrevista do cliente, aprovação ou reprovação) é registrada com data e, quando negativa, com motivo. Dessa cadeia saem quase todos os indicadores comerciais: conversão de cada etapa, tempo para preencher, taxa de aproveitamento por fonte e os dois **no-show** que mais doem, o da entrevista e o do primeiro dia de trabalho.

## 5. `pessoas`: quem foi admitido e onde está alocado

O **colaborador** é a pessoa admitida, com seus documentos e o vínculo ao candidato que ele foi. O **contrato de trabalho** carrega o tipo (temporário, efetivo ou terceirizado), as datas e, no caso do temporário, o **prazo legal**: até 180 dias, prorrogáveis por mais 90, com a prorrogação registrada como um aditivo próprio. Um contrato temporário que passa do prazo sem aditivo é uma irregularidade, e este banco consegue mostrá-la.

A **alocação** liga colaborador e posto por um período. É a tabela mais importante do banco: é dela que sai o headcount alocado de qualquer dia, a ocupação dos postos, os dias descobertos e o custo que vai para cada contrato. **Afastamentos** (atestado, acidente, licença) e **desligamento** com motivo e tipo (voluntário, involuntário, fim de contrato, efetivação pelo cliente) fecham o ciclo de vida.

## 6. `ponto`: o dia a dia de quem está em campo

Um registro por colaborador e por dia, com as horas trabalhadas, as ocorrências (falta justificada ou não, atraso, atestado) e as horas extras, submetidas a uma **escala** (5x2, 6x1, 12x36). É a tabela mais volumosa do banco, porque multiplica mil pessoas por vinte e dois dias por oito anos, e é a origem de dois indicadores caros: **absenteísmo por posto**, que o cliente sente, e **horas extras**, que a Fictalent paga.

## 7. `folha`: o custo por cabeça

O que a Fictalent gasta com cada pessoa, competência a competência. Os **eventos de folha** são o catálogo (salário, adicional noturno, hora extra, DSR, INSS, FGTS, vale transporte, vale refeição), e cada linha da folha é um colaborador, um evento e um valor. As **provisões** de 13º e férias são calculadas mês a mês, e importam mais do que parece: elas apertam a margem exatamente no mês de maior receita.

O **rateio por centro de custo** é o que leva o custo de cada pessoa até o contrato onde ela trabalha. Sem ele existe custo total e não existe margem por cliente, que é justamente a pergunta que ninguém sabe responder.

## 8. `financeiro`: receita, títulos e impostos

O **faturamento** é gerado por contrato e competência, com uma linha por posto (a medição do mês: dias trabalhados, faltas descontadas, horas extras repassadas). Cada fatura vira um **título a receber** com vencimento, e cada recebimento é registrado, o que produz inadimplência e prazo médio de recebimento.

Do outro lado, os **títulos a pagar**: folha, encargos, benefícios, fornecedores de exames e de treinamento. Os **impostos** são apurados por competência conforme o regime tributário vigente (ISS por município, PIS, COFINS, IRPJ e CSLL), e ficam numa tabela própria porque a alíquota muda com o município e com o tempo.

Este módulo é o que permite responder a declaração A1 da Janaína, "cliente grande é sempre melhor": o cliente grande costuma ter preço menor por posto e prazo de pagamento maior, e às vezes rende menos que o cliente médio.

## 9. `treinamento` e `sst`: obrigação legal com data de validade

**Treinamento** guarda cursos, turmas, participantes e certificados, com validade. **SST** guarda os exames (ASO admissional, periódico, de mudança de função e demissional), os programas legais por cliente e posto (PGR, PCMSO, LTCAT), os acidentes e as CAT emitidas.

Os dois módulos têm a mesma natureza: são **documentos com prazo**, e o valor deles no BI é o alerta. Colaborador alocado com ASO vencido é risco jurídico imediato para a Fictalent e para o cliente, e é o tipo de coisa que uma planilha não avisa.

## 10. `seguranca`: quem pode ver o quê

Usuários, perfis (sócio, gerente-geral, coordenadora, assistente, financeiro), permissão por módulo e por filial, e log de auditoria. Não há telas neste projeto, então o módulo existe **modelado e populado**, não usado: ele é a fundação do sistema transacional futuro e, desde já, serve de exemplo de como o autoatendimento em três níveis se sustenta tecnicamente (a assistente vê a filial dela, a coordenadora vê o setor, os sócios veem tudo).

## 11. O que esperar da qualidade destes dados

Este banco **não é limpo**, e isso é deliberado. Ele reproduz a sujeira que aparece em qualquer operação real que cresceu depressa, e cada defeito existe para ser encontrado na auditoria de qualidade e tratado na camada silver, com prestação de contas. O que já se sabe que existe:

- **candidatos duplicados**: a mesma pessoa cadastrada mais de uma vez, com grafias diferentes do nome e às vezes documentos divergentes, porque o cadastro foi feito às pressas em picos de volume;
- **documentos inválidos**: CPF com dígito verificador errado, data de nascimento impossível;
- **datas retroativas**: admissões lançadas depois do fato, com data anterior à do próprio cadastro;
- **contratos temporários fora do prazo legal**: passaram de 180 ou 270 dias sem aditivo registrado;
- **ASO vencido com pessoa alocada**: o exame expirou e ninguém foi avisado;
- **o consolidado da Sabrina**: uma tabela de fechamento mensal, alimentada a partir das planilhas dela, que **diverge da operação a partir de 2022** e cuja divergência cresce com o volume. É a declaração D6 dela virando dado, e o achado mais importante deste projeto: quando dois números discordam, é preciso decidir qual é a fonte da verdade, e essa decisão é do dono do processo, não do analista.

Nenhum desses defeitos é corrigido no banco de origem. Eles são **detectados, medidos e documentados** na auditoria, e tratados na silver segundo regras aprovadas, do mesmo jeito que se faz num cliente real.

---

[Início](#topo) | [Arquitetura →](03_arquitetura.md)
