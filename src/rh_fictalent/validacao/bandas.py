"""As bandas: o que a base sintética precisa mostrar para ser aceita, em seis famílias.

Cada número aqui vem do plano de sintetização do caso (a narrativa 2018 a 2026, a degradação
de qualidade que explica 2025, o financeiro que nunca fecha no vermelho, o catálogo de sujeira)
ou de dado público (o índice sazonal do Novo CAGED). As tolerâncias são decisão deste módulo,
declaradas junto de cada banda: o plano dá o alvo, a régua diz quanto de folga o alvo aceita.
Mudar uma banda é mudar o contrato: entra com data e motivo no histórico do repositório.

As seis famílias:

1. escala e forma: quantos clientes, quanta gente, quantas vagas, quantas linhas;
2. naturalidade: nada acontece "de uma vez", fora dos choques declarados;
3. a história: a degradação ano a ano, a defasagem até a perda de contrato, a margem;
4. sazonalidade: o ritmo do ano contra o índice do CAGED;
5. coerência interna: invariantes que não admitem nenhuma violação;
6. sujeira: cada defeito do catálogo na proporção alvo, nem mais, nem menos.

MEDIDAS é a outra metade do contrato: o nome, a chave e o significado de cada número que o
gerador (ou a consulta na réplica) precisa entregar para a régua conferir.

Revisões do contrato:

- 2026-09-21 (card 4.6, ocupação dos postos). Naturalidade: o limite contra a média móvel
  sobe de 0,35 para 0,45 (a subida da temporada, de outubro para novembro, passa de 35% nos
  anos de maior amplitude sem ser degrau) e os choques declarados ganham 2018 (ano da
  fundação: a base é pequena e cada contrato novo pesa) e a retomada de julho a setembro de
  2020. Sazonalidade: a Fictalent vive de reforço de temporada, então o ritmo dela acompanha
  o CAGED do setor no estado (correlação mínima sobe para 0,75) com amplitude maior que a do
  agregado estadual (desvio máximo de 0,30 para 0,45 nas admissões e de 0,35 para 1,00 nos
  desligamentos; desvio médio de 0,15 para 0,25 e de 0,18 para 0,30). Definições fechadas:
  posto descoberto é dias sem ninguém por posição contratada por mês; o mix de 2024 é sobre
  pessoas em atendimento (alocados por tipo e efetivados por R&S na garantia de 90 dias).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from rh_fictalent.validacao.regua import Banda, Check

ANOS = tuple(range(2018, 2027))  # 2026 vai até 10/09, o dia da primeira reunião

# ───────────────────────────── 1 · escala e forma ─────────────────────────────
CLIENTES_ATIVOS = dict(zip(ANOS, (12, 19, 16, 22, 34, 50, 66, 58, 45), strict=True))
HEADCOUNT_MEDIO = dict(zip(ANOS, (90, 180, 145, 210, 380, 620, 900, 1000, 850), strict=True))
# pico = dezembro; em 2026, o headcount de setembro
HEADCOUNT_PICO = dict(zip(ANOS, (150, 300, 190, 320, 600, 950, 1400, 1150, 800), strict=True))
VAGAS_ABERTAS = dict(zip(ANOS, (380, 820, 560, 980, 1900, 3100, 4500, 4100, 2600), strict=True))
MIX_2024 = {"TEMPORARIO": (0.55, 0.05), "TERCEIRIZACAO": (0.35, 0.05), "RS_EFETIVO": (0.10, 0.03)}
LINHAS = {
    "ponto.marcacao": 4_400_000,
    "ponto.apontamento": 1_100_000,
    "folha.folha_item": 860_000,
    "ats.candidatura_etapa": 750_000,
    "ats.candidatura": 300_000,
    "ponto.ocorrencia_ponto": 165_000,
    "folha.provisao": 114_000,
    "ats.candidato": 60_000,
    "financeiro.fatura_item": 52_000,
    "sst.aso": 40_000,
}
LINHAS_TOTAL = 8_300_000

# ───────────────────────────── 2 · naturalidade ───────────────────────────────
DESVIO_MAXIMO_MEDIA_MOVEL = 0.45  # |mês ÷ média dos 3 meses anteriores - 1|, fora dos choques
PANDEMIA = ("2020-03", "2020-04", "2020-05", "2020-06")
RETOMADA = ("2020-07", "2020-08", "2020-09")  # a volta da pandemia também é degrau declarado
ANO_DA_FUNDACAO = 2018  # base pequena: cada contrato novo pesa, o check não se aplica
INICIO_DA_CRISE = "2025-10"  # a perda de contratos começa aqui; antes, saída é evento raro
SAIDAS_MAXIMAS_NO_MES = 2  # fora da pandemia e da crise
ENTRADAS_MAXIMAS_NO_MES = 5  # a intensidade chega a ~2,4 por mês no auge; 6 já é "combinaram"
CONCENTRACAO_MAXIMA_DE_ENTRADAS = 0.35  # parcela das entradas do ano num único mês

# ───────────────────────────── 3 · a história ─────────────────────────────────
MARGEM_LIQUIDA = dict(
    zip(ANOS, (0.04, 0.07, 0.03, 0.08, 0.11, 0.12, 0.12, 0.08, 0.04), strict=True)
)
TOLERANCIA_DA_MARGEM = 0.015
MARGEM_MINIMA = 0.005  # nenhum ano fecha com prejuízo, nem "quase zero"
DEFASAGEM_MESES = (6.0, 9.0)  # da queda de qualidade sentida pelo cliente até o rompimento


@dataclass(frozen=True)
class Indicador:
    """Um indicador de qualidade da operação: a referência por ano e a folga aceita."""

    codigo: str
    medida: str
    descricao: str
    tolerancia: float
    base: tuple[float, float]  # 2018 a 2022: a operação saudável
    depois: tuple[float, float, float, float]  # 2023, 2024, 2025, 2026

    def referencia(self) -> Mapping[int, tuple[float, float]]:
        por_ano = {ano: self.base for ano in range(2018, 2023)}
        por_ano.update({ano: (v, v) for ano, v in zip(range(2023, 2027), self.depois, strict=True)})
        return por_ano


DEGRADACAO = (
    Indicador(
        "H-01",
        "ttf_temporario_mediana",
        "time to fill temporário, mediana em dias úteis",
        1.0,
        (5, 6),
        (7, 9, 11, 11),
    ),
    Indicador(
        "H-02",
        "ttf_rs_mediana",
        "time to fill R&S efetivo, mediana em dias úteis",
        2.0,
        (16, 18),
        (20, 24, 27, 27),
    ),
    Indicador(
        "H-03",
        "no_show_entrevista",
        "no-show de entrevista",
        0.02,
        (0.12, 0.14),
        (0.17, 0.21, 0.25, 0.25),
    ),
    Indicador(
        "H-04",
        "no_show_primeiro_dia",
        "no-show de primeiro dia",
        0.015,
        (0.05, 0.05),
        (0.07, 0.09, 0.12, 0.12),
    ),
    Indicador(
        "H-05",
        "turnover_90d",
        "turnover nos primeiros 90 dias",
        0.03,
        (0.15, 0.15),
        (0.19, 0.24, 0.30, 0.29),
    ),
    Indicador(
        "H-06",
        "posto_descoberto_dias",
        "dias descobertos por posição contratada por mês",
        0.4,
        (1.5, 1.5),
        (2.2, 3.1, 4.0, 4.0),
    ),
    Indicador("H-07", "fill_rate", "fill rate", 0.02, (0.95, 0.95), (0.92, 0.87, 0.82, 0.83)),
    Indicador(
        "H-08",
        "reclamacoes_100_postos",
        "reclamações por 100 postos por mês",
        0.3,
        (0.8, 0.8),
        (1.3, 2.0, 2.6, 2.5),
    ),
)

# ───────────────────────────── 4 · sazonalidade ───────────────────────────────
# Referência: Novo CAGED 2023 a 2025, subclasses 78 no estado de SP (a maior amostra), em
# dados/publicos/caged/indice_sazonal.csv. O arco é ficção; o ritmo do ano, não.
CAGED_ESCOPO = "35"
CAGED_GRUPO = "78"
SAZONALIDADE = {
    "sazonalidade_admissoes": {"desvio_maximo": 0.45, "desvio_medio": 0.25, "correlacao": 0.75},
    "sazonalidade_desligamentos": {"desvio_maximo": 1.00, "desvio_medio": 0.30, "correlacao": 0.75},
}

# ───────────────────────────── 5 · coerência interna ──────────────────────────
INVARIANTES = {
    "C-01": "alocação sem contrato de trabalho vigente no período",
    "C-02": "apontamento de ponto sem alocação vigente no dia",
    "C-03": "fatura sem contrato comercial",
    "C-04": "competência em que o custo da folha difere da soma do rateio",
    "C-05": "posto com duas pessoas alocadas no mesmo dia",
}

# ───────────────────────────── 6 · sujeira ────────────────────────────────────
TOLERANCIA_DA_SUJEIRA = 0.20  # relativa ao alvo, quando a banda não diz outra coisa
SUJEIRA: dict[str, tuple[str, Banda]] = {
    "CAD-01": ("candidatos duplicados", Banda.em_torno(0.035, relativa=TOLERANCIA_DA_SUJEIRA)),
    "CAD-02": ("CPF com dígito inválido", Banda.em_torno(0.008, relativa=TOLERANCIA_DA_SUJEIRA)),
    "CAD-03": ("data de nascimento impossível", Banda.em_torno(0.002, relativa=0.5)),
    "PES-01/ate_2022": ("admissão retroativa até 2022", Banda.em_torno(0.06, absoluta=0.01)),
    "PES-01/desde_2024": ("admissão retroativa desde 2024", Banda.em_torno(0.11, absoluta=0.015)),
    "PES-02": (
        "temporário além de 180 ou 270 dias sem aditivo",
        Banda.em_torno(0.018, relativa=TOLERANCIA_DA_SUJEIRA),
    ),
    "PES-02/parcela_desde_2023": ("parcela dos PES-02 de 2023 em diante", Banda(minimo=0.60)),
    "PON-01": ("dias com marcação faltante", Banda.em_torno(0.025, relativa=0.12)),
    "PON-02": ("dias com marcação duplicada", Banda.em_torno(0.006, relativa=0.15)),
    "SST-01/2024": ("alocados com ASO vencido em 2024", Banda.em_torno(0.04, absoluta=0.008)),
    "SST-01/2025": ("alocados com ASO vencido em 2025", Banda.em_torno(0.04, absoluta=0.008)),
    "FIN-01": (
        "títulos recebidos com valor diferente, sem desconto",
        Banda.em_torno(0.012, relativa=TOLERANCIA_DA_SUJEIRA),
    ),
    "GER-01/competencias_sem_divergencia": (
        "competências desde 2022 em que o consolidado bate com a operação",
        Banda.exatamente(0),
    ),
}
# GER-01: a divergência do consolidado gerencial cresce de 0,5% (2022) a 9% (2026), em linha reta
GER_01 = {2022: 0.005, 2023: 0.02625, 2024: 0.0475, 2025: 0.06875, 2026: 0.09}
TOLERANCIA_GER_01 = 0.25

# ───────────────────────────── o contrato de medidas ──────────────────────────
MEDIDAS = {
    "clientes_ativos_fim_ano": "por ano: clientes com contrato vigente em 31/12 (2026: em 10/09)",
    "headcount_medio": "por ano: média diária de pessoas alocadas",
    "headcount_pico": "por ano: média de alocados em dezembro (2026: em setembro)",
    "vagas_abertas": "por ano: vagas abertas",
    "mix_servico_2024": (
        "por serviço: parcela das pessoas em atendimento em 2024 (média diária de alocados "
        "temporários e terceirizados, e de efetivados por R&S dentro da garantia de 90 dias)"
    ),
    "linhas_tabela": "por schema.tabela, mais 'total': linhas na réplica",
    "naturalidade": (
        "headcount_desvio_maximo, saidas_max_mes_fora_crise, entradas_max_mes, "
        "entradas_concentracao_max (ver validacao.derivadas)"
    ),
    "defasagem_qualidade_perda": "mediana_meses: da qualidade abaixo do limite ao rompimento",
    "margem_liquida": "por ano: resultado líquido ÷ receita líquida",
    "sazonalidade_admissoes": "desvio_maximo, desvio_medio e correlacao contra o CAGED",
    "sazonalidade_desligamentos": "desvio_maximo, desvio_medio e correlacao contra o CAGED",
    "violacoes": "por invariante (C-01 a C-05): número de violações",
    "sujeira": "por defeito do catálogo: proporção observada (GER-01 por ano)",
    **{i.medida: f"por ano: {i.descricao}" for i in DEGRADACAO},
}


def checks() -> list[Check]:
    """Todos os checks da régua, na ordem das famílias."""
    lista: list[Check] = []

    def por_ano(
        prefixo: str,
        familia: str,
        descricao: str,
        medida: str,
        banda_do_ano: Callable[[int], Banda],
    ) -> None:
        for ano in ANOS:
            banda = banda_do_ano(ano)
            lista.append(
                Check(f"{prefixo}/{ano}", familia, f"{descricao}, {ano}", medida, str(ano), banda)
            )

    # 1 · escala e forma
    por_ano(
        "E-01",
        "escala",
        "clientes ativos no fim do ano",
        "clientes_ativos_fim_ano",
        lambda a: Banda.em_torno(CLIENTES_ATIVOS[a], absoluta=2, relativa=0.15),
    )
    por_ano(
        "E-02",
        "escala",
        "headcount médio",
        "headcount_medio",
        lambda a: Banda.em_torno(HEADCOUNT_MEDIO[a], relativa=0.10),
    )
    por_ano(
        "E-03",
        "escala",
        "headcount no pico",
        "headcount_pico",
        lambda a: Banda.em_torno(HEADCOUNT_PICO[a], relativa=0.12),
    )
    por_ano(
        "E-04",
        "escala",
        "vagas abertas",
        "vagas_abertas",
        lambda a: Banda.em_torno(VAGAS_ABERTAS[a], relativa=0.10),
    )
    for servico, (alvo, folga) in MIX_2024.items():
        lista.append(
            Check(
                f"E-05/{servico}",
                "escala",
                f"parcela de {servico} no headcount de 2024",
                "mix_servico_2024",
                servico,
                Banda.em_torno(alvo, absoluta=folga),
            )
        )
    for tabela, alvo in LINHAS.items():
        lista.append(
            Check(
                f"E-06/{tabela}",
                "escala",
                f"linhas em {tabela}",
                "linhas_tabela",
                tabela,
                Banda.em_torno(alvo, relativa=0.30),
            )
        )
    lista.append(
        Check(
            "E-06/total",
            "escala",
            "linhas na réplica inteira",
            "linhas_tabela",
            "total",
            Banda.em_torno(LINHAS_TOTAL, relativa=0.20),
        )
    )

    # 2 · naturalidade
    lista += [
        Check(
            "N-01",
            "naturalidade",
            "maior desvio do headcount mensal contra a média móvel de 3 meses, fora dos choques",
            "naturalidade",
            "headcount_desvio_maximo",
            Banda(maximo=DESVIO_MAXIMO_MEDIA_MOVEL),
        ),
        Check(
            "N-02",
            "naturalidade",
            "maior número de clientes saindo no mesmo mês, fora da pandemia e da crise",
            "naturalidade",
            "saidas_max_mes_fora_crise",
            Banda(maximo=SAIDAS_MAXIMAS_NO_MES),
        ),
        Check(
            "N-03",
            "naturalidade",
            "maior número de clientes entrando no mesmo mês",
            "naturalidade",
            "entradas_max_mes",
            Banda(maximo=ENTRADAS_MAXIMAS_NO_MES),
        ),
        Check(
            "N-04",
            "naturalidade",
            "maior parcela das entradas de um ano concentrada num mês",
            "naturalidade",
            "entradas_concentracao_max",
            Banda(maximo=CONCENTRACAO_MAXIMA_DE_ENTRADAS),
        ),
    ]

    # 3 · a história
    for indicador in DEGRADACAO:
        for ano, (baixo, alto) in indicador.referencia().items():
            lista.append(
                Check(
                    f"{indicador.codigo}/{ano}",
                    "historia",
                    f"{indicador.descricao}, {ano}",
                    indicador.medida,
                    str(ano),
                    Banda(baixo - indicador.tolerancia, alto + indicador.tolerancia),
                )
            )
    lista.append(
        Check(
            "H-09",
            "historia",
            "defasagem entre a queda de qualidade e a perda do contrato, mediana em meses",
            "defasagem_qualidade_perda",
            "mediana_meses",
            Banda(*DEFASAGEM_MESES),
        )
    )
    por_ano(
        "H-10",
        "historia",
        "margem líquida, sempre positiva",
        "margem_liquida",
        lambda a: Banda(
            max(MARGEM_LIQUIDA[a] - TOLERANCIA_DA_MARGEM, MARGEM_MINIMA),
            MARGEM_LIQUIDA[a] + TOLERANCIA_DA_MARGEM,
        ),
    )

    # 4 · sazonalidade
    for medida, limites in SAZONALIDADE.items():
        o_que = medida.removeprefix("sazonalidade_")
        prefixo = "S-01" if o_que == "admissoes" else "S-02"
        lista += [
            Check(
                f"{prefixo}/desvio_maximo",
                "sazonalidade",
                f"{o_que}: maior desvio mensal contra o índice do CAGED",
                medida,
                "desvio_maximo",
                Banda(maximo=limites["desvio_maximo"]),
            ),
            Check(
                f"{prefixo}/desvio_medio",
                "sazonalidade",
                f"{o_que}: desvio médio contra o índice do CAGED",
                medida,
                "desvio_medio",
                Banda(maximo=limites["desvio_medio"]),
            ),
            Check(
                f"{prefixo}/correlacao",
                "sazonalidade",
                f"{o_que}: correlação com o índice do CAGED",
                medida,
                "correlacao",
                Banda(minimo=limites["correlacao"]),
            ),
        ]

    # 5 · coerência interna
    for codigo, descricao in INVARIANTES.items():
        lista.append(
            Check(codigo, "coerencia", descricao, "violacoes", codigo, Banda.exatamente(0))
        )

    # 6 · sujeira
    for codigo, (descricao, banda) in SUJEIRA.items():
        lista.append(Check(codigo, "sujeira", descricao, "sujeira", codigo, banda))
    for ano, alvo in GER_01.items():
        lista.append(
            Check(
                f"GER-01/{ano}",
                "sujeira",
                f"divergência do consolidado gerencial contra a operação, {ano}",
                "sujeira",
                f"GER-01/{ano}",
                Banda.em_torno(alvo, relativa=TOLERANCIA_GER_01),
            )
        )
    return lista
