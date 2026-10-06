# ruff: noqa: E501
"""A régua da gold: a gold medida com o mesmo motor que aceitou o dado sintético.

O `docs/06` prometeu que a régua, por não saber gerar dado nem ler banco, poderia um dia conferir
"as mesmas medidas tiradas do warehouse". Este módulo é esse dia. Ele produz um laudo com três
famílias de checks:

1. **conservação** (família `gold_conservacao`): cada total que o modelo declara em
   `Conservacao` (`gold.modelo`), medido na gold e na silver; a medida é a diferença absoluta
   e a banda é exatamente zero. É a prova de que nenhum join multiplicou nem perdeu linha ou
   centavo, agora como contrato declarado e não só como conferência interna da construção;
2. **integridade de chaves** (família `gold_integridade`): o grão não se repete, toda chave de
   dimensão existe na dimensão (a linha 0 inclusive), toda dimensão tem a linha 0;
3. **coerência com as bandas** (as famílias do contrato de aceite, `validacao.bandas`): as
   medidas do contrato que a gold consegue reproduzir com a definição do próprio contrato
   (clientes ativos no fim do ano, headcount médio e de pico, vagas abertas, margem líquida,
   invariantes C-01 a C-03 e C-05, e a sujeira CAD-01, PES-02, SST-01, FIN-01 e GER-01),
   conferidas contra as mesmas bandas que aceitaram a base. É a prova de ponta a ponta: o que
   entrou pela réplica e atravessou bronze, silver e gold ainda conta a mesma história.

A gold não é ajustada para caber na banda. Onde a medida da gold reprova, o laudo diz, e a
diferença de definição (quando é isso) é registrada no `docs/16`: o contrato foi escrito para o
gerador, e a gold mede o negócio como o `docs/04` manda. Por isso só as duas primeiras famílias
reprovam o asset da régua no Dagster; a terceira é relatada.

As medidas seguem o contrato de `validacao.bandas.MEDIDAS` ao pé da letra; onde o contrato diz
"2026: em 10/09", a gold usa o horizonte dela.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from rh_fictalent.gold import modelo
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.regua import Banda, Check, Laudo, avaliar

if TYPE_CHECKING:
    import duckdb

    from rh_fictalent.validacao.regua import Medidas

CONSERVACAO = "gold_conservacao"
INTEGRIDADE = "gold_integridade"
FAMILIAS_DA_GOLD = (CONSERVACAO, INTEGRIDADE)
H = modelo.HORIZONTE

# as medidas do contrato de aceite que a gold reproduz com a definição do contrato
DO_CONTRATO: dict[str, tuple[str, ...] | None] = {  # medida -> chaves (None = todas as do contrato)
    "clientes_ativos_fim_ano": None,
    "headcount_medio": None,
    "headcount_pico": None,
    "vagas_abertas": None,
    "margem_liquida": None,
    "violacoes": ("C-01", "C-02", "C-03", "C-05"),  # C-04 compara a folha, que é prioridade 2
    "sujeira": ("CAD-01", "PES-02", "SST-01/2024", "SST-01/2025", "FIN-01")
    + tuple(f"GER-01/{a}" for a in bandas.GER_01),
}


@dataclass(frozen=True)
class Resultado:
    laudo: Laudo

    @property
    def aprovada(self) -> bool:
        """Só as famílias da gold reprovam; a coerência com as bandas é relatada."""
        return not [
            r
            for r in self.laudo.resultados
            if r.check.familia in FAMILIAS_DA_GOLD and r.situacao.value == "REPROVADO"
        ]

    @property
    def veredito(self) -> str:
        """Uma linha: o que reprova (conservação e chaves) e o que se relata (as bandas)."""
        da_gold = [r for r in self.laudo.resultados if r.check.familia in FAMILIAS_DA_GOLD]
        ruins = [r for r in da_gold if r.situacao.value == "REPROVADO"]
        do_contrato = [r for r in self.laudo.resultados if r.check.familia not in FAMILIAS_DA_GOLD]
        pendentes = [r for r in do_contrato if r.situacao.value == "PENDENTE"]
        situacao = "REPROVADA" if ruins else "APROVADA"
        texto = (
            f"RÉGUA DA GOLD {situacao}: {len(da_gold) - len(ruins)} de {len(da_gold)} checks de "
            f"conservação e integridade aprovados; {len(do_contrato) - len(self.fora_da_banda) - len(pendentes)} "
            f"de {len(do_contrato)} medidas do contrato de aceite dentro da banda"
        )
        if pendentes:
            texto += f", {len(pendentes)} pendentes"
        if self.fora_da_banda:
            texto += (
                ".\nFora da banda (relatado, não reprova a gold; ver docs/16):\n  "
                + "\n  ".join(self.fora_da_banda)
            )
        return texto + ("" if self.fora_da_banda else ".")

    @property
    def fora_da_banda(self) -> list[str]:
        return [
            f"{r.check.codigo}: {r.valor:.4g} fora de {r.check.banda}"
            for r in self.laudo.resultados
            if r.check.familia not in FAMILIAS_DA_GOLD
            and r.situacao.value == "REPROVADO"
            and r.valor is not None
        ]


def checks() -> list[Check]:
    """Os checks da régua da gold: conservação, integridade e o recorte do contrato de aceite."""
    lista: list[Check] = []
    for t in modelo.TABELAS:
        for c in t.conservacoes:
            lista.append(
                Check(
                    f"G-C/{t.nome}/{c.o_que}",
                    CONSERVACAO,
                    f"{t.nome}: {c.o_que} igual ao da silver",
                    "conservacao_gold",
                    f"{t.nome}/{c.o_que}",
                    Banda.exatamente(0),
                )
            )
    for t in modelo.TABELAS:
        lista.append(
            Check(
                f"G-K/{t.nome}/grao",
                INTEGRIDADE,
                f"{t.nome}: chaves ({', '.join(t.chave)}) repetidas",
                "integridade_gold",
                f"{t.nome}/grao",
                Banda.exatamente(0),
            )
        )
        for coluna, dimensao in t.referencias.items():
            lista.append(
                Check(
                    f"G-K/{t.nome}/{coluna}",
                    INTEGRIDADE,
                    f"{t.nome}: {coluna} fora de {dimensao}",
                    "integridade_gold",
                    f"{t.nome}/{coluna}",
                    Banda.exatamente(0),
                )
            )
        if not t.fato:
            lista.append(
                Check(
                    f"G-K/{t.nome}/linha_0",
                    INTEGRIDADE,
                    f'{t.nome}: a linha 0 ("{modelo.NAO_SE_APLICA}")',
                    "integridade_gold",
                    f"{t.nome}/linha_0",
                    Banda.exatamente(1),
                )
            )
    for do_contrato in bandas.checks():
        chaves = DO_CONTRATO.get(do_contrato.medida, ())
        if chaves is None or do_contrato.chave in chaves:
            lista.append(do_contrato)
    return lista


def _um(con: duckdb.DuckDBPyConnection, sql: str) -> float:
    (valor,) = con.execute(sql).fetchall()[0]
    return 0.0 if valor is None else float(valor)


def _por_ano(con: duckdb.DuckDBPyConnection, sql: str) -> dict[str, float]:
    return {
        str(int(ano)): float(valor)
        for ano, valor in con.execute(sql).fetchall()
        if valor is not None
    }


def medir(con: duckdb.DuckDBPyConnection) -> Medidas:
    """Todas as medidas da régua da gold, lidas das views `gold.<tabela>` (e, na conservação,
    das views da silver na mesma conexão). A conexão precisa do horizonte (`modelo.preparar`)."""
    medidas: dict[str, dict[str, float]] = {"conservacao_gold": {}, "integridade_gold": {}}

    for t in modelo.TABELAS:
        gold = f"gold.{t.nome}"
        for c in t.conservacoes:
            na_gold = _um(con, f"SELECT {c.na_gold} FROM {gold}")  # noqa: S608 # nosec B608
            na_silver = _um(con, c.na_silver)
            medidas["conservacao_gold"][f"{t.nome}/{c.o_que}"] = float(
                abs(Decimal(str(na_gold)) - Decimal(str(na_silver)))
            )
        chave = ", ".join(t.chave)
        grupos = f"SELECT {chave} FROM {gold} GROUP BY ALL HAVING count(*) > 1"  # noqa: S608 # nosec B608
        medidas["integridade_gold"][f"{t.nome}/grao"] = _um(con, f"SELECT count(*) FROM ({grupos})")  # noqa: S608 # nosec B608
        for coluna, dimensao in t.referencias.items():
            orfas = f"SELECT count(*) FROM {gold} f WHERE f.{coluna} IS NULL OR NOT EXISTS (SELECT 1 FROM gold.{dimensao} d WHERE d.id = f.{coluna})"  # noqa: S608 # nosec B608
            medidas["integridade_gold"][f"{t.nome}/{coluna}"] = _um(con, orfas)
        if not t.fato:
            linha_zero = f"SELECT count(*) FROM {gold} WHERE id = 0"  # noqa: S608 # nosec B608
            medidas["integridade_gold"][f"{t.nome}/linha_0"] = _um(con, linha_zero)  # noqa: S608 # nosec B608

    # ── o recorte do contrato de aceite, com as definições de validacao.bandas.MEDIDAS ──
    medidas["clientes_ativos_fim_ano"] = _por_ano(
        con,
        f"""
        WITH anos AS (SELECT unnest(generate_series(2018, year({H}))) AS ano),
        dias AS (SELECT ano, least(make_date(ano, 12, 31), {H}) AS dia FROM anos),
        contratos AS (
          SELECT k.cliente_id, i.data AS inicio, coalesce(e.data, f.data, DATE '9999-12-31') AS fim
          FROM gold.fato_contrato k JOIN gold.dim_data i ON i.id = k.data_inicio_id
          LEFT JOIN gold.dim_data f ON f.id = k.data_fim_id LEFT JOIN gold.dim_data e ON e.id = k.data_encerramento_id)
        SELECT d.ano, count(DISTINCT c.cliente_id) FROM dias d JOIN contratos c ON c.inicio <= d.dia AND c.fim >= d.dia GROUP BY 1 ORDER BY 1
        """,  # noqa: S608 # nosec B608
    )
    medidas["headcount_medio"] = _por_ano(
        con,
        f"""
        SELECT ano, sum(pessoa_dias_alocados) / (date_diff('day', make_date(ano, 1, 1), least(make_date(ano, 12, 31), {H})) + 1)
        FROM gold.fato_posto_mes WHERE make_date(ano, 1, 1) <= {H} GROUP BY 1 ORDER BY 1
        """,  # noqa: S608 # nosec B608
    )
    medidas["headcount_pico"] = _por_ano(
        con,
        f"""
        WITH pico AS (SELECT ano, CASE WHEN ano = year({H}) THEN year({H}) * 100 + month({H}) ELSE ano * 100 + 12 END AS mes_id,
                             CASE WHEN ano = year({H}) THEN day({H}) ELSE 31 END AS dias
                      FROM (SELECT DISTINCT ano FROM gold.fato_posto_mes) WHERE make_date(ano, 1, 1) <= {H})
        SELECT p.ano, sum(m.pessoa_dias_alocados) / p.dias
        FROM pico p JOIN gold.fato_posto_mes m ON m.mes_id = p.mes_id GROUP BY p.ano, p.dias ORDER BY 1
        """,  # noqa: S608 # nosec B608
    )
    medidas["vagas_abertas"] = _por_ano(
        con, "SELECT ano, count(*) FROM gold.fato_vaga GROUP BY 1 ORDER BY 1"
    )
    medidas["margem_liquida"] = _por_ano(
        con,
        "SELECT ano, sum(resultado) / nullif(sum(faturamento_liquido), 0) FROM gold.fato_resultado_mes GROUP BY 1 ORDER BY 1",
    )
    medidas["violacoes"] = {
        "C-01": _um(
            con,
            """SELECT count(*) FROM gold.fato_alocacao a LEFT JOIN gold.fato_vinculo v ON v.contrato_trabalho_id = a.contrato_trabalho_id
               WHERE v.contrato_trabalho_id IS NULL OR a.data_inicio_id < v.data_admissao_id
                  OR (v.data_rescisao_id > 0 AND coalesce(nullif(a.data_fim_id, 0), 99999999) > v.data_rescisao_id)""",
        ),
        "C-02": _um(
            con,
            """SELECT count(*) FROM gold.fato_ponto_dia p JOIN gold.fato_alocacao a ON a.alocacao_id = p.alocacao_id
               WHERE p.data_id < a.data_inicio_id OR p.data_id > coalesce(nullif(a.data_fim_id, 0), 99999999)""",
        ),
        "C-03": _um(con, "SELECT count(*) FROM gold.fato_faturamento WHERE contrato_id = 0"),
        "C-05": _um(
            con,
            "SELECT count(*) FROM gold.fato_posto_mes WHERE dias_vigentes > 0 AND pessoa_dias_alocados > posicao_dias_contratados",
        ),
    }
    sujeira = {
        "CAD-01": _um(
            con,
            "SELECT count(*) FILTER (WHERE q_ats_01) / count(*) FROM gold.dim_candidato WHERE id > 0",
        ),
        "PES-02": _um(
            con, "SELECT count(*) FILTER (WHERE q_pes_01) / count(*) FROM gold.fato_vinculo"
        ),
        "FIN-01": _um(
            con,
            "SELECT count(*) FILTER (WHERE q_fin_05) / count(*) FILTER (WHERE pago) FROM gold.fato_recebimento",
        ),
    }
    sujeira.update(
        {
            f"SST-01/{ano}": valor
            for ano, valor in _por_ano(
                con,
                """WITH mes AS (SELECT ano, mes_id, sum(com_aso_vencido) / sum(pessoas_alocadas) AS parte
                               FROM gold.fato_conformidade_mes GROUP BY 1, 2 HAVING sum(pessoas_alocadas) > 0)
                   SELECT ano, avg(parte) FROM mes GROUP BY 1 ORDER BY 1""",
            ).items()
        }
    )
    sujeira.update(
        {
            f"GER-01/{ano}": valor
            for ano, valor in _por_ano(
                con,
                """SELECT ano, avg(abs(diferenca_faturamento) / faturamento) FROM gold.fato_resultado_mes
                   WHERE informado AND faturamento > 0 GROUP BY 1 ORDER BY 1""",
            ).items()
        }
    )
    medidas["sujeira"] = sujeira
    return medidas


def laudo(con: duckdb.DuckDBPyConnection) -> Resultado:
    modelo.preparar(con)
    return Resultado(avaliar(checks(), medir(con)))
