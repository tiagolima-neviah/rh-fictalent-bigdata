"""O conteúdo fixo do ponto e da folha: jornadas, eventos, benefícios e as tabelas de cálculo.

A folha daqui é uma aproximação plausível, não um cálculo trabalhista: as alíquotas e faixas
são simplificadas (o suficiente para o custo por cabeça, os encargos e as provisões terem a
ordem de grandeza certa e fecharem com o rateio). Não use como referência legal.
"""

from __future__ import annotations

# escala -> (horas por dia trabalhado, regra dos dias)
JORNADA = {"5X2": 8.8, "6X1": 7.33, "5X1": 7.33, "12X36": 11.0}
INTERVALO_MIN = 60
# turno -> minuto do dia em que começa (REVEZAMENTO sorteia um dos três por alocação)
INICIO_DO_TURNO = {"MANHA": 6 * 60, "TARDE": 14 * 60, "NOITE": 22 * 60, "COMERCIAL": 8 * 60}
NOITE_DE, NOITE_ATE = 22 * 60, 29 * 60  # 22h às 5h do dia seguinte

# o dia a dia: probabilidades por dia programado (a falta cresce com a degradação da operação)
FALTA_BASE, FALTA_NA_DEGRADACAO = 0.018, 0.020
FALTA_JUSTIFICADA = 0.35
ATRASO, SAIDA_ANTECIPADA, HORA_EXTRA = 0.075, 0.025, 0.12
ORIGEM_POR_ALOCACAO = (("RELOGIO", 0.80), ("APP", 0.20))
MARCACAO_MANUAL = 0.03  # batida lançada depois pelo RH, em qualquer origem
# sujeira de origem do relógio (catálogo do plano de sintetização)
MARCACAO_FALTANTE = 0.025  # PON-01: dias em que falta uma das quatro batidas
MARCACAO_DUPLICADA = 0.006  # PON-02: dias com uma batida repetida no mesmo minuto
QUAL_FALTA = (("SAIDA", 0.70), ("RETORNO_INTERVALO", 0.20), ("ENTRADA", 0.10))
TIPOS_DE_MARCACAO = ("ENTRADA", "SAIDA_INTERVALO", "RETORNO_INTERVALO", "SAIDA")
JUSTIFICATIVAS = (
    "Atestado de comparecimento",
    "Problema com transporte",
    "Consulta médica",
    "Assunto familiar",
)

# (código, descrição, tipo, incide INSS, incide FGTS, incide IR)
EVENTOS = (
    ("SALARIO", "Salário", "PROVENTO", True, True, True),
    ("INSALUB", "Adicional de insalubridade", "PROVENTO", True, True, True),
    ("PERICUL", "Adicional de periculosidade", "PROVENTO", True, True, True),
    ("HE50", "Horas extras 50%", "PROVENTO", True, True, True),
    ("DSR_HE", "DSR sobre horas extras", "PROVENTO", True, True, True),
    ("ADIC_NOT", "Adicional noturno", "PROVENTO", True, True, True),
    ("DEC_TERC", "13º salário", "PROVENTO", True, True, True),
    ("RESC_13", "13º proporcional na rescisão", "PROVENTO", True, True, True),
    ("RESC_FER", "Férias proporcionais com um terço na rescisão", "PROVENTO", False, False, False),
    ("FALTAS", "Desconto de faltas", "DESCONTO", False, False, False),
    ("ATRASOS", "Desconto de atrasos e saídas antecipadas", "DESCONTO", False, False, False),
    ("INSS", "INSS do empregado", "DESCONTO", False, False, False),
    ("IRRF", "Imposto de renda retido", "DESCONTO", False, False, False),
    ("VT_DESC", "Desconto de vale-transporte", "DESCONTO", False, False, False),
    ("VR_DESC", "Desconto de vale-refeição", "DESCONTO", False, False, False),
    ("INSS_PAT", "INSS patronal", "ENCARGO", False, False, False),
    ("RAT", "RAT", "ENCARGO", False, False, False),
    ("TERCEIROS", "Contribuição a terceiros", "ENCARGO", False, False, False),
    ("FGTS", "FGTS", "ENCARGO", False, False, False),
    ("VT_EMP", "Vale-transporte, parte da empresa", "ENCARGO", False, False, False),
    ("VR_EMP", "Vale-refeição, parte da empresa", "ENCARGO", False, False, False),
    ("PROV_13", "Provisão de 13º salário", "PROVISAO", False, False, False),
    ("PROV_FER", "Provisão de férias com um terço", "PROVISAO", False, False, False),
    ("PROV_ENC", "Provisão de encargos sobre 13º e férias", "PROVISAO", False, False, False),
)
# o que entra no custo do mês (o rateio leva isto até o posto); 13º e rescisão saem da provisão
PROVENTOS_DO_MES = ("SALARIO", "INSALUB", "PERICUL", "HE50", "DSR_HE", "ADIC_NOT")
REDUTORES = ("FALTAS", "ATRASOS")
ENCARGOS_SOBRE_A_FOLHA = (("INSS_PAT", 0.20), ("RAT", 0.02), ("TERCEIROS", 0.058), ("FGTS", 0.08))
BENEFICIOS_DA_EMPRESA = ("VT_EMP", "VR_EMP")
PROVISOES = (("DECIMO_TERCEIRO", "PROV_13"), ("FERIAS", "PROV_FER"), ("ENCARGOS", "PROV_ENC"))
ENCARGOS_SOBRE_PROVISAO = 0.358
DIAS_PARA_O_AVO = 15  # a provisão do mês só existe com 15 dias trabalhados ou mais

# (código, nome, tipo, valor padrão por dia em 2018, parte descontada do colaborador)
BENEFICIOS = (
    ("VT", "Vale-transporte", "VT", 8.80, 0.06),
    ("VR", "Vale-refeição", "VR", 18.00, 0.10),
)
SALARIO_MINIMO = {
    2018: 954.0,
    2019: 998.0,
    2020: 1045.0,
    2021: 1100.0,
    2022: 1212.0,
    2023: 1320.0,
    2024: 1412.0,
    2025: 1518.0,
    2026: 1621.0,
}
INSALUBRIDADE, PERICULOSIDADE = 0.20, 0.30  # sobre o salário mínimo e sobre o salário-base
# INSS do empregado, simplificado: faixas em salários mínimos -> alíquota efetiva
INSS_EMPREGADO = ((1.0, 0.075), (2.0, 0.082), (3.0, 0.095), (99.0, 0.11))
# IRRF simplificado: isento até este múltiplo do salário mínimo; acima, 7,5% do excedente
IRRF_ISENTO_ATE, IRRF_ALIQUOTA = 1.9, 0.075
DIA_DO_FECHAMENTO = 5
