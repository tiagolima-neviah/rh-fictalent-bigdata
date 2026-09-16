"""Prova o controle de acesso da réplica conectando como cada usuário de serviço.

O teste passa quando o acesso indevido FALHA. Pula quando a réplica não está de pé.
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
SENHAS = {
    "root": ENV.get("STAGING_ROOT_PASSWORD") or "",
    "pipeline": ENV.get("PIPELINE_PASSWORD") or "",
    "relatorios_cliente": ENV.get("RELATORIOS_PASSWORD") or "",
    "replicador": ENV.get("REPLICADOR_PASSWORD") or "",
}
NEGADO = {1044, 1142, 1143, 1227}  # acesso ao banco, ao comando, à coluna, privilégio


def _replica_de_pe() -> bool:
    try:
        socket.create_connection(("127.0.0.1", PORTA), timeout=1).close()
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not all(SENHAS.values()) or not _replica_de_pe(),
    reason="réplica MySQL fora do ar ou .env sem as senhas de serviço",
)


def _conectar(usuario: str) -> pymysql.connections.Connection[Any]:
    return pymysql.connect(
        host="127.0.0.1", port=PORTA, user=usuario, password=SENHAS[usuario], autocommit=True
    )


@pytest.fixture(scope="module")
def root() -> Iterator[pymysql.connections.Connection[Any]]:
    con = _conectar("root")
    yield con
    con.close()


def _executa(
    con: pymysql.connections.Connection[Any], sql: str, *args: Any
) -> list[tuple[Any, ...]]:
    with con.cursor() as cur:
        cur.execute(sql, args or None)  # tupla vazia faria o PyMySQL formatar o '%' literal
        return list(cur.fetchall())


def _nega(con: pymysql.connections.Connection[Any], sql: str) -> None:
    with pytest.raises(pymysql.err.OperationalError) as erro:
        _executa(con, sql)
    assert erro.value.args[0] in NEGADO, erro.value.args


# ─── pipeline: lê tudo, não escreve nada ───


def test_pipeline_le_negocio_e_trilha() -> None:
    con = _conectar("pipeline")
    assert _executa(con, "SELECT COUNT(*) FROM cadastro.regiao")
    assert _executa(con, "SELECT COUNT(*) FROM pessoas.colaborador")
    assert _executa(con, "SELECT COUNT(*) FROM meta.exclusao_auditoria")
    con.close()


def test_pipeline_nao_escreve_nem_cria() -> None:
    con = _conectar("pipeline")
    _nega(con, "INSERT INTO cadastro.regiao (nome) VALUES ('indevido')")
    _nega(con, "DELETE FROM cadastro.regiao")
    _nega(con, "CREATE TABLE cadastro.indevida (a INT)")
    _nega(con, "GRANT SELECT ON cadastro.* TO 'relatorios_cliente'@'%'")
    con.close()


# ─── relatórios do cliente: lê sem dado pessoal ───


def test_relatorios_le_o_que_nao_e_pessoal() -> None:
    con = _conectar("relatorios_cliente")
    # COUNT de coluna nomeada exercita o GRANT de coluna e responde mesmo com a tabela vazia
    assert len(_executa(con, "SELECT COUNT(id), COUNT(nome) FROM cadastro.regiao")) == 1
    assert (
        len(
            _executa(
                con, "SELECT COUNT(matricula), COUNT(dt_admissao_primeira) FROM pessoas.colaborador"
            )
        )
        == 1
    )
    assert len(_executa(con, "SELECT COUNT(dt_exame), COUNT(dt_validade) FROM sst.aso")) == 1
    con.close()


def test_relatorios_nao_le_coluna_pessoal_nem_select_estrela() -> None:
    con = _conectar("relatorios_cliente")
    _nega(con, "SELECT cpf FROM pessoas.colaborador")
    _nega(con, "SELECT nome FROM ats.candidato")
    _nega(con, "SELECT cid_grupo FROM pessoas.afastamento")
    _nega(con, "SELECT resultado FROM sst.aso")
    _nega(con, "SELECT * FROM pessoas.colaborador")  # o asterisco inclui o cpf
    con.close()


def test_relatorios_nao_ve_a_trilha_nem_escreve() -> None:
    con = _conectar("relatorios_cliente")
    _nega(con, "SELECT COUNT(*) FROM meta.exclusao_auditoria")
    _nega(con, "INSERT INTO cadastro.regiao (nome) VALUES ('indevido')")
    _nega(con, "UPDATE cadastro.regiao SET nome = 'x'")
    con.close()


# ─── replicador: escreve o negócio, e só isso ───


def test_replicador_escreve_e_o_gatilho_grava_a_trilha_por_ele(
    root: pymysql.connections.Connection[Any],
) -> None:
    con = _conectar("replicador")
    nome = f"DCL_{uuid4().hex[:12]}"
    _executa(con, "INSERT INTO cadastro.regiao (nome) VALUES (%s)", nome)
    (novo_id,) = _executa(con, "SELECT id FROM cadastro.regiao WHERE nome = %s", nome)[0]
    _executa(con, "UPDATE cadastro.regiao SET nome = %s WHERE id = %s", nome + "_", novo_id)
    _executa(con, "DELETE FROM cadastro.regiao WHERE id = %s", novo_id)
    con.close()
    # o rastro existe (gravado com o direito do definidor do gatilho), e o root limpa
    rastro = _executa(
        root,
        "SELECT usuario_banco FROM meta.exclusao_auditoria "
        "WHERE tabela = 'regiao' AND registro_id = %s",
        novo_id,
    )
    _executa(
        root,
        "DELETE FROM meta.exclusao_auditoria WHERE tabela = 'regiao' AND registro_id = %s",
        novo_id,
    )
    assert len(rastro) == 1 and str(rastro[0][0]).startswith("replicador@")


def test_replicador_nao_faz_ddl_nem_toca_na_trilha_nem_concede() -> None:
    con = _conectar("replicador")
    _nega(con, "CREATE TABLE cadastro.indevida (a INT)")
    _nega(con, "DROP TABLE cadastro.regiao")
    _nega(con, "ALTER TABLE cadastro.regiao ADD COLUMN indevida INT")
    _nega(con, "SELECT COUNT(*) FROM meta.exclusao_auditoria")
    _nega(con, "DELETE FROM meta.exclusao_auditoria")
    _nega(con, "GRANT SELECT ON cadastro.* TO 'relatorios_cliente'@'%'")
    con.close()


# ─── nenhum deles é administrador ───


@pytest.mark.parametrize("usuario", ["pipeline", "relatorios_cliente", "replicador"])
def test_usuario_de_servico_nao_cria_usuarios(usuario: str) -> None:
    con = _conectar(usuario)
    _nega(con, "CREATE USER 'indevido'@'%' IDENTIFIED BY 'x'")
    con.close()
