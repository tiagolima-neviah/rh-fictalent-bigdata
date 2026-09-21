"""O conteúdo fixo do funil e das pessoas: etapas, fontes, nomes, escolaridade, documentos.

Pessoas são montadas por sorteio de listas de nomes comuns; CPF e PIS têm dígito verificador
válido (exceto os inválidos do catálogo de sujeira), e-mails usam o domínio reservado .example
e telefones têm o miolo 0000. Ninguém aqui existe.
"""

from __future__ import annotations

# (código, nome, ordem)
ETAPAS = (
    ("TRIAGEM", "Triagem de currículo", 1),
    ("ENTREVISTA_INTERNA", "Entrevista interna", 2),
    ("ENCAMINHAMENTO", "Encaminhamento ao cliente", 3),
    ("ENTREVISTA_CLIENTE", "Entrevista no cliente", 4),
    ("APROVACAO", "Aprovação e admissão", 5),
)
# (nome, custo médio por candidato captado, peso)
FONTES = (
    ("INDICACAO", 0.00, 0.22),
    ("PORTAL", 4.50, 0.30),
    ("REDES", 2.80, 0.20),
    ("BANCO_INTERNO", 0.00, 0.12),
    ("PRESENCIAL", 1.20, 0.16),
)
ESCOLARIDADES = (("FUNDAMENTAL", 0.22), ("MEDIO", 0.58), ("TECNICO", 0.12), ("SUPERIOR", 0.08))

# candidatos além dos contratados, por tipo de vaga (média), e quem passa de cada etapa
CANDIDATOS_POR_VAGA = {"TEMPORARIO": 12.0, "TERCEIRIZACAO": 15.0, "RECRUTAMENTO": 21.0}
PASSA_DA_TRIAGEM = 0.55
PASSA_DA_ENTREVISTA_INTERNA = 0.45  # entre os que compareceram
DESISTE_NA_ENTREVISTA_INTERNA = 0.08
PASSA_DO_ENCAMINHAMENTO = 0.80
ENTREVISTA_NO_CLIENTE = {"TEMPORARIO": 0.35, "TERCEIRIZACAO": 1.0, "RECRUTAMENTO": 1.0}
PASSA_DA_ENTREVISTA_NO_CLIENTE = 0.45
FATOR_DO_NO_SHOW_NO_CLIENTE = 0.6  # quem chega ao cliente falta menos
CHANCE_DE_CANDIDATO_NOVO = 0.20  # o resto já está no banco de candidatos da filial
MEMORIA_DO_BANCO = 4000  # só os candidatos mais recentes da filial voltam a ser chamados

REPROVACAO_NA_TRIAGEM = {
    "PERFIL": 0.40,
    "SEM_EXPERIENCIA": 0.30,
    "DISTANCIA": 0.15,
    "PRETENSAO": 0.15,
}
REPROVACAO_NA_ENTREVISTA = {"PERFIL": 0.55, "SEM_EXPERIENCIA": 0.25, "PRETENSAO": 0.20}
REPROVACAO_NO_ENCAMINHAMENTO = {"DOCUMENTACAO": 0.6, "EXAME_INAPTO": 0.4}

# sujeira de origem no cadastro de candidatos (catálogo do plano de sintetização)
CHANCE_DE_DUPLICADO = 0.036  # CAD-01: a mesma pessoa cadastrada de novo, com outra grafia
CHANCE_DE_CPF_INVALIDO = 0.008  # CAD-02
CHANCE_DE_NASCIMENTO_IMPOSSIVEL = 0.002  # CAD-03
# PES-01: admissão registrada depois do fato, por ano da admissão
ADMISSAO_RETROATIVA = {2018: 0.06, 2019: 0.06, 2020: 0.06, 2021: 0.06, 2022: 0.06, 2023: 0.085}
ADMISSAO_RETROATIVA_DEPOIS = 0.11

NOMES_F = (
    "Ana",
    "Maria",
    "Juliana",
    "Fernanda",
    "Patrícia",
    "Aline",
    "Camila",
    "Bruna",
    "Jéssica",
    "Letícia",
    "Larissa",
    "Vanessa",
    "Débora",
    "Carla",
    "Tatiane",
    "Priscila",
    "Renata",
    "Simone",
    "Cláudia",
    "Sandra",
    "Luciana",
    "Adriana",
    "Gabriela",
    "Rafaela",
    "Isabela",
    "Bianca",
    "Natália",
    "Daniela",
    "Eliane",
    "Rosana",
)
NOMES_M = (
    "José",
    "João",
    "Carlos",
    "Paulo",
    "Lucas",
    "Marcos",
    "Rafael",
    "Bruno",
    "Diego",
    "Felipe",
    "Rodrigo",
    "André",
    "Leandro",
    "Thiago",
    "Gustavo",
    "Anderson",
    "Fábio",
    "Marcelo",
    "Ricardo",
    "Eduardo",
    "Vinícius",
    "Matheus",
    "Gabriel",
    "Leonardo",
    "Alex",
    "Wesley",
    "Wellington",
    "Douglas",
    "Sérgio",
    "Luiz",
)
SOBRENOMES = (
    "Silva",
    "Santos",
    "Oliveira",
    "Souza",
    "Pereira",
    "Ferreira",
    "Alves",
    "Lima",
    "Gomes",
    "Ribeiro",
    "Carvalho",
    "Almeida",
    "Lopes",
    "Soares",
    "Fernandes",
    "Vieira",
    "Barbosa",
    "Rocha",
    "Dias",
    "Nascimento",
    "Andrade",
    "Moreira",
    "Nunes",
    "Marques",
    "Machado",
    "Mendes",
    "Freitas",
    "Cardoso",
    "Ramos",
    "Gonçalves",
    "Santana",
    "Teixeira",
    "Moraes",
    "Correia",
    "Pinto",
    "Araújo",
    "Campos",
    "Batista",
    "Reis",
    "Monteiro",
)
EMPRESAS_ANTERIORES = (
    "Indústria local",
    "Comércio varejista",
    "Transportadora",
    "Supermercado",
    "Construtora",
    "Restaurante",
    "Centro de distribuição",
    "Metalúrgica",
    "Serviços gerais",
    "Autônomo",
)

DOCUMENTOS = (("RG", "SSP"), ("CTPS", "MTE"))
FUNCOES_COM_CNH = ("L003", "L009")  # empilhadeira e caminhão
PARENTESCOS = (("FILHO", 0.72), ("CONJUGE", 0.20), ("ENTEADO", 0.05), ("MAE", 0.03))
# afastamentos: (tipo, motivo do cadastro, dias mín., dias máx., grupo da CID, peso)
AFASTAMENTOS = (
    ("ATESTADO", "DOENCA", 3, 15, "J00-J06", 0.30),
    ("ATESTADO", "DOENCA", 3, 15, "M50-M54", 0.28),
    ("ATESTADO", "ATESTADO_LONGO", 16, 60, "M50-M54", 0.12),
    ("ACIDENTE", "ACIDENTE_TRABALHO", 5, 90, "S60-S69", 0.07),
    ("LICENCA", "MATERNIDADE", 120, 120, None, 0.23),
)
AFASTAMENTOS_POR_ANO_DE_CASA = 0.30
