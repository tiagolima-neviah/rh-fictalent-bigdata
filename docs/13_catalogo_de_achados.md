<a id="topo"></a>

# Catálogo de achados · o que a auditoria achou e o que a silver vai fazer

<!-- nav:start -->
[Home](../README.md) | [Auditoria (notebooks)](../notebooks/auditoria/README.md) | [← Ingestão](11_ingestao.md) | [Bibliografia →](bibliografia.md)
<!-- nav:end -->

> **Arquivo gerado** por `python -m rh_fictalent.auditoria --catalogo` a partir de `src/rh_fictalent/auditoria/catalogo.py` (as entradas, com as duas redações e a regra proposta) e de `dados/auditoria/*.json` (os achados que os notebooks gravaram, com linhas, total e fração). Não edite à mão: mude a entrada ou refaça a auditoria e gere de novo. O catálogo é a decisão sobre cada achado: o notebook descobre, o catálogo decide, a silver executa. Toda entrada nasce como **proposta**; a silver só implementa o que estiver **aprovado**, e a aprovação é registrada na própria entrada (`situacao`), com data no log de decisões do projeto.

Estado: **40 achados com severidade** (4 altos, 17 médios, 19 baixos) e **21 registros que dizem o que não se trata**; situação das entradas: 40 proposta.

## 1. Os cinco verbos, e o que a silver nunca faz

Cada achado recebe um tratamento, e há só cinco. **Marcar**: a linha ganha uma coluna booleana `q_<codigo>` e nada muda no valor; é o tratamento padrão, porque a prova de que algo foi tratado é poder achá-lo depois. **Derivar**: a silver calcula uma coluna nova a partir das datas ou das partes (a situação de um contrato a partir das vigências, os dias além de um prazo) e preserva a coluna original. **Conformar**: o valor ganha forma canônica (a grafia de um nome) e o original fica em `<coluna>_original`. **Manter**: nada na silver; o achado vira indicador na gold ou alerta no painel. **Pedir**: a regra depende de uma resposta do cliente (qual convenção, qual definição, se é ou não a mesma pessoa); até a resposta, marcar.

O que a silver **nunca** faz, por decisão de método: não funde cadastro (a autoridade sobre o cadastro é do cliente; duplicidade se marca e se agrupa); não preenche ausência (inventar valor cria dado que ninguém coletou e apaga o achado); não apaga linha (a bronze é espelho e a silver conforma no mesmo grão); não corrige valor na origem (a correção é do cliente, e a coluna `origem` de cada entrada diz quando ela é necessária). Toda regra é idempotente: reprocessar a carga dá o mesmo resultado.

## 2. As seis declarações do cliente

O [`docs/02`](02_entendimento_dados.md), seção 11, lista o que o cliente já sabia que existia. A auditoria testou cada uma como hipótese, sem consultar a resposta, e as seis se confirmaram. A tabela lê os registros.

| declaração | achados que a testaram | veredito |
|---|---|---|
| ASO vencido com pessoa alocada: o exame expirou e ninguém foi avisado | TSS-01 | **confirmada** |
| candidatos duplicados: a mesma pessoa cadastrada mais de uma vez, com grafias diferentes do nome e às vezes documentos divergentes | ATS-01, ATS-02 | **confirmada** |
| contratos temporários fora do prazo legal: passaram de 180 ou 270 dias sem aditivo registrado | PES-01 | **confirmada** |
| datas retroativas: admissões lançadas depois do fato, com data anterior à do próprio cadastro | PES-02 | **confirmada** |
| documentos inválidos: CPF com dígito verificador errado, data de nascimento impossível | ATS-03, ATS-04 | **confirmada** |
| o consolidado da gerência diverge da operação a partir de 2022 e a divergência cresce com o volume | FIN-01, FIN-02 | **confirmada** |

## 3. Os achados, por severidade

### Severidade alta

