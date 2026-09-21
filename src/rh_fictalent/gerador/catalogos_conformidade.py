"""O conteúdo fixo da etapa 6: quem usa o sistema, o que cada perfil pode, cursos, exames, riscos.

As pessoas da retaguarda são inventadas (os três primeiros nomes são os do dossiê do caso). Os
prazos de cursos, exames e programas são aproximações plausíveis das normas regulamentadoras,
não consultoria de SST. Registros de conselho (CRM) têm formato obviamente fictício.
"""

from __future__ import annotations

from datetime import date

# ───────────────────────────── segurança ─────────────────────────────
PERFIS = (
    ("SOCIO", "Sócio"),
    ("GERENTE", "Gerente-geral"),
    ("COORDENADOR", "Coordenação de setor"),
    ("ASSISTENTE", "Assistente de setor"),
    ("FINANCEIRO", "Financeiro"),
    ("TI", "Tecnologia da informação"),
)
MODULOS = (
    "cadastro",
    "comercial",
    "ats",
    "pessoas",
    "ponto",
    "folha",
    "financeiro",
    "treinamento",
    "sst",
    "seguranca",
)
ACOES = ("LER", "CRIAR", "EDITAR", "EXCLUIR", "EXPORTAR")
_OPERACAO = ("ats", "pessoas", "ponto", "treinamento", "sst")
_TUDO_MENOS_EXCLUIR = ("LER", "CRIAR", "EDITAR", "EXPORTAR")
# perfil -> módulo -> ações permitidas; o que não está aqui é negado (a matriz grava os dois)
PODE: dict[str, dict[str, tuple[str, ...]]] = {
    "SOCIO": {m: ("LER", "EXPORTAR") for m in MODULOS if m != "seguranca"}
    | {"seguranca": ("LER",)},
    "GERENTE": {m: ("LER", "EXPORTAR") for m in MODULOS if m != "seguranca"}
    | {"cadastro": _TUDO_MENOS_EXCLUIR, "comercial": _TUDO_MENOS_EXCLUIR},
    "COORDENADOR": {m: _TUDO_MENOS_EXCLUIR for m in (*_OPERACAO, "cadastro", "comercial")}
    | {"ats": ACOES, "folha": ("LER",)},
    "ASSISTENTE": {m: _TUDO_MENOS_EXCLUIR for m in _OPERACAO}
    | {"cadastro": ("LER",), "comercial": ("LER",)},
    "FINANCEIRO": {"financeiro": _TUDO_MENOS_EXCLUIR, "folha": _TUDO_MENOS_EXCLUIR}
    | {m: ("LER",) for m in ("cadastro", "comercial", "pessoas", "ponto")},
    "TI": {m: ("LER",) for m in MODULOS} | {"seguranca": ACOES, "cadastro": ACOES},
}

