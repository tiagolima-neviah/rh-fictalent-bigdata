"""O backfill: a réplica MySQL copiada para a bronze do lake, em parquet, ano a ano.

A bronze é **espelho fiel**: mesma coluna, mesmo tipo, mesmo valor, sem regra de negócio
nenhuma. O que ela acrescenta é o que a réplica não tem: arquivo colunar, partição por ano e
linhagem. Corrigir dado é trabalho da silver, com prestação de contas; aqui, o que sai da
réplica entra igual.

Três decisões que valem explicação:

- **Partição por ano de `criado_em`.** É a data que não muda: uma linha nasce num ano e fica
  nele para sempre, então a partição de uma linha nunca se move. Particionar por
  `atualizado_em` faria a linha migrar de arquivo a cada alteração, e o incremental (card 5.2)
  teria de apagar de um arquivo e escrever em outro. `atualizado_em` é a marca d'água da carga,
  não o critério de partição.
- **Leitura em lote, com cursor sem buffer.** `ponto.marcacao` tem 4,3 milhões de linhas; um
  `fetchall` traria tudo para a memória. O cursor de streaming do pymysql entrega por lote, e o
  parquet é escrito lote a lote pelo mesmo escritor.
- **Contagem e leitura na mesma transação.** A conferência "escrevi o que existia" só vale se
  as duas perguntas virem o mesmo banco. `START TRANSACTION WITH CONSISTENT SNAPSHOT` no InnoDB
  dá uma foto: o `COUNT(*)` e o `SELECT` enxergam exatamente as mesmas linhas, mesmo que outra
  sessão esteja gravando (é o que o card 5.5 vai fazer de propósito). O nível REPEATABLE READ,
  que sustenta a foto, é o padrão do InnoDB, e por isso não é declarado aqui.

O esquema do parquet é declarado a partir do `information_schema`, nunca inferido do lote: uma
coluna toda nula num ano não pode virar um tipo diferente do mesmo campo em outro ano.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:  # pragma: no cover
    import pymysql

    from rh_fictalent.orquestracao.recursos import Lake

LOTE = 50_000
IDENTIFICADOR = re.compile(r"^[a-z_][a-z0-9_]*$")
CAMADA = "bronze"
PARTICAO = "criado_em"  # a coluna que define o ano da partição, em toda tabela de negócio


@dataclass(frozen=True)
class Copia:
    """O resultado de copiar uma tabela de um ano: o que a réplica tinha e o que foi gravado."""

    modulo: str
    tabela: str
    ano: int
    linhas: int
    esperadas: int
    bytes_escritos: int
    caminho: str

    @property
    def confere(self) -> bool:
        return self.linhas == self.esperadas


def identificador(nome: str) -> str:
    """Nome de schema, tabela ou coluna que vai para o SQL: só o que a DDL do projeto produz."""
    if not IDENTIFICADOR.match(nome):
        raise ValueError(f"identificador inválido: {nome!r}")
    return f"`{nome}`"


def _tipo_arrow(tipo: str, coluna: str, precisao: int | None, escala: int | None) -> pa.DataType:
    """O tipo do MySQL vira o tipo do parquet, declarado, nunca inferido."""
    if tipo in ("tinyint", "bool", "boolean"):
        return pa.bool_()  # a DDL usa BOOLEAN, que o MySQL guarda como TINYINT(1)
    if tipo in ("smallint", "mediumint", "int", "integer", "bigint"):
        return pa.int64()
    if tipo == "decimal":
        return pa.decimal128(precisao or 38, escala or 0)
    if tipo in ("float", "double"):
        return pa.float64()
    if tipo == "date":
        return pa.date32()
    if tipo in ("datetime", "timestamp"):
        return pa.timestamp("us")
    if tipo == "time":
        return pa.duration("us")
    if tipo in ("char", "varchar", "text", "tinytext", "mediumtext", "longtext", "json", "enum"):
        return pa.string()
    if tipo in ("binary", "varbinary", "blob", "tinyblob", "mediumblob", "longblob"):
        return pa.binary()
    raise ValueError(f"tipo do MySQL sem correspondência no parquet: {tipo!r} em {coluna!r}")


def esquema(con: pymysql.connections.Connection[Any], modulo: str, tabela: str) -> pa.Schema:
    """O esquema do parquet, tirado do information_schema: a bronze copia o tipo, não o adivinha."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT column_name, data_type, numeric_precision, numeric_scale, is_nullable "
            "FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (modulo, tabela),
        )
        colunas = list(cur.fetchall())
    if not colunas:
        raise ValueError(f"tabela sem colunas no information_schema: {modulo}.{tabela}")
    return pa.schema(
        [
            pa.field(
                str(nome),
                _tipo_arrow(str(tipo), str(nome), precisao, escala),
                nullable=anulavel == "YES",
            )
            for nome, tipo, precisao, escala, anulavel in colunas
        ]
    )


