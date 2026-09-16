"""O dicionário de dados é gerado do banco e tem de bater com a DDL e com a réplica.

O teste estático confere, sem banco, que toda etiqueta LGPD da DDL aparece no dicionário
com a classe certa. O de integração regenera o dicionário da réplica e compara com o
arquivo versionado (pula quando a réplica não está de pé).
"""

from __future__ import annotations

import re
import socket
from pathlib import Path

import pytest
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
DDL = RAIZ / "staging" / "ddl"
DICIONARIO = RAIZ / "docs" / "dicionario" / "README.md"
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
CRIA_TABELA = re.compile(
    r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) ENCRYPTION='Y' COMMENT='([^']*)';", re.S
)
CLASSE = {"pessoal": "pessoal", "sensivel": "pessoal sensível"}


def _etiquetas_da_ddl() -> list[tuple[str, str, str, str]]:
    saida = []
    for arquivo in sorted(DDL.glob("[0-1][0-9]_*.sql")):
        modulo = arquivo.stem.split("_", 1)[1]
        for tabela, corpo, _ in CRIA_TABELA.findall(arquivo.read_text(encoding="utf-8")):
            for linha in corpo.splitlines():
                m = re.match(r"^  (\w+)\s.*\[LGPD:(pessoal|sensivel)\]", linha)
                if m:
                    saida.append((modulo, tabela, m.group(1), CLASSE[m.group(2)]))
    return saida


def test_dicionario_existe_e_e_gerado() -> None:
    texto = DICIONARIO.read_text(encoding="utf-8")
    assert "**Arquivo gerado**" in texto
    assert texto.count("\n### `") == 76, "uma seção por tabela"
    assert "Ã" not in texto, (
        "comentário acentuado gravado em latin1: o cliente mysql precisa de utf8mb4"
    )
    assert "endereço é de colaborador" in texto
    assert "Ã" not in texto, (
        "comentário acentuado gravado em latin1: o cliente mysql precisa de utf8mb4"
    )
    assert "endereço é de colaborador" in texto


def test_toda_etiqueta_da_ddl_esta_no_inventario() -> None:
    texto = DICIONARIO.read_text(encoding="utf-8")
    etiquetas = _etiquetas_da_ddl()
    assert len(etiquetas) >= 24
    for modulo, tabela, coluna, classe in etiquetas:
        linha = f"| `{modulo}` | `{tabela}` | `{coluna}` | {classe} |"
        assert linha in texto, f"{modulo}.{tabela}.{coluna} ({classe}) fora do inventário"


def test_referencias_publicas_marcadas() -> None:
    texto = DICIONARIO.read_text(encoding="utf-8")
    for tabela in (
        "cadastro.municipio",
        "cadastro.feriado",
        "financeiro.tributo",
        "sst.tipo_exame",
    ):
        assert f"### `{tabela}` · referência pública" in texto, tabela
    assert "### `pessoas.colaborador` · referência pública" not in texto


def _replica_de_pe() -> bool:
    try:
        socket.create_connection(
            ("127.0.0.1", int(ENV.get("STAGING_PORT") or 3316)), timeout=1
        ).close()
    except OSError:
        return False
    return True


@pytest.mark.skipif(
    not ENV.get("STAGING_ROOT_PASSWORD") or not _replica_de_pe(),
    reason="réplica MySQL fora do ar ou .env ausente",
)
def test_dicionario_versionado_e_igual_ao_da_replica() -> None:
    from rh_fictalent.staging.dicionario import gerar

    assert DICIONARIO.read_text(encoding="utf-8") == gerar(), (
        "dicionário desatualizado: python -m rh_fictalent.staging.dicionario"
    )