DOMINIO_DE_EMAIL = "fictalent.example"
# (nome, setor, cargo, filial, entrada, saída); o cargo vira o perfil de acesso
USUARIOS: tuple[tuple[str, str, str, str, date, date | None], ...] = (
    ("Romeu Bastos Figueira", "DIRECAO", "SOCIO", "ATB", date(2018, 1, 2), None),
    ("Janaína Figueira Prado", "DIRECAO", "SOCIO", "ATB", date(2018, 1, 2), None),
    ("Sabrina Moura Teles", "RECRUTAMENTO", "COORDENADOR", "ATB", date(2018, 1, 2), None),
    ("Débora Nunes Carvalho", "RECRUTAMENTO", "ASSISTENTE", "ATB", date(2018, 1, 2), None),
    ("Marlene Souza Pires", "DP", "ASSISTENTE", "ATB", date(2018, 1, 2), None),
    ("Cláudio Reis Antunes", "FINANCEIRO", "FINANCEIRO", "ATB", date(2018, 1, 2), None),
    (
        "Tatiane Lopes Brandão",
        "RECRUTAMENTO",
        "ASSISTENTE",
        "ATB",
        date(2018, 6, 4),
        date(2020, 5, 29),
    ),
    ("Rafaela Campos Dias", "RECRUTAMENTO", "ASSISTENTE", "BRG", date(2019, 3, 11), None),
    ("Vanessa Ribeiro Lima", "DP", "ASSISTENTE", "BRG", date(2019, 3, 11), date(2023, 8, 31)),
    ("Eduardo Martins Rocha", "COMERCIAL", "ASSISTENTE", "ATB", date(2019, 5, 6), None),
    ("Priscila Almeida Couto", "RECRUTAMENTO", "ASSISTENTE", "ATB", date(2019, 8, 5), None),
    ("Jéssica Barros Leal", "DP", "ASSISTENTE", "ATB", date(2020, 10, 5), None),
    ("Bruno Teixeira Salles", "TI", "TI", "ATB", date(2021, 3, 1), None),
    ("Aline Ferraz Moreira", "SST", "ASSISTENTE", "ATB", date(2021, 6, 7), None),
    (
        "Camila Duarte Neves",
        "RECRUTAMENTO",
        "ASSISTENTE",
        "BRG",
        date(2021, 9, 13),
        date(2024, 11, 29),
    ),
    ("Patrícia Godoy Matos", "FINANCEIRO", "FINANCEIRO", "ATB", date(2022, 2, 7), None),
    (
        "Renata Cardoso Freire",
        "RECRUTAMENTO",
        "ASSISTENTE",
        "ATB",
        date(2022, 4, 4),
        date(2025, 3, 14),
    ),
    ("Gustavo Pereira Lins", "COMERCIAL", "ASSISTENTE", "ATB", date(2022, 5, 2), None),
    ("Letícia Amaral Pinho", "RECRUTAMENTO", "ASSISTENTE", "EXT", date(2022, 8, 1), None),
    ("Simone Vieira Aguiar", "DP", "ASSISTENTE", "EXT", date(2022, 8, 1), None),
    ("Fernanda Queiroz Bento", "DP", "ASSISTENTE", "BRG", date(2022, 10, 3), None),
    ("Larissa Monteiro Paz", "SST", "ASSISTENTE", "ATB", date(2023, 2, 6), None),
    (
        "Bianca Correia Luz",
        "RECRUTAMENTO",
        "ASSISTENTE",
        "EXT",
        date(2023, 3, 6),
        date(2025, 9, 30),
    ),
    ("Daniela Farias Rego", "DP", "ASSISTENTE", "ATB", date(2023, 5, 8), None),
    ("Michele Santana Cruz", "RECRUTAMENTO", "ASSISTENTE", "BRG", date(2023, 7, 3), None),
    ("Rodrigo Azevedo Maia", "FINANCEIRO", "FINANCEIRO", "ATB", date(2023, 9, 4), None),
    ("Natália Borges Sena", "DP", "ASSISTENTE", "BRG", date(2023, 9, 4), None),
    ("Viviane Pacheco Ramos", "RECRUTAMENTO", "ASSISTENTE", "ATB", date(2024, 1, 8), None),
    ("Carolina Mendes Vidal", "SST", "ASSISTENTE", "EXT", date(2024, 3, 4), date(2025, 12, 19)),
    ("Marcelo Guedes Prata", "COMERCIAL", "ASSISTENTE", "EXT", date(2024, 4, 1), None),
    ("Sueli Arantes Bueno", "DP", "ASSISTENTE", "EXT", date(2024, 6, 3), None),
    ("Kátia Rezende Motta", "RECRUTAMENTO", "ASSISTENTE", "BRG", date(2025, 1, 6), None),
    ("Sandro Lacerda Pinto", "TI", "TI", "ATB", date(2025, 2, 3), None),
    ("Elaine Coutinho Braga", "RECRUTAMENTO", "ASSISTENTE", "ATB", date(2025, 4, 7), None),
    ("Juliana Peixoto Sales", "RECRUTAMENTO", "ASSISTENTE", "EXT", date(2025, 10, 13), None),
    # as contratações de fevereiro e de maio de 2026, que não melhoram nenhum indicador (D5)
    ("Paula Medeiros Assis", "RECRUTAMENTO", "ASSISTENTE", "ATB", date(2026, 2, 2), None),
    ("Helena Siqueira Dorta", "DP", "ASSISTENTE", "ATB", date(2026, 2, 2), None),
    ("Isabela Furtado Reis", "SST", "ASSISTENTE", "ATB", date(2026, 2, 2), None),
    ("Yasmin Toledo Frade", "RECRUTAMENTO", "ASSISTENTE", "BRG", date(2026, 5, 4), None),
    ("Lorena Vasques Melo", "FINANCEIRO", "FINANCEIRO", "ATB", date(2026, 5, 4), None),
)
# (nome, desde, novo setor, novo cargo): a vigência do perfil anterior fecha na véspera
PROMOCOES = (
    ("Sabrina Moura Teles", date(2019, 3, 11), "DIRECAO", "GERENTE"),
    ("Débora Nunes Carvalho", date(2019, 3, 11), "RECRUTAMENTO", "COORDENADOR"),
    ("Marlene Souza Pires", date(2021, 2, 1), "DP", "COORDENADOR"),
    ("Eduardo Martins Rocha", date(2022, 3, 1), "COMERCIAL", "COORDENADOR"),
    ("Aline Ferraz Moreira", date(2022, 9, 1), "SST", "COORDENADOR"),
)
# quem cobre o setor quando ele ainda não tem ninguém (antes de 2021 o DP cuidava dos exames)
COBERTURA_DO_SETOR = {
    "SST": "DP",
    "COMERCIAL": "DIRECAO",
    "DP": "DIRECAO",
    "RECRUTAMENTO": "DIRECAO",
}

