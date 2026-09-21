"""O conteúdo fixo do mundo cadastral: o que a Fictalent "cadastrou" no sistema dela.

Tudo aqui é ficção coerente com o caso: três unidades no eixo da Fernão Dias, funções
operacionais de indústria, logística, comércio e serviços, motivos, escalas e parâmetros.
Endereços, CEPs e sindicatos são inventados. Os códigos da CBO só aparecem onde são conhecidos
com segurança; função sem código fica com o campo nulo, como acontece em cadastro de verdade.
"""

from __future__ import annotations

from datetime import date
from typing import NamedTuple

# região imediata do IBGE -> nome comercial da região na Fictalent
REGIOES = {
    "Bragança Paulista": "Região Bragantina",
    "Pouso Alegre": "Sul de Minas · Fernão Dias",
    "Jundiaí": "Jundiaí e região",
    "Campinas": "Região de Campinas",
    "São Paulo": "Grande São Paulo",
}


class Filial(NamedTuple):
    codigo: str
    nome: str
    tipo: str
    codigo_ibge: str
    dt_abertura: date
    logradouro: str
    numero: str
    bairro: str
    cep: str  # fictício


FILIAIS = (
    Filial(
        "ATB",
        "Fictalent Atibaia (matriz)",
        "MATRIZ",
        "3504107",
        date(2018, 1, 2),
        "Avenida dos Ipês",
        "1200",
        "Jardim Empresarial",
        "12940100",
    ),
    Filial(
        "BRG",
        "Fictalent Bragança Paulista",
        "FILIAL",
        "3507605",
        date(2019, 3, 11),
        "Rua das Paineiras",
        "455",
        "Centro",
        "12900200",
    ),
    Filial(
        "EXT",
        "Fictalent Extrema",
        "FILIAL",
        "3125101",
        date(2022, 8, 1),
        "Avenida do Distrito Logístico",
        "3000",
        "Distrito Industrial",
        "37640300",
    ),
)


class Funcao(NamedTuple):
    codigo: str
    nome: str
    cbo: str | None
    familia: str
    nivel: str
    insalubre: bool
    periculosidade: bool
    fator: float  # múltiplo do piso de referência