def _coluna(valores: tuple[Any, ...], campo: pa.Field) -> pa.Array:
    """Uma coluna do lote no tipo declarado. O driver devolve o BOOLEAN do MySQL como 1 ou 0
    (é um TINYINT(1) no fio), e o Arrow não aceita inteiro onde o esquema diz booleano."""
    if pa.types.is_boolean(campo.type):
        valores = tuple(None if v is None else bool(v) for v in valores)
    try:
        return pa.array(valores, type=campo.type)
    except pa.ArrowInvalid as erro:  # pragma: no cover - rede de segurança com nome da coluna
        raise ValueError(f"coluna {campo.name}: {erro}") from erro


def _faixa(ano: int) -> tuple[date, date]:
    return date(ano, 1, 1), date(ano + 1, 1, 1)


def copiar_ano(
    con: pymysql.connections.Connection[Any],
    lake: Lake,
    modulo: str,
    tabela: str,
    ano: int,
    lote: int = LOTE,
) -> Copia:
    """Copia as linhas criadas no ano para um parquet no lake, e confere a contagem.

    A transação com foto consistente garante que o `COUNT(*)` e o `SELECT` leem o mesmo banco;
    sem ela, uma gravação concorrente faria a conferência acusar diferença que não existe.
    """
    import pymysql.cursors

    alvo = f"{identificador(modulo)}.{identificador(tabela)}"
    coluna = identificador(PARTICAO)
    inicio, fim = _faixa(ano)
    campos = esquema(con, modulo, tabela)
    caminho = lake.caminho(CAMADA, modulo, tabela, f"ano={ano}.parquet")

    con.rollback()  # fecha transação pendente: a foto tem de começar do zero
    try:
        with con.cursor() as cur:
            # REPEATABLE READ é o padrão do InnoDB; a foto nasce aqui, antes da primeira leitura
            cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            sql = f"SELECT COUNT(*) FROM {alvo} WHERE {coluna} >= %s AND {coluna} < %s"  # noqa: S608 # nosec B608
            cur.execute(sql, (inicio, fim))
            (esperadas,) = cur.fetchone()
        escritas = 0
        with (
            lake.sistema().open(caminho, "wb") as arquivo,
            pq.ParquetWriter(arquivo, campos, compression="zstd") as escritor,
            con.cursor(pymysql.cursors.SSCursor) as cur,
        ):
            nomes = ", ".join(identificador(c) for c in campos.names)
            faixa = f"{coluna} >= %s AND {coluna} < %s ORDER BY `id`"
            sql = f"SELECT {nomes} FROM {alvo} WHERE {faixa}"  # noqa: S608 # nosec B608
            cur.execute(sql, (inicio, fim))
            while linhas := cur.fetchmany(lote):
                colunas = zip(*linhas, strict=True)
                arrays = [_coluna(v, c) for v, c in zip(colunas, campos, strict=True)]
                escritor.write_table(pa.Table.from_arrays(arrays, schema=campos))
                escritas += len(linhas)
    finally:
        con.rollback()  # só leitura: a transação fecha sem deixar nada

    tamanho = int(lake.sistema().info(caminho)["size"])
    return Copia(modulo, tabela, ano, escritas, int(esperadas), tamanho, caminho)
