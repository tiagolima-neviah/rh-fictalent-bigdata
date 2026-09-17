"""O saude.sh cobre as duas fases; com a plataforma de pé, termina em PLATAFORMA OK."""

from __future__ import annotations

import shutil
import socket
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "saude.sh"
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def test_script_cobre_as_verificacoes_de_ponta_a_ponta() -> None:
    texto = SCRIPT.read_text(encoding="utf-8")
    for trecho in (
        "usuário pipeline lê as 76 tabelas",
        "75 gatilhos",
        "76 tablespaces cifrados",
        "keyring ativo",
        "bucket",
        "grafana_leitor conecta",
        "frescor",
        "code location carregada",
        "sensores de métricas ligados",
        "painel de execuções provisionado",
        "regras de alerta provisionadas",
        "SO_CONTAINERS",
    ):
        assert trecho in texto, trecho


def _plataforma_de_pe() -> bool:
    for porta in ("STAGING_PORT", "DW_PORT", "DAGSTER_PORT", "GRAFANA_PORT"):
        try:
            socket.create_connection(("127.0.0.1", int(ENV.get(porta) or 0)), timeout=1).close()
        except (OSError, ValueError):
            return False
    return True


@pytest.mark.skipif(
    not ENV or shutil.which("docker") is None or not _plataforma_de_pe(),
    reason="plataforma fora do ar, docker ausente ou .env ausente",
)
def test_plataforma_de_pe_termina_em_ok() -> None:
    saida = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, cwd=RAIZ, timeout=300, check=False
    )
    assert saida.returncode == 0, saida.stdout + saida.stderr
    assert "PLATAFORMA OK" in saida.stdout
    assert "✗" not in saida.stdout