FUNCOES = (
    # produção
    Funcao("P001", "Auxiliar de produção", "784205", "PRODUCAO", "AUXILIAR", False, False, 1.00),
    Funcao("P002", "Operador de máquinas", None, "PRODUCAO", "OPERADOR", False, False, 1.25),
    Funcao("P003", "Operador de injetora", None, "PRODUCAO", "OPERADOR", True, False, 1.30),
    Funcao("P004", "Montador", None, "PRODUCAO", "OPERADOR", False, False, 1.20),
    Funcao("P005", "Embalador", "784105", "PRODUCAO", "AUXILIAR", False, False, 1.00),
    Funcao("P006", "Inspetor de qualidade", "391205", "PRODUCAO", "TECNICO", False, False, 1.55),
    Funcao("P007", "Soldador", "724315", "PRODUCAO", "OPERADOR", True, False, 1.60),
    Funcao("P008", "Auxiliar de manutenção", None, "PRODUCAO", "AUXILIAR", False, False, 1.20),
    Funcao("P009", "Mecânico de manutenção", "911305", "PRODUCAO", "TECNICO", False, False, 1.90),
    Funcao("P010", "Eletricista de manutenção", "951105", "PRODUCAO", "TECNICO", False, True, 1.95),
    Funcao("P011", "Líder de produção", None, "PRODUCAO", "LIDER", False, False, 2.00),
    Funcao("P012", "Operador de caldeira", "862120", "PRODUCAO", "OPERADOR", True, False, 1.55),
    # logística
    Funcao("L001", "Auxiliar de logística", None, "LOGISTICA", "AUXILIAR", False, False, 1.05),
    Funcao("L002", "Conferente", "414215", "LOGISTICA", "OPERADOR", False, False, 1.25),
    Funcao(
        "L003", "Operador de empilhadeira", "782220", "LOGISTICA", "OPERADOR", False, False, 1.40
    ),
    Funcao("L004", "Separador de pedidos", None, "LOGISTICA", "AUXILIAR", False, False, 1.05),
    Funcao("L005", "Estoquista", None, "LOGISTICA", "AUXILIAR", False, False, 1.10),
    Funcao("L006", "Almoxarife", "414105", "LOGISTICA", "OPERADOR", False, False, 1.30),
    Funcao("L007", "Ajudante de motorista", "783225", "LOGISTICA", "AUXILIAR", False, False, 1.05),
    Funcao("L008", "Carregador de armazém", "783215", "LOGISTICA", "AUXILIAR", False, False, 1.05),
    Funcao("L009", "Motorista de caminhão", "782510", "LOGISTICA", "OPERADOR", False, False, 1.70),
    Funcao("L010", "Expedidor", None, "LOGISTICA", "OPERADOR", False, False, 1.20),
    Funcao("L011", "Líder de logística", None, "LOGISTICA", "LIDER", False, False, 2.00),
    Funcao("L012", "Analista de logística", None, "LOGISTICA", "TECNICO", False, False, 2.20),
    # comércio
    Funcao("C001", "Repositor", "521125", "COMERCIO", "AUXILIAR", False, False, 1.00),
    Funcao("C002", "Operador de caixa", "421125", "COMERCIO", "OPERADOR", False, False, 1.08),
    Funcao("C003", "Vendedor", "521110", "COMERCIO", "OPERADOR", False, False, 1.10),
    Funcao("C004", "Atendente de loja", None, "COMERCIO", "AUXILIAR", False, False, 1.00),
    Funcao("C005", "Fiscal de loja", None, "COMERCIO", "OPERADOR", False, False, 1.12),
    Funcao("C006", "Promotor de vendas", None, "COMERCIO", "OPERADOR", False, False, 1.10),
    Funcao("C007", "Balconista", None, "COMERCIO", "AUXILIAR", False, False, 1.00),
    Funcao("C008", "Açougueiro", "848510", "COMERCIO", "OPERADOR", True, False, 1.35),
    Funcao("C009", "Padeiro", "848305", "COMERCIO", "OPERADOR", False, False, 1.30),
    # administrativo
    Funcao(
        "A001",
        "Auxiliar administrativo",
        "411005",
        "ADMINISTRATIVO",
        "AUXILIAR",
        False,
        False,
        1.10,
    ),
    Funcao(
        "A002",
        "Assistente administrativo",
        "411010",
        "ADMINISTRATIVO",
        "OPERADOR",
        False,
        False,
        1.35,
    ),
    Funcao("A003", "Recepcionista", "422105", "ADMINISTRATIVO", "AUXILIAR", False, False, 1.08),
    Funcao(
        "A004", "Auxiliar de pessoal", "411030", "ADMINISTRATIVO", "AUXILIAR", False, False, 1.20
    ),
    Funcao("A005", "Assistente financeiro", None, "ADMINISTRATIVO", "OPERADOR", False, False, 1.45),
    Funcao(
        "A006",
        "Operador de telemarketing",
        "422310",
        "ADMINISTRATIVO",
        "OPERADOR",
        False,
        False,
        1.02,
    ),
    Funcao(
        "A007", "Analista administrativo", None, "ADMINISTRATIVO", "TECNICO", False, False, 2.10
    ),
    # serviços
    Funcao("S001", "Auxiliar de limpeza", "514320", "SERVICOS", "AUXILIAR", True, False, 1.00),
    Funcao("S002", "Porteiro", "517410", "SERVICOS", "AUXILIAR", False, False, 1.08),
    Funcao("S003", "Copeira", "513425", "SERVICOS", "AUXILIAR", False, False, 1.00),
    Funcao("S004", "Jardineiro", "622010", "SERVICOS", "AUXILIAR", False, False, 1.05),
    Funcao("S005", "Zelador", "514120", "SERVICOS", "AUXILIAR", False, False, 1.10),
)

