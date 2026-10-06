# ruff: noqa: E501
"""A matriz de barramento da gold: que fatos existem, em que grão, e que dimensões eles dividem.

A matriz é o contrato do modelo dimensional (Kimball): cada linha é um processo do negócio que
vira tabela de fatos, cada coluna é uma dimensão conformada, e a marca no cruzamento diz que
aquele fato pode ser cortado por aquela dimensão. Duas tabelas de fatos que dividem uma
dimensão podem ser comparadas lado a lado; é isso que deixa a margem por cliente, o tempo de
preenchimento por cliente e as reclamações por cliente caberem na mesma tela.

Ela é escrita como código, como o catálogo de achados, por três motivos: o `docs/15` é gerado
daqui e não envelhece; os testes cobram que toda fonte exista na silver, que toda marca de
qualidade citada exista, que todo indicador do `docs/01` tenha fato e que as sete afirmações
dos donos tenham resposta; e a gold do card 7.2 é construída a partir destas declarações.

Nada aqui é dado: é desenho. A matriz é aprovada pelo Tiago antes de a gold existir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

DESTINO = Path(__file__).resolve().parents[3] / "docs" / "15_matriz_de_barramento.md"
SITUACAO = "aprovada pelo Tiago em 05/10/2026, como proposta"

# fontes que não são tabela da silver: entram no lake no card 7.2, com esquema
EXTERNAS = {
    "fontes.caged_movimentacao": "movimentação mensal do Novo CAGED (hoje em `dados/publicos/caged/movimentacao_mensal.csv`)",
}


class Tipo(StrEnum):
    TRANSACAO = "transação"
    ACUMULADO = "foto acumulada"
    PERIODICO = "foto periódica"
    CONSOLIDADO = "consolidado"


TIPOS = {
    Tipo.TRANSACAO: "uma linha por evento, que não muda depois de gravada",
    Tipo.ACUMULADO: "uma linha por coisa que tem começo, meio e fim (a vaga, a candidatura, o contrato), atualizada a cada marco, com uma data por marco",
    Tipo.PERIODICO: "uma linha por período (o mês), mesmo que nada tenha acontecido: é como se mede estoque, e headcount é estoque",
    Tipo.CONSOLIDADO: "fatos de processos diferentes levados ao mesmo grão e postos lado a lado; é onde receita e custo se encontram",
}

FAMILIAS = {
    "funil": "Funil de colocação",
    "carteira": "Carteira alocada",
    "rotatividade": "Rotatividade e absenteísmo",
    "financeiro": "Financeiro por unidade",
    "conformidade": "Compliance e risco",
    "acesso": "Acesso ao sistema",
}


@dataclass(frozen=True)
class Dimensao:
    nome: str
    o_que_e: str
    grao: str
    fontes: tuple[str, ...]
    atributos: tuple[str, ...]
    prioridade: int = 1
    nota: str = ""


@dataclass(frozen=True)
class Fato:
    nome: str
    processo: str
    familia: str
    tipo: Tipo
    grao: str
    dimensoes: dict[str, str]  # dimensão -> papéis ("abertura, fechamento"); vazio = um papel só
    medidas: tuple[str, ...]
    fontes: tuple[str, ...]
    marcas: tuple[str, ...] = ()  # marcas de qualidade da silver que o fato carrega
    prioridade: int = 1
    nota: str = ""


@dataclass(frozen=True)
class Indicador:
    familia: str
    nome: str
    fatos: tuple[str, ...]
    como: str


@dataclass(frozen=True)
class Afirmacao:
    codigo: str
    texto: str
    quem: str
    fatos: tuple[str, ...]
    como: str
    dimensoes: tuple[str, ...] = field(default=())


DIMENSOES: tuple[Dimensao, ...] = (
    Dimensao(
        "dim_data",
        "o calendário, dia a dia",
        "um dia, de 01/01/2018 a 31/12/2026",
        ("cadastro.feriado",),
        ("ano", "trimestre", "mês", "dia da semana", "dia útil", "feriado nacional"),
        nota="tem vários papéis no mesmo fato (abertura e fechamento da vaga, admissão e rescisão); o feriado é o nacional, porque o municipal depende de onde o posto está",
    ),
    Dimensao(
        "dim_mes",
        "o mês de competência",
        "um mês; é a `dim_data` enrolada no primeiro dia do mês",
        ("cadastro.feriado",),
        ("ano", "trimestre", "mês", "dias úteis do mês"),
    ),
    Dimensao(
        "dim_filial",
        "as unidades da Fictalent",
        "uma filial",
        ("cadastro.filial", "cadastro.endereco", "cadastro.municipio", "cadastro.regiao"),
        ("código", "nome", "matriz ou filial", "município", "região", "data de abertura"),
        nota="é a dimensão do isolamento por filial no warehouse (card 7.8)",
    ),
    Dimensao(
        "dim_cliente",
        "quem contrata a Fictalent",
        "um cliente",
        ("comercial.cliente", "cadastro.municipio", "cadastro.regiao"),
        (
            "razão social",
            "nome fantasia",
            "porte",
            "setor",
            "origem",
            "município",
            "região",
            "primeiro contrato",
            "ativo",
        ),
    ),
    Dimensao(
        "dim_contrato",
        "o contrato comercial",
        "um contrato",
        ("comercial.contrato", "comercial.contrato_aditivo"),
        (
            "número",
            "tipo de serviço",
            "status informado",
            "situação derivada",
            "vigência",
            "prazo de pagamento",
            "índice de reajuste",
        ),
        nota="carrega o status do sistema e a situação derivada das datas, lado a lado (COM-01)",
    ),
    Dimensao(
        "dim_posto",
        "o posto de trabalho contratado",
        "um posto",
        (
            "comercial.posto",
            "comercial.contrato",
            "cadastro.escala",
            "cadastro.endereco",
            "cadastro.municipio",
        ),
        ("turno", "escala", "posições contratadas", "vigência", "município do local de trabalho"),
        nota="hierarquia natural cliente, contrato, posto; receita e custo se encontram aqui",
    ),
    Dimensao(
        "dim_funcao",
        "a função exercida",
        "uma função",
        ("cadastro.funcao",),
        ("código", "nome", "família", "nível", "CBO", "insalubre", "periculosidade"),
    ),
    Dimensao(
        "dim_colaborador",
        "a pessoa contratada, sem identidade",
        "um colaborador",
        ("pessoas.colaborador", "ats.candidato", "ats.fonte_candidato", "cadastro.municipio"),
        (
            "ano de nascimento",
            "sexo",
            "escolaridade",
            "fonte de recrutamento",
            "município de residência",
            "primeira admissão",
        ),
        nota="sem nome, documento, chave de documento nem matrícula: a gold conta pessoas, não as identifica",
    ),
    Dimensao(
        "dim_candidato",
        "quem se candidatou, sem identidade",
        "um cadastro de candidato",
        ("ats.candidato", "ats.fonte_candidato", "cadastro.municipio"),
        (
            "fonte",
            "sexo",
            "escolaridade",
            "ano de nascimento",
            "município",
            "cadastro repetido",
            "cadastro canônico",
            "dado pessoal descartado",
        ),
        nota="o cadastro repetido (ATS-01) aponta o canônico: quem lê escolhe contar cadastros ou pessoas",
    ),
    Dimensao(
        "dim_motivo",
        "os motivos do cadastro",
        "um motivo",
        ("cadastro.motivo",),
        ("tipo", "código", "descrição", "grupo"),
        nota="um papel por fato: de desligamento, de reprovação, de perda de contrato, de fim de alocação, de ocorrência",
    ),
    Dimensao(
        "dim_escopo_mercado",
        "o recorte do mercado de trabalho público",
        "um território (UF ou município) e um grupo de atividade",
        ("fontes.caged_movimentacao",),
        ("território", "UF ou município", "grupo de atividade"),
        nota="vem do Novo CAGED, não do cliente",
    ),
    Dimensao(
        "dim_evento_folha",
        "as rubricas da folha",
        "um evento",
        ("folha.evento_folha",),
        ("código", "descrição", "tipo", "incidências"),
        prioridade=2,
    ),
    Dimensao(
        "dim_curso",
        "os cursos e treinamentos",
        "um curso",
        ("treinamento.curso",),
        ("código", "nome", "tipo", "carga horária", "validade"),
        prioridade=2,
    ),
    Dimensao(
        "dim_usuario",
        "quem acessa o sistema, sem identidade",
        "um usuário",
        ("seguranca.usuario", "seguranca.usuario_perfil", "seguranca.perfil"),
        ("chave do login", "perfil vigente", "filial", "ativo"),
        prioridade=2,
    ),
)

FATOS: tuple[Fato, ...] = (
    Fato(
        "fato_vaga",
        "abrir e preencher uma vaga",
        "funil",
        Tipo.ACUMULADO,
        "uma vaga",
        {
            "dim_data": "abertura, fechamento",
            "dim_filial": "",
            "dim_cliente": "",
            "dim_contrato": "",
            "dim_posto": "",
            "dim_funcao": "",
        },
        (
            "posições",
            "candidaturas recebidas",
            "aprovados",
            "dias até fechar",
            "preenchida",
            "cancelada",
            "dias em aberto",
        ),
        ("ats.vaga", "ats.requisicao", "ats.candidatura"),
    ),
    Fato(
        "fato_candidatura",
        "levar um candidato pelo funil",
        "funil",
        Tipo.ACUMULADO,
        "uma candidatura",
        {
            "dim_data": "inscrição, conclusão",
            "dim_candidato": "",
            "dim_filial": "",
            "dim_cliente": "",
            "dim_funcao": "",
            "dim_motivo": "reprovação ou desistência",
        },
        (
            "chegou a cada etapa (uma coluna por etapa)",
            "entrevistas",
            "faltou à entrevista",
            "aprovada",
            "admitida",
            "aprovada que não começou (no-show do primeiro dia)",
            "dias no funil",
            "custo médio da fonte",
        ),
        (
            "ats.candidatura",
            "ats.candidatura_etapa",
            "ats.entrevista",
            "ats.vaga",
            "ats.requisicao",
            "ats.etapa_funil",
            "ats.candidato",
            "ats.fonte_candidato",
            "pessoas.colaborador",
            "pessoas.contrato_trabalho",
        ),
        marcas=("q_ats_01",),
        nota="as etapas viram colunas, não linhas: a conversão de cada etapa é uma divisão entre duas colunas",
    ),
    Fato(
        "fato_alocacao",
        "alocar uma pessoa num posto",
        "carteira",
        Tipo.ACUMULADO,
        "uma alocação",
        {
            "dim_data": "início, fim",
            "dim_colaborador": "",
            "dim_posto": "",
            "dim_contrato": "",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_funcao": "",
            "dim_motivo": "fim da alocação",
        },
        (
            "dias alocado",
            "em substituição de outra alocação",
            "terminou em efetivação pelo cliente",
        ),
        (
            "pessoas.alocacao",
            "pessoas.contrato_trabalho",
            "pessoas.desligamento",
            "comercial.posto",
            "comercial.contrato",
        ),
        marcas=("q_fin_06", "q_tss_01", "q_tss_06"),
    ),
    Fato(
        "fato_posto_mes",
        "ocupar o posto, faturar e custear",
        "carteira",
        Tipo.CONSOLIDADO,
        "um posto num mês da vigência dele",
        {
            "dim_mes": "",
            "dim_posto": "",
            "dim_contrato": "",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_funcao": "",
        },
        (
            "posições contratadas",
            "pessoas no fim do mês",
            "pessoa-dias alocados",
            "posição-dias descobertos",
            "taxa de ocupação",
            "entradas",
            "saídas",
            "preço mensal vigente",
            "receita",
            "custo de pessoal",
            "margem",
            "margem percentual",
        ),
        (
            "comercial.posto",
            "comercial.posto_preco",
            "comercial.contrato",
            "pessoas.alocacao",
            "financeiro.fatura_item",
            "financeiro.fatura",
            "folha.rateio_custo",
            "ponto.apontamento",
        ),
        marcas=("q_fin_06", "q_fol_01"),
        nota="é a espinha da margem (`docs/04`, seção 4): o único lugar onde receita e custo estão no mesmo grão",
    ),
    Fato(
        "fato_contrato",
        "ganhar, manter e perder um contrato",
        "carteira",
        Tipo.ACUMULADO,
        "um contrato comercial",
        {
            "dim_data": "assinatura, início, fim da vigência, encerramento",
            "dim_contrato": "",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_motivo": "encerramento",
        },
        (
            "meses de vida",
            "encerrado",
            "prorrogações",
            "postos",
            "reclamações",
            "elogios",
            "avisos de rescisão",
            "receita total",
        ),
        (
            "comercial.contrato",
            "comercial.contrato_aditivo",
            "comercial.contrato_ocorrencia",
            "comercial.posto",
            "financeiro.fatura",
        ),
        marcas=("q_com_01",),
    ),
    Fato(
        "fato_vinculo",
        "admitir e desligar",
        "rotatividade",
        Tipo.ACUMULADO,
        "um contrato de trabalho",
        {
            "dim_data": "admissão, término previsto, rescisão",
            "dim_colaborador": "",
            "dim_filial": "",
            "dim_funcao": "",
            "dim_motivo": "desligamento",
        },
        (
            "dias de vínculo",
            "desligado",
            "tipo de desligamento",
            "saiu em até 90 dias",
            "dias além do prazo legal",
            "dias de atraso do lançamento",
            "salário base",
            "valor da rescisão",
        ),
        (
            "pessoas.contrato_trabalho",
            "pessoas.desligamento",
            "pessoas.contrato_trabalho_prorrogacao",
        ),
        marcas=("q_pes_01", "q_pes_02", "q_pes_03"),
    ),
    Fato(
        "fato_ponto_dia",
        "trabalhar o dia",
        "rotatividade",
        Tipo.TRANSACAO,
        "um colaborador num dia (um apontamento)",
        {
            "dim_data": "",
            "dim_colaborador": "",
            "dim_posto": "",
            "dim_contrato": "",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_funcao": "",
        },
        (
            "horas trabalhadas",
            "horas extras",
            "horas noturnas",
            "dia previsto",
            "falta",
            "falta injustificada",
            "atestado",
            "minutos de atraso",
        ),
        (
            "ponto.apontamento",
            "ponto.ocorrencia_ponto",
            "pessoas.alocacao",
            "comercial.posto",
            "comercial.contrato",
        ),
        marcas=("q_pon_01", "q_pon_03"),
        nota="as batidas (4,3 milhões) ficam na silver: o fato é o dia, e a batida é evidência dele",
    ),
    Fato(
        "fato_faturamento",
        "faturar o cliente",
        "financeiro",
        Tipo.TRANSACAO,
        "um item de fatura (a fatura de um posto num mês); fatura de recrutamento, sem posto, entra numa linha só",
        {
            "dim_mes": "competência",
            "dim_data": "emissão",
            "dim_cliente": "",
            "dim_contrato": "",
            "dim_posto": "",
            "dim_filial": "",
            "dim_funcao": "",
        },
        (
            "valor dos postos",
            "valor de horas extras",
            "descontos",
            "valor bruto",
            "impostos",
            "valor líquido",
            "dias trabalhados",
            "faltas",
        ),
        ("financeiro.fatura", "financeiro.fatura_item", "comercial.posto", "comercial.contrato"),
        marcas=("q_fin_03", "q_fin_07"),
    ),
    Fato(
        "fato_recebimento",
        "receber do cliente",
        "financeiro",
        Tipo.ACUMULADO,
        "um título a receber",
        {
            "dim_data": "vencimento, pagamento",
            "dim_mes": "competência da fatura",
            "dim_cliente": "",
            "dim_contrato": "",
            "dim_filial": "",
        },
        (
            "valor",
            "valor pago",
            "dias de atraso",
            "vencido e não pago",
            "diferença entre pago e devido",
        ),
        ("financeiro.titulo_receber", "financeiro.fatura", "comercial.contrato"),
        marcas=("q_fin_05",),
        nota="a situação vem das datas (FIN-04), não do status do sistema",
    ),
    Fato(
        "fato_custo_pessoal",
        "custear a pessoa alocada",
        "financeiro",
        Tipo.TRANSACAO,
        "o rateio do custo de um colaborador numa alocação num mês",
        {
            "dim_mes": "",
            "dim_colaborador": "",
            "dim_posto": "",
            "dim_contrato": "",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_funcao": "",
        },
        (
            "salário",
            "encargos",
            "provisões",
            "benefícios",
            "custo total",
            "diferença entre o rateio e a folha",
        ),
        ("folha.rateio_custo", "comercial.posto", "comercial.contrato"),
        marcas=("q_fol_01", "q_fol_03"),
    ),
    Fato(
        "fato_resultado_mes",
        "fechar o mês da filial",
        "financeiro",
        Tipo.CONSOLIDADO,
        "uma filial num mês",
        {"dim_mes": "", "dim_filial": ""},
        (
            "faturamento",
            "custo de pessoal",
            "impostos",
            "despesas",
            "resultado",
            "margem líquida",
            "pessoas alocadas",
            "vagas abertas",
            "clientes ativos",
            "faturamento informado",
            "custo informado",
            "headcount informado",
            "vagas abertas informadas",
            "diferença de cada par",
        ),
        (
            "financeiro.fatura",
            "folha.rateio_custo",
            "financeiro.imposto_apurado",
            "financeiro.titulo_pagar",
            "financeiro.consolidado_gerencial",
            "pessoas.alocacao",
            "pessoas.contrato_trabalho",
            "ats.vaga",
            "comercial.contrato",
            "cadastro.centro_custo",
        ),
        nota="a operação é a fonte da verdade e o consolidado da gerência fica ao lado, como série informada (FIN-01 e FIN-02); como imposto e despesa chegam à filial é regra a escrever e aprovar no card 7.2",
    ),
    Fato(
        "fato_ocorrencia",
        "ouvir o cliente",
        "conformidade",
        Tipo.TRANSACAO,
        "uma ocorrência de contrato (reclamação, elogio, advertência, aviso de rescisão)",
        {
            "dim_data": "",
            "dim_cliente": "",
            "dim_contrato": "",
            "dim_posto": "",
            "dim_filial": "",
            "dim_motivo": "ocorrência",
        },
        ("ocorrência", "tipo"),
        ("comercial.contrato_ocorrencia", "comercial.contrato"),
        marcas=("q_com_03",),
    ),
    Fato(
        "fato_conformidade_mes",
        "manter a operação regular",
        "conformidade",
        Tipo.PERIODICO,
        "um posto no último dia de cada mês",
        {
            "dim_mes": "",
            "dim_posto": "",
            "dim_contrato": "",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_funcao": "",
        },
        (
            "pessoas alocadas",
            "com ASO vencido",
            "com ASO a vencer em 30 dias",
            "com curso obrigatório faltando",
            "temporários além do prazo legal",
            "temporários a 30 dias do prazo",
            "programas legais vencidos",
        ),
        (
            "pessoas.alocacao",
            "pessoas.contrato_trabalho",
            "pessoas.contrato_trabalho_prorrogacao",
            "sst.aso",
            "sst.programa_sst",
            "treinamento.certificado",
            "treinamento.turma_participante",
            "treinamento.turma",
            "treinamento.curso_funcao",
            "comercial.posto",
            "comercial.contrato",
        ),
        nota="é a série mensal das marcas com prazo, que na silver só valem na data de referência; conta pessoas por posto e não leva chave de pessoa",
    ),
    Fato(
        "fato_mercado_mes",
        "o mercado de trabalho da região",
        "funil",
        Tipo.PERIODICO,
        "um território e um grupo de atividade num mês",
        {"dim_mes": "", "dim_escopo_mercado": ""},
        ("admissões", "desligamentos", "saldo"),
        ("fontes.caged_movimentacao",),
        nota="não é dado do cliente: é a régua de fora, para separar o que é mercado do que é serviço",
    ),
    Fato(
        "fato_folha",
        "pagar a folha",
        "financeiro",
        Tipo.TRANSACAO,
        "um colaborador, um mês, um evento da folha",
        {"dim_mes": "", "dim_colaborador": "", "dim_filial": "", "dim_evento_folha": ""},
        ("valor", "referência"),
        ("folha.folha_item", "folha.folha_competencia", "folha.evento_folha"),
        prioridade=2,
    ),
    Fato(
        "fato_despesa",
        "pagar fornecedor, encargo e imposto",
        "financeiro",
        Tipo.ACUMULADO,
        "um título a pagar",
        {"dim_mes": "competência", "dim_data": "vencimento, pagamento", "dim_filial": ""},
        ("valor", "tipo", "dias de atraso"),
        ("financeiro.titulo_pagar", "financeiro.fornecedor", "cadastro.centro_custo"),
        prioridade=2,
    ),
    Fato(
        "fato_afastamento",
        "afastar-se do trabalho",
        "rotatividade",
        Tipo.ACUMULADO,
        "um afastamento, sem chave de pessoa",
        {
            "dim_data": "início, fim",
            "dim_cliente": "",
            "dim_filial": "",
            "dim_funcao": "",
            "dim_motivo": "afastamento",
        },
        ("dias afastado", "tipo", "grupo da CID"),
        (
            "pessoas.afastamento",
            "pessoas.alocacao",
            "pessoas.contrato_trabalho",
            "comercial.posto",
            "comercial.contrato",
        ),
        marcas=("q_pes_04",),
        prioridade=2,
        nota="dado de saúde: entra para o agregado, sem a dimensão de colaborador",
    ),
    Fato(
        "fato_saude_ocupacional",
        "examinar e registrar acidente",
        "conformidade",
        Tipo.TRANSACAO,
        "um exame (ASO) ou um acidente, sem chave de pessoa",
        {"dim_data": "", "dim_cliente": "", "dim_filial": "", "dim_funcao": ""},
        (
            "exame",
            "dias de atraso do admissional",
            "acidente",
            "gravidade",
            "dias de afastamento",
            "dias além do prazo da CAT",
        ),
        (
            "sst.aso",
            "sst.tipo_exame",
            "sst.acidente",
            "sst.cat",
            "pessoas.alocacao",
            "pessoas.contrato_trabalho",
            "comercial.posto",
            "comercial.contrato",
        ),
        marcas=("q_tss_02", "q_tss_03"),
        prioridade=2,
        nota="dado de saúde: entra para o agregado, sem a dimensão de colaborador",
    ),
    Fato(
        "fato_treinamento",
        "treinar e certificar",
        "conformidade",
        Tipo.TRANSACAO,
        "a participação de um colaborador numa turma",
        {
            "dim_data": "início da turma",
            "dim_colaborador": "",
            "dim_filial": "",
            "dim_cliente": "",
            "dim_curso": "",
        },
        ("presença", "aprovado", "certificado emitido", "custo da turma rateado por participante"),
        (
            "treinamento.turma_participante",
            "treinamento.turma",
            "treinamento.certificado",
            "treinamento.curso",
        ),
        marcas=("q_tss_05",),
        prioridade=2,
    ),
    Fato(
        "fato_acesso",
        "usar o sistema",
        "acesso",
        Tipo.TRANSACAO,
        "um evento da trilha de auditoria do sistema",
        {"dim_data": "", "dim_usuario": "", "dim_filial": ""},
        ("evento", "módulo", "ação", "sem permissão vigente"),
        ("seguranca.log_auditoria", "seguranca.usuario"),
        marcas=("q_seg_01",),
        prioridade=2,
        nota="serve às consultas de auditoria da v1.0.0",
    ),
)

INDICADORES: tuple[Indicador, ...] = (
    Indicador(
        "funil", "vagas abertas, preenchidas e canceladas", ("fato_vaga",), "contagem por situação"
    ),
    Indicador("funil", "fill rate", ("fato_vaga",), "posições preenchidas sobre posições abertas"),
    Indicador(
        "funil",
        "time to fill por vaga, cliente e filial",
        ("fato_vaga",),
        "dias entre a abertura e o fechamento das vagas preenchidas",
    ),
    Indicador(
        "funil",
        "conversão de cada etapa",
        ("fato_candidatura",),
        "quem chegou à etapa seguinte sobre quem chegou à etapa",
    ),
    Indicador(
        "funil",
        "no-show de entrevista e de primeiro dia",
        ("fato_candidatura",),
        "faltou à entrevista; aprovada que não começou",
    ),
    Indicador(
        "funil",
        "fonte do candidato",
        ("fato_candidatura",),
        "conversão por fonte, pela `dim_candidato`",
    ),
    Indicador(
        "funil",
        "custo por contratação",
        ("fato_candidatura",),
        "custo médio da fonte somado nas candidaturas, sobre as admitidas",
    ),
    Indicador(
        "carteira",
        "headcount alocado por cliente, posto e filial",
        ("fato_posto_mes",),
        "pessoas no fim do mês",
    ),
    Indicador(
        "carteira",
        "entradas e saídas",
        ("fato_posto_mes", "fato_alocacao"),
        "alocações que começam e terminam no mês",
    ),
    Indicador(
        "carteira",
        "taxa de ocupação dos postos",
        ("fato_posto_mes",),
        "pessoa-dias alocados sobre posição-dias contratados",
    ),
    Indicador(
        "carteira",
        "dias de posto descoberto",
        ("fato_posto_mes",),
        "posição-dias sem ninguém alocado",
    ),
    Indicador(
        "carteira",
        "efetivações pelo cliente",
        ("fato_alocacao",),
        "alocações que terminaram em efetivação",
    ),
    Indicador(
        "rotatividade",
        "turnover total, voluntário e involuntário",
        ("fato_vinculo", "fato_posto_mes"),
        "desligamentos do mês, por tipo, sobre o headcount médio",
    ),
    Indicador(
        "rotatividade",
        "turnover nos primeiros 90 dias",
        ("fato_vinculo",),
        "admitidos no mês que saíram em até 90 dias, sobre os admitidos",
    ),
    Indicador(
        "rotatividade",
        "absenteísmo por posto",
        ("fato_ponto_dia",),
        "faltas e atestados sobre os dias previstos",
    ),
    Indicador(
        "rotatividade",
        "horas extras e banco de horas",
        ("fato_ponto_dia",),
        "horas extras sobre horas trabalhadas; o saldo do banco de horas fica na silver até o painel pedir",
    ),
    Indicador(
        "financeiro",
        "faturamento por cliente, posto e filial",
        ("fato_faturamento",),
        "valor bruto por competência",
    ),
    Indicador(
        "financeiro",
        "custo por cabeça",
        ("fato_custo_pessoal",),
        "salário, encargos, provisões e benefícios sobre as pessoas do mês",
    ),
    Indicador(
        "financeiro",
        "margem por posto e por contrato",
        ("fato_posto_mes",),
        "receita menos custo de pessoal, no posto e no mês",
    ),
    Indicador(
        "financeiro",
        "inadimplência",
        ("fato_recebimento",),
        "valor vencido e não pago sobre o valor vencido",
    ),
    Indicador(
        "financeiro",
        "ticket médio de recrutamento e seleção",
        ("fato_faturamento",),
        "valor das faturas sem posto sobre a quantidade delas",
    ),
    Indicador(
        "conformidade",
        "vencimento do prazo legal do temporário",
        ("fato_conformidade_mes", "fato_vinculo"),
        "temporários além do prazo e a 30 dias dele, mês a mês",
    ),
    Indicador(
        "conformidade",
        "ASO e exames vencidos",
        ("fato_conformidade_mes",),
        "pessoas alocadas com ASO vencido no fim do mês",
    ),
    Indicador(
        "conformidade",
        "treinamentos obrigatórios vencidos",
        ("fato_conformidade_mes",),
        "pessoas alocadas sem certificado válido de curso obrigatório",
    ),
    Indicador(
        "conformidade",
        "acidentes e CAT",
        ("fato_saude_ocupacional",),
        "acidentes por gravidade e CAT fora do prazo",
    ),
    Indicador(
        "conformidade",
        "reclamações por posto",
        ("fato_ocorrencia",),
        "ocorrências do tipo reclamação",
    ),
)

AFIRMACOES: tuple[Afirmacao, ...] = (
    Afirmacao(
        "D1",
        "A gente cresceu muito de 2022 a 2025.",
        "Romeu",
        ("fato_resultado_mes", "fato_posto_mes", "fato_vaga"),
        "a mesma série mensal em quatro medidas (receita, pessoas, clientes ativos, vagas): cresceu em quê, e até quando",
        ("dim_mes", "dim_filial"),
    ),
    Afirmacao(
        "D2",
        "Não sei se tenho lucro ou prejuízo.",
        "Romeu",
        ("fato_posto_mes", "fato_resultado_mes"),
        "margem por posto, contrato, cliente e filial ao longo do arco, e o resultado do mês por filial",
        ("dim_cliente", "dim_contrato", "dim_posto", "dim_filial"),
    ),
    Afirmacao(
        "D3",
        "Os clientes começaram a sair no fim de 2025.",
        "Romeu",
        ("fato_contrato", "fato_ocorrencia"),
        "a data de encerramento de cada contrato e a do primeiro aviso de rescisão: quando começou de fato, e em quais clientes",
        ("dim_cliente", "dim_contrato"),
    ),
    Afirmacao(
        "D4",
        "A queda é do mercado.",
        "Romeu",
        ("fato_mercado_mes", "fato_vaga", "fato_vinculo", "fato_ocorrencia", "fato_contrato"),
        "a série do mercado da região ao lado da série de qualidade (time to fill, turnover em 90 dias, reclamações) e da série de perda de contratos, com a defasagem medida em meses",
        ("dim_mes",),
    ),
    Afirmacao(
        "D5",
        "Contratar mais assistente resolveria.",
        "Romeu",
        ("fato_vaga", "fato_candidatura", "fato_vinculo"),
        "os indicadores do funil antes e depois das contratações de 2026",
        ("dim_data", "dim_filial"),
    ),
    Afirmacao(
        "D6",
        "Depois de 2022 os relatórios pararam de bater.",
        "Sabrina",
        ("fato_resultado_mes",),
        "o informado e o apurado lado a lado, por mês e filial, com a diferença de cada par",
        ("dim_mes", "dim_filial"),
    ),
    Afirmacao(
        "A1",
        "Cliente grande é sempre melhor.",
        "Janaína",
        ("fato_posto_mes", "fato_recebimento"),
        "margem e inadimplência pelo porte do cliente",
        ("dim_cliente",),
    ),
)

DECISOES: tuple[tuple[str, str], ...] = (
    (
        "A chave é o `id` da réplica",
        'Há uma fonte só, e as dimensões não guardam versões: o `id` do sistema do cliente já é estável e único. Chave substituta só onde não há `id` (a data, como AAAAMMDD, e o mês, como AAAAMM). Cada dimensão ganha a linha 0, "não se aplica", para o fato que não tem aquela dimensão (a fatura de recrutamento não tem posto).',
    ),
    (
        "Dimensão guarda o estado atual; a história mora no fato",
        "O sistema do cliente não versiona o cadastro do cliente nem da função, então a dimensão é do tipo 1. O que tem vigência de verdade (o preço do posto, o piso salarial, o perfil do usuário) entra no fato como medida do período, que é onde a pergunta acontece.",
    ),
    (
        "A gold conta pessoas e não as identifica",
        "As dimensões de pessoa não têm nome, documento, chave de documento nem matrícula. Os fatos de saúde (afastamento, exame, acidente) não têm dimensão de pessoa nenhuma: servem ao agregado por cliente, filial e função. É o que o `docs/05` promete.",
    ),
    (
        "A marca de qualidade viaja com o fato",
        "A silver marcou e não corrigiu; a gold leva a marca como coluna do fato. Quem lê decide contar com ou sem a linha marcada, e o painel pode mostrar os dois números. A gold não apaga o que a silver marcou.",
    ),
    (
        "A linha excluída fica na silver; a descartada entra",
        'A linha apagada no sistema do cliente não existe para o negócio e não vira fato. O candidato com dado pessoal descartado continua contando no funil, com os atributos de pessoa como "não informado".',
    ),
    (
        "O ano do arquivo é o da data de negócio",
        "Na bronze e na silver o arquivo é do ano em que a linha foi criada no sistema. Na gold o fato é particionado pelo ano da data principal dele (a competência, a admissão, o dia trabalhado), que é o que a pergunta usa.",
    ),
    (
        "Foto periódica vale no último dia do mês",
        "Headcount, ocupação e conformidade são estoque: a medida é a do último dia do mês. O mês corrente, incompleto, é medido na data de referência da carga e identificado como parcial.",
    ),
    (
        "Dois níveis de prioridade",
        "Os fatos de prioridade 1 respondem às sete afirmações e aos indicadores em destaque do `docs/01`, e são construídos no card 7.2. Os de prioridade 2 completam os módulos do painel e entram depois, na ordem em que o painel pedir.",
    ),
)

FORA = (
    "As batidas de ponto, uma a uma, e o saldo do banco de horas: ficam na silver, que já as tem conferidas.",
    "Dimensão com história (tipo 2): só faria sentido se o cliente passasse a versionar o cadastro, o que o sistema dele não faz.",
    "Indicador pré-calculado por tela: a gold entrega fatos e dimensões; a conta de cada indicador é do SQL analítico (card 7.3) e do painel.",
    "Previsão e modelo: risco de desistência, projeção de receita. São da trilha prevista (P.3), depois do painel.",
)


def dimensao(nome: str) -> Dimensao:
    return next(d for d in DIMENSOES if d.nome == nome)


def fato(nome: str) -> Fato:
    return next(f for f in FATOS if f.nome == nome)


# os nomes das tabelas não têm acento; o rótulo que o leitor vê, tem
_ACENTOS = {
    "mes": "mês",
    "funcao": "função",
    "alocacao": "alocação",
    "vinculo": "vínculo",
    "ocorrencia": "ocorrência",
    "saude": "saúde",
    "usuario": "usuário",
}


def _rotulo(nome: str) -> str:
    palavras = nome.removeprefix("dim_").removeprefix("fato_").split("_")
    return " ".join(_ACENTOS.get(p, p) for p in palavras)


def gerar_markdown() -> str:
    linhas: list[str] = []
    w = linhas.append
    p1 = [f for f in FATOS if f.prioridade == 1]
    p2 = [f for f in FATOS if f.prioridade == 2]
    w('<a id="topo"></a>\n')
    w("# Matriz de barramento · os fatos, as dimensões e o grão da gold\n")
    w("<!-- nav:start -->")
    w("[Home](../README.md) | [← Silver](14_silver.md) | [Bibliografia →](bibliografia.md)")
    w("<!-- nav:end -->\n")
    w(
        "> **Arquivo gerado** por `python -m rh_fictalent.gold --matriz` a partir de "
        "`src/rh_fictalent/gold/barramento.py`. Não edite à mão: mude a declaração e gere de novo. "
        "A matriz é o desenho do modelo dimensional, escrito antes de a gold existir: diz que "
        "tabelas de fatos haverá, o que é uma linha de cada uma e por quais dimensões cada uma pode "
        "ser cortada. É o documento que se aprova antes de construir, porque mudar o grão de um fato "
        "depois de pronto é refazer o fato.\n"
    )
    w(
        f"Situação: **{SITUACAO}**. São **{len(FATOS)} fatos** ({len(p1)} de prioridade 1 e "
        f"{len(p2)} de prioridade 2) e **{len(DIMENSOES)} dimensões**, cobrindo os "
        f"{len(INDICADORES)} indicadores do [Entendimento do Negócio](01_entendimento_negocio.md) "
        f"e as {len(AFIRMACOES)} afirmações dos donos.\n"
    )

    w("## 1. Como ler\n")
    w(
        "Um **fato** é uma tabela em que cada linha é algo que aconteceu ou uma medida tirada: uma "
        "vaga, um dia trabalhado, o mês de um posto. Uma **dimensão** é uma tabela pela qual o fato "
        "é cortado e descrito: o cliente, a filial, o mês. O **grão** é a frase que diz o que é uma "
        "linha do fato, e é a decisão mais importante do modelo: tudo o que o fato consegue responder "
        "sai dela.\n"
    )
    w(
        "Na matriz, cada linha é um fato e cada coluna é uma dimensão. Dois fatos com a marca na "
        "mesma coluna dividem aquela dimensão e podem ser postos lado a lado por ela: é assim que "
        "a margem, o tempo de preenchimento e as reclamações de um cliente cabem na mesma tela, "
        "vindos de três tabelas diferentes.\n"
    )
    w("Os fatos são de quatro tipos:\n")
    w("| tipo | o que é |\n|---|---|")
    for tipo, texto in TIPOS.items():
        w(f"| {tipo.value} | {texto} |")
    w("")

    w("## 2. A matriz\n")
    colunas = [d.nome for d in DIMENSOES]
    w("| fato | P | " + " | ".join(_rotulo(c) for c in colunas) + " |")
    w("|---|:-:|" + ":-:|" * len(colunas))
    for f in FATOS:
        marcas = " | ".join("●" if c in f.dimensoes else " " for c in colunas)
        w(f"| [{_rotulo(f.nome)}](#{f.nome}) | {f.prioridade} | {marcas} |")
    w("")
    w("A coluna P é a prioridade (seção 7). O nome de cada fato leva ao detalhe dele.\n")

    w("## 3. Os fatos, um a um\n")
    for chave, titulo in FAMILIAS.items():
        da_familia = [f for f in FATOS if f.familia == chave]
        if not da_familia:
            continue
        w(f"### {titulo}\n")
        for f in da_familia:
            w(f'<a id="{f.nome}"></a>\n')
            w(f"**`{f.nome}`** · {f.processo} · {f.tipo.value} · prioridade {f.prioridade}\n")
            w(f"- **Grão:** {f.grao}.")
            dims = ", ".join(
                f"`{d}`" + (f" ({papeis})" if papeis else "") for d, papeis in f.dimensoes.items()
            )
            w(f"- **Dimensões:** {dims}.")
            w(f"- **Medidas:** {'; '.join(f.medidas)}.")
            w(f"- **Vem de:** {', '.join(f'`{t}`' for t in f.fontes)}.")
            if f.marcas:
                w(
                    f"- **Marcas de qualidade que carrega:** {', '.join(f'`{m}`' for m in f.marcas)}."
                )
            if f.nota:
                w(f"- **Nota:** {f.nota}.")
            w("")

    w("## 4. As dimensões\n")
    w("| dimensão | o que é | uma linha é | atributos | P |\n|---|---|---|---|:-:|")
    for d in DIMENSOES:
        w(f"| `{d.nome}` | {d.o_que_e} | {d.grao} | {', '.join(d.atributos)} | {d.prioridade} |")
    w("")
    for d in DIMENSOES:
        if d.nota:
            w(f"- **`{d.nome}`:** {d.nota}.")
    w("")

    w("## 5. Dos indicadores aos fatos\n")
    w(
        "Cada indicador da seção 3 do [Entendimento do Negócio](01_entendimento_negocio.md), o "
        "fato de onde sai e como se calcula. Um teste reprova a matriz se um indicador ficar sem fato.\n"
    )
    w("| família | indicador | fato | como |\n|---|---|---|---|")
    for i in INDICADORES:
        w(
            f"| {FAMILIAS[i.familia]} | {i.nome} | {', '.join(f'`{x}`' for x in i.fatos)} | {i.como} |"
        )
    w("")

    w("## 6. As sete afirmações dos donos\n")
    w(
        "As afirmações da primeira reunião são o contrato da análise. Cada uma tem os fatos que a "
        'respondem; a resposta pode ser "confirma" ou "contradiz", e sai dos números, não da matriz.\n'
    )
    w("| # | afirmação | quem | fatos | como se responde |\n|---|---|---|---|---|")
    for a in AFIRMACOES:
        w(
            f'| {a.codigo} | "{a.texto}" | {a.quem} | {", ".join(f"`{x}`" for x in a.fatos)} | {a.como} |'
        )
    w("")

    w("## 7. Decisões de modelagem\n")
    for n, (titulo, texto) in enumerate(DECISOES, 1):
        w(f"**{n}. {titulo}.** {texto}\n")

    w("## 8. O que fica fora\n")
    for item in FORA:
        w(f"- {item}")
    w("")
    w("Fontes que ainda não estão no lake e entram no card 7.2, com esquema:\n")
    for nome, texto in EXTERNAS.items():
        w(f"- `{nome}`: {texto}.")
    w("\n---\n")
    w("[Início](#topo)")
    return "\n".join(linhas) + "\n"


def gerar(destino: Path = DESTINO) -> Path:
    destino.write_text(gerar_markdown(), encoding="utf-8", newline="\n")
    return destino
