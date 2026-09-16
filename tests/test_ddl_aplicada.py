"""Confere a DDL aplicada na réplica de verdade (MySQL do compose).

Pula, em vez de falhar, quando a réplica não está de pé ou não há .env: a esteira do
repositório roda sem banco; a conferência completa roda na máquina de quem subiu a
plataforma (docs/08, seção 3).
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymysql
import pytest
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PORTA = int(ENV.get("STAGING_PORT") or 3316)
SENHA = ENV.get("STAGING_ROOT_PASSWORD") or ""
MODULOS = {
    "cadastro": 12,
    "comercial": 8,
    "ats": 9,
    "pessoas": 8,
    "ponto": 5,
    "folha": 7,
    "financeiro": 10,
    "treinamento": 5,
    "sst": 6,
    "seguranca": 5,
    "meta": 1,
}


def _replica_de_pe() -> bool:
    try:
        socket.create_connection(("127.0.0.1", PORTA), timeout=1).close()
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not SENHA or not _replica_de_pe(), reason="réplica MySQL fora do ar ou .env ausente"
)


@pytest.fixture(scope="module")
def con() -> Iterator[pymysql.connections.Connection[Any]]:
    conexao = pymysql.connect(host="127.0.0.1", port=PORTA, user="root", password=SENHA)
    yield conexao
    conexao.close()


def _linhas(
    con: pymysql.connections.Connection[Any], sql: str, *args: Any
) -> list[tuple[Any, ...]]:
    with con.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def test_contagem_de_tabelas_por_modulo(con: pymysql.connections.Connection[Any]) -> None:
    linhas = _linhas(
        con,
        "SELECT table_schema, COUNT(*) FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' AND table_schema IN %s GROUP BY table_schema",
        tuple(MODULOS),
    )
    assert {m: int(n) for m, n in linhas} == MODULOS


def test_toda_tabela_tem_id_e_carimbos(con: pymysql.connections.Connection[Any]) -> None:
    linhas = _linhas(
        con,
        "SELECT table_schema, table_name, GROUP_CONCAT(column_name) "
        "FROM information_schema.columns "
        "WHERE table_schema IN %s GROUP BY table_schema, table_name",
        tuple(MODULOS),
    )
    assert len(linhas) == 76
    for modulo, tabela, colunas in linhas:
        cols = set(colunas.split(","))
        exigidas = {"id", "criado_em"} if modulo == "meta" else {"id", "criado_em", "atualizado_em"}
        assert exigidas <= cols, f"{modulo}.{tabela}"


def test_toda_tabela_tem_comentario(con: pymysql.connections.Connection[Any]) -> None:
    sem = _linhas(
        con,
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' AND table_schema IN %s AND table_comment = ''",
        tuple(MODULOS),
    )
    assert not sem, sem


def test_marca_dagua_indexada_em_toda_tabela_de_negocio(
    con: pymysql.connections.Connection[Any],
) -> None:
    (n,) = _linhas(
        con,
        "SELECT COUNT(DISTINCT CONCAT(table_schema, '.', table_name)) "
        "FROM information_schema.statistics "
        "WHERE column_name = 'atualizado_em' AND table_schema IN %s",
        tuple(m for m in MODULOS if m != "meta"),
    )[0]
    assert int(n) == 75


def test_chaves_e_regras_declaradas(con: pymysql.connections.Connection[Any]) -> None:
    (fks,) = _linhas(
        con,
        "SELECT COUNT(*) FROM information_schema.referential_constraints "
        "WHERE constraint_schema IN %s",
        tuple(MODULOS),
    )[0]
    (checks,) = _linhas(
        con,
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE constraint_type = 'CHECK' AND constraint_schema IN %s",
        tuple(MODULOS),
    )[0]
    assert int(fks) >= 120, fks
    assert int(checks) >= 50, checks
    ciclos = _linhas(
        con,
        "SELECT constraint_name FROM information_schema.referential_constraints "
        "WHERE constraint_name IN ('fk_centro_custo_contrato', 'fk_entrevista_usuario')",
    )
    assert {c for (c,) in ciclos} == {"fk_centro_custo_contrato", "fk_entrevista_usuario"}


def test_dado_pessoal_etiquetado_no_banco(con: pymysql.connections.Connection[Any]) -> None:
    etiquetadas = _linhas(
        con,
        "SELECT table_schema, table_name, column_name FROM information_schema.columns "
        "WHERE column_comment LIKE '[LGPD:%%' AND table_schema IN %s",
        tuple(MODULOS),
    )
    assert len(etiquetadas) >= 24
    assert ("pessoas", "colaborador", "cpf") in etiquetadas
    assert ("sst", "aso", "resultado") in etiquetadas


def test_gatilho_de_exclusao_em_toda_tabela_de_negocio(
    con: pymysql.connections.Connection[Any],
) -> None:
    linhas = _linhas(
        con,
        "SELECT trigger_schema, event_object_table FROM information_schema.triggers "
        "WHERE event_manipulation = 'DELETE' AND action_timing = 'BEFORE' "
        "AND trigger_schema IN %s",
        tuple(m for m in MODULOS if m != "meta"),
    )
    assert len(linhas) == 75 and len(set(linhas)) == 75


def test_delete_deixa_rastro_na_trilha(con: pymysql.connections.Connection[Any]) -> None:
    """Insere, apaga e confere o rastro; depois apaga o próprio rastro para não sujar a réplica."""
    nome = f"TRILHA_{uuid4().hex[:12]}"
    with con.cursor() as cur:
        cur.execute("INSERT INTO cadastro.regiao (nome) VALUES (%s)", (nome,))
        novo_id = cur.lastrowid
        cur.execute("DELETE FROM cadastro.regiao WHERE id = %s", (novo_id,))
        cur.execute(
            "SELECT banco, tabela, registro_id, usuario_banco FROM meta.exclusao_auditoria "
            "WHERE banco = 'cadastro' AND tabela = 'regiao' AND registro_id = %s",
            (novo_id,),
        )
        rastro = list(cur.fetchall())
        cur.execute(
            "DELETE FROM meta.exclusao_auditoria "
            "WHERE banco = 'cadastro' AND tabela = 'regiao' AND registro_id = %s",
            (novo_id,),
        )
    con.commit()
    assert len(rastro) == 1, rastro
    banco, tabela, registro_id, usuario = rastro[0]
    assert (banco, tabela, int(registro_id)) == ("cadastro", "regiao", novo_id)
    assert str(usuario).startswith("root@")


def test_relogio_do_banco_em_utc(con: pymysql.connections.Connection[Any]) -> None:
    (fuso,) = _linhas(con, "SELECT @@global.time_zone")[0]
    assert fuso == "+00:00"