# (tipo, código, descrição, grupo analítico)
MOTIVOS = (
    ("DESLIGAMENTO", "TERMINO_CONTRATO", "Término do contrato temporário", "LEGAL"),
    ("DESLIGAMENTO", "FIM_EXPERIENCIA", "Término do contrato de experiência", "LEGAL"),
    ("DESLIGAMENTO", "PEDIDO_DEMISSAO", "Pedido de demissão", "PESSOAL"),
    ("DESLIGAMENTO", "ABANDONO", "Abandono de emprego", "PESSOAL"),
    ("DESLIGAMENTO", "SEM_JUSTA_CAUSA", "Dispensa sem justa causa", "SERVICO"),
    ("DESLIGAMENTO", "JUSTA_CAUSA", "Dispensa por justa causa", "LEGAL"),
    ("DESLIGAMENTO", "PEDIDO_CLIENTE", "Substituição pedida pelo cliente", "SERVICO"),
    ("DESLIGAMENTO", "REDUCAO_QUADRO", "Redução de quadro do cliente", "MERCADO"),
    ("DESLIGAMENTO", "EFETIVADO_CLIENTE", "Efetivado pelo cliente", "MERCADO"),
    ("REPROVACAO", "PERFIL", "Perfil fora do pedido da vaga", "SERVICO"),
    ("REPROVACAO", "SEM_EXPERIENCIA", "Sem a experiência exigida", "PESSOAL"),
    ("REPROVACAO", "PRETENSAO", "Pretensão salarial acima da vaga", "MERCADO"),
    ("REPROVACAO", "DISTANCIA", "Mora longe do local de trabalho", "PESSOAL"),
    ("REPROVACAO", "NO_SHOW", "Não compareceu à entrevista", "PESSOAL"),
    ("REPROVACAO", "DOCUMENTACAO", "Documentação incompleta", "LEGAL"),
    ("REPROVACAO", "EXAME_INAPTO", "Inapto no exame admissional", "LEGAL"),
    ("REPROVACAO", "CLIENTE", "Reprovado na entrevista do cliente", "SERVICO"),
    ("REPROVACAO", "DESISTENCIA", "Candidato desistiu do processo", "PESSOAL"),
    ("CANCELAMENTO_VAGA", "CLIENTE_CANCELOU", "Cliente cancelou a requisição", "MERCADO"),
    ("CANCELAMENTO_VAGA", "SEM_ORCAMENTO", "Cliente sem orçamento aprovado", "MERCADO"),
    (
        "CANCELAMENTO_VAGA",
        "PREENCHIDA_CLIENTE",
        "Cliente preencheu por conta própria",
        "SERVICO",
    ),
    ("CANCELAMENTO_VAGA", "DUPLICADA", "Requisição aberta em duplicidade", "SERVICO"),
    ("CANCELAMENTO_VAGA", "PRAZO_EXPIRADO", "Prazo expirou sem preenchimento", "SERVICO"),
    ("PERDA_CONTRATO", "PRECO", "Proposta mais barata de concorrente", "MERCADO"),
    ("PERDA_CONTRATO", "INTERNALIZACAO", "Cliente internalizou a operação", "MERCADO"),
    ("PERDA_CONTRATO", "REDUCAO_OPERACAO", "Cliente reduziu ou encerrou a operação", "MERCADO"),
    ("PERDA_CONTRATO", "FIM_PROJETO", "Fim do projeto contratado", "MERCADO"),
    ("PERDA_CONTRATO", "QUALIDADE_SERVICO", "Insatisfação com a qualidade do serviço", "SERVICO"),
    ("PERDA_CONTRATO", "SLA_DESCUMPRIDO", "Descumprimento recorrente de SLA", "SERVICO"),
    ("PERDA_CONTRATO", "INADIMPLENCIA", "Rescisão por inadimplência do cliente", "LEGAL"),
    ("AFASTAMENTO", "DOENCA", "Auxílio-doença", "PESSOAL"),
    ("AFASTAMENTO", "ACIDENTE_TRABALHO", "Acidente de trabalho", "LEGAL"),
    ("AFASTAMENTO", "MATERNIDADE", "Licença-maternidade", "LEGAL"),
    ("AFASTAMENTO", "ATESTADO_LONGO", "Atestado superior a 15 dias", "PESSOAL"),
    ("FIM_ALOCACAO", "FIM_CONTRATO", "Fim do contrato de trabalho", "LEGAL"),
    ("FIM_ALOCACAO", "SUBSTITUICAO", "Substituído a pedido do cliente", "SERVICO"),
    ("FIM_ALOCACAO", "TRANSFERENCIA", "Transferido para outro posto", "SERVICO"),
    ("FIM_ALOCACAO", "ENCERRAMENTO_POSTO", "Posto encerrado pelo cliente", "MERCADO"),
    ("FIM_ALOCACAO", "NO_SHOW_PRIMEIRO_DIA", "Não compareceu no primeiro dia", "PESSOAL"),
    ("OCORRENCIA", "ATRASO_REPOSICAO", "Demora na reposição de profissional", "SERVICO"),
    ("OCORRENCIA", "POSTO_DESCOBERTO", "Posto descoberto", "SERVICO"),
    ("OCORRENCIA", "FALTA_RECORRENTE", "Faltas recorrentes do profissional", "SERVICO"),
    ("OCORRENCIA", "DESEMPENHO", "Profissional abaixo do esperado", "SERVICO"),
    ("OCORRENCIA", "ERRO_FATURA", "Erro na fatura", "SERVICO"),
    ("OCORRENCIA", "ELOGIO", "Elogio ao atendimento", "SERVICO"),
)

