"""O Grafana é código: o painel e os alertas são arquivos, só leem observabilidade e funcionam.

Estático: JSON e YAML válidos, toda consulta apontando para a fonte do warehouse e tocando
só o schema observabilidade (nunca dado de negócio, nunca dado pessoal). Integração: cada
SQL executado como grafana_leitor contra o warehouse, e a API do Grafana confirmando que o
painel e as regras foram provisionados. Pula sem a plataforma.
"""

from __future__ import annotations

import base64
import json
import re
import socket
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
import pytest
import yaml
from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]
PROVISIONING = RAIZ / "infra" / "grafana" / "provisioning"
PAINEL = json.loads(
    (PROVISIONING / "dashboards" / "json" / "execucoes.json").read_text(encoding="utf-8")
)
REGRAS = yaml.safe_load((PROVISIONING / "alerting" / "regras.yaml").read_text(encoding="utf-8"))
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
FONTE = "warehouse-postgres"


def _consultas_do_painel() -> list[tuple[str, str]]:
    return [(p["title"], t["rawSql"]) for p in PAINEL["panels"] for t in p["targets"]]


def _consultas_dos_alertas() -> list[tuple[str, str]]:
    saida = []
    for grupo in REGRAS["groups"]:
        for regra in grupo["rules"]:
            for dado in regra["data"]:
                if dado["datasourceUid"] == FONTE:
                    saida.append((regra["title"], dado["model"]["rawSql"]))
    return saida


def _sem_macros(sql: str) -> str:
    return re.sub(r"\$__timeFilter\(([^)]+)\)", r"\1 > now() - interval '7 days'", sql)


def test_painel_e_provisionado_e_nao_editavel() -> None:
    provedor = yaml.safe_load(
        (PROVISIONING / "dashboards" / "painel.yaml").read_text(encoding="utf-8")
    )
    assert provedor["providers"][0]["allowUiUpdates"] is False
    assert PAINEL["uid"] == "fictalent-execucoes" and PAINEL["editable"] is False
    assert len(PAINEL["panels"]) == 9


def test_toda_consulta_le_o_warehouse_e_so_o_schema_observabilidade() -> None:
    for p in PAINEL["panels"]:
        assert p["datasource"]["uid"] == FONTE, p["title"]
    for titulo, sql in _consultas_do_painel() + _consultas_dos_alertas():
        tabelas = set(re.findall(r"\b(?:FROM|JOIN)\s+([a-z_]+\.[a-z_]+)", sql, flags=re.I))
        assert tabelas and all(t.startswith("observabilidade.") for t in tabelas), (titulo, tabelas)
        assert not re.search(r"\b(cpf|nome|salario|cid_grupo)\b", sql, flags=re.I), titulo


def test_alertas_cobrem_falha_e_frescor_com_limiar() -> None:
    regras = {r["uid"]: r for g in REGRAS["groups"] for r in g["rules"]}
    assert set(regras) == {"fictalent-execucao-falhou", "fictalent-dado-envelheceu"}
    for r in regras.values():
        assert r["condition"] == "C" and r["data"][-1]["model"]["type"] == "threshold"
    assert regras["fictalent-dado-envelheceu"]["data"][-1]["model"]["conditions"][0]["evaluator"][
        "params"
    ] == [26]


def _porta_aberta(porta: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        return False
    return True


plataforma = pytest.mark.skipif(
    not ENV
    or not _porta_aberta(int(ENV.get("DW_PORT") or 5441))
    or not _porta_aberta(int(ENV.get("GRAFANA_PORT") or 3011)),
    reason="warehouse ou Grafana fora do ar, ou .env ausente",
)


@plataforma
@pytest.mark.parametrize(("titulo", "sql"), _consultas_do_painel() + _consultas_dos_alertas())
def test_consulta_roda_como_grafana_leitor(titulo: str, sql: str) -> None:
    with (
        psycopg.connect(
            host="127.0.0.1",
            port=int(ENV.get("DW_PORT") or 5441),
            dbname=ENV.get("DW_DB") or "dw_fictalent",
            user="grafana_leitor",
            password=ENV.get("GRAFANA_LEITOR_PASSWORD") or "",
        ) as con,
        con.cursor() as cur,
    ):
        cur.execute(_sem_macros(sql))
        cur.fetchall()  # sem exceção: a consulta é válida e o papel tem direito de ler


def _grafana(caminho: str) -> Any:
    credencial = (
        f"{ENV.get('GRAFANA_ADMIN_USER') or 'admin'}:{ENV.get('GRAFANA_ADMIN_PASSWORD') or ''}"
    )
    pedido = urllib.request.Request(
        f"http://127.0.0.1:{ENV.get('GRAFANA_PORT') or 3011}{caminho}",
        headers={"Authorization": "Basic " + base64.b64encode(credencial.encode()).decode()},
    )
    with urllib.request.urlopen(pedido, timeout=10) as resposta:  # noqa: S310
        return json.loads(resposta.read())


@plataforma
def test_grafana_tem_o_painel_e_as_regras_provisionados() -> None:
    paineis = _grafana("/api/search?type=dash-db&query=Fictalent")
    assert any(p["uid"] == "fictalent-execucoes" for p in paineis), paineis
    regras = _grafana("/api/v1/provisioning/alert-rules")
    assert {r["uid"] for r in regras} >= {"fictalent-execucao-falhou", "fictalent-dado-envelheceu"}
