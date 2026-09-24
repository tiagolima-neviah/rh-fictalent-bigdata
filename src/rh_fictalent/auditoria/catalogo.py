"""O catálogo de achados: a decisão sobre cada achado da auditoria, escrita uma vez, em duas
redações, com a regra que a silver vai aplicar.

O notebook descobre; o catálogo decide; a silver executa. Este módulo é o meio: uma entrada
por achado com severidade (os de severidade `nenhuma` são regra ou hipótese refutada, e
entram no documento como "o que não se trata"), chaveada pelo texto exato que o notebook
gravou em `dados/auditoria/`. Nenhum número mora aqui: o documento gerado lê linhas, total e
fração do registro, na hora de gerar, e o teste garante que toda entrada casa com um achado
e todo achado com severidade tem entrada.

As duas redações têm leitores diferentes e por isso vocabulários diferentes:

- `impacto` é para quem decide: fala de decisão, risco e dinheiro, nunca de coluna;
- `detalhe` é para quem implementa: nomeia tabela, coluna e regra. Pode usar `{linhas}`,
  `{total}` e `{pct}`, preenchidos do registro.

O tratamento é um de cinco verbos, e o que a silver **nunca** faz está no documento: não
funde cadastro, não preenche ausência, não apaga linha, não corrige valor na origem.

Toda entrada nasce com situação `proposta`. A aprovação é do Tiago, entrada a entrada, e é
o que autoriza a silver (card 6.4) a implementar a regra.
"""

# ruff: noqa: E501  (módulo de prosa: as duas redações de cada achado são texto corrido)
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from rh_fictalent.auditoria import achados
from rh_fictalent.auditoria.achados import Achado

DESTINO = Path(__file__).resolve().parents[3] / "docs" / "13_catalogo_de_achados.md"
DECLARACOES = (
    "candidatos duplicados",
    "documentos inválidos",
    "datas retroativas",
    "contratos temporários fora do prazo legal",
    "ASO vencido com pessoa alocada",
    "o consolidado da gerência diverge",
)


class Tratamento(StrEnum):
    """O que a silver faz com o achado. Cinco verbos, e só esses."""

    MARCAR = "marcar"  # a linha ganha uma coluna booleana q_<codigo>; nada muda no valor
    DERIVAR = "derivar"  # a silver calcula uma coluna nova a partir das datas ou das partes
    CONFORMAR = "conformar"  # o valor ganha forma canônica; o original fica em <coluna>_original
    MANTER = "manter"  # nada na silver: vira indicador na gold ou alerta no painel
    PEDIR = "pedir"  # a regra depende de uma resposta do cliente; até lá, marcar


@dataclass(frozen=True)
class Entrada:
    codigo: str  # <DOMÍNIO>-<nn>, na ordem da severidade
    dominio: str  # o registro em dados/auditoria
    achado: str  # o texto exato gravado pelo notebook: é a chave
    titulo: str
    impacto: str  # redação executiva
    detalhe: str  # redação técnica, com {linhas}, {total} e {pct}
    tratamento: Tratamento
    regra: str  # a frase que vira código na silver
    origem: bool = False  # precisa de correção no sistema do cliente?
    acao_cliente: str = ""
    situacao: str = "proposta"  # proposta | aprovada | ajustada | recusada


