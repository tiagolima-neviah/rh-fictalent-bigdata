# ruff: noqa: E501
"""A trilha de auditoria: as consultas do lake num DuckDB pequeno, as do warehouse no banco de verdade.

O DuckDB de teste tem a silver de segurança (quatro usuários, um sem perfil, um inativo) e a
trilha de exclusões da bronze, com eventos escolhidos para cada pergunta ter uma resposta
conhecida: um login fora da janela, uma ação sem permissão, uma exportação de madrugada, uma
exclusão num domingo.
"""

from __future__ import annotations

import os
import socket
from datetime import date
from pathlib import Path

import duckdb
import pytest
from dotenv import dotenv_values

from rh_fictalent.orquestracao.recursos import Warehouse
from rh_fictalent.trilha import consultas

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


@pytest.fixture(scope="module")
def lake() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS silver")
    con.execute("CREATE SCHEMA silver.seguranca")
    con.execute("CREATE SCHEMA meta")
    con.execute("CREATE TABLE silver.seguranca.perfil (id BIGINT, codigo VARCHAR)")
    con.execute(
        "INSERT INTO silver.seguranca.perfil VALUES (1, 'SOCIO'), (2, 'ASSISTENTE'), (3, 'COORDENADOR')"
    )
    con.execute(
        "CREATE TABLE silver.seguranca.usuario (id BIGINT, login_chave VARCHAR, filial_id BIGINT, ativo BOOLEAN)"
    )
    con.execute(
        "INSERT INTO silver.seguranca.usuario VALUES (1, 'a' || repeat('0', 63), 1, true), (2, 'b' || repeat('0', 63), 2, true), "
        "(3, 'c' || repeat('0', 63), 3, true), (4, 'd' || repeat('0', 63), 1, false)"
    )
    con.execute(
        "CREATE TABLE silver.seguranca.usuario_perfil (usuario_id BIGINT, perfil_id BIGINT, vigencia_fim DATE)"
    )
    con.execute(
        "INSERT INTO silver.seguranca.usuario_perfil VALUES (1, 1, NULL), (2, 2, NULL), (2, 3, DATE '2024-01-01'), (4, 2, NULL)"
    )
    con.execute(
        "CREATE TABLE silver.seguranca.log_auditoria (id BIGINT, usuario_id BIGINT, dt_evento TIMESTAMP, modulo VARCHAR, tabela VARCHAR, acao VARCHAR, q_seg_01 BOOLEAN)"
    )
    con.execute(
        """INSERT INTO silver.seguranca.log_auditoria VALUES
        (1, 1, TIMESTAMP '2026-09-01 09:00:00', 'seguranca', 'usuario', 'LOGIN', false),
        (2, 1, TIMESTAMP '2026-09-02 09:00:00', 'seguranca', 'usuario', 'LOGIN', false),
        (3, 2, TIMESTAMP '2026-09-02 10:00:00', 'seguranca', 'usuario', 'LOGIN', false),
        (4, 2, TIMESTAMP '2026-09-02 10:05:00', 'ats', 'candidato', 'CRIAR', false),
        (5, 2, TIMESTAMP '2026-09-02 10:06:00', 'ats', 'candidato', 'EDITAR', false),
        (6, 2, TIMESTAMP '2026-09-03 03:00:00', 'ats', 'candidato', 'EXPORTAR', false),
        (7, 2, TIMESTAMP '2026-09-06 11:00:00', 'financeiro', 'fatura', 'EDITAR', true),
        (8, 3, TIMESTAMP '2026-05-10 09:00:00', 'seguranca', 'usuario', 'LOGIN', false),
        (9, 1, TIMESTAMP '2026-08-14 09:00:00', 'comercial', 'contrato', 'EXCLUIR', false)"""
    )
    con.execute(
        "CREATE TABLE meta.exclusao_auditoria (id BIGINT, banco VARCHAR, tabela VARCHAR, registro_id BIGINT, dt_exclusao TIMESTAMP, usuario_banco VARCHAR)"
    )
    con.execute(
        "INSERT INTO meta.exclusao_auditoria VALUES (1, 'comercial', 'contrato', 10, TIMESTAMP '2026-08-14 09:00:01', 'replicador@%'), "
        "(2, 'ats', 'candidato', 20, TIMESTAMP '2026-09-06 11:00:00', 'replicador@%'), (3, 'ats', 'candidato', 21, TIMESTAMP '2026-09-06 11:00:01', 'replicador@%')"
    )
    return con


def test_toda_consulta_tem_pergunta_fonte_grao_e_parametros_da_fonte() -> None:
    assert len({c.nome for c in consultas.CONSULTAS}) == len(consultas.CONSULTAS) == 13
    for c in consultas.CONSULTAS:
        assert c.pergunta.endswith("?") and c.grao and c.fonte in ("lake", "warehouse"), c.nome
        if c.fonte == "lake":
            assert "$desde" in c.sql or "$ate" in c.sql or c.nome == "exclusoes_na_replica", c.nome
            assert "%(desde)s" not in c.sql
        elif "%(desde)s" in c.sql:
            assert "%(ate)s" in c.sql, c.nome
        # nunca o token, nunca o valor alterado, nunca o nome
        assert "hash" not in c.sql.lower().replace("hash =", "") or c.nome == "tokens_da_api"
        assert (
            "valor_anterior" not in c.sql
            and "valor_novo" not in c.sql
            and "nome" not in c.sql.split("rolname")[0]
        )


