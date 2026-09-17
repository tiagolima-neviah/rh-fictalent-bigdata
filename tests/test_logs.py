"""Cada linha de log é JSON; dentro de uma execução carrega o run_id; o Dagster está configurado."""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import dagster as dg
import pytest
import yaml
from dotenv import dotenv_values

from rh_fictalent.observabilidade.logs import FormatadorJSON, obter_logger
from rh_fictalent.orquestracao.definicoes import defs
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON, logger_json
from rh_fictalent.orquestracao.verificacao import verificar_plataforma

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def _registro(mensagem: str, **extras: object) -> logging.LogRecord:
    registro = logging.LogRecord(
        "rh_fictalent.teste", logging.INFO, __file__, 1, mensagem, None, None
    )
    for chave, valor in extras.items():
        setattr(registro, chave, valor)
    return registro


def test_linha_e_json_com_os_campos_basicos() -> None:
    linha = json.loads(FormatadorJSON().format(_registro("réplica com 76 tabelas")))
    assert linha["mensagem"] == "réplica com 76 tabelas"
    assert linha["nivel"] == "INFO" and linha["logger"] == "rh_fictalent.teste"
    assert linha["instante"].endswith("+00:00"), "instante em UTC"
    assert "run_id" not in linha, "fora de uma execução não há run_id"


def test_dentro_de_uma_execucao_leva_run_id_job_passo_evento_e_mensagem_limpa() -> None:
    meta = {
        "run_id": "9e11f0e3",
        "job_name": "verificar_plataforma",
        "step_key": "lake_pronto",
        "orig_message": "lake alcançado",
        "dagster_event": SimpleNamespace(event_type_value="STEP_SUCCESS"),
    }
    prefixada = "verificar_plataforma - 9e11f0e3 - lake_pronto - lake alcançado"
    linha = json.loads(FormatadorJSON().format(_registro(prefixada, dagster_meta=meta)))
    assert linha["run_id"] == "9e11f0e3"
    assert linha["job"] == "verificar_plataforma"
    assert linha["passo"] == "lake_pronto"
    assert linha["evento"] == "STEP_SUCCESS"
    assert linha["mensagem"] == "lake alcançado", "o prefixo do Dagster vira campos, não texto"


def test_excecao_vai_no_campo_excecao() -> None:
    try:
        raise ValueError("falhou de propósito")
    except ValueError:
        registro = _registro("erro")
        registro.exc_info = sys.exc_info()
    linha = json.loads(FormatadorJSON().format(registro))
    assert "ValueError: falhou de propósito" in linha["excecao"]


def test_acentos_nao_sao_escapados() -> None:
    texto = FormatadorJSON().format(_registro("exclusão registrada"))
    assert "exclusão" in texto and "\\u" not in texto


def test_logger_do_projeto_fica_sob_a_raiz() -> None:
    assert obter_logger("staging.gatilhos").name == "rh_fictalent.staging.gatilhos"
    assert obter_logger("rh_fictalent.x").name == "rh_fictalent.x"


def test_logger_de_job_escreve_json_na_saida_padrao() -> None:
    contexto = dg.build_init_logger_context(logger_config={"nivel": "INFO"})
    logger = logger_json.logger_fn(contexto)
    (handler,) = logger.handlers
    assert isinstance(handler.formatter, FormatadorJSON)
    assert isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout
    assert logger.level == logging.INFO


def test_definicoes_usam_o_logger_json_como_padrao() -> None:
    assert set(defs.loggers or {}) == {"json"}
    assert verificar_plataforma.config == CONFIG_LOGS_JSON, "todo job seleciona o logger json"
    assert list(defs.get_job_def("verificar_plataforma").loggers) == ["json"]


def test_dagster_gerencia_os_loggers_do_projeto_sem_handler_duplicado() -> None:
    config = yaml.safe_load(
        (RAIZ / "infra" / "dagster" / "dagster.yaml").read_text(encoding="utf-8")
    )
    logs = config["python_logs"]
    assert "rh_fictalent" in logs["managed_python_loggers"]
    assert "dagster_handler_config" not in logs, (
        "o logger do job já escreve o JSON; handler duplicaria"
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
def test_execucao_local_sai_em_json_com_um_run_id_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for nome, valor in ENV.items():
        if valor is not None:
            monkeypatch.setenv(nome, valor)
    os.environ["S3_ENDPOINT"] = f"http://127.0.0.1:{ENV.get('S3_PORT') or 8333}"
    resultado = defs.get_job_def("verificar_plataforma").execute_in_process()
    assert resultado.success
    linhas = [
        json.loads(linha) for linha in capsys.readouterr().out.splitlines() if linha.startswith("{")
    ]
    assert linhas, "nenhuma linha JSON na saída"
    assert {linha["run_id"] for linha in linhas} == {resultado.run_id}
    assert {"STEP_START", "STEP_SUCCESS"} <= {linha.get("evento") for linha in linhas}
    assert any(linha["mensagem"].startswith("réplica alcançada") for linha in linhas)
