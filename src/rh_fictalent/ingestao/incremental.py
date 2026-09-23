"""A carga incremental: só o que mudou desde a última vez, aplicado nas partições certas.

O backfill (card 5.1) traz tudo; rodá-lo todo dia custaria 124 segundos e transferiria 8,4
milhões de linhas para reescrever o que já estava igual. A carga incremental pede à réplica
apenas as linhas com `atualizado_em` acima da marca d'água, descobre em que partições elas
caem (pelo ano de `criado_em`, que não muda) e reescreve só essas.

Três armadilhas desta carga, e o que este módulo faz com cada uma:

- **O relógio.** A comparação é contra `atualizado_em`, que o MySQL grava. O corte de cada
  carga é pedido à própria réplica (`SELECT NOW(6)`), não ao relógio de quem roda o pipeline:
  máquinas diferentes têm relógios diferentes, e a diferença viraria linha perdida.
- **A transação que commita tarde.** `atualizado_em` é gravado quando o `UPDATE` roda, mas a
  linha só fica visível no commit. Uma transação que grava 10:00:00 e commita 10:00:05 é
  invisível para a carga das 10:00:02, e ficaria para sempre abaixo da marca nova. Por isso a
  carga volta um pouco no tempo (`SOBREPOSICAO`) e relê uma janela que já leu. Reler é
  inofensivo porque a aplicação é por id: a linha entra no lugar dela, não duas vezes.
- **A linha apagada.** `DELETE` não deixa `atualizado_em` para ser encontrado. A conferência de
  contagem por partição detecta o buraco e a carga falha dizendo o que houve; aplicar exclusão
  como marcação lógica é o card 5.3, que lê a trilha de `meta.exclusao_auditoria`.

A aplicação é um merge por partição: lê o parquet que está lá, tira as linhas que vieram de
novo (pelo id), junta as versões novas, ordena por id e reescreve. No fim, conta a partição na
réplica e compara. Se bater, a bronze é de novo espelho fiel.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from rh_fictalent.ingestao.backfill import (
    CAMADA,
    PARTICAO,
    _coluna,
    _faixa,
    copiar_ano,
    esquema,
    esquema_bronze,
    identificador,
)
from rh_fictalent.ingestao.exclusoes import vivas

if TYPE_CHECKING:  # pragma: no cover
    import pymysql

    from rh_fictalent.orquestracao.recursos import Lake

# quanto a carga volta no tempo antes da marca, para não perder transação que commitou tarde.
# Custa reler uma janela pequena; não voltar custa perder linha, e perder linha é silencioso.
SOBREPOSICAO = timedelta(hours=1)
ANOS = tuple(range(2018, 2027))


@dataclass
class Sincronizacao:
    """O que a carga fez numa tabela."""

    modulo: str
    tabela: str
    desde: datetime
    ate: datetime
    alteradas: int = 0
    particoes: dict[int, int] = field(default_factory=dict)  # ano -> linhas na partição depois
    divergencias: list[str] = field(default_factory=list)

    @property
    def nome(self) -> str:
        return f"{self.modulo}.{self.tabela}"

    @property
    def confere(self) -> bool:
        return not self.divergencias


def agora_na_replica(con: pymysql.connections.Connection[Any]) -> datetime:
    """O corte da carga, pedido ao relógio de quem grava `atualizado_em`."""
    con.rollback()  # fora de qualquer foto: ver `nova_foto`
    with con.cursor() as cur:
        cur.execute("SELECT NOW(6)")
        (instante,) = cur.fetchone()
    con.rollback()
    return instante  # type: ignore[no-any-return]


def nova_foto(con: pymysql.connections.Connection[Any]) -> None:
    """Começa uma foto consistente, descartando a anterior.

    Em REPEATABLE READ, que é o padrão do InnoDB, a transação que o driver abre sozinho na
    primeira leitura congela o que a conexão enxerga **até o fim dela**. Sem este descarte, a
    segunda carga na mesma conexão leria o mundo da primeira e juraria que nada mudou. Foi o
    que aconteceu na primeira prova contra a réplica: o `UPDATE` estava commitado e a carga
    via zero linhas alteradas.
    """
    con.rollback()
    with con.cursor() as cur:
        cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")


def marca_da_bronze(lake: Lake, modulo: str, tabela: str) -> datetime | None:
    """O maior `atualizado_em` já gravado na bronze: a marca que a própria camada sabe dizer.

    Serve para a primeira carga depois do backfill, quando ainda não há registro no warehouse.
    Lê só a coluna do carimbo de cada partição, não o parquet inteiro.
    """
    fs = lake.sistema()
    maior: datetime | None = None
    for ano in ANOS:
        caminho = lake.caminho(CAMADA, modulo, tabela, f"ano={ano}.parquet")
        if not fs.exists(caminho):
            continue
        with fs.open(caminho, "rb") as arquivo:
            coluna = pq.read_table(arquivo, columns=["atualizado_em"])["atualizado_em"]
        if not len(coluna):
            continue
        desta = pa.compute.max(coluna).as_py()
        maior = desta if maior is None or desta > maior else maior
    return maior


def _alteradas(
    con: pymysql.connections.Connection[Any],
    modulo: str,
    tabela: str,
    campos: pa.Schema,
    desde: datetime,
    ate: datetime,
) -> dict[int, list[tuple[Any, ...]]]:
    """As linhas alteradas na janela, repartidas pelo ano da partição a que pertencem."""
    alvo = f"{identificador(modulo)}.{identificador(tabela)}"
    nomes = ", ".join(identificador(c) for c in campos.names)
    janela = "`atualizado_em` > %s AND `atualizado_em` <= %s"
    sql = f"SELECT {nomes} FROM {alvo} WHERE {janela} ORDER BY `id`"  # noqa: S608 # nosec B608
    posicao = campos.names.index(PARTICAO)
    por_ano: dict[int, list[tuple[Any, ...]]] = {}
    with con.cursor() as cur:
        cur.execute(sql, (desde, ate))
        for linha in cur.fetchall():
            por_ano.setdefault(linha[posicao].year, []).append(linha)
    return por_ano


def _aplicar(
    lake: Lake, modulo: str, tabela: str, ano: int, campos: pa.Schema, linhas: list[tuple[Any, ...]]
) -> int:
    """Merge da partição: o que já estava, menos os ids que voltaram, mais as versões novas.

    A linha que volta da réplica volta viva: se ela está lá para ser lida, não foi apagada. O
    `excluido_em` das que não voltaram fica como estava.
    """
    caminho = lake.caminho(CAMADA, modulo, tabela, f"ano={ano}.parquet")
    fs = lake.sistema()
    na_bronze = esquema_bronze(campos)
    arrays = [_coluna(v, c) for v, c in zip(zip(*linhas, strict=True), campos, strict=True)]
    arrays.append(pa.nulls(len(linhas), type=pa.timestamp("us")))
    novas = pa.Table.from_arrays(arrays, schema=na_bronze)
    if fs.exists(caminho):
        with fs.open(caminho, "rb") as arquivo:
            antiga = pq.read_table(arquivo)
        trocados = pa.compute.is_in(antiga["id"], value_set=novas["id"])
        mantidas = antiga.filter(pa.compute.invert(trocados))
        juntas = pa.concat_tables([mantidas.cast(na_bronze), novas])
    else:
        juntas = novas
    juntas = juntas.sort_by([("id", "ascending")])
    with fs.open(caminho, "wb") as arquivo:
        pq.write_table(juntas, arquivo, compression="zstd")
    return int(juntas.num_rows)


def _contar(
    con: pymysql.connections.Connection[Any], modulo: str, tabela: str, ano: int, ate: datetime
) -> int:
    """Quantas linhas a partição deve ter na bronze depois desta carga.

    O recorte é por `criado_em` **até o corte**, não pelo que existe agora: a bronze representa
    a réplica no instante do corte, e uma linha criada depois dele ainda não é dela. Contar por
    `atualizado_em` seria errado na direção oposta: a linha alterada depois do corte continua
    na bronze, com a versão antiga, e precisa continuar sendo contada.
    """
    alvo = f"{identificador(modulo)}.{identificador(tabela)}"
    coluna = identificador(PARTICAO)
    inicio, fim = _faixa(ano)
    limite = min(fim, ate.date() + timedelta(days=1))
    sql = f"SELECT COUNT(*) FROM {alvo} WHERE {coluna} >= %s AND {coluna} < %s AND {coluna} <= %s"  # noqa: S608 # nosec B608
    with con.cursor() as cur:
        cur.execute(sql, (inicio, limite, ate))
        (quantas,) = cur.fetchone()
    return int(quantas)


def conferir(
    con: pymysql.connections.Connection[Any],
    lake: Lake,
    modulo: str,
    tabela: str,
    anos: Iterable[int],
    ate: datetime,
) -> list[str]:
    """As linhas vivas de cada partição têm de ser as que a réplica tinha no corte.

    Vale para toda partição que a carga mexeu, seja por alteração (o merge) ou por exclusão (a
    marcação). Uma linha apagada não gera alteração nenhuma, então a partição dela só é
    conferida se alguém disser explicitamente que ela mudou.
    """
    divergencias = []
    for ano in sorted(set(anos)):
        na_bronze = vivas(lake, modulo, tabela, ano)
        na_replica = _contar(con, modulo, tabela, ano, ate)
        if na_bronze != na_replica:
            divergencias.append(
                f"{modulo}.{tabela}/{ano}: {na_bronze} linhas vivas na bronze, {na_replica} na "
                f"réplica (diferença de {na_bronze - na_replica})"
            )
    return divergencias


def sincronizar(
    con: pymysql.connections.Connection[Any],
    lake: Lake,
    modulo: str,
    tabela: str,
    desde: datetime,
    ate: datetime,
) -> Sincronizacao:
    """Traz o que mudou na janela e reescreve as partições tocadas, conferindo a contagem."""
    resultado = Sincronizacao(modulo, tabela, desde, ate)
    campos = esquema(con, modulo, tabela)
    nova_foto(con)  # ler as alteradas e contar as partições têm de enxergar o mesmo banco
    por_ano = _alteradas(con, modulo, tabela, campos, desde, ate)
    resultado.alteradas = sum(len(v) for v in por_ano.values())
    for ano, linhas in sorted(por_ano.items()):
        _aplicar(lake, modulo, tabela, ano, campos, linhas)
        resultado.particoes[ano] = vivas(lake, modulo, tabela, ano)  # marcada não conta
    resultado.divergencias += conferir(con, lake, modulo, tabela, por_ano, ate)
    con.rollback()  # a foto fecha com a tabela: a próxima começa a sua
    return resultado


def refazer(
    con: pymysql.connections.Connection[Any], lake: Lake, modulo: str, tabela: str
) -> Sincronizacao:
    """A saída de emergência: recopia a tabela inteira da réplica, partição a partição.

    Serve quando a bronze não existe (sem backfill) ou quando a conferência acusou buraco que
    a carga incremental não sabe fechar sozinha. É o backfill de uma tabela só.
    """
    agora = agora_na_replica(con)
    resultado = Sincronizacao(modulo, tabela, datetime.min, agora)
    for ano in ANOS:
        copia = copiar_ano(con, lake, modulo, tabela, ano)
        resultado.particoes[ano] = copia.linhas
        resultado.alteradas += copia.linhas
        if not copia.confere:
            resultado.divergencias.append(
                f"{modulo}.{tabela}/{ano}: {copia.linhas} gravadas, {copia.esperadas} na réplica"
            )
    return resultado