ENTRADAS: list[Entrada] = [
    # cadastro
    Entrada(
        "CAD-01",
        "cadastro",
        "função sem código CBO",
        "Funções sem o código de ocupação",
        "O CBO é o código que o eSocial exige e o que liga cada função da Fictalent às estatísticas públicas de emprego. Sem ele, mais de um terço das funções, líderes e analistas entre elas, fica fora de qualquer comparação por ocupação.",
        "`cadastro.funcao.cbo` nulo em {linhas} de {total} funções ({pct}%), espalhadas por todas as famílias e níveis. Não há regra que derive o CBO do nome da função sem inventar.",
        Tratamento.PEDIR,
        "marcar `q_cad_01` nas funções sem CBO; não preencher; quando o cliente enviar os códigos, eles entram pela réplica, não pela silver",
        origem=True,
        acao_cliente="informar o CBO das funções sem código no cadastro do sistema",
    ),
    Entrada(
        "CAD-02",
        "cadastro",
        "coluna nunca preenchida",
        "Complemento de endereço que ninguém preenche",
        "A coluna existe e não informa nada. Um relatório que a mostre exibe vazio em toda linha e parece defeito; um cadastro que a exija trava.",
        "`cadastro.endereco.complemento` nulo em {linhas} de {total} endereços ({pct}%). Não é falha de linha, é coluna não coletada.",
        Tratamento.MANTER,
        "a silver mantém a coluna como está e a documenta como não coletada; o modelo dimensional não a leva até que passe a ser preenchida",
    ),
    # comercial
    Entrada(
        "COM-01",
        "comercial",
        "contrato ATIVO com vigência vencida e sem prorrogação que a cubra",
        "Contrato vencido que continua ativo",
        "Um contrato vencido que segue como ativo conta o cliente como ativo, mantém o SLA em cobrança e faz a carteira parecer maior. É um caso hoje; sem regra, vira um por semana.",
        "`comercial.contrato` com `status = 'ATIVO'`, `vigencia_fim` anterior à data de referência e nenhum aditivo de prorrogação com `vigencia_nova` que a cubra: {linhas} de {total} contratos ({pct}%). O comentário da DDL diz que status e vigência convivem e que a auditoria confere se batem.",
        Tratamento.DERIVAR,
        "a silver deriva `situacao_derivada` (vigente, vencido, encerrado) das datas e dos aditivos, preserva `status` e marca `q_com_01` onde os dois discordam",
        origem=True,
        acao_cliente="encerrar ou prorrogar o contrato vencido no sistema",
    ),
    Entrada(
        "COM-02",
        "comercial",
        "postos idênticos em contrato, função, turno, endereço e início, diferindo só em quantidade, escala ou fim",
        "Postos que podem ser o mesmo posto",
        "Se o par for o mesmo posto cadastrado duas vezes, as vagas contam em dobro no headcount contratado e o preço se aplica duas vezes. Se for desdobramento legítimo, não há nada a fazer. Só o comercial sabe.",
        "`comercial.posto` sem chave natural na DDL: {linhas} de {total} postos ({pct}%) em pares idênticos em `contrato_id`, `funcao_id`, `turno`, `endereco_id` e `vigencia_inicio`.",
        Tratamento.PEDIR,
        "marcar `q_com_02` nos dois postos de cada par; nunca fundir",
        origem=True,
        acao_cliente="confirmar, par a par, se são postos distintos ou duplicidade",
    ),
    Entrada(
        "COM-03",
        "comercial",
        "ocorrência lançada fora da vigência do contrato (depois do encerramento)",
        "Reclamação depois do fim do contrato",
        "Uma reclamação lançada depois do encerramento é plausível (reclamação tardia), mas qualquer indicador de SLA por contrato vigente a perde ou a atribui a um período sem receita.",
        "`comercial.contrato_ocorrencia.dt_ocorrencia` posterior a `contrato.dt_encerramento`: {linhas} de {total} ocorrências.",
        Tratamento.MARCAR,
        "marcar `q_com_03`; o indicador de SLA da gold considera a ocorrência no último mês vigente do contrato",
    ),
    # ats
    Entrada(
        "ATS-01",
        "ats",
        "a mesma pessoa cadastrada mais de uma vez: o mesmo CPF em vários cadastros, com o nome em outra grafia",
        "A mesma pessoa cadastrada mais de uma vez",
        "A base de talentos parece maior do que é, o histórico da pessoa fica dividido (a reprovação de ontem não aparece na candidatura de hoje), a conversão por fonte sai errada e a mesma pessoa conta mais de uma vez no funil. É o defeito mais caro do funil, e o cliente já o conhecia.",
        "`ats.candidato.cpf` sem `UNIQUE` de propósito: {linhas} de {total} cadastros ({pct}%) compartilham o CPF com outro cadastro, sempre com o nome em outra grafia (caixa alta, inicial abreviada, sobrenome omitido) e nunca com nascimento divergente.",
        Tratamento.MARCAR,
        "a silver marca `q_ats_01`, atribui `grupo_pessoa` (o CPF) a todos os cadastros do grupo e elege o cadastro canônico (o mais antigo com CPF válido) em `cadastro_canonico`; nunca funde",
        origem=True,
        acao_cliente="a tela de cadastro passa a buscar por CPF antes de criar; os grupos existentes são unificados por quem tem autoridade sobre o cadastro",
    ),
    Entrada(
        "ATS-02",
        "ats",
        "mesmo nome e nascimento com CPFs diferentes entre si: mesma pessoa com CPF errado ou homônimos",
        "Mesmo nome e nascimento, CPFs diferentes",
        "Ou é a mesma pessoa com um CPF digitado errado, ou são dois homônimos nascidos no mesmo dia. Fundir seria errado no segundo caso; ignorar, no primeiro.",
        "{linhas} de {total} cadastros ({pct}%) em pares com `nome` (normalizado) e `dt_nascimento` iguais e `cpf` diferente entre si.",
        Tratamento.PEDIR,
        "marcar `q_ats_02` como duplicidade provável, sem grupo; a conferência é do cliente",
        origem=True,
        acao_cliente="conferir cada par com documento em mãos",
    ),
    Entrada(
        "ATS-03",
        "ats",
        "CPF que não passa no dígito verificador",
        "CPF inválido",
        "A admissão é rejeitada pelo eSocial e a deduplicação por documento falha. Todos os casos estão no cadastro de candidato: a admissão barra o que o cadastro deixou passar.",
        "`ats.candidato.cpf` reprovado nos dois dígitos verificadores (ou sequência repetida): {linhas} de {total} cadastros com CPF ({pct}%).",
        Tratamento.MARCAR,
        "marcar `q_ats_03`; o valor fica como está (é evidência), e o CPF marcado não participa de `grupo_pessoa`",
        origem=True,
        acao_cliente="validar o dígito na tela de cadastro; corrigir os existentes",
    ),
    Entrada(
        "ATS-04",
        "ats",
        "data de nascimento impossível: menos de 14 anos no cadastro ou nascimento antes de 1930",
        "Data de nascimento impossível",
        "Distorce a faixa etária de qualquer análise e barra a admissão. São menores de 14 anos no cadastro (o mais novo nasceu em 2024) e pessoas nascidas antes de 1930.",
        "`ats.candidato.dt_nascimento` com idade menor que 14 anos em `dt_cadastro` ou anterior a 1930: {linhas} de {total} cadastros ({pct}%).",
        Tratamento.MARCAR,
        "marcar `q_ats_04`; o valor fica; a gold trata a idade como desconhecida onde a marca é verdadeira",
        origem=True,
        acao_cliente="validar a faixa de nascimento na tela; corrigir os existentes",
    ),
    Entrada(
        "ATS-05",
        "ats",
        "nome em grafia inconsistente: caixa alta integral ou inicial abreviada no meio",
        "Nome escrito de vários jeitos",
        "É o mecanismo da duplicidade: o cadastro repetido entra com o nome escrito de outro jeito e passa por qualquer busca. Também é rótulo de painel e de relatório.",
        "`ats.candidato.nome` em caixa alta integral ou com inicial abreviada no meio (`Wellington M. Fernandes`): {linhas} de {total} cadastros ({pct}%); centenas de formas normalizadas existem em mais de uma grafia.",
        Tratamento.CONFORMAR,
        "a silver grava `nome_conformado` (caixa de título, espaços normalizados, sem abreviar o que não dá para expandir) e mantém `nome` como veio; a busca e o rótulo usam o conformado",
        origem=True,
        acao_cliente="a tela de cadastro padroniza a caixa ao salvar",
    ),
    Entrada(
        "ATS-06",
        "ats",
        "candidato cadastrado sem CPF",
        "Candidato sem CPF",
        "Sem documento não há deduplicação por CPF nem admissão sem retrabalho. É pequeno, e o cliente completa na admissão.",
        "`ats.candidato.cpf` nulo em {linhas} de {total} cadastros ({pct}%).",
        Tratamento.MARCAR,
        "marcar `q_ats_06`; o cadastro sem CPF entra em `grupo_pessoa` só por nome e nascimento",
        origem=True,
        acao_cliente="completar o CPF na admissão",
    ),
    Entrada(
        "ATS-07",
        "ats",
        "telefone repetido entre cadastros: só 10000 números distintos para 60294 candidatos",
        "Telefone que não identifica a pessoa",
        "O telefone se repete entre cadastros numa escala que o torna inútil como contato confiável e como chave de deduplicação; parece campo preenchido com número de recado ou de terceiro.",
        "`ats.candidato.telefone`: cerca de dez mil números distintos para {total} cadastros; {linhas} linhas em grupos repetidos ({pct}%).",
        Tratamento.MANTER,
        "a silver não usa o telefone como chave nem como contato; documenta o achado",
        origem=True,
        acao_cliente="avaliar como o campo é preenchido no cadastro",
    ),
    Entrada(
        "ATS-08",
        "ats",
        "experiência profissional começando antes dos 14 anos do candidato",
        "Experiência antes dos 14 anos",
        "Contamina qualquer análise de senioridade; ou a data da experiência ou o nascimento está errado.",
        "`ats.candidato_experiencia.dt_inicio` anterior aos 14 anos de `candidato.dt_nascimento`: {linhas} de {total} experiências ({pct}%).",
        Tratamento.MARCAR,
        "marcar `q_ats_08`; a gold não conta a experiência marcada na senioridade",
        origem=True,
        acao_cliente="conferir a data da experiência ou o nascimento",
    ),
    # pessoas
    Entrada(
        "PES-01",
        "pessoas",
        "contrato temporário além de 180 dias sem prorrogação registrada (parte deles ainda ativos; parte além de 270 dias no total)",
        "Temporário além do prazo legal",
        "Contrato temporário além de 180 dias sem aditivo é irregularidade trabalhista, com multa e risco de vínculo. Parte dos casos ainda está ativa, e a concentração em 2025 e 2026 diz que o controle se perdeu com o crescimento. É o achado de maior consequência jurídica do banco.",
        "`pessoas.contrato_trabalho` com `tipo = 'TEMPORARIO'` e duração (rescisão, ou a data de referência se ativo) acima de 180 dias sem linha em `contrato_trabalho_prorrogacao`: {linhas} de {total} temporários ({pct}%); parte deles acima de 270 dias no total.",
        Tratamento.DERIVAR,
        "a silver deriva `dias_de_vinculo` e `dias_alem_do_prazo` (considerando prorrogações), marca `q_pes_01` e o alerta vai para o painel; o dado não muda",
        origem=True,
        acao_cliente="regularizar os contratos ativos (prorrogação ou encerramento) e criar o alerta de prazo no processo",
    ),
    Entrada(
        "PES-02",
        "pessoas",
        "admissão lançada depois do fato: data de admissão anterior ao dia em que o registro foi criado",
        "Admissão lançada depois do fato",
        "O headcount e o custo do mês ficam errados até o lançamento, e a proporção sobe ano a ano: o processo está piorando com o volume. A data de admissão está certa; o atraso é do lançamento.",
        "`pessoas.contrato_trabalho.dt_admissao` anterior a `criado_em` (data): {linhas} de {total} contratos ({pct}%), com atraso mediano de duas semanas e máximo de um mês.",
        Tratamento.DERIVAR,
        "a silver deriva `dias_de_atraso_do_lancamento` e marca `q_pes_02`; a gold usa `dt_admissao` como fato e expõe a série de atraso por ano",
        origem=True,
        acao_cliente="lançar a admissão no dia; a série por ano mede o processo",
    ),
    Entrada(
        "PES-03",
        "pessoas",
        "contrato temporário sem data prevista de término",
        "Temporário sem data prevista de término",
        "É o contrato que nenhum alerta de prazo alcança: o sistema não sabe quando ele vence, e é por aqui que o temporário passa dos 180 dias sem ninguém ver.",
        "`pessoas.contrato_trabalho.dt_prevista_termino` nulo com `tipo = 'TEMPORARIO'`: {linhas} de {total} temporários ({pct}%), em todos os anos, todos com `prazo_legal_dias = 180`.",
        Tratamento.DERIVAR,
        "a silver grava `dt_prevista_termino_derivada` (admissão mais o prazo legal) e marca `q_pes_03` onde foi derivada; a coluna original fica nula",
        origem=True,
        acao_cliente="exigir a data prevista na admissão do temporário",
    ),
    Entrada(
        "PES-04",
        "pessoas",
        "afastamentos da mesma pessoa que se cruzam no tempo",
        "Afastamentos sobrepostos",
        "O mesmo dia conta duas vezes no absenteísmo e no custo do afastamento.",
        "`pessoas.afastamento` com dois períodos da mesma pessoa que se cruzam: {linhas} de {total} afastamentos ({pct}%).",
        Tratamento.MARCAR,
        "marcar `q_pes_04` nos dois afastamentos do par; a gold conta o dia uma vez",
        origem=True,
        acao_cliente="decidir qual afastamento prevalece",
    ),
    # ponto
    Entrada(
        "PON-01",
        "ponto",
        "dia trabalhado com uma batida a menos (duas ou três batidas em vez de quatro)",
        "A batida que falta",
        "Sem uma das quatro batidas, o cálculo de horas do dia depende de suposição: a pessoa esqueceu de bater a saída ou saiu mais cedo? É o defeito clássico do relógio de ponto, e aqui atinge um dia em cada quarenta.",
        "`ponto.marcacao` com duas ou três batidas no dia para a pessoa, todas em dias com apontamento `NORMAL`: {linhas} de {total} dias com batida ({pct}%).",
        Tratamento.MARCAR,
        "a silver marca `q_pon_01` no dia (na tabela de apontamento) e não infere a batida ausente; o cálculo de horas usa o apontamento, que já existe",
        origem=True,
        acao_cliente="o relógio ou o aplicativo avisa a batida que falta no fim do dia",
    ),
    Entrada(
        "PON-02",
        "ponto",
        "batida repetida: o mesmo tipo de batida registrado mais de uma vez no mesmo dia",
        "A batida repetida",
        "Infla o total de marcações e, se o cálculo de horas pegar a batida errada, muda a jornada do dia. É pequeno e localizável.",
        "`ponto.marcacao` com o mesmo `tipo` mais de uma vez para a mesma pessoa e `data`: {linhas} de {total} marcações ({pct}%); uma parte é cópia exata (mesma hora).",
        Tratamento.MARCAR,
        "a silver marca `q_pon_02` na batida repetida e elege a primeira do tipo no dia como válida em `batida_valida`; nada é apagado",
    ),
    Entrada(
        "PON-03",
        "ponto",
        "horas noturnas maiores que as horas trabalhadas do dia",
        "Horas noturnas acima das trabalhadas",
        "Compatível com a hora noturna reduzida da CLT (52 minutos e 30 segundos), mas só aparece numa fração dos dias noturnos: ou a redução é aplicada em parte, ou é defeito de cálculo. O adicional noturno da folha depende da resposta.",
        "`ponto.apontamento.horas_noturnas > horas_trabalhadas` em {linhas} de {total} apontamentos ({pct}%), com diferença de até 2,5 horas.",
        Tratamento.PEDIR,
        "marcar `q_pon_03`; não recalcular",
        origem=False,
        acao_cliente="dizer qual convenção de hora noturna o sistema aplica",
    ),
    Entrada(
        "PON-04",
        "ponto",
        "batida solta: dia com uma batida só e sem apontamento",
        "A batida solta",
        "Registro sem dia de trabalho correspondente; ruído no total de marcações.",
        "`ponto.marcacao` com uma batida só no dia e nenhum `apontamento` para a pessoa e a data: {linhas} de {total} dias com batida.",
        Tratamento.MARCAR,
        "marcar `q_pon_04`; a gold ignora a batida marcada",
        origem=True,
        acao_cliente="decidir se descarta na origem",
    ),
    # folha
    Entrada(
        "FOL-01",
        "folha",
        "salário rateado diferente dos proventos mensais pagos na folha da mesma pessoa e mês (sempre um pouco abaixo; 1,7% a menos no agregado)",
        "O rateio não fecha com a folha",
        "O rateio é a base da margem por cliente. Se o salário rateado é menor que o pago, a margem de cada contrato aparece maior do que é, e ninguém vê porque o total da folha está certo. Numa folha de dezenas de milhões por ano, a diferença é de centenas de milhares atribuídos ao cliente errado ou a nenhum.",
        "`folha.rateio_custo.valor_salario` somado por pessoa e competência difere dos proventos mensais da folha (proventos sem 13º e verbas rescisórias) em {linhas} de {total} pessoa-mês ({pct}%), sempre um pouco abaixo; encargos, benefícios e provisões batem. A regra de rateio não está escrita.",
        Tratamento.PEDIR,
        "a silver grava `diferenca_rateio_folha` por pessoa-mês e marca `q_fol_01`; não corrige o rateio",
        origem=True,
        acao_cliente="dizer qual é a regra do rateio (o que entra no salário rateado e como se divide entre alocações)",
    ),
    Entrada(
        "FOL-02",
        "folha",
        "provisão fora do encadeamento: saldo zerado sem baixa registrada, ou saldo reiniciado",
        "Provisão que não encadeia",
        "A provisão dessas pessoas não é reconstruível mês a mês; são três pessoas.",
        "`folha.provisao` com `saldo_anterior + valor_mes` diferente de `saldo_acumulado`: {linhas} de {total} linhas.",
        Tratamento.MARCAR,
        "marcar `q_fol_02`",
        origem=True,
        acao_cliente="explicar a baixa ou o reinício",
    ),
    Entrada(
        "FOL-03",
        "folha",
        "rateio com custo zero",
        "Rateio zerado",
        "Alocação no mês sem custo atribuído ao contrato.",
        "`folha.rateio_custo.custo_total <= 0` em {linhas} de {total} rateios.",
        Tratamento.MARCAR,
        "marcar `q_fol_03`",
        origem=True,
        acao_cliente="conferir os rateios zerados",
    ),
    # financeiro
    Entrada(
        "FIN-01",
        "financeiro",
        "faturamento e custo do consolidado idênticos à operação até 2021 e divergentes desde 01/2022, com a diferença crescendo (informado abaixo do faturado e do rateado)",
        "O consolidado da gerência deixou de bater com a operação",
        "Há dois números para a mesma pergunta, e a decisão sobre qual é a fonte da verdade é do dono do processo, não do pipeline. O que a auditoria entrega é a prova: o consolidado era fiel até 2021 e deixou de ser quando o volume cresceu, com a diferença chegando a alguns por cento do faturamento e do custo. O cliente já sabia; agora sabe desde quando e quanto.",
        "`financeiro.consolidado_gerencial.faturamento_informado` e `custo_informado` contra a soma de `fatura.valor_bruto` e de `rateio_custo.custo_total` por filial e competência: idênticos até 2021, diferentes em {linhas} de {total} meses-filial ({pct}%) desde janeiro de 2022, sempre abaixo da operação.",
        Tratamento.MANTER,
        "a gold usa a operação como fonte da verdade para faturamento e custo e guarda o consolidado como série informada, lado a lado, com a diferença por mês e filial",
        origem=True,
        acao_cliente="decidir a fonte da verdade e o destino da planilha de fechamento",
    ),
    Entrada(
        "FIN-02",
        "financeiro",
        "headcount e vagas abertas do consolidado não reproduzíveis pela operação em nenhum ano, desde 2018: definição não escrita, não degradação",
        "Headcount e vagas do consolidado sem definição",
        "O número que a gerência reporta não tem definição que o pipeline consiga recalcular, em nenhum ano. Não é degradação: é uma conta que ninguém escreveu.",
        "`headcount_informado` e `vagas_abertas_informado` diferem do headcount alocado e das vagas abertas no último dia do mês em {linhas} de {total} meses-filial ({pct}%), desde 2018.",
        Tratamento.PEDIR,
        "a gold reporta os dois números com a origem de cada um; nada na silver",
        origem=True,
        acao_cliente="escrever a definição de headcount e de vaga aberta usada no fechamento",
    ),
    Entrada(
        "FIN-03",
        "financeiro",
        "fatura de competência posterior ao encerramento do contrato",
        "Fatura depois do fim do contrato",
        "Receita reconhecida em contrato que não existe mais, ou encerramento lançado com data errada. Qualquer margem por contrato e mês sai errada nesses casos.",
        "`financeiro.fatura.competencia` posterior a `contrato.dt_encerramento`: {linhas} de {total} faturas ({pct}%), de dias a meses depois.",
        Tratamento.MARCAR,
        "marcar `q_fin_03`; a gold atribui a receita ao último mês vigente até o cliente dizer qual data está certa",
        origem=True,
        acao_cliente="dizer qual data está certa, a da fatura ou a do encerramento",
    ),
    Entrada(
        "FIN-04",
        "financeiro",
        "título a receber ABERTO com vencimento passado, que deveria estar ATRASADO",
        "Título vencido que continua aberto",
        "Inadimplência escondida do indicador de atraso.",
        "`financeiro.titulo_receber` com `status = 'ABERTO'` e `dt_vencimento` anterior à data de referência: {linhas} de {total} títulos.",
        Tratamento.DERIVAR,
        "a silver deriva `situacao_derivada` do título (em dia, vencido, pago em dia, pago com atraso) das datas e preserva `status`",
    ),
    Entrada(
        "FIN-05",
        "financeiro",
        "título pago com valor diferente do valor do título (desconto ou juros que o modelo não separa)",
        "Valor pago diferente do título",
        "A diferença entre valor e valor pago some do indicador de inadimplência se ninguém a separa.",
        "`financeiro.titulo_receber.valor_pago` diferente de `valor` em {linhas} de {total} títulos pagos, a maioria a menos.",
        Tratamento.DERIVAR,
        "a silver grava `diferenca_pagamento` (pago menos devido) e marca `q_fin_05`",
    ),
    Entrada(
        "FIN-06",
        "financeiro",
        "posto com pessoa alocada no mês e sem item de fatura (meses já fechados)",
        "Alocação sem faturamento",
        "Custo sem receita correspondente: a margem do contrato fica subestimada no mês.",
        "posto com `alocacao` iniciada no mês e sem `fatura_item` na competência, em meses já fechados: {linhas} de {total} posto-mês.",
        Tratamento.MARCAR,
        "marcar `q_fin_06` no posto-mês",
        origem=True,
        acao_cliente="conferir o faturamento desses postos",
    ),
    Entrada(
        "FIN-07",
        "financeiro",
        "item cujo total não é postos mais extras menos descontos",
        "Item de fatura que não fecha",
        "Um item; ruído.",
        "`financeiro.fatura_item.valor_total` diferente de `valor_postos + valor_horas_extras - valor_descontos`: {linhas} de {total} itens.",
        Tratamento.MARCAR,
        "marcar `q_fin_07`",
    ),
    # treinamento e sst
    Entrada(
        "TSS-01",
        "treinamento_sst",
        "pessoa alocada com o exame (ASO) vencido na data de referência; prevalência mensal crescendo de zero em 2018 a cerca de 4% em 2025",
        "Pessoa em campo com ASO vencido",
        "Risco jurídico imediato para a Fictalent e para o cliente. O cliente declarou o defeito; a auditoria mostrou a história: a proporção de alocados sem exame válido era zero em 2018 e chegou a cerca de quatro por cento, porque a renovação do periódico não acompanhou o crescimento.",
        "alocados na data de referência sem `sst.aso` com `dt_validade` cobrindo o dia e `resultado <> 'INAPTO'`: {linhas} de {total} ({pct}%); ninguém está sem admissional; a prevalência mensal está no notebook.",
        Tratamento.DERIVAR,
        "a silver deriva, por pessoa e dia, `aso_valido` e `dias_para_vencer`; marca `q_tss_01` onde a pessoa está alocada sem exame válido; o painel alerta com 30 dias de antecedência",
        origem=True,
        acao_cliente="renovar os exames vencidos e criar o alerta de vencimento no processo",
    ),
    Entrada(
        "TSS-02",
        "treinamento_sst",
        "exame admissional feito depois da admissão",
        "Admissional depois da admissão",
        "A pessoa trabalhou sem exame; irregularidade que a fiscalização autua.",
        "`sst.aso` do tipo `ADMISSIONAL` com `dt_exame` posterior à `dt_admissao` do contrato: {linhas} de {total} admissionais ({pct}%), com atraso mediano de mês e meio.",
        Tratamento.DERIVAR,
        "a silver deriva `dias_de_atraso_do_admissional` e marca `q_tss_02`",
        origem=True,
        acao_cliente="o exame passa a ser condição da admissão no processo",
    ),
    Entrada(
        "TSS-03",
        "treinamento_sst",
        "CAT emitida mais de dois dias depois do acidente (o prazo legal é o primeiro dia útil)",
        "CAT fora do prazo",
        "Multa por CAT fora do prazo; metade das CATs.",
        "`sst.cat.dt_emissao` mais de dois dias depois de `acidente.dt_acidente`: {linhas} de {total} CATs ({pct}%).",
        Tratamento.DERIVAR,
        "a silver deriva `dias_alem_do_prazo_da_cat` e marca `q_tss_03`",
        origem=True,
        acao_cliente="emitir a CAT no primeiro dia útil",
    ),
    Entrada(
        "TSS-04",
        "treinamento_sst",
        "contrato ativo com programa legal (PGR, PCMSO ou LTCAT) vencido e sem substituto",
        "Programa legal vencido em contrato ativo",
        "Irregularidade em contrato em andamento; autuação para a Fictalent e para o cliente.",
        "`sst.programa_sst.dt_validade` anterior à data de referência, em contrato `ATIVO`, sem programa do mesmo tipo com validade posterior: {linhas} de {total} contratos ativos com programa ({pct}%).",
        Tratamento.DERIVAR,
        "a silver deriva `programa_vigente` por contrato e tipo e marca `q_tss_04`; o painel alerta",
        origem=True,
        acao_cliente="renovar os programas vencidos",
    ),
    Entrada(
        "TSS-05",
        "treinamento_sst",
        "turmas do mesmo curso, na mesma filial, começando no mesmo dia: paralelas legítimas ou cadastro em duplicidade",
        "Turmas que podem ser a mesma turma",
        "Turma duplicada dobra o custo de treinamento no rateio e o número de treinados no indicador.",
        "`treinamento.turma` em grupos de mesmo `curso_id`, `filial_id` e `dt_inicio`: {linhas} de {total} turmas ({pct}%).",
        Tratamento.PEDIR,
        "marcar `q_tss_05`; nunca fundir",
        origem=True,
        acao_cliente="confirmar se são turmas paralelas",
    ),
    Entrada(
        "TSS-06",
        "treinamento_sst",
        "pessoa alocada sem certificado válido de curso obrigatório da função",
        "Curso obrigatório sem certificado válido",
        "Exigência de norma descoberta em campo; pequena em número.",
        "alocados na data de referência com `curso_funcao.fl_obrigatorio` e sem `certificado` válido do curso: {linhas} de {total} exigências ({pct}%).",
        Tratamento.DERIVAR,
        "a silver deriva `certificado_valido` por pessoa e curso obrigatório e marca `q_tss_06`; o painel alerta",
        origem=True,
        acao_cliente="treinar quem está descoberto",
    ),
    # seguranca
    Entrada(
        "SEG-01",
        "seguranca",
        "ação registrada na trilha sem permissão vigente do perfil do usuário naquele dia (a maioria exportações)",
        "Ação sem permissão vigente",
        "Ou o controle de acesso do sistema falha, ou o perfil foi concedido depois do fato e retroagido. A maioria são exportações de dado pessoal, o caso sensível pela LGPD.",
        "`seguranca.log_auditoria` com evento cuja `acao` no `modulo` não era permitida por nenhum perfil vigente do usuário no dia: {linhas} de {total} eventos ({pct}%).",
        Tratamento.MARCAR,
        "marcar `q_seg_01`; a auditoria de acesso da v1.0.0 lista por usuário e perfil",
        origem=True,
        acao_cliente="explicar os casos e revisar o controle de acesso",
    ),
    Entrada(
        "SEG-02",
        "seguranca",
        "usuário sem vínculo com a tabela de colaboradores (a retaguarda não está modelada como colaborador)",
        "Usuário sem colaborador",
        "A trilha diz o login mas não diz quem é a pessoa, em que setor e filial está e se ainda trabalha na empresa.",
        "`seguranca.usuario.colaborador_id` nulo em {linhas} de {total} usuários: a retaguarda não está em `pessoas.colaborador`, que só tem quem vai a campo.",
        Tratamento.MANTER,
        "nada na silver; a auditoria de acesso usa o login; a modelagem da retaguarda é decisão do cliente",
        origem=True,
        acao_cliente="modelar a retaguarda como colaborador, ou aceitar e documentar",
    ),
    Entrada(
        "SEG-03",
        "seguranca",
        "evento posterior ao último acesso registrado do usuário",
        "Último acesso desatualizado",
        "O campo de último acesso não é confiável como indicador de atividade.",
        "`seguranca.log_auditoria.dt_evento` posterior a `usuario.ultimo_acesso`: {linhas} de {total} eventos.",
        Tratamento.MANTER,
        "a gold deriva o último acesso da trilha, não do campo",
    ),
]


