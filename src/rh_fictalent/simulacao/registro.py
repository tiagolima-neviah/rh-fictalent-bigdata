"""O registro dos dias simulados: o que a operação acrescentou depois do marco da régua.

Sem isto, ligar a simulação tornaria impossível conferir a base gerada: a contagem de linhas na
réplica deixaria de bater com o laudo da régua, e não haveria como saber se a diferença é
operação corrente ou defeito. Com isto, a conferência continua exata: conta-se o que está lá e
desconta-se o que a operação pôs depois de 10/09/2026.
"""

from __future__ import annotations

from datetime import date

from rh_fictalent.orquestracao.recursos import Warehouse
from rh_fictalent.simulacao.dia import Movimento

DDL = """
CREATE SCHEMA IF NOT EXISTS ingestao;

CREATE TABLE IF NOT EXISTS ingestao.dia_simulado (
  dia            date NOT NULL,
  tabela         text NOT NULL,
  inseridas      integer NOT NULL DEFAULT 0,
  alteradas      integer NOT NULL DEFAULT 0,
  excluidas      integer NOT NULL DEFAULT 0,
  registrado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (dia, tabela)
);
COMMENT ON TABLE ingestao.dia_simulado IS
  'O que a operacao corrente acrescentou a replica depois do fim da historia gerada';
"""


def criar(warehouse: Warehouse) -> None:
    with warehouse.conectar() as con, con.cursor() as cur:
        cur.execute(DDL)
        con.commit()


def gravar(warehouse: Warehouse, movimento: Movimento) -> None:
    tabelas = {*movimento.inseridas, *movimento.alteradas, *movimento.excluidas}
    linhas = [
        (
            movimento.dia,
            tabela,
            movimento.inseridas.get(tabela, 0),
            movimento.alteradas.get(tabela, 0),
            movimento.excluidas.get(tabela, 0),
        )
        for tabela in sorted(tabelas)
    ]
    if not linhas:
        return
    with warehouse.conectar() as con, con.cursor() as cur:
        cur.executemany(
            "INSERT INTO ingestao.dia_simulado (dia, tabela, inseridas, alteradas, excluidas) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (dia, tabela) DO UPDATE SET inseridas = EXCLUDED.inseridas, "
            "alteradas = EXCLUDED.alteradas, excluidas = EXCLUDED.excluidas, registrado_em = now()",
            linhas,
        )
        con.commit()


def acrescentado(warehouse: Warehouse) -> dict[str, int]:
    """Por tabela, o saldo de linhas que a operação corrente pôs na réplica (inseridas menos
    excluídas). É o que se desconta para conferir a base contra o laudo da régua."""
    linhas = warehouse.consultar(
        "SELECT tabela, SUM(inseridas) - SUM(excluidas) FROM ingestao.dia_simulado GROUP BY tabela"
    )
    return {str(tabela): int(saldo) for tabela, saldo in linhas}


def simulados(warehouse: Warehouse) -> list[date]:
    return [
        d
        for (d,) in warehouse.consultar(
            "SELECT DISTINCT dia FROM ingestao.dia_simulado ORDER BY dia"
        )
    ]


def esquecer(warehouse: Warehouse, dia: date | None = None) -> int:
    """Apaga o registro (de um dia ou de todos). Usado pelos testes, que desfazem o que fazem."""
    sql = "DELETE FROM ingestao.dia_simulado"
    args: tuple[date, ...] = ()
    if dia is not None:
        sql += " WHERE dia = %s"
        args = (dia,)
    with warehouse.conectar() as con, con.cursor() as cur:
        cur.execute(sql, args or None)
        apagadas = cur.rowcount
        con.commit()
    return int(apagadas)
