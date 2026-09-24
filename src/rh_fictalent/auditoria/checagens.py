"""As perguntas que toda auditoria de qualidade faz, escritas uma vez, sobre a bronze.

Um notebook de auditoria repete as mesmas perguntas em tabelas diferentes: o que está vazio,
o que está repetido, o que aponta para um registro que não existe, o que está fora do domínio
declarado, o que termina antes de começar. Repetir a pergunta em código dentro de cada
notebook é repetir o erro em cada um; aqui ela é escrita uma vez, testada, e o notebook só
diz em que tabela e em que coluna.

Tudo roda no DuckDB, sobre as views que `rh_fictalent.lake.consulta.abrir` cria com os nomes
da réplica, e sempre sobre as **linhas vivas** (as marcadas como excluídas na bronze ficam de
fora). Nenhuma função conhece o gerador: as regras vêm do esquema (`esquema.py`) e do que o
consulente pergunta.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import duckdb
import pandas as pd

from rh_fictalent.auditoria.esquema import Tabela
from rh_fictalent.ingestao.backfill import CONTROLE

SEM_FIM = "DATE '9999-12-31'"  # vigência aberta: o fim que ainda não aconteceu


def _vivas(tabela: str) -> str:
    """A tabela sem as linhas marcadas como excluídas, como subconsulta."""
    return f'(SELECT * FROM {tabela} WHERE "{CONTROLE}" IS NULL)'  # noqa: S608 # nosec B608


def _normalizado(expressao: str) -> str:
    """Texto comparável: sem acento, sem caixa, sem espaço sobrando."""
    limpo = f"regexp_replace(trim(CAST({expressao} AS VARCHAR)), '\\s+', ' ', 'g')"
    return f"strip_accents(lower({limpo}))"


def contar(con: duckdb.DuckDBPyConnection, sql: str, *parametros: Any) -> int:
    """Uma consulta que devolve um número só."""
    return int(con.execute(sql, list(parametros) or None).fetchall()[0][0])


def linhas(con: duckdb.DuckDBPyConnection, tabela: str) -> int:
    """Linhas vivas da tabela."""
    return contar(con, f"SELECT count(*) FROM {_vivas(tabela)}")  # noqa: S608 # nosec B608


def perfil(con: duckdb.DuckDBPyConnection, tabela: str) -> pd.DataFrame:
    """Uma linha por coluna: tipo, nulos, distintos aproximados, mínimo e máximo.

    É o mapa que diz onde olhar: coluna toda nula, coluna com um valor só, data fora do arco.
    Os nulos são contados exatos (o `SUMMARIZE` só dá o percentual arredondado); mínimo,
    máximo e distintos vêm do `SUMMARIZE`, que é aproximado nos distintos e basta para o mapa.
    """
    total = linhas(con, tabela)
    resumo = con.execute(
        f"SUMMARIZE SELECT * FROM {tabela} WHERE {CONTROLE} IS NULL"  # noqa: S608 # nosec B608
    ).df()
    resumo = resumo[resumo["column_name"] != CONTROLE].reset_index(drop=True)
    colunas = list(resumo["column_name"])
    contagens = ", ".join(f"count({c}) AS c{i}" for i, c in enumerate(colunas))
    preenchidas = con.execute(
        f"SELECT {contagens} FROM {_vivas(tabela)}"  # noqa: S608 # nosec B608
    ).fetchall()[0]
    quadro = pd.DataFrame(
        {
            "tabela": tabela,
            "coluna": colunas,
            "tipo": resumo["column_type"].to_numpy(),
            "nulos": [total - int(n) for n in preenchidas],
            "distintos": resumo["approx_unique"].astype(int).to_numpy(),
            "minimo": resumo["min"].to_numpy(),
            "maximo": resumo["max"].to_numpy(),
        }
    )
    quadro["pct_nulo"] = (quadro["nulos"] / total * 100).round(2) if total else 0.0
    return quadro[
        ["tabela", "coluna", "tipo", "nulos", "pct_nulo", "distintos", "minimo", "maximo"]
    ]


_COMPATIVEIS: dict[tuple[str, ...], tuple[str, ...]] = {
    ("BIGINT", "INT", "INTEGER", "SMALLINT", "TINYINT", "MEDIUMINT"): (
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
    ),
    ("BOOLEAN", "BOOL"): ("BOOLEAN",),
    ("VARCHAR", "CHAR", "TEXT", "JSON", "ENUM"): ("VARCHAR",),
    ("DATE",): ("DATE",),
    ("DATETIME", "TIMESTAMP"): ("TIMESTAMP",),
    ("TIME",): ("TIME",),
    ("DECIMAL",): ("DECIMAL",),
    ("FLOAT", "DOUBLE"): ("DOUBLE", "FLOAT"),
}


def compativel(ddl: str, bronze: str) -> bool:
    """O tipo que a DDL declara e o tipo que a bronze gravou contam a mesma coisa?"""
    for origens, destinos in _COMPATIVEIS.items():
        if ddl.upper() in origens:
            return any(bronze.upper().startswith(d) for d in destinos)
    return False


def tipos(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> pd.DataFrame:
    """Coluna a coluna, o tipo da DDL e o tipo da bronze, e se são compatíveis.

    A bronze promete ser espelho da réplica, e espelho de tipo é parte da promessa: um
    inteiro copiado como booleano vira `True` em toda linha e nenhuma contagem acusa.
    """
    descricao = con.execute(f"DESCRIBE {tabela.qualificado}").df()  # noqa: S608 # nosec B608
    na_bronze = dict(zip(descricao["column_name"], descricao["column_type"], strict=True))
    return pd.DataFrame(
        [
            {
                "tabela": tabela.qualificado,
                "coluna": c.nome,
                "ddl": c.tipo,
                "bronze": na_bronze.get(c.nome, "AUSENTE"),
                "compativel": compativel(c.tipo, na_bronze.get(c.nome, "")),
            }
            for c in tabela.colunas
        ],
        columns=["tabela", "coluna", "ddl", "bronze", "compativel"],
    )


def duplicatas(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    colunas: Sequence[str],
    normalizar: bool = False,
) -> pd.DataFrame:
    """Os grupos de linhas que repetem a mesma combinação de colunas, do maior para o menor.

    Com `normalizar`, a comparação ignora acento, caixa e espaço: é a duplicata de conteúdo,
    a que passa por qualquer `UNIQUE` do banco porque, para o banco, "São Paulo" e
    "SAO PAULO" são textos diferentes.
    """
    expressoes = [(_normalizado(c) if normalizar else c) for c in colunas]
    selecao = ", ".join(f"{e} AS {c}" for e, c in zip(expressoes, colunas, strict=True))
    posicoes = ", ".join(str(i + 1) for i in range(len(colunas)))
    condicao = " AND ".join(f"{c} IS NOT NULL" for c in colunas)
    sql = (  # noqa: S608
        f"SELECT {selecao}, count(*) AS linhas FROM {_vivas(tabela)} WHERE {condicao} "  # nosec B608
        f"GROUP BY {posicoes} HAVING count(*) > 1 ORDER BY linhas DESC, 1"
    )
    return con.execute(sql).df()


def repetidos(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    colunas: Sequence[str],
    normalizar: bool = False,
) -> tuple[int, int]:
    """(grupos repetidos, linhas envolvidas) para a combinação de colunas."""
    grupos = duplicatas(con, tabela, colunas, normalizar)
    return len(grupos), int(grupos["linhas"].sum()) if len(grupos) else 0


def orfaos(
    con: duckdb.DuckDBPyConnection,
    filha: str,
    coluna: str,
    mae: str,
    chave: str = "id",
) -> int:
    """Linhas vivas da filha cuja referência não encontra uma linha viva na mãe.

    Uma mãe marcada como excluída conta como ausente: na bronze, a referência a uma linha
    que morreu é justamente o que vale a pena achar.
    """
    sql = (  # noqa: S608
        f"SELECT count(*) FROM {_vivas(filha)} f WHERE f.{coluna} IS NOT NULL "  # nosec B608
        f"AND NOT EXISTS (SELECT 1 FROM {_vivas(mae)} m WHERE m.{chave} = f.{coluna})"
    )
    return contar(con, sql)


def integridade(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> pd.DataFrame:
    """Todas as chaves estrangeiras da tabela, conferidas: uma linha por chave."""
    return pd.DataFrame(
        [
            {
                "tabela": tabela.qualificado,
                "coluna": chave.coluna,
                "alvo": chave.alvo,
                "orfaos": orfaos(con, tabela.qualificado, chave.coluna, chave.alvo),
            }
            for chave in tabela.chaves
        ],
        columns=["tabela", "coluna", "alvo", "orfaos"],
    )


def fora_do_dominio(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna: str,
    esperados: Sequence[str],
) -> pd.DataFrame:
    """Os valores da coluna que não estão na lista esperada, com quantas linhas cada um."""
    marcadores = ", ".join("?" for _ in esperados)
    sql = (  # noqa: S608
        f"SELECT {coluna} AS valor, count(*) AS linhas FROM {_vivas(tabela)} "  # nosec B608
        f"WHERE {coluna} IS NOT NULL AND {coluna} NOT IN ({marcadores}) "
        f"GROUP BY 1 ORDER BY 2 DESC"
    )
    return con.execute(sql, list(esperados)).df()


def dominios(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> pd.DataFrame:
    """Todos os domínios que a DDL declara em `CHECK`, conferidos: uma linha por coluna."""
    quadro = []
    for coluna, esperados in tabela.dominios.items():
        fora = fora_do_dominio(con, tabela.qualificado, coluna, esperados)
        quadro.append(
            {
                "tabela": tabela.qualificado,
                "coluna": coluna,
                "esperados": len(esperados),
                "fora": int(fora["linhas"].sum()) if len(fora) else 0,
                "exemplos": ", ".join(str(v) for v in fora["valor"].head(5)),
            }
        )
    return pd.DataFrame(quadro, columns=["tabela", "coluna", "esperados", "fora", "exemplos"])


def ordem_temporal(con: duckdb.DuckDBPyConnection, tabela: str, antes: str, depois: str) -> int:
    """Linhas em que `depois` vem antes de `antes` (as duas preenchidas)."""
    sql = (  # noqa: S608
        f"SELECT count(*) FROM {_vivas(tabela)} "  # nosec B608
        f"WHERE {antes} IS NOT NULL AND {depois} IS NOT NULL AND {depois} < {antes}"
    )
    return contar(con, sql)


def fora_da_faixa(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna: str,
    minimo: float | str | None = None,
    maximo: float | str | None = None,
) -> int:
    """Linhas com a coluna abaixo do mínimo ou acima do máximo (limites inclusivos)."""
    condicoes = [f"{coluna} IS NOT NULL"]
    if minimo is not None:
        condicoes.append(f"{coluna} < {minimo}")
    if maximo is not None:
        condicoes.append(f"{coluna} > {maximo}")
    fora = " OR ".join(condicoes[1:]) or "FALSE"
    sql = f"SELECT count(*) FROM {_vivas(tabela)} WHERE {condicoes[0]} AND ({fora})"  # noqa: S608 # nosec B608
    return contar(con, sql)


def texto_inconsistente(con: duckdb.DuckDBPyConnection, tabela: str, coluna: str) -> dict[str, int]:
    """Os vícios do texto digitado: espaço nas pontas, espaço duplo, caixa alta, caixa baixa
    e o efeito prático deles, valores que existem em mais de uma grafia."""
    c = coluna
    sql = (  # noqa: S608
        f"SELECT count(*) FILTER (WHERE {c} <> trim({c})) AS espacos_nas_pontas, "  # nosec B608
        f"count(*) FILTER (WHERE {c} LIKE '%  %') AS espacos_duplos, "
        f"count(*) FILTER (WHERE {c} = upper({c}) AND {c} <> lower({c}) AND length({c}) > 3) "
        "AS caixa_alta, "
        f"count(*) FILTER (WHERE {c} = lower({c}) AND {c} <> upper({c})) AS caixa_baixa "
        f"FROM {_vivas(tabela)} WHERE {c} IS NOT NULL"
    )
    espacos_pontas, espacos_duplos, caixa_alta, caixa_baixa = con.execute(sql).fetchall()[0]
    grafias = variantes(con, tabela, coluna, limite=None)
    return {
        "espacos_nas_pontas": int(espacos_pontas),
        "espacos_duplos": int(espacos_duplos),
        "caixa_alta": int(caixa_alta),
        "caixa_baixa": int(caixa_baixa),
        "valores_com_mais_de_uma_grafia": len(grafias),
        "linhas_em_grafia_multipla": int(grafias["linhas"].sum()) if len(grafias) else 0,
    }


def variantes(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna: str,
    limite: int | None = 20,
) -> pd.DataFrame:
    """Os valores que, normalizados, são o mesmo, mas foram gravados em mais de uma grafia."""
    sql = (  # noqa: S608
        f"SELECT {_normalizado(coluna)} AS forma, list(DISTINCT {coluna}) AS grafias, "  # nosec B608
        f"count(DISTINCT {coluna}) AS quantas, count(*) AS linhas "
        f"FROM {_vivas(tabela)} WHERE {coluna} IS NOT NULL "
        f"GROUP BY 1 HAVING count(DISTINCT {coluna}) > 1 ORDER BY linhas DESC, forma"
    )
    if limite is not None:
        sql += f" LIMIT {int(limite)}"
    return con.execute(sql).df()


def sobreposicoes(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    grupo: str | Sequence[str],
    inicio: str,
    fim: str,
) -> int:
    """Pares de linhas do mesmo grupo cujos períodos se cruzam (fim nulo = ainda vigente).

    O grupo pode ser uma coluna ou várias (um piso é por convenção **e** função).
    """
    colunas = [grupo] if isinstance(grupo, str) else list(grupo)
    mesmo_grupo = " AND ".join(f"a.{g} = b.{g}" for g in colunas)
    sql = (  # noqa: S608
        f"SELECT count(*) FROM {_vivas(tabela)} a JOIN {_vivas(tabela)} b "  # nosec B608
        f"ON {mesmo_grupo} AND a.id < b.id "
        f"AND a.{inicio} <= coalesce(b.{fim}, {SEM_FIM}) "
        f"AND b.{inicio} <= coalesce(a.{fim}, {SEM_FIM})"
    )
    return contar(con, sql)


def _digitos(valor: str) -> str:
    return "".join(ch for ch in valor if ch.isdigit())


def _digito(numeros: Sequence[int], pesos: Sequence[int]) -> int:
    resto = sum(n * p for n, p in zip(numeros, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def cpf_valido(cpf: str) -> bool:
    """O CPF pelos dois dígitos verificadores; sequências repetidas (111.111.111-11) não valem."""
    d = _digitos(cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    n = [int(ch) for ch in d]
    return n[9] == _digito(n[:9], range(10, 1, -1)) and n[10] == _digito(n[:10], range(11, 1, -1))


def cnpj_valido(cnpj: str) -> bool:
    """O CNPJ numérico pelos dois dígitos verificadores."""
    d = _digitos(cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    n = [int(ch) for ch in d]
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, *pesos1]
    return n[12] == _digito(n[:12], pesos1) and n[13] == _digito(n[:13], pesos2)


def documentos_invalidos(
    con: duckdb.DuckDBPyConnection,
    tabela: str,
    coluna: str,
    validador: Callable[[str], bool],
) -> tuple[int, int]:
    """(linhas, valores distintos) cujo documento não passa no validador; nulos ficam de fora."""
    sql = (  # noqa: S608
        f"SELECT CAST({coluna} AS VARCHAR) AS documento, count(*) AS linhas "  # nosec B608
        f"FROM {_vivas(tabela)} WHERE {coluna} IS NOT NULL GROUP BY 1"
    )
    quadro = con.execute(sql).df()
    if quadro.empty:
        return 0, 0
    invalidos = quadro[~quadro["documento"].map(validador)]
    return int(invalidos["linhas"].sum()), len(invalidos)
