"""Regras de segurança e de operação do compose.yaml, verificadas a cada commit.

Estas regras valem para qualquer serviço que entrar no arquivo no futuro:
quem adicionar um container sem healthcheck, com imagem "latest", porta aberta
para a rede ou senha escrita no arquivo quebra a esteira.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
COMPOSE = RAIZ / "compose.yaml"
JOBS_DE_INICIALIZACAO = {"s3-init", "keyring-init"}


def _carregar() -> dict[str, Any]:
    dados: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return dados


def _servicos() -> dict[str, dict[str, Any]]:
    servicos: dict[str, dict[str, Any]] = _carregar()["services"]
    return servicos


def _longa_duracao() -> list[str]:
    return [nome for nome in _servicos() if nome not in JOBS_DE_INICIALIZACAO]


def test_servicos_esperados_existem() -> None:
    esperados = {
        "mysql-staging",
        "pg-dw",
        "pg-dagster",
        "s3",
        "s3-init",
        "keyring-init",
        "dagster-web",
        "dagster-daemon",
        "grafana",
    }
    assert set(_servicos()) == esperados


def test_motores_de_banco_conforme_adr_0001() -> None:
    """MySQL na réplica do cliente (staging), Postgres no warehouse: docs/adr/0001."""
    assert _servicos()["mysql-staging"]["image"].startswith("mysql:")
    assert _servicos()["pg-dw"]["image"].startswith("postgres:")
    assert "pg-origem" not in _servicos(), (
        "a consultoria não toca o sistema do cliente: não existe origem aqui"
    )


def test_replica_aplica_a_ddl_na_primeira_subida() -> None:
    assert "./staging/ddl:/docker-entrypoint-initdb.d:ro" in _servicos()["mysql-staging"]["volumes"]
    assert "--default-time-zone=+00:00" in _servicos()["mysql-staging"]["command"]


@pytest.mark.parametrize("nome", _longa_duracao())
def test_todo_servico_de_longa_duracao_tem_healthcheck(nome: str) -> None:
    saude = _servicos()[nome].get("healthcheck")
    assert saude and saude.get("test"), f"{nome} sem healthcheck"


@pytest.mark.parametrize("nome", _longa_duracao())
def test_todo_servico_de_longa_duracao_reinicia_sozinho(nome: str) -> None:
    assert _servicos()[nome].get("restart") == "unless-stopped", nome


@pytest.mark.parametrize("nome", list(_servicos()))
def test_imagem_com_versao_exata(nome: str) -> None:
    imagem = _servicos()[nome]["image"]
    assert ":" in imagem, f"{nome}: imagem sem versão"
    tag = imagem.rsplit(":", 1)[1]
    assert tag != "latest" and re.search(r"\d", tag), f"{nome}: versão não fixada ({imagem})"


@pytest.mark.parametrize("nome", list(_servicos()))
def test_sem_ganho_de_privilegio(nome: str) -> None:
    assert "no-new-privileges:true" in _servicos()[nome].get("security_opt", []), nome


@pytest.mark.parametrize("nome", list(_servicos()))
def test_portas_publicadas_so_em_localhost(nome: str) -> None:
    for porta in _servicos()[nome].get("ports", []):
        assert str(porta).startswith("127.0.0.1:"), f"{nome}: porta exposta na rede ({porta})"


def test_replica_cifra_em_repouso() -> None:
    replica = _servicos()["mysql-staging"]
    for opcao in (
        "--default-table-encryption=ON",
        "--table-encryption-privilege-check=ON",
        "--innodb-redo-log-encrypt=ON",
        "--innodb-undo-log-encrypt=ON",
        "--binlog-encryption=ON",
    ):
        assert opcao in replica["command"], opcao
    assert "mysql_keyring:/var/lib/mysql-keyring" in replica["volumes"]
    assert "./infra/mysql/mysqld.my:/usr/sbin/mysqld.my:ro" in replica["volumes"]
    assert replica["depends_on"]["keyring-init"]["condition"] == "service_completed_successfully"
    assert replica["user"] == "999:999", "a réplica não roda como root"


def test_banco_de_metadados_nao_publica_porta() -> None:
    assert not _servicos()["pg-dagster"].get("ports")


def test_nenhuma_senha_escrita_no_arquivo() -> None:
    for nome, servico in _servicos().items():
        ambiente = servico.get("environment") or {}
        for chave, valor in ambiente.items():
            if any(p in chave for p in ("PASSWORD", "SECRET", "_KEY")):
                texto = str(valor)
                assert texto.startswith("${") and ":?" in texto, (
                    f"{nome}.{chave}: segredo precisa vir do .env e ser obrigatório"
                )


def test_env_example_declara_todo_segredo_obrigatorio() -> None:
    obrigatorios = set(re.findall(r"\$\{([A-Z0-9_]+):\?", COMPOSE.read_text(encoding="utf-8")))
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    faltando = {v for v in obrigatorios if not re.search(rf"^{v}=", exemplo, re.MULTILINE)}
    assert not faltando, f".env.example sem: {sorted(faltando)}"