CHANCE_DE_LOGIN_NO_DIA = {"SOCIO": 0.35, "GERENTE": 0.95, "TI": 0.90}  # os demais: 0.93
CHANCE_DE_LOGIN_PADRAO = 0.93
# exportações por dia útil: (base, o quanto a degradação soma). É o "exporta e cruza à mão"
EXPORTACOES_POR_DIA = {
    "ASSISTENTE": (0.35, 0.90),
    "FINANCEIRO": (0.35, 0.90),
    "COORDENADOR": (0.25, 0.60),
    "GERENTE": (0.60, 1.60),
    "SOCIO": (0.02, 0.0),
    "TI": (0.02, 0.0),
}
# o que cada setor exporta: (módulo, tabela)
EXPORTA = {
    "RECRUTAMENTO": (("ats", "vaga"), ("ats", "candidatura"), ("ats", "entrevista")),
    "DP": (("ponto", "apontamento"), ("folha", "folha_item"), ("pessoas", "alocacao")),
    "COMERCIAL": (("comercial", "contrato"), ("comercial", "posto")),
    "FINANCEIRO": (("financeiro", "fatura"), ("financeiro", "titulo_receber")),
    "SST": (("sst", "aso"), ("treinamento", "certificado")),
    "TI": (("seguranca", "usuario"),),
}
EXPORTA["DIRECAO"] = tuple(
    t for s in ("RECRUTAMENTO", "DP", "COMERCIAL", "FINANCEIRO") for t in EXPORTA[s]
)

