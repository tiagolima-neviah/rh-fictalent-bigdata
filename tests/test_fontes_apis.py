"""O cliente HTTP recua, respeita a taxa e desiste; as fontes viram tabelas; os assets gravam."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import dagster as dg
import httpx
import pandas as pd
import pytest
from dotenv import dotenv_values

from rh_fictalent.fontes import apis
from rh_fictalent.fontes.apis import BRASILAPI, IBGE, ClienteHTTP, feriados, municipios
from rh_fictalent.orquestracao.definicoes import defs
from rh_fictalent.orquestracao.fontes import feriados_brasilapi, municipios_ibge
from rh_fictalent.orquestracao.recursos import ApisPublicas, Lake

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"

MICRO_BRAGANCA = {
    "id": 35013,
    "nome": "Bragança Paulista",
    "mesorregiao": {"nome": "Macro Metropolitana Paulista"},
}
IMEDIATA_BRAGANCA = {"nome": "Bragança Paulista", "regiao-intermediaria": {"nome": "Campinas"}}
MUNICIPIOS_SP = [
    {
        "id": 3504107,
        "nome": "Atibaia",
        "microrregiao": MICRO_BRAGANCA,
        "regiao-imediata": IMEDIATA_BRAGANCA,
    },
    {
        "id": 3507605,
        "nome": "Bragança Paulista",
        "microrregiao": MICRO_BRAGANCA,
        "regiao-imediata": IMEDIATA_BRAGANCA,
    },
]
MUNICIPIOS_MG = [{"id": 3125101, "nome": "Extrema", "microrregiao": None, "regiao-imediata": None}]
FERIADOS_2024 = [
    {"date": "2024-01-01", "name": "Confraternização mundial", "type": "national"},
    {"date": "2024-11-15", "name": "Proclamação da República", "type": "national"},
    {"date": "2024-11-20", "name": "Dia da consciência negra", "type": "national"},
]


class Relogio:
    """Relógio de mentira: o tempo só anda quando alguém dorme."""

    def __init__(self) -> None:
        self.agora = 0.0
        self.sonos: list[float] = []

    def dormir(self, segundos: float) -> None:
        self.sonos.append(round(segundos, 3))
        self.agora += segundos


def _cliente(relogio: Relogio, **kw: Any) -> ClienteHTTP:
    return ClienteHTTP(dormir=relogio.dormir, relogio=lambda: relogio.agora, **kw)


def _transporte(rotas: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Um MockTransport por rota: cada pedido consome a próxima resposta da lista."""
    pedidos: list[str] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(str(pedido.url))
        resposta = rotas[str(pedido.url)].pop(0)
        if isinstance(resposta, httpx.Response):
            return resposta
        if isinstance(resposta, Exception):
            raise resposta
        return httpx.Response(200, json=resposta)

    monkeypatch.setattr(apis, "transporte_de_teste", httpx.MockTransport(responder))
    return pedidos


def test_retry_recua_exponencialmente_e_respeita_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://exemplo/api"
    _transporte(
        {
            url: [
                httpx.Response(503),
                httpx.Response(429, headers={"Retry-After": "3"}),
                httpx.ConnectError("caiu"),
                {"ok": True},
            ]
        },
        monkeypatch,
    )
    relogio = Relogio()
    cliente = _cliente(relogio, intervalo_minimo=0)
    assert cliente.obter_json(url) == {"ok": True}
    # 0,5 s após o 503; 3 s (Retry-After > 1 s do recuo) após o 429; 2 s após a queda de rede
    assert relogio.sonos == [0.5, 3.0, 2.0]


def test_retry_desiste_depois_das_tentativas_e_nao_repete_erro_de_cliente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://exemplo/api"
    pedidos = _transporte({url: [httpx.Response(500)] * 3 + [httpx.Response(404)]}, monkeypatch)
    relogio = Relogio()
    with pytest.raises(httpx.HTTPStatusError) as erro:
        _cliente(relogio, tentativas=3, intervalo_minimo=0).obter_json(url)
    assert erro.value.response.status_code == 500 and len(pedidos) == 3
    with pytest.raises(httpx.HTTPStatusError) as erro:
        _cliente(relogio, tentativas=3, intervalo_minimo=0).obter_json(url)
    assert erro.value.response.status_code == 404 and len(pedidos) == 4  # 404 não se repete


