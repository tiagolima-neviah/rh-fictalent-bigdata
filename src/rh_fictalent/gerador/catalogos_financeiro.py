"""O conteúdo fixo do financeiro: tributos do lucro presumido, fornecedores, inadimplência.

Como na folha, a apuração aqui é uma aproximação plausível do lucro presumido de uma empresa
de cessão de mão de obra, não um cálculo fiscal. Os fornecedores são inventados.
"""

from __future__ import annotations

from rh_fictalent.validacao.bandas import GER_01

# (código, descrição, esfera, alíquota, base presumida)
TRIBUTOS = (
    ("ISS", "Imposto sobre serviços", "MUNICIPAL", None, None),
    ("PIS", "PIS cumulativo", "FEDERAL", 0.0065, None),
    ("COFINS", "COFINS cumulativa", "FEDERAL", 0.03, None),
    ("IRPJ", "Imposto de renda da pessoa jurídica", "FEDERAL", 0.15, 0.32),
    ("CSLL", "Contribuição social sobre o lucro líquido", "FEDERAL", 0.09, 0.32),
)
ISS_DA_FILIAL = {"ATB": 0.05, "BRG": 0.05, "EXT": 0.03}  # o ISS é do município da filial
PIS, COFINS, IRPJ, CSLL = 0.0065, 0.03, 0.15, 0.09
BASE_PRESUMIDA = 0.32
ADICIONAL_DO_IRPJ, LIMITE_DO_ADICIONAL = 0.10, 60_000.0  # por trimestre

HONORARIO_DE_RS = (1.0, 1.5)  # salários por pessoa colocada
FATOR_DA_HORA_EXTRA = 1.5

# quem não paga: fora da crise, na crise (2024 em diante) e o cliente que está de saída
CALOTE_BASE, CALOTE_NA_CRISE, CALOTE_DE_QUEM_SAI = 0.004, 0.012, 0.45
RECEBIDO_DIFERENTE = 0.012  # FIN-01: valor recebido diferente do emitido, sem registro de desconto
DIVERGENCIA_DO_CONSOLIDADO = GER_01  # GER-01: de 0,5% em 2022 a 9% em 2026; antes disso, bate

OPERADORA_DE_BENEFICIOS = "Valecard Benefícios Fictícios Ltda"
CLINICA_DE_EXAMES = "Clínica Ocupacional Fictícia Atibaia Ltda"
EXAME_ADMISSIONAL = 65.0  # por admissão, em reais de 2018
# (razão social, tipo)
FORNECEDORES = (
    (OPERADORA_DE_BENEFICIOS, "BENEFICIOS"),
    (CLINICA_DE_EXAMES, "EXAMES"),
    ("Clínica Ocupacional Fictícia Extrema Ltda", "EXAMES"),
    ("Centro de Treinamento NR Fictício Ltda", "TREINAMENTO"),
    ("Imobiliária Fictícia do Eixo Ltda", "SERVICOS"),
    ("Sistemas de Folha Fictícios S.A.", "SERVICOS"),
    ("Escritório Contábil Fictício Ltda", "SERVICOS"),
    ("Portal de Vagas Fictício Ltda", "SERVICOS"),
    ("Telecom e Internet Fictícia Ltda", "SERVICOS"),
)
# a retaguarda: a equipe interna é a maior parte; o resto são contratos fixos (fornecedor, parte)
PARTE_DA_EQUIPE_INTERNA = 0.55
DESPESAS_FIXAS = (
    ("Imobiliária Fictícia do Eixo Ltda", 0.34),
    ("Sistemas de Folha Fictícios S.A.", 0.22),
    ("Escritório Contábil Fictício Ltda", 0.18),
    ("Portal de Vagas Fictício Ltda", 0.16),
    ("Telecom e Internet Fictícia Ltda", 0.10),
)
# em 2026 a empresa contrata para a retaguarda em fevereiro e em maio, e nada melhora (D5)
PESO_DA_RETAGUARDA_EM_2026 = {
    1: 0.90,
    2: 0.97,
    3: 0.97,
    4: 0.97,
    5: 1.05,
    6: 1.05,
    7: 1.05,
    8: 1.05,
}
# parte da receita bruta; fora disso a história não fecha (em 2018, empresa pequena, pesa mais)
RETAGUARDA_PLAUSIVEL = (0.02, 0.20)