# A decisão sobre cada entrada, com data. Toda entrada nasce `proposta`; o que está aqui é o que
# o Tiago decidiu, no papel de cliente do caso. Em 24/09/2026 as 40 foram aprovadas como
# propostas. As de tratamento `pedir` ficam aprovadas como marcação: a resposta que num cliente
# real viria de quem opera (a regra do rateio, a definição de headcount, a convenção da hora
# noturna, se o par é duplicidade) só o gerador conhece aqui, e a auditoria às cegas não o
# consulta; a silver marca e não inventa a regra, e a gold mostra os dois números lado a lado.
DECISOES: dict[str, str] = {
    "CAD-01": "aprovada",  # 24/09/2026
    "CAD-02": "aprovada",  # 24/09/2026
    "COM-01": "aprovada",  # 24/09/2026
    "COM-02": "aprovada",  # 24/09/2026
    "COM-03": "aprovada",  # 24/09/2026
    "ATS-01": "aprovada",  # 24/09/2026
    "ATS-02": "aprovada",  # 24/09/2026
    "ATS-03": "aprovada",  # 24/09/2026
    "ATS-04": "aprovada",  # 24/09/2026
    "ATS-05": "aprovada",  # 24/09/2026
    "ATS-06": "aprovada",  # 24/09/2026
    "ATS-07": "aprovada",  # 24/09/2026
    "ATS-08": "aprovada",  # 24/09/2026
    "PES-01": "aprovada",  # 24/09/2026
    "PES-02": "aprovada",  # 24/09/2026
    "PES-03": "aprovada",  # 24/09/2026
    "PES-04": "aprovada",  # 24/09/2026
    "PON-01": "aprovada",  # 24/09/2026
    "PON-02": "aprovada",  # 24/09/2026
    "PON-03": "aprovada",  # 24/09/2026
    "PON-04": "aprovada",  # 24/09/2026
    "FOL-01": "aprovada",  # 24/09/2026
    "FOL-02": "aprovada",  # 24/09/2026
    "FOL-03": "aprovada",  # 24/09/2026
    "FIN-01": "aprovada",  # 24/09/2026
    "FIN-02": "aprovada",  # 24/09/2026
    "FIN-03": "aprovada",  # 24/09/2026
    "FIN-04": "aprovada",  # 24/09/2026
    "FIN-05": "aprovada",  # 24/09/2026
    "FIN-06": "aprovada",  # 24/09/2026
    "FIN-07": "aprovada",  # 24/09/2026
    "TSS-01": "aprovada",  # 24/09/2026
    "TSS-02": "aprovada",  # 24/09/2026
    "TSS-03": "aprovada",  # 24/09/2026
    "TSS-04": "aprovada",  # 24/09/2026
    "TSS-05": "aprovada",  # 24/09/2026
    "TSS-06": "aprovada",  # 24/09/2026
    "SEG-01": "aprovada",  # 24/09/2026
    "SEG-02": "aprovada",  # 24/09/2026
    "SEG-03": "aprovada",  # 24/09/2026
}
ENTRADAS = [replace(e, situacao=DECISOES.get(e.codigo, e.situacao)) for e in ENTRADAS]


