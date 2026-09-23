"""A marca d'água da ingestão: até onde cada tabela já foi lida.

**Onde ela mora é decisão de arquitetura, não detalhe.** A réplica é do cliente: o pipeline lê e
não escreve nela, nem para anotar o próprio progresso. A marca fica, portanto, do lado do
pipeline, no warehouse, ao lado das métricas de execução. Quem olha o Grafana vê, por tabela,
até quando o dado chegou.

A marca é um instante **do relógio da réplica**, não do relógio de quem roda o pipeline. Ela é
comparada com `atualizado_em`, que o próprio MySQL grava; se o pipeline usasse o relógio dele,
qualquer diferença entre as duas máquinas viraria linha perdida ou linha relida. Por isso a
coluna é `timestamp` sem fuso: é o relógio de lá, guardado como ele veio.

Tabela sem marca não é caso de erro: a marca inicial é **derivada da própria bronze**, pelo
maior `atualizado_em` que já está lá. A bronze é quem sabe até onde foi lida; a tabela de
controle registra e acelera. Se não há nem bronze, aí sim falta o backfill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rh_fictalent.orquestracao.recursos import Warehouse

SCHEMA = "ingestao"
DDL = """
CREATE SCHEMA IF NOT EXISTS ingestao;

CREATE TABLE IF NOT EXISTS ingestao.marca_dagua (
  tabela         text PRIMARY KEY,
  marca          timestamp NOT NULL,
  linhas         bigint NOT NULL DEFAULT 0,
  particoes      integer NOT NULL DEFAULT 0,
  run_id         text,
  atualizado_em  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE ingestao.marca_dagua IS
  'Ate onde cada tabela da replica ja foi lida para a bronze (relogio da replica)';
COMMENT ON COLUMN ingestao.marca_dagua.marca IS
  'Maior atualizado_em ja ingerido; a carga seguinte pede o que esta acima dele';
"""


@dataclass(frozen=True)
class Marca:
    tabela: str
    marca: datetime
    linhas: int
    particoes: int


def criar(warehouse: Warehouse) -> None:
    """Cria schema e tabela se faltarem. Idempotente, como a DDL das métricas."""
    with warehouse.conectar() as con, con.cursor() as cur:
        cur.execute(DDL)
        con.commit()


def ler(warehouse: Warehouse) -> dict[str, Marca]:
    linhas = warehouse.consultar(
        "SELECT tabela, marca, linhas, particoes FROM ingestao.marca_dagua"
    )
    return {str(t): Marca(str(t), m, int(n), int(p)) for t, m, n, p in linhas}


def gravar(warehouse: Warehouse, marca: Marca, run_id: str | None = None) -> None:
    """Upsert: a marca de uma tabela é sempre a última, nunca uma linha nova."""
    with warehouse.conectar() as con, con.cursor() as cur:
        cur.execute(
            "INSERT INTO ingestao.marca_dagua (tabela, marca, linhas, particoes, run_id) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (tabela) DO UPDATE SET marca = EXCLUDED.marca, "
            "linhas = EXCLUDED.linhas, particoes = EXCLUDED.particoes, "
            "run_id = EXCLUDED.run_id, atualizado_em = now()",
            (marca.tabela, marca.marca, marca.linhas, marca.particoes, run_id),
        )
        con.commit()


def apagar(warehouse: Warehouse, tabela: str | None = None) -> int:
    """Esquece a marca (de uma tabela ou de todas): a próxima carga a deriva da bronze."""
    sql = "DELETE FROM ingestao.marca_dagua"
    args: tuple[str, ...] = ()
    if tabela is not None:
        sql += " WHERE tabela = %s"
        args = (tabela,)
    with warehouse.conectar() as con, con.cursor() as cur:
        cur.execute(sql, args or None)
        apagadas = cur.rowcount
        con.commit()
    return int(apagadas)
