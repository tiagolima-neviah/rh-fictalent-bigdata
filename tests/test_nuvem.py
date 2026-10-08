"""O destino em nuvem: o recurso com TLS, a CLI com `--destino`, e a conexão real com `.env`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import psycopg
import pytest
from dotenv import dotenv_values

from rh_fictalent.gold import __main__ as cli
from rh_fictalent.orquestracao import recursos

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
NUVEM = {k: v for k, v in ENV.items() if k.startswith("NUVEM_") and v and "troque" not in v}


def test_o_destino_em_nuvem_exige_tls_e_as_variaveis(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("NUVEM_HOST", "NUVEM_USER", "NUVEM_PASSWORD", "NUVEM_PORT", "NUVEM_DB"):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(RuntimeError, match="NUVEM_HOST, NUVEM_USER, NUVEM_PASSWORD"):
        recursos.nuvem_do_ambiente()
    monkeypatch.setenv("NUVEM_HOST", "ep-x.sa-east-1.aws.neon.tech")
    monkeypatch.setenv("NUVEM_USER", "dono")
    monkeypatch.setenv("NUVEM_PASSWORD", "x" * 16)
    dw = recursos.nuvem_do_ambiente()
    assert (dw.nome, dw.sslmode, dw.porta, dw.banco) == ("nuvem", "require", 5432, "dw_fictalent")


def test_o_recurso_local_nao_pede_tls_e_o_da_nuvem_pede(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[dict[str, Any]] = []

    def conectar_falso(**kw: Any) -> str:
        chamadas.append(kw)
        return "conexao"

    monkeypatch.setattr(psycopg, "connect", conectar_falso)
    recursos.Warehouse(host="h", porta=1, banco="b", usuario="u", senha="s").conectar()
    recursos.Warehouse(
        host="h", porta=1, banco="b", usuario="u", senha="s", sslmode="require"
    ).conectar()
    assert "sslmode" not in chamadas[0] and chamadas[1]["sslmode"] == "require"
    assert chamadas[0]["connect_timeout"] == 20


def test_a_cli_da_gold_aceita_o_destino(monkeypatch: pytest.MonkeyPatch) -> None:
    visto: dict[str, Any] = {}

    def falso(*args: Any) -> int:
        visto["args"] = args
        return 0

    monkeypatch.setattr(cli, "_warehouse", falso)
    assert cli.main(["--warehouse", "--destino", "nuvem"]) == 0
    assert visto["args"] == ([], "nuvem")
    assert cli.main(["--warehouse"]) == 0 and visto["args"] == ([], "local")
    monkeypatch.setattr(cli, "_indices", falso)
    assert cli.main(["--indices", "--aplicar", "--destino", "nuvem"]) == 0
    assert visto["args"] == (False, True, "nuvem")
    with pytest.raises(SystemExit):
        cli.main(["--warehouse", "--destino", "marte"])


@pytest.mark.skipif(len(NUVEM) < 3, reason="sem NUVEM_* preenchidas no .env")
def test_o_neon_responde_com_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Com as variáveis no .env: conecta ao destino de verdade e lê a versão; nada é escrito.

    O TLS termina no proxy do Neon, então `SHOW ssl` no servidor diz `off`: a prova do TLS é o
    `sslmode=require` do recurso, que faz o cliente recusar conexão em claro."""
    for chave, valor in NUVEM.items():
        monkeypatch.setenv(chave, valor)
    dw = recursos.nuvem_do_ambiente()
    with dw.conectar() as con, con.cursor() as cur:
        cur.execute("SELECT version(), current_database()")
        versao, banco = cur.fetchone() or ("", "")
    assert versao.startswith("PostgreSQL") and banco == dw.banco and dw.sslmode == "require"