# ───────────────────────────── treinamento ─────────────────────────────
# (código, nome, tipo, carga horária, validade em meses, comprado de fornecedor, custo por pessoa)
CURSOS = (
    (
        "INTEGRA",
        "Integração e noções de segurança do trabalho",
        "COMPORTAMENTAL",
        4.0,
        None,
        False,
        6.0,
    ),
    ("NR06", "NR-06 Uso e conservação de EPI", "NR", 2.0, 12, False, 6.0),
    ("NR10", "NR-10 Segurança em instalações elétricas", "NR", 40.0, 24, True, 320.0),
    ("NR11", "NR-11 Operação de empilhadeira", "NR", 16.0, 12, True, 140.0),
    ("NR12", "NR-12 Segurança em máquinas e equipamentos", "NR", 8.0, 24, True, 85.0),
    ("NR35", "NR-35 Trabalho em altura", "NR", 8.0, 24, True, 95.0),
    ("DIRDEF", "Direção defensiva", "TECNICO", 8.0, 24, True, 90.0),
    ("BPF", "Boas práticas na manipulação de alimentos", "TECNICO", 8.0, 12, True, 70.0),
    ("ATEND", "Atendimento ao cliente", "COMPORTAMENTAL", 8.0, None, False, 12.0),
    ("LIDER", "Liderança de equipes operacionais", "COMPORTAMENTAL", 16.0, None, False, 18.0),
    ("EXCEL", "Excel para rotinas administrativas", "TECNICO", 12.0, None, False, 12.0),
)
FAMILIAS_COM_EPI = ("PRODUCAO", "LOGISTICA")
# curso -> funções (código); True = obrigatório para a função
CURSO_DA_FUNCAO: dict[str, tuple[tuple[str, bool], ...]] = {
    "NR06": (("S001", True), ("S004", True), ("S005", True)),  # mais as famílias com EPI
    "NR10": (("P010", True),),
    "NR11": (("L003", True),),
    "NR12": (("P002", True), ("P003", True), ("P004", True), ("P012", True)),
    "NR35": (("P008", True), ("P009", True), ("P010", True), ("L006", True)),
    "DIRDEF": (("L009", True), ("L007", False)),
    "BPF": (("C008", True), ("C009", True), ("S003", True)),
    "ATEND": tuple((f"C00{i}", False) for i in range(1, 8)) + (("A003", False), ("A006", False)),
    "LIDER": (("P011", False), ("L011", False)),
    "EXCEL": tuple((c, False) for c in ("A001", "A002", "A004", "A005", "A007", "L012")),
}
FORNECEDOR_DE_TREINAMENTO = "Centro de Treinamento NR Fictício Ltda"
INSTRUTORES_DO_FORNECEDOR = (
    "Instrutor Almir Tavares",
    "Instrutora Célia Varga",
    "Instrutor Ênio Lobato",
)
LOTACAO_DA_TURMA = 30
INTEGRACAO_VALE_POR_DIAS = 365  # quem volta em menos de um ano não refaz a integração
CHANCE_DE_REPROVAR = 0.015
# reciclagem: em dia (antes de vencer), atrasada, ou nunca; a degradação soma às duas últimas
RECICLAGEM_ATRASADA, RECICLAGEM_ATRASADA_NA_CRISE = 0.04, 0.40
RECICLAGEM_ESQUECIDA_NA_CRISE = 0.10
CHANCE_DE_TREINAMENTO_VENDIDO = 0.30  # por cliente e ano, quando há gente para formar turma
MINIMO_PARA_VENDER = 4