| código | achado | tabela | linhas atingidas | tratamento | situação |
|---|---|---|---|---|---|
| [FIN-01](#fin-01) | O consolidado da gerência deixou de bater com a operação | `financeiro.consolidado_gerencial` | 158 de 237 (66,67%) | manter | proposta |
| [ATS-01](#ats-01) | A mesma pessoa cadastrada mais de uma vez | `ats.candidato` | 2.735 de 60.294 (4,54%) | marcar | proposta |
| [TSS-01](#tss-01) | Pessoa em campo com ASO vencido | `sst.aso` | 25 de 858 (2,91%) | derivar | proposta |
| [PES-01](#pes-01) | Temporário além do prazo legal | `pessoas.contrato_trabalho` | 263 de 15.064 (1,75%) | derivar | proposta |

### Severidade média

| código | achado | tabela | linhas atingidas | tratamento | situação |
|---|---|---|---|---|---|
| [FIN-02](#fin-02) | Headcount e vagas do consolidado sem definição | `financeiro.consolidado_gerencial` | 220 de 237 (92,83%) | pedir | proposta |
| [FOL-01](#fol-01) | O rateio não fecha com a folha | `folha.rateio_custo` | 39.104 de 63.445 (61,63%) | pedir | proposta |
| [TSS-03](#tss-03) | CAT fora do prazo | `sst.cat` | 48 de 99 (48,48%) | derivar | proposta |
| [CAD-01](#cad-01) | Funções sem o código de ocupação | `cadastro.funcao` | 17 de 45 (37,78%) | pedir | proposta |
| [TSS-04](#tss-04) | Programa legal vencido em contrato ativo | `sst.programa_sst` | 5 de 41 (12,20%) | derivar | proposta |
| [PES-02](#pes-02) | Admissão lançada depois do fato | `pessoas.contrato_trabalho` | 1.621 de 16.992 (9,54%) | derivar | proposta |
| [PES-03](#pes-03) | Temporário sem data prevista de término | `pessoas.contrato_trabalho` | 1.281 de 15.064 (8,50%) | derivar | proposta |
| [SEG-01](#seg-01) | Ação sem permissão vigente | `seguranca.log_auditoria` | 4.092 de 111.406 (3,67%) | marcar | proposta |
| [PON-01](#pon-01) | A batida que falta | `ponto.marcacao` | 26.900 de 1.080.569 (2,49%) | marcar | proposta |
| [ATS-05](#ats-05) | Nome escrito de vários jeitos | `ats.candidato` | 1.333 de 60.294 (2,21%) | conformar | proposta |
| [FIN-03](#fin-03) | Fatura depois do fim do contrato | `financeiro.fatura` | 42 de 3.459 (1,21%) | marcar | proposta |
| [TSS-02](#tss-02) | Admissional depois da admissão | `sst.aso` | 155 de 16.992 (0,91%) | derivar | proposta |
| [COM-01](#com-01) | Contrato vencido que continua ativo | `comercial.contrato` | 1 de 128 (0,78%) | derivar | proposta |
| [ATS-03](#ats-03) | CPF inválido | `ats.candidato` | 457 de 59.999 (0,76%) | marcar | proposta |
| [ATS-02](#ats-02) | Mesmo nome e nascimento, CPFs diferentes | `ats.candidato` | 181 de 60.294 (0,30%) | pedir | proposta |
| [PON-02](#pon-02) | A batida repetida | `ponto.marcacao` | 12.736 de 4.300.719 (0,30%) | marcar | proposta |
| [ATS-04](#ats-04) | Data de nascimento impossível | `ats.candidato` | 94 de 60.294 (0,16%) | marcar | proposta |

### Severidade baixa

| código | achado | tabela | linhas atingidas | tratamento | situação |
|---|---|---|---|---|---|
| [ATS-07](#ats-07) | Telefone que não identifica a pessoa | `ats.candidato` | 60.294 de 60.294 (100,00%) | manter | proposta |
| [CAD-02](#cad-02) | Complemento de endereço que ninguém preenche | `cadastro.endereco` | 15.721 de 15.721 (100,00%) | manter | proposta |
| [SEG-02](#seg-02) | Usuário sem colaborador | `seguranca.usuario` | 40 de 40 (100,00%) | manter | proposta |
| [TSS-05](#tss-05) | Turmas que podem ser a mesma turma | `treinamento.turma` | 192 de 5.411 (3,55%) | pedir | proposta |
| [PES-04](#pes-04) | Afastamentos sobrepostos | `pessoas.afastamento` | 37 de 1.058 (3,50%) | marcar | proposta |
| [COM-02](#com-02) | Postos que podem ser o mesmo posto | `comercial.posto` | 8 de 694 (1,15%) | pedir | proposta |
| [FIN-05](#fin-05) | Valor pago diferente do título | `financeiro.titulo_receber` | 37 de 3.459 (1,07%) | derivar | proposta |
| [TSS-06](#tss-06) | Curso obrigatório sem certificado válido | `treinamento.certificado` | 17 de 1.763 (0,96%) | derivar | proposta |
| [ATS-08](#ats-08) | Experiência antes dos 14 anos | `ats.candidato_experiencia` | 667 de 71.668 (0,93%) | marcar | proposta |
| [PON-03](#pon-03) | Horas noturnas acima das trabalhadas | `ponto.apontamento` | 6.269 de 1.166.361 (0,54%) | pedir | proposta |
| [ATS-06](#ats-06) | Candidato sem CPF | `ats.candidato` | 295 de 60.294 (0,49%) | marcar | proposta |
| [FIN-04](#fin-04) | Título vencido que continua aberto | `financeiro.titulo_receber` | 5 de 3.459 (0,14%) | derivar | proposta |
| [FIN-06](#fin-06) | Alocação sem faturamento | `financeiro.fatura_item` | 4 de 4.678 (0,09%) | marcar | proposta |
| [COM-03](#com-03) | Reclamação depois do fim do contrato | `comercial.contrato_ocorrencia` | 1 de 1.321 (0,08%) | marcar | proposta |
| [PON-04](#pon-04) | A batida solta | `ponto.marcacao` | 292 de 1.080.569 (0,03%) | marcar | proposta |
| [FIN-07](#fin-07) | Item de fatura que não fecha | `financeiro.fatura_item` | 1 de 9.116 (0,01%) | marcar | proposta |
| [FOL-02](#fol-02) | Provisão que não encadeia | `folha.provisao` | 9 de 146.926 (0,01%) | marcar | proposta |
| [FOL-03](#fol-03) | Rateio zerado | `folha.rateio_custo` | 7 de 63.470 (0,01%) | marcar | proposta |
| [SEG-03](#seg-03) | Último acesso desatualizado | `seguranca.log_auditoria` | 9 de 146.520 (0,01%) | manter | proposta |

## 4. Os achados, um a um

Cada entrada tem as duas redações: a primeira para quem decide, a segunda para quem implementa. A evidência aponta o notebook e a seção em que o achado foi medido.

### cadastro

<a id="cad-01"></a>

#### CAD-01 · Funções sem o código de ocupação

**Severidade:** média · **Onde:** `cadastro.funcao` (`cbo`) · **Linhas atingidas:** 17 de 45 (37,78%) · **Evidência:** [`00_cadastro`](../notebooks/auditoria/00_cadastro.ipynb), seção 4

**Para quem decide:** O CBO é o código que o eSocial exige e o que liga cada função da Fictalent às estatísticas públicas de emprego. Sem ele, mais de um terço das funções, líderes e analistas entre elas, fica fora de qualquer comparação por ocupação.

**Para quem implementa:** `cadastro.funcao.cbo` nulo em 17 de 45 funções (37,78%), espalhadas por todas as famílias e níveis. Não há regra que derive o CBO do nome da função sem inventar.

**Regra proposta (pedir):** marcar `q_cad_01` nas funções sem CBO; não preencher; quando o cliente enviar os códigos, eles entram pela réplica, não pela silver.

**Correção na origem:** sim: informar o CBO das funções sem código no cadastro do sistema. **Situação:** proposta.

<a id="cad-02"></a>

#### CAD-02 · Complemento de endereço que ninguém preenche

**Severidade:** baixa · **Onde:** `cadastro.endereco` (`complemento`) · **Linhas atingidas:** 15.721 de 15.721 (100,00%) · **Evidência:** [`00_cadastro`](../notebooks/auditoria/00_cadastro.ipynb), seção 4

**Para quem decide:** A coluna existe e não informa nada. Um relatório que a mostre exibe vazio em toda linha e parece defeito; um cadastro que a exija trava.

**Para quem implementa:** `cadastro.endereco.complemento` nulo em 15.721 de 15.721 endereços (100,00%). Não é falha de linha, é coluna não coletada.

**Regra proposta (manter):** a silver mantém a coluna como está e a documenta como não coletada; o modelo dimensional não a leva até que passe a ser preenchida.

**Correção na origem:** não. **Situação:** proposta.

### comercial

<a id="com-01"></a>

#### COM-01 · Contrato vencido que continua ativo

**Severidade:** média · **Onde:** `comercial.contrato` (`status, vigencia_fim`) · **Linhas atingidas:** 1 de 128 (0,78%) · **Evidência:** [`01_comercial`](../notebooks/auditoria/01_comercial.ipynb), seção 10

**Para quem decide:** Um contrato vencido que segue como ativo conta o cliente como ativo, mantém o SLA em cobrança e faz a carteira parecer maior. É um caso hoje; sem regra, vira um por semana.

**Para quem implementa:** `comercial.contrato` com `status = 'ATIVO'`, `vigencia_fim` anterior à data de referência e nenhum aditivo de prorrogação com `vigencia_nova` que a cubra: 1 de 128 contratos (0,78%). O comentário da DDL diz que status e vigência convivem e que a auditoria confere se batem.

**Regra proposta (derivar):** a silver deriva `situacao_derivada` (vigente, vencido, encerrado) das datas e dos aditivos, preserva `status` e marca `q_com_01` onde os dois discordam.

**Correção na origem:** sim: encerrar ou prorrogar o contrato vencido no sistema. **Situação:** proposta.

<a id="com-02"></a>

#### COM-02 · Postos que podem ser o mesmo posto

**Severidade:** baixa · **Onde:** `comercial.posto` (`contrato_id, funcao_id, turno, endereco_id, vigencia_inicio`) · **Linhas atingidas:** 8 de 694 (1,15%) · **Evidência:** [`01_comercial`](../notebooks/auditoria/01_comercial.ipynb), seção 5

**Para quem decide:** Se o par for o mesmo posto cadastrado duas vezes, as vagas contam em dobro no headcount contratado e o preço se aplica duas vezes. Se for desdobramento legítimo, não há nada a fazer. Só o comercial sabe.

**Para quem implementa:** `comercial.posto` sem chave natural na DDL: 8 de 694 postos (1,15%) em pares idênticos em `contrato_id`, `funcao_id`, `turno`, `endereco_id` e `vigencia_inicio`.

**Regra proposta (pedir):** marcar `q_com_02` nos dois postos de cada par; nunca fundir.

**Correção na origem:** sim: confirmar, par a par, se são postos distintos ou duplicidade. **Situação:** proposta.

<a id="com-03"></a>

#### COM-03 · Reclamação depois do fim do contrato

**Severidade:** baixa · **Onde:** `comercial.contrato_ocorrencia` (`dt_ocorrencia`) · **Linhas atingidas:** 1 de 1.321 (0,08%) · **Evidência:** [`01_comercial`](../notebooks/auditoria/01_comercial.ipynb), seção 8

**Para quem decide:** Uma reclamação lançada depois do encerramento é plausível (reclamação tardia), mas qualquer indicador de SLA por contrato vigente a perde ou a atribui a um período sem receita.

**Para quem implementa:** `comercial.contrato_ocorrencia.dt_ocorrencia` posterior a `contrato.dt_encerramento`: 1 de 1.321 ocorrências.

**Regra proposta (marcar):** marcar `q_com_03`; o indicador de SLA da gold considera a ocorrência no último mês vigente do contrato.

**Correção na origem:** não. **Situação:** proposta.

### ats

<a id="ats-01"></a>

#### ATS-01 · A mesma pessoa cadastrada mais de uma vez

**Severidade:** alta · **Onde:** `ats.candidato` (`cpf, nome`) · **Linhas atingidas:** 2.735 de 60.294 (4,54%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 5 · **Declaração do cliente:** candidatos duplicados: a mesma pessoa cadastrada mais de uma vez, com grafias diferentes do nome e às vezes documentos divergentes

**Para quem decide:** A base de talentos parece maior do que é, o histórico da pessoa fica dividido (a reprovação de ontem não aparece na candidatura de hoje), a conversão por fonte sai errada e a mesma pessoa conta mais de uma vez no funil. É o defeito mais caro do funil, e o cliente já o conhecia.

**Para quem implementa:** `ats.candidato.cpf` sem `UNIQUE` de propósito: 2.735 de 60.294 cadastros (4,54%) compartilham o CPF com outro cadastro, sempre com o nome em outra grafia (caixa alta, inicial abreviada, sobrenome omitido) e nunca com nascimento divergente.

**Regra proposta (marcar):** a silver marca `q_ats_01`, atribui `grupo_pessoa` (o CPF) a todos os cadastros do grupo e elege o cadastro canônico (o mais antigo com CPF válido) em `cadastro_canonico`; nunca funde.

**Correção na origem:** sim: a tela de cadastro passa a buscar por CPF antes de criar; os grupos existentes são unificados por quem tem autoridade sobre o cadastro. **Situação:** proposta.

<a id="ats-02"></a>

#### ATS-02 · Mesmo nome e nascimento, CPFs diferentes

**Severidade:** média · **Onde:** `ats.candidato` (`nome, dt_nascimento, cpf`) · **Linhas atingidas:** 181 de 60.294 (0,30%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 5 · **Declaração do cliente:** candidatos duplicados: a mesma pessoa cadastrada mais de uma vez, com grafias diferentes do nome e às vezes documentos divergentes

**Para quem decide:** Ou é a mesma pessoa com um CPF digitado errado, ou são dois homônimos nascidos no mesmo dia. Fundir seria errado no segundo caso; ignorar, no primeiro.

**Para quem implementa:** 181 de 60.294 cadastros (0,30%) em pares com `nome` (normalizado) e `dt_nascimento` iguais e `cpf` diferente entre si.

**Regra proposta (pedir):** marcar `q_ats_02` como duplicidade provável, sem grupo; a conferência é do cliente.

**Correção na origem:** sim: conferir cada par com documento em mãos. **Situação:** proposta.

<a id="ats-03"></a>

#### ATS-03 · CPF inválido

**Severidade:** média · **Onde:** `ats.candidato` (`cpf`) · **Linhas atingidas:** 457 de 59.999 (0,76%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 7 · **Declaração do cliente:** documentos inválidos: CPF com dígito verificador errado, data de nascimento impossível

**Para quem decide:** A admissão é rejeitada pelo eSocial e a deduplicação por documento falha. Todos os casos estão no cadastro de candidato: a admissão barra o que o cadastro deixou passar.

**Para quem implementa:** `ats.candidato.cpf` reprovado nos dois dígitos verificadores (ou sequência repetida): 457 de 59.999 cadastros com CPF (0,76%).

**Regra proposta (marcar):** marcar `q_ats_03`; o valor fica como está (é evidência), e o CPF marcado não participa de `grupo_pessoa`.

**Correção na origem:** sim: validar o dígito na tela de cadastro; corrigir os existentes. **Situação:** proposta.

<a id="ats-04"></a>

#### ATS-04 · Data de nascimento impossível

**Severidade:** média · **Onde:** `ats.candidato` (`dt_nascimento`) · **Linhas atingidas:** 94 de 60.294 (0,16%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 7 · **Declaração do cliente:** documentos inválidos: CPF com dígito verificador errado, data de nascimento impossível

**Para quem decide:** Distorce a faixa etária de qualquer análise e barra a admissão. São menores de 14 anos no cadastro (o mais novo nasceu em 2024) e pessoas nascidas antes de 1930.

**Para quem implementa:** `ats.candidato.dt_nascimento` com idade menor que 14 anos em `dt_cadastro` ou anterior a 1930: 94 de 60.294 cadastros (0,16%).

**Regra proposta (marcar):** marcar `q_ats_04`; o valor fica; a gold trata a idade como desconhecida onde a marca é verdadeira.

**Correção na origem:** sim: validar a faixa de nascimento na tela; corrigir os existentes. **Situação:** proposta.

<a id="ats-05"></a>

#### ATS-05 · Nome escrito de vários jeitos

**Severidade:** média · **Onde:** `ats.candidato` (`nome`) · **Linhas atingidas:** 1.333 de 60.294 (2,21%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 7

**Para quem decide:** É o mecanismo da duplicidade: o cadastro repetido entra com o nome escrito de outro jeito e passa por qualquer busca. Também é rótulo de painel e de relatório.

**Para quem implementa:** `ats.candidato.nome` em caixa alta integral ou com inicial abreviada no meio (`Wellington M. Fernandes`): 1.333 de 60.294 cadastros (2,21%); centenas de formas normalizadas existem em mais de uma grafia.

**Regra proposta (conformar):** a silver grava `nome_conformado` (caixa de título, espaços normalizados, sem abreviar o que não dá para expandir) e mantém `nome` como veio; a busca e o rótulo usam o conformado.

**Correção na origem:** sim: a tela de cadastro padroniza a caixa ao salvar. **Situação:** proposta.

<a id="ats-06"></a>

#### ATS-06 · Candidato sem CPF

**Severidade:** baixa · **Onde:** `ats.candidato` (`cpf`) · **Linhas atingidas:** 295 de 60.294 (0,49%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 4

**Para quem decide:** Sem documento não há deduplicação por CPF nem admissão sem retrabalho. É pequeno, e o cliente completa na admissão.

**Para quem implementa:** `ats.candidato.cpf` nulo em 295 de 60.294 cadastros (0,49%).

**Regra proposta (marcar):** marcar `q_ats_06`; o cadastro sem CPF entra em `grupo_pessoa` só por nome e nascimento.

**Correção na origem:** sim: completar o CPF na admissão. **Situação:** proposta.

<a id="ats-07"></a>

#### ATS-07 · Telefone que não identifica a pessoa

**Severidade:** baixa · **Onde:** `ats.candidato` (`telefone`) · **Linhas atingidas:** 60.294 de 60.294 (100,00%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 5

**Para quem decide:** O telefone se repete entre cadastros numa escala que o torna inútil como contato confiável e como chave de deduplicação; parece campo preenchido com número de recado ou de terceiro.

**Para quem implementa:** `ats.candidato.telefone`: cerca de dez mil números distintos para 60.294 cadastros; 60.294 linhas em grupos repetidos (100,00%).

**Regra proposta (manter):** a silver não usa o telefone como chave nem como contato; documenta o achado.

**Correção na origem:** sim: avaliar como o campo é preenchido no cadastro. **Situação:** proposta.

<a id="ats-08"></a>

#### ATS-08 · Experiência antes dos 14 anos

**Severidade:** baixa · **Onde:** `ats.candidato_experiencia` (`dt_inicio`) · **Linhas atingidas:** 667 de 71.668 (0,93%) · **Evidência:** [`02_ats`](../notebooks/auditoria/02_ats.ipynb), seção 10

**Para quem decide:** Contamina qualquer análise de senioridade; ou a data da experiência ou o nascimento está errado.

**Para quem implementa:** `ats.candidato_experiencia.dt_inicio` anterior aos 14 anos de `candidato.dt_nascimento`: 667 de 71.668 experiências (0,93%).

**Regra proposta (marcar):** marcar `q_ats_08`; a gold não conta a experiência marcada na senioridade.

**Correção na origem:** sim: conferir a data da experiência ou o nascimento. **Situação:** proposta.

### pessoas

<a id="pes-01"></a>

#### PES-01 · Temporário além do prazo legal

**Severidade:** alta · **Onde:** `pessoas.contrato_trabalho` (`dt_admissao, dt_rescisao, prazo_legal_dias`) · **Linhas atingidas:** 263 de 15.064 (1,75%) · **Evidência:** [`03_pessoas`](../notebooks/auditoria/03_pessoas.ipynb), seção 10 · **Declaração do cliente:** contratos temporários fora do prazo legal: passaram de 180 ou 270 dias sem aditivo registrado

**Para quem decide:** Contrato temporário além de 180 dias sem aditivo é irregularidade trabalhista, com multa e risco de vínculo. Parte dos casos ainda está ativa, e a concentração em 2025 e 2026 diz que o controle se perdeu com o crescimento. É o achado de maior consequência jurídica do banco.

**Para quem implementa:** `pessoas.contrato_trabalho` com `tipo = 'TEMPORARIO'` e duração (rescisão, ou a data de referência se ativo) acima de 180 dias sem linha em `contrato_trabalho_prorrogacao`: 263 de 15.064 temporários (1,75%); parte deles acima de 270 dias no total.

**Regra proposta (derivar):** a silver deriva `dias_de_vinculo` e `dias_alem_do_prazo` (considerando prorrogações), marca `q_pes_01` e o alerta vai para o painel; o dado não muda.

**Correção na origem:** sim: regularizar os contratos ativos (prorrogação ou encerramento) e criar o alerta de prazo no processo. **Situação:** proposta.

<a id="pes-02"></a>

#### PES-02 · Admissão lançada depois do fato

**Severidade:** média · **Onde:** `pessoas.contrato_trabalho` (`dt_admissao, criado_em`) · **Linhas atingidas:** 1.621 de 16.992 (9,54%) · **Evidência:** [`03_pessoas`](../notebooks/auditoria/03_pessoas.ipynb), seção 8 · **Declaração do cliente:** datas retroativas: admissões lançadas depois do fato, com data anterior à do próprio cadastro

**Para quem decide:** O headcount e o custo do mês ficam errados até o lançamento, e a proporção sobe ano a ano: o processo está piorando com o volume. A data de admissão está certa; o atraso é do lançamento.

**Para quem implementa:** `pessoas.contrato_trabalho.dt_admissao` anterior a `criado_em` (data): 1.621 de 16.992 contratos (9,54%), com atraso mediano de duas semanas e máximo de um mês.

**Regra proposta (derivar):** a silver deriva `dias_de_atraso_do_lancamento` e marca `q_pes_02`; a gold usa `dt_admissao` como fato e expõe a série de atraso por ano.

**Correção na origem:** sim: lançar a admissão no dia; a série por ano mede o processo. **Situação:** proposta.

<a id="pes-03"></a>

#### PES-03 · Temporário sem data prevista de término

**Severidade:** média · **Onde:** `pessoas.contrato_trabalho` (`dt_prevista_termino`) · **Linhas atingidas:** 1.281 de 15.064 (8,50%) · **Evidência:** [`03_pessoas`](../notebooks/auditoria/03_pessoas.ipynb), seção 4

**Para quem decide:** É o contrato que nenhum alerta de prazo alcança: o sistema não sabe quando ele vence, e é por aqui que o temporário passa dos 180 dias sem ninguém ver.

**Para quem implementa:** `pessoas.contrato_trabalho.dt_prevista_termino` nulo com `tipo = 'TEMPORARIO'`: 1.281 de 15.064 temporários (8,50%), em todos os anos, todos com `prazo_legal_dias = 180`.

**Regra proposta (derivar):** a silver grava `dt_prevista_termino_derivada` (admissão mais o prazo legal) e marca `q_pes_03` onde foi derivada; a coluna original fica nula.

**Correção na origem:** sim: exigir a data prevista na admissão do temporário. **Situação:** proposta.

<a id="pes-04"></a>

#### PES-04 · Afastamentos sobrepostos

**Severidade:** baixa · **Onde:** `pessoas.afastamento` (`dt_inicio, dt_fim`) · **Linhas atingidas:** 37 de 1.058 (3,50%) · **Evidência:** [`03_pessoas`](../notebooks/auditoria/03_pessoas.ipynb), seção 5

**Para quem decide:** O mesmo dia conta duas vezes no absenteísmo e no custo do afastamento.

**Para quem implementa:** `pessoas.afastamento` com dois períodos da mesma pessoa que se cruzam: 37 de 1.058 afastamentos (3,50%).

**Regra proposta (marcar):** marcar `q_pes_04` nos dois afastamentos do par; a gold conta o dia uma vez.

**Correção na origem:** sim: decidir qual afastamento prevalece. **Situação:** proposta.

### ponto

<a id="pon-01"></a>

#### PON-01 · A batida que falta

**Severidade:** média · **Onde:** `ponto.marcacao` (`colaborador_id, data`) · **Linhas atingidas:** 26.900 de 1.080.569 (2,49%) · **Evidência:** [`04_ponto`](../notebooks/auditoria/04_ponto.ipynb), seção 7

**Para quem decide:** Sem uma das quatro batidas, o cálculo de horas do dia depende de suposição: a pessoa esqueceu de bater a saída ou saiu mais cedo? É o defeito clássico do relógio de ponto, e aqui atinge um dia em cada quarenta.

**Para quem implementa:** `ponto.marcacao` com duas ou três batidas no dia para a pessoa, todas em dias com apontamento `NORMAL`: 26.900 de 1.080.569 dias com batida (2,49%).

**Regra proposta (marcar):** a silver marca `q_pon_01` no dia (na tabela de apontamento) e não infere a batida ausente; o cálculo de horas usa o apontamento, que já existe.

**Correção na origem:** sim: o relógio ou o aplicativo avisa a batida que falta no fim do dia. **Situação:** proposta.

<a id="pon-02"></a>

#### PON-02 · A batida repetida

**Severidade:** média · **Onde:** `ponto.marcacao` (`colaborador_id, data, tipo`) · **Linhas atingidas:** 12.736 de 4.300.719 (0,30%) · **Evidência:** [`04_ponto`](../notebooks/auditoria/04_ponto.ipynb), seção 5

**Para quem decide:** Infla o total de marcações e, se o cálculo de horas pegar a batida errada, muda a jornada do dia. É pequeno e localizável.

**Para quem implementa:** `ponto.marcacao` com o mesmo `tipo` mais de uma vez para a mesma pessoa e `data`: 12.736 de 4.300.719 marcações (0,30%); uma parte é cópia exata (mesma hora).

**Regra proposta (marcar):** a silver marca `q_pon_02` na batida repetida e elege a primeira do tipo no dia como válida em `batida_valida`; nada é apagado.

**Correção na origem:** não. **Situação:** proposta.

<a id="pon-03"></a>

#### PON-03 · Horas noturnas acima das trabalhadas

**Severidade:** baixa · **Onde:** `ponto.apontamento` (`horas_noturnas, horas_trabalhadas`) · **Linhas atingidas:** 6.269 de 1.166.361 (0,54%) · **Evidência:** [`04_ponto`](../notebooks/auditoria/04_ponto.ipynb), seção 4

**Para quem decide:** Compatível com a hora noturna reduzida da CLT (52 minutos e 30 segundos), mas só aparece numa fração dos dias noturnos: ou a redução é aplicada em parte, ou é defeito de cálculo. O adicional noturno da folha depende da resposta.

**Para quem implementa:** `ponto.apontamento.horas_noturnas > horas_trabalhadas` em 6.269 de 1.166.361 apontamentos (0,54%), com diferença de até 2,5 horas.

**Regra proposta (pedir):** marcar `q_pon_03`; não recalcular.

**Correção na origem:** não. **Situação:** proposta.

<a id="pon-04"></a>

#### PON-04 · A batida solta

**Severidade:** baixa · **Onde:** `ponto.marcacao` (`colaborador_id, data`) · **Linhas atingidas:** 292 de 1.080.569 (0,03%) · **Evidência:** [`04_ponto`](../notebooks/auditoria/04_ponto.ipynb), seção 7

**Para quem decide:** Registro sem dia de trabalho correspondente; ruído no total de marcações.

**Para quem implementa:** `ponto.marcacao` com uma batida só no dia e nenhum `apontamento` para a pessoa e a data: 292 de 1.080.569 dias com batida.

**Regra proposta (marcar):** marcar `q_pon_04`; a gold ignora a batida marcada.

**Correção na origem:** sim: decidir se descarta na origem. **Situação:** proposta.

### folha

<a id="fol-01"></a>

#### FOL-01 · O rateio não fecha com a folha

**Severidade:** média · **Onde:** `folha.rateio_custo` (`valor_salario`) · **Linhas atingidas:** 39.104 de 63.445 (61,63%) · **Evidência:** [`05_folha`](../notebooks/auditoria/05_folha.ipynb), seção 7

**Para quem decide:** O rateio é a base da margem por cliente. Se o salário rateado é menor que o pago, a margem de cada contrato aparece maior do que é, e ninguém vê porque o total da folha está certo. Numa folha de dezenas de milhões por ano, a diferença é de centenas de milhares atribuídos ao cliente errado ou a nenhum.

**Para quem implementa:** `folha.rateio_custo.valor_salario` somado por pessoa e competência difere dos proventos mensais da folha (proventos sem 13º e verbas rescisórias) em 39.104 de 63.445 pessoa-mês (61,63%), sempre um pouco abaixo; encargos, benefícios e provisões batem. A regra de rateio não está escrita.

**Regra proposta (pedir):** a silver grava `diferenca_rateio_folha` por pessoa-mês e marca `q_fol_01`; não corrige o rateio.

**Correção na origem:** sim: dizer qual é a regra do rateio (o que entra no salário rateado e como se divide entre alocações). **Situação:** proposta.

<a id="fol-02"></a>

#### FOL-02 · Provisão que não encadeia

**Severidade:** baixa · **Onde:** `folha.provisao` (`saldo_acumulado, valor_mes`) · **Linhas atingidas:** 9 de 146.926 (0,01%) · **Evidência:** [`05_folha`](../notebooks/auditoria/05_folha.ipynb), seção 7

**Para quem decide:** A provisão dessas pessoas não é reconstruível mês a mês; são três pessoas.

**Para quem implementa:** `folha.provisao` com `saldo_anterior + valor_mes` diferente de `saldo_acumulado`: 9 de 146.926 linhas.

**Regra proposta (marcar):** marcar `q_fol_02`.

**Correção na origem:** sim: explicar a baixa ou o reinício. **Situação:** proposta.

<a id="fol-03"></a>

#### FOL-03 · Rateio zerado

**Severidade:** baixa · **Onde:** `folha.rateio_custo` (`custo_total`) · **Linhas atingidas:** 7 de 63.470 (0,01%) · **Evidência:** [`05_folha`](../notebooks/auditoria/05_folha.ipynb), seção 7

**Para quem decide:** Alocação no mês sem custo atribuído ao contrato.

**Para quem implementa:** `folha.rateio_custo.custo_total <= 0` em 7 de 63.470 rateios.

**Regra proposta (marcar):** marcar `q_fol_03`.

**Correção na origem:** sim: conferir os rateios zerados. **Situação:** proposta.

### financeiro

<a id="fin-01"></a>

#### FIN-01 · O consolidado da gerência deixou de bater com a operação

**Severidade:** alta · **Onde:** `financeiro.consolidado_gerencial` (`faturamento_informado, custo_informado`) · **Linhas atingidas:** 158 de 237 (66,67%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 10 · **Declaração do cliente:** o consolidado da gerência diverge da operação a partir de 2022 e a divergência cresce com o volume

**Para quem decide:** Há dois números para a mesma pergunta, e a decisão sobre qual é a fonte da verdade é do dono do processo, não do pipeline. O que a auditoria entrega é a prova: o consolidado era fiel até 2021 e deixou de ser quando o volume cresceu, com a diferença chegando a alguns por cento do faturamento e do custo. O cliente já sabia; agora sabe desde quando e quanto.

**Para quem implementa:** `financeiro.consolidado_gerencial.faturamento_informado` e `custo_informado` contra a soma de `fatura.valor_bruto` e de `rateio_custo.custo_total` por filial e competência: idênticos até 2021, diferentes em 158 de 237 meses-filial (66,67%) desde janeiro de 2022, sempre abaixo da operação.

**Regra proposta (manter):** a gold usa a operação como fonte da verdade para faturamento e custo e guarda o consolidado como série informada, lado a lado, com a diferença por mês e filial.

**Correção na origem:** sim: decidir a fonte da verdade e o destino da planilha de fechamento. **Situação:** proposta.

<a id="fin-02"></a>

#### FIN-02 · Headcount e vagas do consolidado sem definição

**Severidade:** média · **Onde:** `financeiro.consolidado_gerencial` (`headcount_informado, vagas_abertas_informado`) · **Linhas atingidas:** 220 de 237 (92,83%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 10 · **Declaração do cliente:** o consolidado da gerência diverge da operação a partir de 2022 e a divergência cresce com o volume

**Para quem decide:** O número que a gerência reporta não tem definição que o pipeline consiga recalcular, em nenhum ano. Não é degradação: é uma conta que ninguém escreveu.

**Para quem implementa:** `headcount_informado` e `vagas_abertas_informado` diferem do headcount alocado e das vagas abertas no último dia do mês em 220 de 237 meses-filial (92,83%), desde 2018.

**Regra proposta (pedir):** a gold reporta os dois números com a origem de cada um; nada na silver.

**Correção na origem:** sim: escrever a definição de headcount e de vaga aberta usada no fechamento. **Situação:** proposta.

<a id="fin-03"></a>

#### FIN-03 · Fatura depois do fim do contrato

**Severidade:** média · **Onde:** `financeiro.fatura` (`competencia, contrato.dt_encerramento`) · **Linhas atingidas:** 42 de 3.459 (1,21%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 7

**Para quem decide:** Receita reconhecida em contrato que não existe mais, ou encerramento lançado com data errada. Qualquer margem por contrato e mês sai errada nesses casos.

**Para quem implementa:** `financeiro.fatura.competencia` posterior a `contrato.dt_encerramento`: 42 de 3.459 faturas (1,21%), de dias a meses depois.

**Regra proposta (marcar):** marcar `q_fin_03`; a gold atribui a receita ao último mês vigente até o cliente dizer qual data está certa.

**Correção na origem:** sim: dizer qual data está certa, a da fatura ou a do encerramento. **Situação:** proposta.

<a id="fin-04"></a>

#### FIN-04 · Título vencido que continua aberto

**Severidade:** baixa · **Onde:** `financeiro.titulo_receber` (`status, dt_vencimento`) · **Linhas atingidas:** 5 de 3.459 (0,14%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 4

**Para quem decide:** Inadimplência escondida do indicador de atraso.

**Para quem implementa:** `financeiro.titulo_receber` com `status = 'ABERTO'` e `dt_vencimento` anterior à data de referência: 5 de 3.459 títulos.

**Regra proposta (derivar):** a silver deriva `situacao_derivada` do título (em dia, vencido, pago em dia, pago com atraso) das datas e preserva `status`.

**Correção na origem:** não. **Situação:** proposta.

<a id="fin-05"></a>

#### FIN-05 · Valor pago diferente do título

**Severidade:** baixa · **Onde:** `financeiro.titulo_receber` (`valor_pago, valor`) · **Linhas atingidas:** 37 de 3.459 (1,07%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 7

**Para quem decide:** A diferença entre valor e valor pago some do indicador de inadimplência se ninguém a separa.

**Para quem implementa:** `financeiro.titulo_receber.valor_pago` diferente de `valor` em 37 de 3.459 títulos pagos, a maioria a menos.

**Regra proposta (derivar):** a silver grava `diferenca_pagamento` (pago menos devido) e marca `q_fin_05`.

**Correção na origem:** não. **Situação:** proposta.

<a id="fin-06"></a>

#### FIN-06 · Alocação sem faturamento

**Severidade:** baixa · **Onde:** `financeiro.fatura_item` (`posto_id, competencia`) · **Linhas atingidas:** 4 de 4.678 (0,09%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 7

**Para quem decide:** Custo sem receita correspondente: a margem do contrato fica subestimada no mês.

**Para quem implementa:** posto com `alocacao` iniciada no mês e sem `fatura_item` na competência, em meses já fechados: 4 de 4.678 posto-mês.

**Regra proposta (marcar):** marcar `q_fin_06` no posto-mês.

**Correção na origem:** sim: conferir o faturamento desses postos. **Situação:** proposta.

<a id="fin-07"></a>

#### FIN-07 · Item de fatura que não fecha

**Severidade:** baixa · **Onde:** `financeiro.fatura_item` (`valor_total`) · **Linhas atingidas:** 1 de 9.116 (0,01%) · **Evidência:** [`06_financeiro`](../notebooks/auditoria/06_financeiro.ipynb), seção 7

**Para quem decide:** Um item; ruído.

**Para quem implementa:** `financeiro.fatura_item.valor_total` diferente de `valor_postos + valor_horas_extras - valor_descontos`: 1 de 9.116 itens.

**Regra proposta (marcar):** marcar `q_fin_07`.

**Correção na origem:** não. **Situação:** proposta.

### treinamento e sst

<a id="tss-01"></a>

#### TSS-01 · Pessoa em campo com ASO vencido

**Severidade:** alta · **Onde:** `sst.aso` (`dt_validade, colaborador_id`) · **Linhas atingidas:** 25 de 858 (2,91%) · **Evidência:** [`07_treinamento_sst`](../notebooks/auditoria/07_treinamento_sst.ipynb), seção 10 · **Declaração do cliente:** ASO vencido com pessoa alocada: o exame expirou e ninguém foi avisado

**Para quem decide:** Risco jurídico imediato para a Fictalent e para o cliente. O cliente declarou o defeito; a auditoria mostrou a história: a proporção de alocados sem exame válido era zero em 2018 e chegou a cerca de quatro por cento, porque a renovação do periódico não acompanhou o crescimento.

**Para quem implementa:** alocados na data de referência sem `sst.aso` com `dt_validade` cobrindo o dia e `resultado <> 'INAPTO'`: 25 de 858 (2,91%); ninguém está sem admissional; a prevalência mensal está no notebook.

**Regra proposta (derivar):** a silver deriva, por pessoa e dia, `aso_valido` e `dias_para_vencer`; marca `q_tss_01` onde a pessoa está alocada sem exame válido; o painel alerta com 30 dias de antecedência.

**Correção na origem:** sim: renovar os exames vencidos e criar o alerta de vencimento no processo. **Situação:** proposta.

<a id="tss-02"></a>

#### TSS-02 · Admissional depois da admissão

**Severidade:** média · **Onde:** `sst.aso` (`dt_exame (ADMISSIONAL)`) · **Linhas atingidas:** 155 de 16.992 (0,91%) · **Evidência:** [`07_treinamento_sst`](../notebooks/auditoria/07_treinamento_sst.ipynb), seção 8

**Para quem decide:** A pessoa trabalhou sem exame; irregularidade que a fiscalização autua.

**Para quem implementa:** `sst.aso` do tipo `ADMISSIONAL` com `dt_exame` posterior à `dt_admissao` do contrato: 155 de 16.992 admissionais (0,91%), com atraso mediano de mês e meio.

**Regra proposta (derivar):** a silver deriva `dias_de_atraso_do_admissional` e marca `q_tss_02`.

**Correção na origem:** sim: o exame passa a ser condição da admissão no processo. **Situação:** proposta.

<a id="tss-03"></a>

#### TSS-03 · CAT fora do prazo

**Severidade:** média · **Onde:** `sst.cat` (`dt_emissao`) · **Linhas atingidas:** 48 de 99 (48,48%) · **Evidência:** [`07_treinamento_sst`](../notebooks/auditoria/07_treinamento_sst.ipynb), seção 8

**Para quem decide:** Multa por CAT fora do prazo; metade das CATs.

**Para quem implementa:** `sst.cat.dt_emissao` mais de dois dias depois de `acidente.dt_acidente`: 48 de 99 CATs (48,48%).

**Regra proposta (derivar):** a silver deriva `dias_alem_do_prazo_da_cat` e marca `q_tss_03`.

**Correção na origem:** sim: emitir a CAT no primeiro dia útil. **Situação:** proposta.

<a id="tss-04"></a>

#### TSS-04 · Programa legal vencido em contrato ativo

**Severidade:** média · **Onde:** `sst.programa_sst` (`dt_validade, contrato_id`) · **Linhas atingidas:** 5 de 41 (12,20%) · **Evidência:** [`07_treinamento_sst`](../notebooks/auditoria/07_treinamento_sst.ipynb), seção 8

**Para quem decide:** Irregularidade em contrato em andamento; autuação para a Fictalent e para o cliente.

**Para quem implementa:** `sst.programa_sst.dt_validade` anterior à data de referência, em contrato `ATIVO`, sem programa do mesmo tipo com validade posterior: 5 de 41 contratos ativos com programa (12,20%).

**Regra proposta (derivar):** a silver deriva `programa_vigente` por contrato e tipo e marca `q_tss_04`; o painel alerta.

**Correção na origem:** sim: renovar os programas vencidos. **Situação:** proposta.

<a id="tss-05"></a>

#### TSS-05 · Turmas que podem ser a mesma turma

**Severidade:** baixa · **Onde:** `treinamento.turma` (`curso_id, filial_id, dt_inicio`) · **Linhas atingidas:** 192 de 5.411 (3,55%) · **Evidência:** [`07_treinamento_sst`](../notebooks/auditoria/07_treinamento_sst.ipynb), seção 5

**Para quem decide:** Turma duplicada dobra o custo de treinamento no rateio e o número de treinados no indicador.

**Para quem implementa:** `treinamento.turma` em grupos de mesmo `curso_id`, `filial_id` e `dt_inicio`: 192 de 5.411 turmas (3,55%).

**Regra proposta (pedir):** marcar `q_tss_05`; nunca fundir.

**Correção na origem:** sim: confirmar se são turmas paralelas. **Situação:** proposta.

<a id="tss-06"></a>

#### TSS-06 · Curso obrigatório sem certificado válido

**Severidade:** baixa · **Onde:** `treinamento.certificado` (`curso_id, colaborador_id, dt_validade`) · **Linhas atingidas:** 17 de 1.763 (0,96%) · **Evidência:** [`07_treinamento_sst`](../notebooks/auditoria/07_treinamento_sst.ipynb), seção 10

**Para quem decide:** Exigência de norma descoberta em campo; pequena em número.

**Para quem implementa:** alocados na data de referência com `curso_funcao.fl_obrigatorio` e sem `certificado` válido do curso: 17 de 1.763 exigências (0,96%).

**Regra proposta (derivar):** a silver deriva `certificado_valido` por pessoa e curso obrigatório e marca `q_tss_06`; o painel alerta.

**Correção na origem:** sim: treinar quem está descoberto. **Situação:** proposta.

### segurança

<a id="seg-01"></a>

#### SEG-01 · Ação sem permissão vigente

**Severidade:** média · **Onde:** `seguranca.log_auditoria` (`usuario_id, modulo, acao, dt_evento`) · **Linhas atingidas:** 4.092 de 111.406 (3,67%) · **Evidência:** [`08_seguranca`](../notebooks/auditoria/08_seguranca.ipynb), seção 7

**Para quem decide:** Ou o controle de acesso do sistema falha, ou o perfil foi concedido depois do fato e retroagido. A maioria são exportações de dado pessoal, o caso sensível pela LGPD.

**Para quem implementa:** `seguranca.log_auditoria` com evento cuja `acao` no `modulo` não era permitida por nenhum perfil vigente do usuário no dia: 4.092 de 111.406 eventos (3,67%).

**Regra proposta (marcar):** marcar `q_seg_01`; a auditoria de acesso da v1.0.0 lista por usuário e perfil.

**Correção na origem:** sim: explicar os casos e revisar o controle de acesso. **Situação:** proposta.

<a id="seg-02"></a>

#### SEG-02 · Usuário sem colaborador

**Severidade:** baixa · **Onde:** `seguranca.usuario` (`colaborador_id`) · **Linhas atingidas:** 40 de 40 (100,00%) · **Evidência:** [`08_seguranca`](../notebooks/auditoria/08_seguranca.ipynb), seção 4

**Para quem decide:** A trilha diz o login mas não diz quem é a pessoa, em que setor e filial está e se ainda trabalha na empresa.

**Para quem implementa:** `seguranca.usuario.colaborador_id` nulo em 40 de 40 usuários: a retaguarda não está em `pessoas.colaborador`, que só tem quem vai a campo.

**Regra proposta (manter):** nada na silver; a auditoria de acesso usa o login; a modelagem da retaguarda é decisão do cliente.

**Correção na origem:** sim: modelar a retaguarda como colaborador, ou aceitar e documentar. **Situação:** proposta.

<a id="seg-03"></a>

#### SEG-03 · Último acesso desatualizado

**Severidade:** baixa · **Onde:** `seguranca.log_auditoria` (`dt_evento, usuario.ultimo_acesso`) · **Linhas atingidas:** 9 de 146.520 (0,01%) · **Evidência:** [`08_seguranca`](../notebooks/auditoria/08_seguranca.ipynb), seção 8

**Para quem decide:** O campo de último acesso não é confiável como indicador de atividade.

**Para quem implementa:** `seguranca.log_auditoria.dt_evento` posterior a `usuario.ultimo_acesso`: 9 de 146.520 eventos.

**Regra proposta (manter):** a gold deriva o último acesso da trilha, não do campo.

**Correção na origem:** não. **Situação:** proposta.

## 5. O que não se trata

Os registros de severidade nenhuma: hipóteses refutadas (o defeito esperado não existe), regras de negócio que pareciam defeito no primeiro teste, pontos fortes e os dois defeitos do próprio pipeline, já corrigidos. Estão aqui para a silver não tratar como erro o que é regra.

| domínio | tabela | registro | ação |
|---|---|---|---|
| ats | `ats.candidatura_etapa` | hipótese refutada: nenhuma etapa fora de ordem, fora da candidatura ou com data invertida | nenhuma |
| ats | `ats.candidatura` | candidatura aprovada que não virou colaborador: o no-show do primeiro dia de trabalho | nenhuma na silver; vira indicador na gold |
| cadastro | `cadastro.escala` | defeito de ingestão encontrado e corrigido: colunas TINYINT copiadas para a bronze como BOOLEAN (todo valor virava True) | feito nesta auditoria: o backfill passou a mapear como booleano só o tinyint(1) que a DDL usa para BOOLEAN, e as quatro tabelas foram recopiadas; a checagem de tipo entrou em toda auditoria |
| cadastro | `cadastro.endereco` | hipótese refutada: não há endereço nem outro cadastro de referência duplicado por conteúdo | nenhuma |
| cadastro | `cadastro.feriado` | feriados nacionais conferidos contra a BrasilAPI só nos anos que a fonte tem no lake (2024): 14 de 14; os demais anos aguardam a carga da fonte | materializar fontes/brasilapi/feriados para 2018 a 2026 e repetir a conferência antes do catálogo (pendência do pipeline, não do dado) |
| comercial | `comercial.cliente` | hipótese refutada: não há cliente duplicado por grafia nem CNPJ repetido | nenhuma |
| financeiro | `financeiro.fatura` | faturas sem item: todas de contratos de recrutamento, que faturam honorário por colocação e não posto por mês (regra, não defeito) | nenhuma |
| financeiro | `financeiro.imposto_apurado` | apurações trimestrais de IRPJ com alíquota efetiva acima da tabela: é o adicional de 10% sobre o lucro que excede o limite do lucro presumido (regra, não defeito) | nenhuma; documentar a regra no catálogo para ninguém tratar como erro |
| financeiro | `financeiro.consolidado_gerencial` | hipótese refutada: a tabela da réplica e a planilha ingerida são idênticas linha a linha; a tabela é a planilha carregada | nenhuma |
| folha | `folha.folha_competencia` | folhas sem item: os três primeiros meses das filiais recém-abertas e as folhas abertas do mês corrente (regra, não defeito) | nenhuma |
| folha | `folha.folha_competencia` | hipótese refutada: os totais de cada competência batem com a soma dos itens em todas as folhas | nenhuma |
| pessoas | `pessoas.desligamento` | desligamento sem homologação, todos dos últimos 30 dias: pendência de prazo, não defeito | nenhuma; o painel pode listar os pendentes |
| pessoas | `pessoas.alocacao` | hipótese refutada: nenhuma pessoa com duas alocações ou dois contratos ao mesmo tempo, nenhuma duplicidade de cadastro | nenhuma |
| pessoas | `pessoas.colaborador` | hipótese refutada: nenhum CPF inválido nem nascimento impossível em pessoa admitida; a admissão filtra o que o cadastro de candidato deixa passar | nenhuma |
| ponto | `ponto.marcacao` | defeito de ingestão encontrado e corrigido: TIME copiado para a bronze como duração (BIGINT de microssegundos) | feito nesta auditoria: o backfill grava TIME como time64 e a tabela foi recopiada; a checagem de tipo entrou em toda auditoria |
| ponto | `ponto.banco_horas` | hipótese refutada: o banco de horas fecha no mês e encadeia com o mês anterior em todos os fechamentos; status e horas do apontamento coerentes em todos os testes | nenhuma |
| ponto | `ponto.marcacao` | jornada noturna que vira a meia-noite: saída com hora menor que a entrada no mesmo dia (não é defeito, é o turno da noite) | regra para a silver e a gold: toda comparação de hora do ponto usa o relógio deslocado pela entrada |
| ponto | `ponto.apontamento` | hipótese refutada: nenhum apontamento no futuro, fora da alocação, sem contrato ou sem escala; trabalho em feriado e falta em fim de semana são regra das escalas 6x1 e 12x36 | nenhuma; o adicional de feriado e o absenteísmo por escala são indicadores da gold |
| seguranca | `seguranca.log_auditoria` | hipótese refutada: todo registro nomeado pela trilha existe, todo CRIAR bate com o carimbo de criação e nenhum EDITAR é posterior à última atualização | nenhuma |
| seguranca | `seguranca.log_auditoria` | exportações de dado pessoal crescendo em número e em peso (de 11.74% para 24.64% dos eventos), concentradas no perfil de assistente | indicador de exportações por usuário e perfil no painel de auditoria de acesso da v1.0.0 |
| treinamento_sst | `treinamento.certificado` | hipótese refutada: a validade derivada (emissão mais validade do curso; exame mais periodicidade) bate em todos os certificados e exames | nenhuma |

## 6. Como este catálogo é mantido

A entrada vive em `catalogo.py` e o número vive no registro do notebook; o documento junta os dois na geração, e um teste (`tests/test_catalogo.py`) garante que toda entrada casa com um achado gravado e que todo achado com severidade tem entrada. Achado novo na auditoria sem entrada reprova a esteira: o catálogo não fica para trás. A aprovação muda `situacao` para `aprovada`, `ajustada` (com a regra ajustada na própria entrada) ou `recusada`, com a data no log de decisões; a silver lê a situação e só implementa o aprovado.

---

[Início](#topo)
