"""O projeto Dagster carrega, obedece às convenções e, com a plataforma de pé, verifica-a."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import dagster as dg
import pytest
from dotenv import dotenv_values

from rh_fictalent.orquestracao import convencoes
from rh_fictalent.orquestracao.definicoes import defs
from rh_fictalent.orquestracao.recursos import recursos_do_ambiente
from rh_fictalent.orquestracao.verificacao import lake_pronto, replica_pronta, warehouse_pronto

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def test_definicoes_carregam_com_o_grupo_de_verificacao() -> None:
    job = defs.get_job_def("verificar_plataforma")
    assert job.name == "verificar_plataforma"
    chaves = {
        asset.key.to_user_string() for asset in (replica_pronta, lake_pronto, warehouse_pronto)
    }
    assert chaves == {"replica_pronta", "lake_pronto", "warehouse_pronto"}
    for asset in (replica_pronta, lake_pronto, warehouse_pronto):
        assert asset.group_names_by_key[asset.key] == "plataforma"


def test_recursos_leem_o_ambiente_com_padrao_local(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in ("STAGING_HOST", "STAGING_PORT", "S3_ENDPOINT", "DW_HOST", "DW_PORT"):
        monkeypatch.delenv(nome, raising=False)
    recursos = recursos_do_ambiente()
    assert recursos["replica"].host == "127.0.0.1" and recursos["replica"].porta == 3316
    assert recursos["lake"].endpoint == "http://127.0.0.1:8333"
    assert recursos["warehouse"].porta == 5441
    monkeypatch.setenv("STAGING_HOST", "mysql-staging")
    monkeypatch.setenv("STAGING_PORT", "3306")
    assert recursos_do_ambiente()["replica"].host == "mysql-staging"
    assert recursos_do_ambiente()["replica"].porta == 3306


def test_segredos_vem_por_envvar_e_nao_ficam_no_objeto() -> None:
    recursos = recursos_do_ambiente()
    assert isinstance(recursos["replica"].senha, dg.EnvVar)
    assert isinstance(recursos["lake"].segredo, dg.EnvVar)
    assert isinstance(recursos["warehouse"].senha, dg.EnvVar)


def test_convencoes_de_chave_e_particao() -> None:
    assert convencoes.chave("bronze", "ats", "candidato").path == ["bronze", "ats", "candidato"]
    with pytest.raises(ValueError):
        convencoes.chave("prata", "ats", "candidato")
    with pytest.raises(ValueError):
        convencoes.chave("bronze", "vendas", "x")
    assert convencoes.PARTICAO_ANUAL.get_partition_keys()[0] == "2018"
    assert convencoes.PARTICAO_ANUAL.get_partition_keys()[-1] == "2026"
    assert convencoes.PARTICAO_DIARIA.get_first_partition_key() == "2018-01-02"


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
def test_job_de_verificacao_materializa_contra_a_plataforma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nome, valor in ENV.items():
        if valor is not None:
            monkeypatch.setenv(nome, valor)
    for nome in ("STAGING_HOST", "S3_ENDPOINT", "DW_HOST"):
        monkeypatch.delenv(nome, raising=False)
    os.environ["S3_ENDPOINT"] = f"http://127.0.0.1:{ENV.get('S3_PORT') or 8333}"
    resultado = dg.materialize(
        [replica_pronta, lake_pronto, warehouse_pronto], resources=recursos_do_ambiente()
    )
    assert resultado.success
    materializacoes = {
        m.asset_key.to_user_string()
        for m in resultado.asset_materializations_for_node("replica_pronta")
    }
    assert materializacoes == {"replica_pronta"}
    metadados = resultado.asset_materializations_for_node("replica_pronta")[0].metadata
    assert metadados["tabelas"].value == 76
