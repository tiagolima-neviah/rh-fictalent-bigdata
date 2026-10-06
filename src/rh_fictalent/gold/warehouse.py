# ruff: noqa: E501
"""O warehouse Postgres: a gold servida num banco, nos schemas `dim` e `fato`.

O parquet no lake é a gold; o Postgres é onde ela é consultada (a API, o Power BI, o Grafana).
A DDL não é escrita à mão: sai do modelo (`gold.modelo`) e dos tipos que o DuckDB já deu a
cada coluna ao construir a tabela, traduzidos para o Postgres. O que o modelo declara vira
restrição no banco:

- o grão (`chave`) vira chave primária; no fato, o ano entra nela porque o Postgres exige a
  coluna de partição na chave;
- cada referência (`referencias`) vira chave estrangeira para a dimensão, o que obriga a
  carregar as dimensões antes dos fatos (a linhagem do Dagster já faz isso);
- a partição (`particao`) vira partição declarativa por intervalo, uma por ano, e **a carga
  é por partição**: o ano que chega do parquet substitui a partição inteira (`TRUNCATE` e
  `COPY`), e repetir a carga dá o mesmo resultado. A dimensão é pequena e tipo 1: entra por
  upsert pelo `id`, e a linha que deixou de existir no parquet sai.

Depois de carregar, a conferência lê o parquet e o Postgres com as mesmas expressões: a
contagem por ano e cada total de `Conservacao` do modelo. O que não bater, reprova; é a
mesma disciplina de auditar antes de dar por carregado que a silver e a gold seguem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from rh_fictalent.gold import barramento, modelo
from rh_fictalent.gold.modelo import Tabela

if TYPE_CHECKING:
    import duckdb

    from rh_fictalent.orquestracao.recursos import Warehouse

ESQUEMA_DIM = "dim"
ESQUEMA_FATO = "fato"
TIPOS = {  # DuckDB -> Postgres; o DECIMAL(p, s) é tratado à parte
    "BIGINT": "bigint",
    "INTEGER": "integer",
    "SMALLINT": "smallint",
    "TINYINT": "smallint",
    "HUGEINT": "numeric(38, 0)",
    "VARCHAR": "text",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIMESTAMP": "timestamp",
    "DOUBLE": "double precision",
    "FLOAT": "real",
}
_DECIMAL = re.compile(r"DECIMAL\((\d+),\s*(\d+)\)")
LOTE = 50_000  # linhas por lote do COPY


@dataclass(frozen=True)
class Alvo:
    """Onde a tabela do modelo mora no warehouse."""

    esquema: str
    nome: str

    @property
    def qualificado(self) -> str:
        return f"{self.esquema}.{self.nome}"

    def particao(self, ano: int) -> str:
        return f"{self.esquema}.{self.nome}_{ano}"


@dataclass
class Resultado:
    tabela: str
    linhas: int = 0
    anos: list[int] = field(default_factory=list)
    conferido: dict[str, str] = field(default_factory=dict)
    problemas: list[str] = field(default_factory=list)

    @property
    def aprovada(self) -> bool:
        return not self.problemas


def alvo(tabela: Tabela, esquema_dim: str = ESQUEMA_DIM, esquema_fato: str = ESQUEMA_FATO) -> Alvo:
    """`dim_cliente` vira `dim.cliente`; `fato_posto_mes` vira `fato.posto_mes`."""
    prefixo, nome = tabela.nome.split("_", 1)
    return Alvo(esquema_fato if tabela.fato else esquema_dim, nome)


def tipo_postgres(tipo_duckdb: str) -> str:
    decimal = _DECIMAL.fullmatch(tipo_duckdb)
    if decimal:
        return f"numeric({decimal.group(1)}, {decimal.group(2)})"
    try:
        return TIPOS[tipo_duckdb]
    except KeyError:
        raise ValueError(f"tipo do DuckDB sem tradução para o Postgres: {tipo_duckdb}") from None


def colunas(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> list[tuple[str, str]]:
    """As colunas da tabela como o DuckDB as construiu, já com o tipo do Postgres."""
    return [
        (nome, tipo_postgres(tipo))
        for nome, tipo, *_ in con.execute(f"DESCRIBE gold.{tabela.nome}").fetchall()
    ]  # noqa: S608 # nosec B608


def _descricao(tabela: Tabela) -> str:
    try:
        if tabela.fato:
            fato = barramento.fato(tabela.nome)
            texto = f"{fato.grao}; o processo: {fato.processo}"
        else:
            dimensao = barramento.dimensao(tabela.nome)
            texto = f"{dimensao.grao}; {dimensao.o_que_e}"
    except StopIteration:
        return tabela.nome
    return texto.replace("'", "''")


def ddl(
    con: duckdb.DuckDBPyConnection,
    tabela: Tabela,
    esquema_dim: str = ESQUEMA_DIM,
    esquema_fato: str = ESQUEMA_FATO,
) -> str:
    """A DDL da tabela no warehouse, gerada do modelo e dos tipos do DuckDB. Idempotente."""
    destino = alvo(tabela, esquema_dim, esquema_fato)
    linhas = [f"  {nome} {tipo}" for nome, tipo in colunas(con, tabela)]
    chave = list(tabela.chave) + ([tabela.particao] if tabela.fato else [])
    linhas.append(f"  PRIMARY KEY ({', '.join(chave)})")
    for coluna, dimensao in tabela.referencias.items():
        dim = alvo(modelo.tabela(dimensao), esquema_dim, esquema_fato)
        linhas.append(f"  FOREIGN KEY ({coluna}) REFERENCES {dim.qualificado} (id)")
    corpo = ",\n".join(linhas)
    particao = f"\nPARTITION BY RANGE ({tabela.particao})" if tabela.fato else ""
    return (
        f"CREATE SCHEMA IF NOT EXISTS {destino.esquema};\n"
        f"CREATE TABLE IF NOT EXISTS {destino.qualificado} (\n{corpo}\n){particao};\n"
        f"COMMENT ON TABLE {destino.qualificado} IS '{_descricao(tabela)}';\n"
    )


def ddl_da_particao(destino: Alvo, ano: int) -> str:
    return f"CREATE TABLE IF NOT EXISTS {destino.particao(ano)} PARTITION OF {destino.qualificado} FOR VALUES FROM ({ano}) TO ({ano + 1});"


def anos_no_parquet(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> list[int]:
    anos_sql = f"SELECT DISTINCT {tabela.particao} FROM gold.{tabela.nome} ORDER BY 1"  # noqa: S608 # nosec B608
    return [int(a) for (a,) in con.execute(anos_sql).fetchall()]  # noqa: S608 # nosec B608


def anos_no_warehouse(cur: Any, destino: Alvo) -> list[int]:
    """As partições que já existem: pelo nome, `<tabela>_<ano>`."""
    cur.execute(
        "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
        "JOIN pg_class p ON p.oid = i.inhparent JOIN pg_namespace n ON n.oid = p.relnamespace "
        "WHERE n.nspname = %s AND p.relname = %s",
        (destino.esquema, destino.nome),
    )
    return sorted(int(str(nome).rsplit("_", 1)[1]) for (nome,) in cur.fetchall())


def _copiar(
    con: duckdb.DuckDBPyConnection, cur: Any, destino: str, nomes: list[str], sql: str
) -> int:
    """COPY FROM STDIN com as linhas lidas do DuckDB em lotes; devolve quantas entraram."""
    lidas = 0
    leitor = con.sql(sql).to_arrow_reader(LOTE)
    with cur.copy(f"COPY {destino} ({', '.join(nomes)}) FROM STDIN") as copia:  # noqa: S608 # nosec B608
        for lote in leitor:
            for linha in lote.to_pylist():
                copia.write_row([linha[n] for n in nomes])
                lidas += 1
    return lidas


def carregar(
    con: duckdb.DuckDBPyConnection,
    warehouse: Warehouse,
    tabela: Tabela,
    esquema_dim: str = ESQUEMA_DIM,
    esquema_fato: str = ESQUEMA_FATO,
) -> Resultado:
    """Cria o que faltar, carrega (a dimensão por upsert; o fato por partição) e confere."""
    destino = alvo(tabela, esquema_dim, esquema_fato)
    nomes = [n for n, _ in colunas(con, tabela)]
    resultado = Resultado(tabela.nome)
    with warehouse.conectar() as conexao, conexao.cursor() as cur:
        cur.execute(ddl(con, tabela, esquema_dim, esquema_fato))
        if tabela.fato:
            anos = anos_no_parquet(con, tabela)
            for ano in sorted(set(anos) | set(anos_no_warehouse(cur, destino))):
                cur.execute(ddl_da_particao(destino, ano))
                cur.execute(f"TRUNCATE TABLE {destino.particao(ano)}")  # noqa: S608 # nosec B608
                if ano in anos:
                    sql = f"SELECT {', '.join(nomes)} FROM gold.{tabela.nome} WHERE {tabela.particao} = {ano}"  # noqa: S608 # nosec B608
                    resultado.linhas += _copiar(con, cur, destino.particao(ano), nomes, sql)
            resultado.anos = anos
        else:
            cur.execute(
                f"CREATE TEMP TABLE entrada (LIKE {destino.qualificado} INCLUDING DEFAULTS) ON COMMIT DROP"
            )  # noqa: S608 # nosec B608
            tudo = f"SELECT {', '.join(nomes)} FROM gold.{tabela.nome}"  # noqa: S608 # nosec B608
            resultado.linhas = _copiar(con, cur, "entrada", nomes, tudo)
            atualiza = ", ".join(f"{n} = EXCLUDED.{n}" for n in nomes if n != "id")
            cur.execute(
                f"INSERT INTO {destino.qualificado} ({', '.join(nomes)}) SELECT {', '.join(nomes)} FROM entrada "  # noqa: S608 # nosec B608
                f"ON CONFLICT (id) DO UPDATE SET {atualiza}"
            )
            sumidas = f"DELETE FROM {destino.qualificado} WHERE id NOT IN (SELECT id FROM entrada)"  # noqa: S608 # nosec B608
            cur.execute(sumidas)
        conexao.commit()
    resultado.problemas = conferir(
        con, warehouse, tabela, esquema_dim, esquema_fato, resultado.conferido
    )
    return resultado


def _numero(valor: Any) -> Decimal:
    return Decimal(0) if valor is None else Decimal(str(valor))


def conferir(
    con: duckdb.DuckDBPyConnection,
    warehouse: Warehouse,
    tabela: Tabela,
    esquema_dim: str = ESQUEMA_DIM,
    esquema_fato: str = ESQUEMA_FATO,
    conferido: dict[str, str] | None = None,
) -> list[str]:
    """O parquet e o Postgres com as mesmas expressões: contagem (por ano, no fato) e cada total do modelo."""
    destino = alvo(tabela, esquema_dim, esquema_fato)
    problemas: list[str] = []
    conferido = {} if conferido is None else conferido
    # o total que depende do horizonte (uma variável da sessão do DuckDB) não tem como ser lido
    # no Postgres com a mesma expressão; a contagem por ano e os demais totais bastam
    expressoes = [("linhas", "count(*)")] + [
        (c.o_que, c.na_gold) for c in tabela.conservacoes if modelo.HORIZONTE not in c.na_gold
    ]
    for o_que, expressao in expressoes:
        if tabela.fato:
            no_parquet_sql = (
                f"SELECT {tabela.particao}, {expressao} FROM gold.{tabela.nome} GROUP BY 1"  # noqa: S608 # nosec B608
            )
            no_postgres_sql = (
                f"SELECT {tabela.particao}, {expressao} FROM {destino.qualificado} GROUP BY 1"  # noqa: S608 # nosec B608
            )
            no_parquet = {int(a): _numero(v) for a, v in con.execute(no_parquet_sql).fetchall()}  # noqa: S608 # nosec B608
            no_postgres = {int(a): _numero(v) for a, v in warehouse.consultar(no_postgres_sql)}  # noqa: S608 # nosec B608
        else:
            total_parquet = f"SELECT {expressao} FROM gold.{tabela.nome}"  # noqa: S608 # nosec B608
            total_postgres = f"SELECT {expressao} FROM {destino.qualificado}"  # noqa: S608 # nosec B608
            no_parquet = {0: _numero(con.execute(total_parquet).fetchall()[0][0])}
            no_postgres = {0: _numero(warehouse.consultar(total_postgres)[0][0])}
        conferido[o_que] = str(sum(no_parquet.values()))
        for ano in sorted(set(no_parquet) | set(no_postgres)):
            a, b = no_parquet.get(ano, Decimal(0)), no_postgres.get(ano, Decimal(0))
            if a != b:
                onde = f" em {ano}" if tabela.fato else ""
                problemas.append(f"{o_que}{onde}: parquet {a}, postgres {b}")
    return problemas