def test_acessos_por_perfil_e_mes(lake: duckdb.DuckDBPyConnection) -> None:
    t = consultas.no_lake(lake, "acessos_por_perfil_e_mes", date(2026, 9, 1), date(2026, 9, 30))
    assert t[["perfil", "filial_id", "logins", "usuarios"]].to_dict("records") == [
        {"perfil": "ASSISTENTE", "filial_id": 2, "logins": 1, "usuarios": 1},
        {"perfil": "SOCIO", "filial_id": 1, "logins": 2, "usuarios": 1},
    ]
    assert consultas.no_lake(lake, "acessos_por_perfil_e_mes", date(2026, 1, 1), date(2026, 5, 31))[
        "perfil"
    ].tolist() == ["SEM PERFIL"]


def test_usuarios_ativos_sem_acesso(lake: duckdb.DuckDBPyConnection) -> None:
    t = consultas.no_lake(lake, "usuarios_ativos_sem_acesso", ate=date(2026, 9, 30))
    # o usuário 3 entrou em maio (mais de 90 dias); o 4 é inativo e não entra na lista; 1 e 2 entraram em setembro
    assert t["login_chave"].str[0].tolist() == ["c"] and int(t["dias_sem_entrar"].iloc[0]) == 143


def test_alteracoes_acoes_sem_permissao_exportacoes_e_fora_do_horario(
    lake: duckdb.DuckDBPyConnection,
) -> None:
    alteracoes = consultas.no_lake(
        lake, "alteracoes_por_modulo_e_mes", date(2026, 9, 1), date(2026, 9, 30)
    )
    assert alteracoes[["tabela", "acao", "eventos"]].to_dict("records") == [
        {"tabela": "candidato", "acao": "CRIAR", "eventos": 1},
        {"tabela": "candidato", "acao": "EDITAR", "eventos": 1},
        {"tabela": "fatura", "acao": "EDITAR", "eventos": 1},
    ]
    sem = consultas.no_lake(lake, "acoes_sem_permissao")
    assert (
        len(sem) == 1
        and sem.iloc[0]["modulo"] == "financeiro"
        and sem.iloc[0]["perfil"] == "ASSISTENTE"
    )
    exportacoes = consultas.no_lake(lake, "exportacoes_por_usuario_e_mes")
    assert (
        len(exportacoes) == 1
        and exportacoes.iloc[0]["modulo"] == "ats"
        and int(exportacoes.iloc[0]["exportacoes"]) == 1
    )
    fora = consultas.no_lake(lake, "acoes_fora_do_horario")
    # a exportação das 3h e a edição de domingo (06/09/2026) são da assistente; o resto é em horário
    # comercial e em dia útil (14/08/2026 é sexta-feira)
    assert fora["login_chave"].str[0].tolist() == ["b", "b"]
    assert fora.set_index("acao").loc["EDITAR", "no_fim_de_semana"] == 1
    assert fora.set_index("acao").loc["EXPORTAR", "no_fim_de_semana"] == 0


def test_exclusoes_na_replica(lake: duckdb.DuckDBPyConnection) -> None:
    t = consultas.no_lake(lake, "exclusoes_na_replica", date(2026, 9, 1), date(2026, 9, 30))
    assert t[["banco", "tabela", "linhas_apagadas"]].to_dict("records") == [
        {"banco": "ats", "tabela": "candidato", "linhas_apagadas": 2}
    ]
    assert consultas.no_lake(lake, "exclusoes_na_replica")["linhas_apagadas"].sum() == 3


def test_a_consulta_da_outra_fonte_e_recusada(lake: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ValueError, match="warehouse"):
        consultas.no_lake(lake, "execucoes_por_job")
    with pytest.raises(StopIteration):
        consultas.consulta("quem_sabe")


# ------------------------------------------------------------- o warehouse de verdade


def _dw_de_pe() -> bool:
    try:
        socket.create_connection(("127.0.0.1", int(ENV.get("DW_PORT") or 0)), timeout=1).close()
    except (OSError, ValueError):
        return False
    return True


@pytest.mark.skipif(not ENV or not _dw_de_pe(), reason="warehouse fora do ar ou .env ausente")
def test_as_consultas_do_warehouse_respondem_no_banco_de_verdade() -> None:
    dw = Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or os.environ.get("DW_ADMIN_PASSWORD", ""),
    )
    execucoes = consultas.no_warehouse(dw, "execucoes_por_job")
    assert {"job", "status", "execucoes", "duracao_media_s"} <= set(execucoes.columns)
    assert "carregar_warehouse" in execucoes["job"].tolist()
    papeis = consultas.no_warehouse(dw, "papeis_do_warehouse")
    assert "api" in papeis["papel"].tolist() and "grafana_leitor" in papeis["papel"].tolist()
    assert not papeis[papeis["papel"] == "api"]["entra_com_senha"].isna().any()
    tokens = consultas.no_warehouse(dw, "tokens_da_api")
    assert "hash" not in tokens.columns
    for nome in ("passos_que_falharam", "descartes_lgpd", "pedidos_da_api_por_dia"):
        assert consultas.no_warehouse(dw, nome, date(2026, 1, 1), date(2099, 12, 31)) is not None


def test_o_docs_10_cita_toda_consulta_da_trilha() -> None:
    """O `docs/10` é escrito à mão, mas a lista de perguntas sai do código: consulta nova sem linha reprova."""
    texto = (RAIZ / "docs" / "10_auditoria.md").read_text(encoding="utf-8")
    faltando = [c.nome for c in consultas.CONSULTAS if f"`{c.nome}`" not in texto]
    assert faltando == []
    assert f"As {len(consultas.CONSULTAS)} perguntas" in texto or "treze perguntas" in texto