def test_limite_de_taxa_espaca_os_pedidos(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://exemplo/api"
    _transporte({url: [{"n": 1}, {"n": 2}, {"n": 3}]}, monkeypatch)
    relogio = Relogio()
    cliente = _cliente(relogio, intervalo_minimo=0.5)
    for _ in range(3):
        cliente.obter_json(url)
    assert relogio.sonos == [0.5, 0.5]  # o primeiro sai na hora; os outros esperam a vez


def test_municipios_e_feriados_viram_tabelas_com_esquema_fixo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _transporte(
        {
            f"{IBGE}/estados/35/municipios": [MUNICIPIOS_SP],
            f"{IBGE}/estados/31/municipios": [MUNICIPIOS_MG],
            f"{BRASILAPI}/feriados/v1/2024": [FERIADOS_2024],
        },
        monkeypatch,
    )
    cliente = _cliente(Relogio(), intervalo_minimo=0)
    m = municipios(cliente)
    assert list(m.columns) == list(apis.COLUNAS_MUNICIPIO)
    assert m["codigo_ibge"].tolist() == ["3125101", "3504107", "3507605"]  # MG antes de SP
    assert m.loc[m["nome"] == "Atibaia", "regiao_intermediaria"].item() == "Campinas"
    assert m.loc[m["nome"] == "Extrema", "microrregiao"].item() == ""  # nulo vira vazio
    f = feriados(cliente, (2024,))
    assert list(f.columns) == list(apis.COLUNAS_FERIADO)
    assert f["abrangencia"].unique().tolist() == ["NACIONAL"] and f["ano"].unique().tolist() == [
        2024
    ]
    assert f["data"].tolist() == ["2024-01-01", "2024-11-15", "2024-11-20"]


def test_derivar_escreve_as_tabelas_e_a_fonte(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rotas: dict[str, list[Any]] = {
        f"{IBGE}/estados/35/municipios": [MUNICIPIOS_SP],
        f"{IBGE}/estados/31/municipios": [MUNICIPIOS_MG],
    }
    for ano in apis.ANOS:
        rotas[f"{BRASILAPI}/feriados/v1/{ano}"] = [FERIADOS_2024]
    _transporte(rotas, monkeypatch)
    apis.derivar(_cliente(Relogio(), intervalo_minimo=0), tmp_path)
    fonte = json.loads((tmp_path / "ibge" / "fonte.json").read_text(encoding="utf-8"))
    assert fonte["linhas"] == 3 and fonte["ufs"] == ["SP", "MG"]
    lido = pd.read_csv(tmp_path / "ibge" / "municipios.csv", dtype=str)
    assert lido["codigo_ibge"].str.len().eq(7).all()
    lido = pd.read_csv(tmp_path / "brasilapi" / "feriados_nacionais.csv")
    assert len(lido) == 3 * len(apis.ANOS)


GRAVADO: dict[str, pd.DataFrame] = {}  # o que o LakeEmMemoria recebeu (fora da classe: pydantic)


class LakeEmMemoria(Lake):
    """O Lake sem S3: guarda o que os assets gravam, para o teste ler."""

    def escrever_parquet(self, tabela: pd.DataFrame, caminho: str) -> None:
        GRAVADO[caminho] = tabela


def test_assets_gravam_no_lake_com_metadados(monkeypatch: pytest.MonkeyPatch) -> None:
    _transporte(
        {
            f"{IBGE}/estados/35/municipios": [MUNICIPIOS_SP],
            f"{IBGE}/estados/31/municipios": [MUNICIPIOS_MG],
            f"{BRASILAPI}/feriados/v1/2024": [FERIADOS_2024],
        },
        monkeypatch,
    )
    GRAVADO.clear()
    recursos = {
        "apis": ApisPublicas(intervalo_minimo=0),
        "lake": LakeEmMemoria(endpoint="", chave="", segredo="", bucket="teste"),
    }
    resultado = dg.materialize([municipios_ibge], resources=recursos)
    assert resultado.success
    assert len(GRAVADO["s3://teste/fontes/ibge/municipios.parquet"]) == 3
    (mat,) = resultado.asset_materializations_for_node("fontes__ibge__municipios")
    assert mat.metadata["por_uf"].value == {"SP": 2, "MG": 1}
    resultado = dg.materialize([feriados_brasilapi], resources=recursos, partition_key="2024")
    assert resultado.success
    assert len(GRAVADO["s3://teste/fontes/brasilapi/feriados/ano=2024.parquet"]) == 3


def test_definicoes_tem_o_grupo_fontes_e_os_dois_jobs() -> None:
    assert defs.resolve_job_def("carregar_municipios").name == "carregar_municipios"
    job = defs.resolve_job_def("carregar_feriados")
    assert job.partitions_def is not None
    assert job.partitions_def.get_partition_keys()[0] == "2018"
    assert municipios_ibge.key.path == ["fontes", "ibge", "municipios"]
    assert feriados_brasilapi.key.path == ["fontes", "brasilapi", "feriados"]


@pytest.mark.skipif(
    not (PUBLICOS / "ibge" / "municipios.csv").exists(), reason="tabelas versionadas ausentes"
)
def test_tabelas_versionadas_sao_coerentes() -> None:
    m = pd.read_csv(PUBLICOS / "ibge" / "municipios.csv", dtype=str)
    assert m["uf"].value_counts().to_dict() == {"MG": 853, "SP": 645}  # IBGE, contagem oficial
    assert m["codigo_ibge"].is_unique and m["codigo_ibge"].str.len().eq(7).all()
    do_caso = m.set_index("codigo_ibge").loc[["3504107", "3507605", "3125101"], "nome"].tolist()
    assert do_caso == ["Atibaia", "Bragança Paulista", "Extrema"]
    f = pd.read_csv(PUBLICOS / "brasilapi" / "feriados_nacionais.csv", dtype={"data": str})
    assert f["ano"].min() == 2018 and f["ano"].max() == 2026
    assert f.groupby("ano").size().between(8, 16).all()
    assert (f["data"].str[5:] == "11-15").sum() == 9  # Proclamação da República todo ano
    assert f["abrangencia"].eq("NACIONAL").all()


def _plataforma_de_pe() -> bool:
    try:
        socket.create_connection(("127.0.0.1", int(ENV.get("S3_PORT") or 0)), timeout=1).close()
    except (OSError, ValueError):
        return False
    return True


@pytest.mark.skipif(not ENV or not _plataforma_de_pe(), reason="lake fora do ar ou .env ausente")
def test_assets_materializam_contra_o_lake_e_as_apis_reais(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nome, valor in ENV.items():
        if valor is not None:
            monkeypatch.setenv(nome, valor)
    lake = Lake(
        endpoint=f"http://127.0.0.1:{ENV['S3_PORT']}",
        chave=str(ENV["S3_ACCESS_KEY"]),
        segredo=str(ENV["S3_SECRET_KEY"]),
        bucket=str(ENV.get("S3_BUCKET") or "fictalent-lake"),
    )
    recursos = {"apis": ApisPublicas(), "lake": lake}
    assert dg.materialize([municipios_ibge], resources=recursos).success
    m = lake.ler_parquet(lake.caminho("fontes", "ibge", "municipios.parquet"))
    assert len(m) == 853 + 645
    assert dg.materialize([feriados_brasilapi], resources=recursos, partition_key="2024").success
    f = lake.ler_parquet(lake.caminho("fontes", "brasilapi", "feriados", "ano=2024.parquet"))
    assert "2024-11-15" in f["data"].tolist()
