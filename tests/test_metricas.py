"""Resumo de passos certo sem banco; com a plataforma, a execução vira linhas no warehouse."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import dagster as dg
import pytest
from dotenv import dotenv_values

from rh_fictalent.observabilidade.metricas import Evento, registrar_execucao, resumir_passos
from rh_fictalent.orquestracao.definicoes import defs
from rh_fictalent.orquestracao.recursos import Warehouse
from rh_fictalent.orquestracao.sensores import SENSORES

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def test_resumo_junta_inicio_fim_status_asset_e_linhas() -> None:
    eventos = [
        Evento(10.0, "STEP_START", "bronze_candidato"),
        Evento(
            12.5,
            "ASSET_MATERIALIZATION",
            "bronze_candidato",
            asset="bronze/ats/candidato",
            particao="2026-09-16",
            metadados={"linhas": 1200, "arquivo": "x.parquet"},
        ),
        Evento(13.0, "STEP_SUCCESS", "bronze_candidato"),
        Evento(13.0, "STEP_START", "silver_candidato"),
        Evento(14.2, "STEP_FAILURE", "silver_candidato", erro="CPF inválido"),
    ]
    passos = {p.passo: p for p in resumir_passos(eventos)}
    bronze, silver = passos["bronze_candidato"], passos["silver_candidato"]
    assert bronze.status == "SUCESSO" and bronze.duracao_s == 3.0
    assert bronze.asset == "bronze/ats/candidato" and bronze.particao == "2026-09-16"
    assert bronze.linhas == 1200 and bronze.metadados["arquivo"] == "x.parquet"
    assert silver.status == "FALHA" and silver.erro == "CPF inválido" and silver.duracao_s == 1.2


def test_passo_sem_fim_fica_em_andamento_e_sem_duracao() -> None:
    (p,) = resumir_passos([Evento(1.0, "STEP_START", "x")])
    assert p.status == "EM_ANDAMENTO" and p.duracao_s is None


def test_sensores_cobrem_os_tres_desfechos_e_ligam_sozinhos() -> None:
    nomes = {s.name for s in SENSORES}
    assert nomes == {"metricas_sucesso", "metricas_falha", "metricas_cancelamento"}
    for s in SENSORES:
        assert s.default_status == dg.DefaultSensorStatus.RUNNING
        assert defs.get_sensor_def(s.name) is not None


def _warehouse_local() -> Warehouse:
    """Fora do Dagster o EnvVar não se resolve: o recurso leva os valores concretos do .env."""
    return Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or "",
    )


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
def test_execucao_vira_linhas_no_warehouse(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome, valor in ENV.items():
        if valor is not None:
            monkeypatch.setenv(nome, valor)
    os.environ["S3_ENDPOINT"] = f"http://127.0.0.1:{ENV.get('S3_PORT') or 8333}"
    warehouse = _warehouse_local()
    with dg.DagsterInstance.ephemeral() as instance:
        resultado = defs.get_job_def("verificar_plataforma").execute_in_process(instance=instance)
        assert resultado.success
        run = instance.get_run_by_id(resultado.run_id)
        assert run is not None
        passos = registrar_execucao(instance, run, "SUCESSO", warehouse)
        registrar_execucao(instance, run, "SUCESSO", warehouse)  # de novo: upsert, não duplica
    assert {p.passo for p in passos} == {"replica_pronta", "lake_pronto", "warehouse_pronto"}
    assert all(p.status == "SUCESSO" and p.duracao_s is not None for p in passos)

    admin = _warehouse_local()
    (execucoes,) = admin.consultar(
        "SELECT COUNT(*) FROM observabilidade.execucao WHERE run_id = %s", resultado.run_id
    )[0]
    linhas = admin.consultar(
        "SELECT passo, status, asset, metadados->>'tabelas' FROM observabilidade.execucao_passo "
        "WHERE run_id = %s ORDER BY passo",
        resultado.run_id,
    )
    assert execucoes == 1 and len(linhas) == 3
    replica = next(linha for linha in linhas if linha[0] == "replica_pronta")
    assert replica[1] == "SUCESSO" and replica[2] == "replica_pronta" and replica[3] == "76"
    # limpeza do que o teste gravou
    admin.consultar(
        "DELETE FROM observabilidade.execucao WHERE run_id = %s RETURNING run_id", resultado.run_id
    )
