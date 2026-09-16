"""Prova a cifra em repouso na réplica de verdade: variáveis, keyring, tablespaces e o disco.

A prova que importa é a última: um CPF gravado em pessoas.colaborador não aparece em claro
no arquivo .ibd, enquanto o mesmo CPF numa tabela de controle sem cifra aparece.
Pula quando a réplica não está de pé ou quando o docker não está acessível.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
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
CONTAINER = "fictalent_mysql_staging"
MODULOS = (
    "cadastro",
    "comercial",
    "ats",
    "pessoas",
    "ponto",
    "folha",
    "financeiro",
    "treinamento",
    "sst",
    "seguranca",
    "meta",
)


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
    conexao = pymysql.connect(
        host="127.0.0.1", port=PORTA, user="root", password=SENHA, autocommit=True
    )
    yield conexao
    conexao.close()


def _linhas(
    con: pymysql.connections.Connection[Any], sql: str, *args: Any
) -> list[tuple[Any, ...]]:
    with con.cursor() as cur:
        cur.execute(sql, args or None)
        return list(cur.fetchall())


def _ocorrencias_no_disco(arquivo: str, texto: str) -> int:
    """Conta quantas vezes o texto aparece em claro no arquivo, dentro do container."""
    saida = subprocess.run(
        ["docker", "exec", CONTAINER, "grep", "-c", "-a", texto, arquivo],
        capture_output=True,
        text=True,
        check=False,
    )
    return int(saida.stdout.strip() or 0)


def test_servidor_cifra_redo_undo_e_binlog(con: pymysql.connections.Connection[Any]) -> None:
    variaveis = dict(
        _linhas(
            con,
            "SHOW VARIABLES WHERE Variable_name IN ('innodb_redo_log_encrypt', "
            "'innodb_undo_log_encrypt', 'binlog_encryption', 'default_table_encryption', "
            "'table_encryption_privilege_check')",
        )
    )
    assert variaveis == {
        "innodb_redo_log_encrypt": "ON",
        "innodb_undo_log_encrypt": "ON",
        "binlog_encryption": "ON",
        "default_table_encryption": "ON",
        "table_encryption_privilege_check": "ON",
    }


def test_keyring_carregado_e_fora_do_diretorio_de_dados(
    con: pymysql.connections.Connection[Any],
) -> None:
    estado = dict(
        _linhas(
            con, "SELECT status_key, status_value FROM performance_schema.keyring_component_status"
        )
    )
    assert estado.get("Component_name") == "component_keyring_file"
    assert estado.get("Component_status") == "Active"
    assert estado.get("Data_file") == "/var/lib/mysql-keyring/keyring"


def test_todo_tablespace_da_replica_esta_cifrado(con: pymysql.connections.Connection[Any]) -> None:
    linhas = _linhas(
        con,
        "SELECT encryption, COUNT(*) FROM information_schema.innodb_tablespaces "
        "WHERE SUBSTRING_INDEX(name, '/', 1) IN %s GROUP BY encryption",
        MODULOS,
    )
    assert dict(linhas) == {"Y": 76}, linhas


def test_tabela_nova_nasce_cifrada(con: pymysql.connections.Connection[Any]) -> None:
    nome = f"prova_{uuid4().hex[:8]}"
    _linhas(con, f"CREATE TABLE cadastro.{nome} (id INT PRIMARY KEY)")
    try:
        (cifra,) = _linhas(
            con,
            "SELECT encryption FROM information_schema.innodb_tablespaces WHERE name = %s",
            f"cadastro/{nome}",  # o InnoDB nomeia o tablespace com barra, não com ponto
        )[0]
    finally:
        _linhas(con, f"DROP TABLE cadastro.{nome}")
    assert cifra == "Y"


def test_rotacao_da_chave_mestra(con: pymysql.connections.Connection[Any]) -> None:
    _linhas(con, "ALTER INSTANCE ROTATE INNODB MASTER KEY")


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker indisponível para ler o disco")
def test_dado_pessoal_nao_aparece_em_claro_no_disco(
    con: pymysql.connections.Connection[Any],
) -> None:
    cpf = "99988877766"
    marca = uuid4().hex[:8]
    controle = f"cadastro.clara_{marca}"
    _linhas(con, "INSERT INTO cadastro.regiao (nome) VALUES (%s)", f"CIFRA_{marca}")
    (regiao_id,) = _linhas(con, "SELECT id FROM cadastro.regiao WHERE nome = %s", f"CIFRA_{marca}")[
        0
    ]
    _linhas(
        con,
        "INSERT INTO cadastro.municipio (nome, uf, regiao_id, codigo_ibge) "
        "VALUES (%s, 'SP', %s, %s)",
        f"Cifra {marca}",
        regiao_id,
        f"9{marca[:6]}",
    )
    (municipio_id,) = _linhas(
        con, "SELECT id FROM cadastro.municipio WHERE regiao_id = %s", regiao_id
    )[0]
    _linhas(
        con,
        "INSERT INTO pessoas.colaborador (matricula, nome, cpf, dt_nascimento, municipio_id, "
        "dt_admissao_primeira) VALUES (%s, 'Prova da Cifra', %s, '1990-01-01', %s, '2020-01-01')",
        f"C{marca}",
        cpf,
        municipio_id,
    )
    # tabela de controle SEM cifra: root tem TABLE_ENCRYPTION_ADMIN para desobedecer o padrão
    _linhas(con, f"CREATE TABLE {controle} (cpf CHAR(11)) ENCRYPTION='N'")
    _linhas(con, f"INSERT INTO {controle} (cpf) VALUES (%s)", cpf)
    try:
        # força a escrita das páginas em disco antes de olhar os arquivos
        _linhas(con, f"FLUSH TABLES pessoas.colaborador, {controle} FOR EXPORT")
        cifrado = _ocorrencias_no_disco("/var/lib/mysql/pessoas/colaborador.ibd", cpf)
        em_claro = _ocorrencias_no_disco(
            f"/var/lib/mysql/cadastro/{controle.split('.')[1]}.ibd", cpf
        )
        _linhas(con, "UNLOCK TABLES")
    finally:
        _linhas(con, f"DROP TABLE {controle}")
        _linhas(con, "DELETE FROM pessoas.colaborador WHERE cpf = %s", cpf)
        _linhas(con, "DELETE FROM cadastro.municipio WHERE id = %s", municipio_id)
        _linhas(con, "DELETE FROM cadastro.regiao WHERE id = %s", regiao_id)
        _linhas(
            con,
            "DELETE FROM meta.exclusao_auditoria WHERE registro_id IN (%s, %s)",
            municipio_id,
            regiao_id,
        )
        _linhas(con, "DELETE FROM meta.exclusao_auditoria WHERE tabela = 'colaborador'")
    assert em_claro >= 1, "a tabela de controle em claro deveria expor o CPF no disco"
    assert cifrado == 0, "o CPF apareceu em claro no tablespace cifrado"