# (código, descrição, horas semanais, dias do ciclo)
ESCALAS = (
    ("5X2", "Cinco dias de trabalho, dois de folga (segunda a sexta)", 44.00, 7),
    ("6X1", "Seis dias de trabalho, um de folga", 44.00, 7),
    ("5X1", "Cinco dias de trabalho, um de folga, em revezamento", 42.00, 6),
    ("12X36", "Doze horas de trabalho por trinta e seis de descanso", 42.00, 2),
)

# (chave, valor, início da vigência); a mesma chave de novo encerra a vigência anterior
PARAMETROS = (
    ("PRAZO_TEMPORARIO_DIAS", "180", date(2018, 1, 2)),
    ("PRORROGACAO_TEMPORARIO_DIAS", "90", date(2018, 1, 2)),
    ("EXPERIENCIA_DIAS", "90", date(2018, 1, 2)),
    ("GARANTIA_REPOSICAO_DIAS", "90", date(2018, 1, 2)),
    ("FECHAMENTO_FOLHA_DIA", "5", date(2018, 1, 2)),
    ("PRAZO_PAGAMENTO_PADRAO_DIAS", "28", date(2018, 1, 2)),
    ("ALERTA_ASO_DIAS", "30", date(2018, 1, 2)),
    ("MARKUP_PADRAO", "1.55", date(2018, 1, 2)),
    ("MARKUP_PADRAO", "1.50", date(2022, 1, 1)),
    ("ALERTA_ASO_DIAS", "45", date(2024, 3, 1)),
)

# convenção por município das filiais: (código IBGE, cidade, mês da data-base, fator regional)
CONVENCOES = (
    ("3504107", "Atibaia", 5, 1.00),
    ("3507605", "Bragança Paulista", 5, 0.98),
    ("3125101", "Extrema", 1, 0.94),
)
SINDICATO = (
    "Sindicato dos Trabalhadores em Trabalho Temporário e Terceirização de {cidade} e Região "
    "(fictício)"
)
PISO_DE_REFERENCIA = 1180.00  # piso da função de fator 1,00 na data-base de 2017, em Atibaia
REAJUSTES = {  # reajuste da convenção na data-base de cada ano (fictício)
    2018: 0.021,
    2019: 0.039,
    2020: 0.033,
    2021: 0.062,
    2022: 0.108,
    2023: 0.055,
    2024: 0.039,
    2025: 0.049,
    2026: 0.044,
}
ADICIONAL_DE_INSALUBRIDADE = 0.20  # grau médio, sobre o piso

# feriados que a BrasilAPI não traz: (mês, dia, nome, abrangência, código IBGE ou None)
FERIADOS_LOCAIS = (
    (7, 9, "Revolução Constitucionalista (SP)", "ESTADUAL", None),
    (6, 24, "Aniversário de Atibaia", "MUNICIPAL", "3504107"),
    (12, 15, "Aniversário de Bragança Paulista", "MUNICIPAL", "3507605"),
    (9, 16, "Aniversário de Extrema", "MUNICIPAL", "3125101"),
)