def registros() -> dict[tuple[str, str], Achado]:
    """Os achados gravados, pela chave (domínio, texto do achado)."""
    return {(a.dominio, a.achado): a for a in achados.carregar()}


def casar() -> list[tuple[Entrada, Achado]]:
    """Cada entrada com o seu achado. Falha se uma entrada não tem achado ou um achado com
    severidade não tem entrada: o catálogo e os registros andam juntos."""
    gravados = registros()
    pares = []
    sem_registro = []
    for entrada in ENTRADAS:
        achado = gravados.get((entrada.dominio, entrada.achado))
        if achado is None:
            sem_registro.append(entrada.codigo)
        else:
            pares.append((entrada, achado))
    catalogados = {(e.dominio, e.achado) for e in ENTRADAS}
    sem_entrada = [
        f"{a.dominio}: {a.achado[:60]}"
        for a in gravados.values()
        if a.severidade != "nenhuma" and (a.dominio, a.achado) not in catalogados
    ]
    if sem_registro or sem_entrada:
        raise ValueError(
            f"entradas sem achado gravado: {sem_registro}; achados sem entrada: {sem_entrada}"
        )
    return pares


def _numero(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _pct(a: Achado) -> str:
    return f"{a.pct:.2f}".replace(".", ",")


def _detalhe(entrada: Entrada, achado: Achado) -> str:
    return entrada.detalhe.format(
        linhas=_numero(achado.linhas), total=_numero(achado.total), pct=_pct(achado)
    )


def gerar_markdown() -> str:
    """O documento do catálogo, gerado dos objetos e dos registros."""
    pares = casar()
    todos = achados.carregar()
    ordem = {s: i for i, s in enumerate(achados.SEVERIDADES)}
    pares.sort(key=lambda p: (ordem[p[1].severidade], -p[1].pct, p[0].codigo))
    por_severidade = {
        s: [p for p in pares if p[1].severidade == s] for s in ("alta", "media", "baixa")
    }
    nomes = {"alta": "alta", "media": "média", "baixa": "baixa"}
    nao_tratados = [a for a in todos if a.severidade == "nenhuma"]
    situacoes: dict[str, int] = {}
    for entrada, _ in pares:
        situacoes[entrada.situacao] = situacoes.get(entrada.situacao, 0) + 1

    linhas: list[str] = []
    w = linhas.append
    w('<a id="topo"></a>\n')
    w("# Catálogo de achados · o que a auditoria achou e o que a silver vai fazer\n")
    w("<!-- nav:start -->")
    w(
        "[Home](../README.md) | [Auditoria (notebooks)](../notebooks/auditoria/README.md) | "
        "[← Ingestão](11_ingestao.md) | [Bibliografia →](bibliografia.md)"
    )
    w("<!-- nav:end -->\n")
    w(
        "> **Arquivo gerado** por `python -m rh_fictalent.auditoria --catalogo` a partir de "
        "`src/rh_fictalent/auditoria/catalogo.py` (as entradas, com as duas redações e a regra proposta) "
        "e de `dados/auditoria/*.json` (os achados que os notebooks gravaram, com linhas, total e fração). "
        "Não edite à mão: mude a entrada ou refaça a auditoria e gere de novo. O catálogo é a decisão sobre "
        "cada achado: o notebook descobre, o catálogo decide, a silver executa. Toda entrada nasce como "
        "**proposta**; a silver só implementa o que estiver **aprovado**, e a aprovação é registrada na "
        "própria entrada (`situacao`), com data no log de decisões do projeto."
    )
    w("")
    total = len(pares)
    w(
        f"Estado: **{total} achados com severidade** ({len(por_severidade['alta'])} altos, "
        f"{len(por_severidade['media'])} médios, {len(por_severidade['baixa'])} baixos) e "
        f"**{len(nao_tratados)} registros que dizem o que não se trata**; situação das entradas: "
        + ", ".join(f"{n} {s}" for s, n in sorted(situacoes.items()))
        + "."
    )
    w("")
    w("## 1. Os cinco verbos, e o que a silver nunca faz\n")
    w(
        "Cada achado recebe um tratamento, e há só cinco. **Marcar**: a linha ganha uma coluna booleana "
        "`q_<codigo>` e nada muda no valor; é o tratamento padrão, porque a prova de que algo foi "
        "tratado é poder achá-lo depois. **Derivar**: a silver calcula uma coluna nova a partir das "
        "datas ou das partes (a situação de um contrato a partir das vigências, os dias além de um "
        "prazo) e preserva a coluna original. **Conformar**: o valor ganha forma canônica (a grafia de "
        "um nome) e o original fica em `<coluna>_original`. **Manter**: nada na silver; o achado vira "
        "indicador na gold ou alerta no painel. **Pedir**: a regra depende de uma resposta do cliente "
        "(qual convenção, qual definição, se é ou não a mesma pessoa); até a resposta, marcar."
    )
    w("")
    w(
        "O que a silver **nunca** faz, por decisão de método: não funde cadastro (a autoridade sobre o "
        "cadastro é do cliente; duplicidade se marca e se agrupa); não preenche ausência (inventar valor "
        "cria dado que ninguém coletou e apaga o achado); não apaga linha (a bronze é espelho e a silver "
        "conforma no mesmo grão); não corrige valor na origem (a correção é do cliente, e a coluna "
        "`origem` de cada entrada diz quando ela é necessária). Toda regra é idempotente: reprocessar a "
        "carga dá o mesmo resultado."
    )
    w("")
    w("## 2. As seis declarações do cliente\n")
    w(
        "O [`docs/02`](02_entendimento_dados.md), seção 11, lista o que o cliente já sabia que existia. "
        "A auditoria testou cada uma como hipótese, sem consultar a resposta, e as seis se confirmaram. "
        "A tabela lê os registros."
    )
    w("")
    w("| declaração | achados que a testaram | veredito |")
    w("|---|---|---|")
    com_declaracao = [a for a in todos if a.declaracao]
    for texto in sorted({a.declaracao for a in com_declaracao}):
        grupo = [a for a in com_declaracao if a.declaracao == texto]
        codigos = [e.codigo for e, a in pares if a in grupo]
        veredito = "confirmada" if any(a.severidade != "nenhuma" for a in grupo) else "refutada"
        w(
            f"| {texto} | {', '.join(codigos) or 'só registros de severidade nenhuma'} | **{veredito}** |"
        )
    w("")
    w("## 3. Os achados, por severidade\n")
    for sev in ("alta", "media", "baixa"):
        w(f"### Severidade {nomes[sev]}\n")
        w("| código | achado | tabela | linhas atingidas | tratamento | situação |")
        w("|---|---|---|---|---|---|")
        for entrada, achado in por_severidade[sev]:
            w(
                f"| [{entrada.codigo}](#{entrada.codigo.lower()}) | {entrada.titulo} | `{achado.tabela}` | "
                f"{_numero(achado.linhas)} de {_numero(achado.total)} ({_pct(achado)}%) | "
                f"{entrada.tratamento.value} | {entrada.situacao} |"
            )
        w("")
    w("## 4. Os achados, um a um\n")
    w(
        "Cada entrada tem as duas redações: a primeira para quem decide, a segunda para quem implementa. "
        "A evidência aponta o notebook e a seção em que o achado foi medido."
    )
    w("")
    dominios_nome = {
        "cadastro": "cadastro",
        "comercial": "comercial",
        "ats": "ats",
        "pessoas": "pessoas",
        "ponto": "ponto",
        "folha": "folha",
        "financeiro": "financeiro",
        "treinamento_sst": "treinamento e sst",
        "seguranca": "segurança",
    }
    notebooks = {
        "cadastro": "00_cadastro",
        "comercial": "01_comercial",
        "ats": "02_ats",
        "pessoas": "03_pessoas",
        "ponto": "04_ponto",
        "folha": "05_folha",
        "financeiro": "06_financeiro",
        "treinamento_sst": "07_treinamento_sst",
        "seguranca": "08_seguranca",
    }
    for dominio in dominios_nome:
        do_dominio = [(e, a) for e, a in pares if e.dominio == dominio]
        if not do_dominio:
            continue
        w(f"### {dominios_nome[dominio]}\n")
        for entrada, achado in sorted(do_dominio, key=lambda p: p[0].codigo):
            w(f'<a id="{entrada.codigo.lower()}"></a>\n')
            w(f"#### {entrada.codigo} · {entrada.titulo}\n")
            w(
                f"**Severidade:** {nomes[achado.severidade]} · **Onde:** `{achado.tabela}` (`{achado.coluna}`) · "
                f"**Linhas atingidas:** {_numero(achado.linhas)} de {_numero(achado.total)} ({_pct(achado)}%) · "
                f"**Evidência:** [`{notebooks[dominio]}`](../notebooks/auditoria/{notebooks[dominio]}.ipynb), seção {achado.secao}"
                + (
                    f" · **Declaração do cliente:** {achado.declaracao}"
                    if achado.declaracao
                    else ""
                )
            )
            w("")
            w(f"**Para quem decide:** {entrada.impacto}")
            w("")
            w(f"**Para quem implementa:** {_detalhe(entrada, achado)}")
            w("")
            w(f"**Regra proposta ({entrada.tratamento.value}):** {entrada.regra}.")
            w("")
            origem = f"sim: {entrada.acao_cliente}" if entrada.origem else "não"
            w(f"**Correção na origem:** {origem}. **Situação:** {entrada.situacao}.")
            w("")
    w("## 5. O que não se trata\n")
    w(
        "Os registros de severidade nenhuma: hipóteses refutadas (o defeito esperado não existe), regras "
        "de negócio que pareciam defeito no primeiro teste, pontos fortes e os dois defeitos do próprio "
        "pipeline, já corrigidos. Estão aqui para a silver não tratar como erro o que é regra."
    )
    w("")
    w("| domínio | tabela | registro | ação |")
    w("|---|---|---|---|")
    for a in nao_tratados:
        w(f"| {a.dominio} | `{a.tabela}` | {a.achado} | {a.acao} |")
    w("")
    w("## 6. Como este catálogo é mantido\n")
    w(
        "A entrada vive em `catalogo.py` e o número vive no registro do notebook; o documento junta os "
        "dois na geração, e um teste (`tests/test_catalogo.py`) garante que toda entrada casa com um "
        "achado gravado e que todo achado com severidade tem entrada. Achado novo na auditoria sem "
        "entrada reprova a esteira: o catálogo não fica para trás. A aprovação muda `situacao` para "
        "`aprovada`, `ajustada` (com a regra ajustada na própria entrada) ou `recusada`, com a data no "
        "log de decisões; a silver lê a situação e só implementa o aprovado."
    )
    w("")
    w("---\n")
    w("[Início](#topo)")
    return "\n".join(linhas) + "\n"


def gerar(destino: Path = DESTINO) -> Path:
    destino.write_text(gerar_markdown(), encoding="utf-8")
    return destino
