"""O conteúdo fixo da carteira comercial: de que são feitos os clientes fictícios.

Nomes de empresa são montados por sílabas sorteadas (não existem), contatos saem de listas de
nomes comuns, e-mails usam o domínio reservado .example e telefones têm o miolo 0000: nada
aqui aponta para empresa ou pessoa de verdade.
"""

from __future__ import annotations

# porte -> (peso no sorteio, posições-base mín., máx., posto mín., posto máx., markup mín., máx.)
PORTES = {
    "GRANDE": (0.12, 40, 120, 5, 30, 1.35, 1.42),
    "MEDIA": (0.38, 12, 40, 2, 12, 1.45, 1.55),
    "EPP": (0.35, 4, 12, 1, 5, 1.52, 1.62),
    "ME": (0.15, 1, 4, 1, 2, 1.58, 1.65),
}
FUNDADORES = ("GRANDE", "MEDIA", "MEDIA")  # os clientes âncora, que entram em janeiro de 2018

# setor -> (peso, famílias de função com peso, ramos para a razão social, contrato principal)
SETORES = {
    "INDUSTRIA": (
        0.35,
        {"PRODUCAO": 0.70, "LOGISTICA": 0.20, "SERVICOS": 0.10},
        ("Indústria de Plásticos", "Metalúrgica", "Embalagens", "Autopeças", "Alimentos"),
        {"TERCEIRIZACAO": 0.5, "TEMPORARIO": 0.5},
    ),
    "LOGISTICA": (
        0.30,
        {"LOGISTICA": 0.85, "ADMINISTRATIVO": 0.05, "SERVICOS": 0.10},
        ("Logística", "Transportes e Armazéns", "Centro de Distribuição", "Operações Logísticas"),
        {"TERCEIRIZACAO": 0.25, "TEMPORARIO": 0.75},
    ),
    "VAREJO": (
        0.22,
        {"COMERCIO": 0.70, "LOGISTICA": 0.25, "SERVICOS": 0.05},
        ("Supermercados", "Atacadista", "Lojas de Departamento", "Comércio Eletrônico"),
        {"TERCEIRIZACAO": 0.15, "TEMPORARIO": 0.85},
    ),
    "SERVICOS": (
        0.10,
        {"SERVICOS": 0.60, "ADMINISTRATIVO": 0.40},
        ("Facilities", "Serviços Hospitalares", "Hotelaria", "Administração de Condomínios"),
        {"TERCEIRIZACAO": 0.85, "TEMPORARIO": 0.15},
    ),
    "AGRO": (
        0.03,
        {"PRODUCAO": 0.60, "LOGISTICA": 0.40},
        ("Agroindustrial", "Flores e Plantas"),
        {"TERCEIRIZACAO": 0.3, "TEMPORARIO": 0.7},
    ),
}

# região comercial -> peso do sorteio de onde fica o cliente
REGIOES_DOS_CLIENTES = {
    "Região Bragantina": 0.45,
    "Sul de Minas · Fernão Dias": 0.20,
    "Jundiaí e região": 0.12,
    "Região de Campinas": 0.13,
    "Grande São Paulo": 0.10,
}
PESO_DA_CIDADE_DE_FILIAL = 8.0  # Atibaia, Bragança e Extrema concentram os clientes da região
MUNICIPIOS_DA_FILIAL_DE_BRAGANCA = (
    "Bragança Paulista",
    "Pinhalzinho",
    "Pedra Bela",
    "Socorro",
    "Tuiuti",
    "Vargem",
    "Joanópolis",
)

# família da função -> (turnos com peso, escalas com peso)
JORNADAS = {
    "PRODUCAO": (
        {"MANHA": 0.35, "TARDE": 0.30, "NOITE": 0.20, "REVEZAMENTO": 0.15},
        {"6X1": 0.55, "5X1": 0.25, "12X36": 0.10, "5X2": 0.10},
    ),
    "LOGISTICA": (
        {"MANHA": 0.40, "TARDE": 0.35, "NOITE": 0.25},
        {"6X1": 0.60, "12X36": 0.20, "5X2": 0.20},
    ),
    "COMERCIO": ({"COMERCIAL": 0.55, "TARDE": 0.45}, {"6X1": 0.85, "5X2": 0.15}),
    "ADMINISTRATIVO": ({"COMERCIAL": 1.0}, {"5X2": 1.0}),
    "SERVICOS": ({"COMERCIAL": 0.6, "NOITE": 0.4}, {"5X2": 0.5, "12X36": 0.4, "6X1": 0.1}),
}
PESO_DO_NIVEL = {"AUXILIAR": 5.0, "OPERADOR": 3.0, "TECNICO": 0.7, "LIDER": 0.3}