# ───────────────────────────── sst ─────────────────────────────
TIPOS_DE_EXAME = (
    ("ADMISSIONAL", None),
    ("PERIODICO", 12),
    ("MUDANCA_FUNCAO", None),
    ("RETORNO", None),
    ("DEMISSIONAL", None),
)
VALIDADE_DO_ASO_MESES = 12
RETORNO_A_PARTIR_DE_DIAS = 30  # afastamento de 30 dias ou mais pede exame de retorno
# o demissional é dispensado quando o último exame é recente (NR-7): risco comum e risco alto
DISPENSA_DO_DEMISSIONAL = {False: 135, True: 90}
APTO_COM_RESTRICAO = {"ADMISSIONAL": 0.03, "PERIODICO": 0.05, "RETORNO": 0.15, "DEMISSIONAL": 0.02}
# SST-01: parte dos dias alocados sem ASO válido. É o que o gerador conduz; 2024 e 2025 são régua
ASO_VENCIDO = {
    2018: 0.003,
    2019: 0.003,
    2020: 0.005,
    2021: 0.003,
    2022: 0.006,
    2023: 0.02,
    2024: 0.04,
    2025: 0.04,
    2026: 0.045,
}
ANO_EM_QUE_O_PERIODICO_PASSA_A_SER_ESQUECIDO = 2023
CHANCE_DE_ESQUECER_O_PERIODICO = 0.25  # entre os atrasados; o resto atrasa de 15 a 120 dias
CLINICAS = {
    "ATB": "Clínica Ocupacional Fictícia Atibaia Ltda",
    "BRG": "Clínica Ocupacional Fictícia Atibaia Ltda",
    "EXT": "Clínica Ocupacional Fictícia Extrema Ltda",
}
MEDICOS = {
    "Clínica Ocupacional Fictícia Atibaia Ltda": (
        "CRM/SP FIC-0101",
        "CRM/SP FIC-0102",
        "CRM/SP FIC-0103",
    ),
    "Clínica Ocupacional Fictícia Extrema Ltda": ("CRM/MG FIC-0201", "CRM/MG FIC-0202"),
}

# (tipo, validade em meses, responsável)
PROGRAMAS = (
    ("PGR", 24, "Otávio Brandão Luz, engenheiro de segurança do trabalho"),
    ("PCMSO", 12, "Helga Simões Prado, médica do trabalho"),
    ("LTCAT", 36, "Otávio Brandão Luz, engenheiro de segurança do trabalho"),  # só com risco alto
)
PROGRAMA_ATRASADO, PROGRAMA_ATRASADO_NA_CRISE = 0.03, 0.35
# riscos por família: (agente, grau); e os da função: (agente, grau, insalubre, periculosidade)
RISCOS_DA_FAMILIA = {
    "PRODUCAO": (("RUIDO", "MEDIO"), ("ERGONOMICO", "MEDIO")),
    "LOGISTICA": (("ERGONOMICO", "MEDIO"),),
    "COMERCIO": (("ERGONOMICO", "BAIXO"),),
    "ADMINISTRATIVO": (("ERGONOMICO", "BAIXO"),),
    "SERVICOS": (("ERGONOMICO", "BAIXO"),),
}
RISCOS_DA_FUNCAO = {
    "P003": (("QUIMICO", "ALTO", True, False),),
    "P007": (("QUIMICO", "ALTO", True, False),),
    "P012": (("CALOR", "ALTO", True, False),),
    "C008": (("FRIO", "MEDIO", True, False),),
    "S001": (("BIOLOGICO", "MEDIO", True, False),),
    "P010": (("ELETRICIDADE", "ALTO", False, True), ("ALTURA", "MEDIO", False, False)),
    "P008": (("ALTURA", "MEDIO", False, False),),
    "P009": (("ALTURA", "MEDIO", False, False),),
    "L006": (("ALTURA", "MEDIO", False, False),),
    "L001": (("POEIRA", "BAIXO", False, False),),
    "L004": (("POEIRA", "BAIXO", False, False),),
    "L008": (("POEIRA", "BAIXO", False, False),),
}

# acidentes: os com afastamento já existem em pessoas.afastamento; estes são os sem afastamento
ACIDENTES_SEM_AFASTAMENTO_POR_ANO = 0.002  # por pessoa alocada; a degradação soma até 100%
CHANCE_DE_TRAJETO = 0.2
GRAVIDADE_POR_DIAS = ((15, "LEVE"), (75, "MODERADA"), (10_000, "GRAVE"))
CAT_ATRASADA, CAT_ATRASADA_NA_CRISE = 0.05, 0.40  # o prazo legal é o primeiro dia útil seguinte
REABERTURA_A_PARTIR_DE_DIAS = 60
