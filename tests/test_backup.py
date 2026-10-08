# ruff: noqa: E501
"""Backup e restauração: as partes e o manifesto sem a plataforma; a prova de restauração com ela.

A prova viva faz um backup pequeno (um database da réplica, a chave, o warehouse, o Dagster e
uma camada do lake), restaura num MySQL efêmero, em bancos `*_prova` e num prefixo de prova do
bucket, compara as contagens com o manifesto e apaga os alvos. O backup inteiro, com os dez
databases e o lake completo, é a rotina da linha de comando, medida no `docs/19`.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest
from dotenv import dotenv_values

from rh_fictalent.backup import rotinas

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def test_as_partes_sao_lidas_do_texto() -> None:
    tudo = rotinas.Partes.de_texto(None)
    assert (
        tudo.replica == list(rotinas.DATABASES)
        and tudo.keyring
        and tudo.warehouse
        and tudo.dagster
        and tudo.quer_lake
    )
    so = rotinas.Partes.de_texto("replica:seguranca,warehouse,lake:controle")
    assert so.replica == ["seguranca"] and so.warehouse and not so.dagster and not so.keyring
    assert so.lake == ["controle"] and so.quer_lake
    sem_lake = rotinas.Partes.de_texto("keyring")
    assert sem_lake.keyring and not sem_lake.replica and not sem_lake.quer_lake
    assert rotinas.Partes.de_texto("lake").lake is None
    with pytest.raises(ValueError, match="parte desconhecida"):
        rotinas.Partes.de_texto("grafana")
    with pytest.raises(ValueError, match="database desconhecido"):
        rotinas.Partes.de_texto("replica:clientes")


def test_o_manifesto_e_conferido_arquivo_a_arquivo(tmp_path: Path) -> None:
    (tmp_path / "replica").mkdir()
    (tmp_path / "replica" / "cadastro.sql.gz").write_bytes(b"dump")
    manifesto = {
        "partes": {},
        "arquivos": {
            "replica/cadastro.sql.gz": {
                "bytes": 4,
                "sha256": rotinas._sha256(tmp_path / "replica" / "cadastro.sql.gz"),
            }
        },
    }
    (tmp_path / rotinas.MANIFESTO).write_text(json.dumps(manifesto), encoding="utf-8")
    assert rotinas.conferir_arquivos(tmp_path) == []
    (tmp_path / "replica" / "cadastro.sql.gz").write_bytes(b"dumq")
    assert rotinas.conferir_arquivos(tmp_path) == [
        "replica/cadastro.sql.gz: diferente do manifesto"
    ]
    (tmp_path / "replica" / "cadastro.sql.gz").unlink()
    assert rotinas.conferir_arquivos(tmp_path) == ["replica/cadastro.sql.gz: ausente"]


def test_a_comparacao_de_contagens_aponta_a_tabela() -> None:
    assert rotinas._comparar({"a.x": 1, "a.y": 2}, {"a.x": 1, "a.y": 2}) == []
    assert rotinas._comparar({"a.x": 1, "a.y": 2}, {"a.x": 1}) == [
        "a.y: esperado 2, obtido ausente"
    ]
    assert rotinas._comparar({"a.x": 1}, {"a.x": 3}) == ["a.x: esperado 1, obtido 3"]
    # num banco vivo, a contagem antes e depois do dump abrem um intervalo
    assert rotinas._comparar({"a.x": 10}, {"a.x": 8}, antes={"a.x": 7}) == []
    assert rotinas._comparar({"a.x": 10}, {"a.x": 11}, antes={"a.x": 7}) == [
        "a.x: esperado entre 7 e 10, obtido 11"
    ]
    assert rotinas.nome_da_pasta().count("-") == 1 and len(rotinas.nome_da_pasta()) == 15


def _plataforma_de_pe() -> bool:
    for porta in ("STAGING_PORT", "DW_PORT", "S3_PORT"):
        try:
            socket.create_connection(("127.0.0.1", int(ENV.get(porta) or 0)), timeout=1).close()
        except (OSError, ValueError):
            return False
    return True


@pytest.mark.skipif(
    not ENV or not _plataforma_de_pe(), reason="plataforma fora do ar ou .env ausente"
)
def test_o_backup_pequeno_se_restaura_e_confere(tmp_path: Path) -> None:
    """Com a plataforma de pé: um database da réplica, a chave, o warehouse, o Dagster e a camada
    de controle do lake vão para a pasta; a prova restaura cada um num alvo descartável e as
    contagens batem com o manifesto; os alvos somem ao fim."""
    for chave, valor in ENV.items():
        if valor is not None:
            os.environ.setdefault(chave, valor)
    os.environ["S3_ENDPOINT"] = f"http://127.0.0.1:{ENV.get('S3_PORT') or 8333}"
    amb = rotinas.Ambiente.do_ambiente()
    partes = rotinas.Partes.de_texto("replica:seguranca,keyring,warehouse,dagster,lake:controle")
    pasta = tmp_path / rotinas.nome_da_pasta()
    feito = rotinas.fazer(amb, pasta, partes)
    assert [r.parte for r in feito] == [
        "replica",
        "keyring",
        "warehouse",
        "dagster",
        "lake",
    ] and all(r.ok for r in feito)
    manifesto = rotinas.ler_manifesto(pasta)
    assert manifesto["partes"]["replica"]["linhas"]["seguranca.usuario"] > 0
    assert manifesto["partes"]["warehouse"]["linhas"]["fato.ponto_dia"] > 1_000_000
    assert (
        manifesto["partes"]["keyring"]["bytes"] > 0
        and (pasta / "replica" / "keyring").stat().st_mode & 0o077 == 0
    )
    assert set(manifesto["arquivos"]) >= {
        "replica/seguranca.sql.gz",
        "replica/keyring",
        f"warehouse/{amb.banco_dw}.dump",
        f"dagster/{amb.banco_dagster}.dump",
    }
    assert rotinas.conferir_arquivos(pasta) == []

    prova = rotinas.provar(amb, pasta, partes)
    assert [r.parte for r in prova] == [
        "arquivos",
        "replica",
        "keyring",
        "warehouse",
        "dagster",
        "lake",
    ]
    assert all(r.ok for r in prova), rotinas.texto(prova)
    assert "tudo confere" in next(r for r in prova if r.parte == "replica").detalhe
    # os alvos descartáveis sumiram
    fs = amb.lake.sistema()
    fs.invalidate_cache()
    assert rotinas.contar_lake(amb.lake, rotinas.PREFIXO_DE_PROVA) == {}  # nenhum arquivo ficou
    bancos = rotinas._psql(
        rotinas.CONTAINER_DW,
        amb.usuario_dw,
        amb.senha_dw,
        amb.banco_dw,
        "SELECT datname FROM pg_database WHERE datname LIKE '%_prova'",
    )
    assert bancos == []


def test_o_docs_19_cita_toda_parte_e_toda_opcao() -> None:
    texto = (RAIZ / "docs" / "19_backup_e_restauracao.md").read_text(encoding="utf-8")
    faltando = [p for p in rotinas.PARTES if f"`{p}`" not in texto]
    faltando += [
        o for o in ("--fazer", "--provar", "--restaurar", "--sim", "--parte") if o not in texto
    ]
    faltando += [
        a for a in ("_prova_restauracao", "dw_fictalent_prova", "manifesto.json") if a not in texto
    ]
    assert faltando == []