ORIGENS = {"INDICACAO": 0.45, "PROSPECCAO": 0.35, "SITE": 0.12, "LICITACAO": 0.03, "RETORNO": 0.05}
INDICES_DE_REAJUSTE = {"CONVENCAO": 0.6, "IPCA": 0.25, "INPC": 0.15}

# SLA por tipo de contrato: (indicador, meta, unidade)
SLAS = {
    "TEMPORARIO": (
        ("TIME_TO_FILL", 7, "DIAS"),
        ("REPOSICAO", 3, "DIAS"),
        ("ABSENTEISMO", 4, "PCT"),
    ),
    "TERCEIRIZACAO": (
        ("TIME_TO_FILL", 10, "DIAS"),
        ("REPOSICAO", 3, "DIAS"),
        ("ABSENTEISMO", 4, "PCT"),
    ),
    "RECRUTAMENTO": (("TIME_TO_FILL", 20, "DIAS"),),
}

# custo estimado de um posto, para o preço: encargos e provisões sobre o piso, mais benefícios
ENCARGOS_SOBRE_O_PISO = 0.68
BENEFICIOS_EM_2017 = 420.00
HORAS_NO_MES = 220

# motivos de saída (códigos de cadastro.motivo, tipo PERDA_CONTRATO) com peso
SAIDA_POR_MERCADO = {
    "PRECO": 0.35,
    "INTERNALIZACAO": 0.2,
    "REDUCAO_OPERACAO": 0.25,
    "FIM_PROJETO": 0.2,
}
SAIDA_NA_PANDEMIA = {"REDUCAO_OPERACAO": 0.8, "FIM_PROJETO": 0.2}
# quem sai por serviço nem sempre diz isso: parte declara "preço" (é a declaração D4 do dossiê)
SAIDA_POR_SERVICO = {"QUALIDADE_SERVICO": 0.45, "SLA_DESCUMPRIDO": 0.30, "PRECO": 0.25}

# reclamações (códigos de cadastro.motivo, tipo OCORRENCIA): (peso saudável, peso degradado, texto)
RECLAMACOES = {
    "ATRASO_REPOSICAO": (0.20, 0.34, "Reposição de profissional fora do prazo combinado"),
    "POSTO_DESCOBERTO": (0.15, 0.28, "Posto ficou descoberto no turno"),
    "FALTA_RECORRENTE": (0.25, 0.18, "Faltas recorrentes do profissional alocado"),
    "DESEMPENHO": (0.25, 0.12, "Profissional abaixo do esperado para a função"),
    "ERRO_FATURA": (0.15, 0.08, "Fatura com divergência de horas ou valores"),
}
TEXTO_DA_ADVERTENCIA = "Cliente formalizou insatisfação com o nível de serviço"
TEXTO_DO_AVISO = "Cliente comunicou que não seguirá com o contrato"
TEXTO_DO_ELOGIO = "Cliente elogiou o atendimento da equipe"

# nomes de empresa por sílabas: não existem
INICIOS = (
    "b",
    "br",
    "c",
    "d",
    "f",
    "g",
    "j",
    "l",
    "m",
    "n",
    "p",
    "pr",
    "r",
    "s",
    "t",
    "tr",
    "v",
    "z",
)
VOGAIS = ("a", "e", "i", "o", "u")
FINAIS = ("ra", "na", "lis", "tex", "mar", "vale", "sul", "nor", "plan", "tec", "lux", "pack")

LOGRADOUROS = (
    "Rua das Acácias",
    "Rua dos Jacarandás",
    "Avenida das Indústrias",
    "Rua do Comércio",
    "Avenida Marginal",
    "Rua das Oficinas",
    "Estrada dos Galpões",
    "Avenida dos Trabalhadores",
    "Rua Projetada",
    "Rua das Laranjeiras",
    "Avenida do Contorno",
    "Rua dos Pinheiros Altos",
)
BAIRROS = (
    "Centro",
    "Distrito Industrial",
    "Jardim das Flores",
    "Vila Nova",
    "Parque Empresarial",
    "Jardim Primavera",
    "Chácaras Reunidas",
)

NOMES = (
    "Ana", "Bruno", "Carla", "Daniel", "Eduarda", "Fábio", "Gabriela", "Henrique", "Isabela",
    "João", "Karina", "Leandro", "Mariana", "Nelson", "Olívia", "Paulo", "Rafaela", "Sérgio",
    "Tatiane", "Vinícius", "Aline", "Caio", "Débora", "Marcelo", "Patrícia", "Rodrigo",
)  # fmt: skip
SOBRENOMES = (
    "Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira", "Gomes", "Lima", "Machado",
    "Nogueira", "Oliveira", "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vieira",
)  # fmt: skip
CARGOS_DE_CONTATO = (
    "Gerente de RH",
    "Coordenador de Operações",
    "Analista de RH",
    "Gerente de Logística",
    "Supervisor de Produção",
    "Comprador",
    "Gerente Administrativo",
)
