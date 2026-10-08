# ruff: noqa: E501
"""A API contra o warehouse de verdade: o acesso negado falha, e o RLS conta certo.

Com a plataforma de pé, o teste cadastra consumidores descartáveis (um por perfil, com as
filiais) e tokens gerados aqui dentro, nunca impressos, e chama a aplicação como o serviço a
chama: o `Leitor` conectando como o usuário `api` e fazendo `SET LOCAL ROLE` por pedido. É o
teste que o `docs/03` pede: passa quando o acesso indevido falha. As contagens que o RLS
filtra são conferidas contra o parquet da gold, que é a verdade. Tudo é apagado ao fim.
"""

from __future__ import annotations

import os
import secrets
import socket
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient

from rh_fictalent.api import acesso, consultas
from rh_fictalent.api.app import criar_app
from rh_fictalent.api.servico import Leitor
from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.recursos import Lake, Warehouse

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PORTA_DA_API = int(ENV.get("API_PORT") or 8010)


def _de_pe(porta: str) -> bool:
    try:
        socket.create_connection(("127.0.0.1", int(ENV.get(porta) or 0)), timeout=1).close()
    except (OSError, ValueError):
        return False
    return True


pytestmark = pytest.mark.skipif(
    not ENV or not ENV.get("API_DB_PASSWORD") or not _de_pe("DW_PORT") or not _de_pe("S3_PORT"),
    reason="plataforma fora do ar, ou .env sem API_DB_PASSWORD",
)

# um consumidor por perfil, com as filiais do caso: 1 matriz (Atibaia), 2 Bragança, 3 Extrema
CONSUMIDORES: dict[str, tuple[str, tuple[int, ...]]] = {
    "teste_api_socio": ("socio", ()),
    "teste_api_financeiro": ("financeiro", ()),
    "teste_api_coord_extrema": ("coordenacao", (3,)),
    "teste_api_assist_braganca": ("assistente", (2,)),
}


def _admin() -> Warehouse:
    return Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or os.environ.get("DW_ADMIN_PASSWORD", ""),
    )


def _apagar(dw: Warehouse, papeis: list[str]) -> None:
    with dw.conectar() as con, con.cursor() as cur:
        for papel in papeis:
            cur.execute("DELETE FROM acesso.token WHERE papel = %s", (papel,))
            cur.execute("DELETE FROM acesso.filial_do_papel WHERE papel = %s", (papel,))
            cur.execute(
                f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{papel}') THEN "  # noqa: S608
                f"REVOKE {papel} FROM api; DROP ROLE {papel}; END IF; END $$;"
            )
        con.commit()


@pytest.fixture(scope="module")
def tokens() -> Iterator[dict[str, str]]:
    """Os consumidores descartáveis e os tokens deles; `sem_grant` é um papel que a API não pode assumir."""
    dw = _admin()
    papeis = [*CONSUMIDORES, "teste_api_sem_grant", "teste_api_vencido"]
    _apagar(dw, papeis)
    gerados: dict[str, str] = {}
    for papel, (perfil, filiais) in CONSUMIDORES.items():
        acesso.cadastrar_consumidor(dw, papel, perfil, filiais)
        gerados[papel] = secrets.token_hex(32)
        acesso.cadastrar_token(dw, papel, gerados[papel], descricao="teste 8.2")
    with dw.conectar() as con, con.cursor() as cur:
        # no perfil, mas sem GRANT ... TO api: a API não consegue assumir o papel
        cur.execute("CREATE ROLE teste_api_sem_grant NOLOGIN IN ROLE perfil_socio")
        cur.execute("CREATE ROLE teste_api_vencido NOLOGIN IN ROLE perfil_socio")
        cur.execute("GRANT teste_api_vencido TO api")
        con.commit()
    for papel in ("teste_api_sem_grant", "teste_api_vencido"):
        gerados[papel] = secrets.token_hex(32)
    acesso.cadastrar_token(dw, "teste_api_sem_grant", gerados["teste_api_sem_grant"])
    acesso.cadastrar_token(
        dw,
        "teste_api_vencido",
        gerados["teste_api_vencido"],
        valido_ate=date.today() - timedelta(days=1),
    )
    try:
        yield gerados
    finally:
        _apagar(dw, papeis)


@pytest.fixture(scope="module")
def cliente() -> TestClient:
    """A aplicação como o serviço a sobe: o Leitor conectando como o usuário api."""
    leitor = Leitor(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("API_DB_USER") or acesso.USUARIO,
        senha=ENV["API_DB_PASSWORD"] or "",
    )
    return TestClient(criar_app(leitor))


@pytest.fixture(scope="module")
def gold() -> Iterator[Any]:
    """A gold no lake, a verdade contra a qual o RLS é conferido."""
    lake = Lake(
        endpoint=f"http://127.0.0.1:{ENV.get('S3_PORT') or 8333}",
        chave=ENV.get("S3_ACCESS_KEY") or "",
        segredo=ENV.get("S3_SECRET_KEY") or "",
        bucket=ENV.get("S3_BUCKET") or "fictalent-lake",
    )
    con = consulta.abrir_gold(lake)
    try:
        yield con
    finally:
        con.close()


def _como(tokens: dict[str, str], papel: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens[papel]}"}


def _um(gold: Any, sql: str) -> Any:
    (valor,) = gold.execute(sql).fetchone()
    return valor


# ------------------------------------------------------------- o token


def test_sem_token_token_inventado_e_token_vencido_dao_401(
    cliente: TestClient, tokens: dict[str, str]
) -> None:
    assert cliente.get("/v1/filiais").status_code == 401
    assert (
        cliente.get(
            "/v1/filiais", headers={"Authorization": f"Bearer {secrets.token_hex(32)}"}
        ).status_code
        == 401
    )
    vencido = cliente.get("/v1/filiais", headers=_como(tokens, "teste_api_vencido"))
    assert vencido.status_code == 401 and "vencido" in vencido.json()["detalhe"]


def test_token_revogado_deixa_de_entrar(cliente: TestClient, tokens: dict[str, str]) -> None:
    dw = _admin()
    token = secrets.token_hex(32)
    acesso.cadastrar_token(dw, "teste_api_socio", token, descricao="vai ser revogado")
    assert (
        cliente.get("/v1/filiais", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    )
    assert acesso.revogar_tokens(dw, "teste_api_socio") >= 1
    assert (
        cliente.get("/v1/filiais", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    )
    acesso.cadastrar_token(
        dw, "teste_api_socio", tokens["teste_api_socio"], descricao="teste 8.2"
    )  # devolve o da fixture


# ------------------------------------------------------------- o acesso negado


@pytest.mark.parametrize(
    ("papel", "caminho", "tabela"),
    [
        ("teste_api_financeiro", "/v1/postos/1/ponto?mes=202409", "ponto_dia"),
        ("teste_api_financeiro", "/v1/funil?ano=2024", "candidatura"),
        ("teste_api_financeiro", "/v1/mercado/escopos", "escopo_mercado"),
        ("teste_api_coord_extrema", "/v1/filiais/3/resultado", "resultado_mes"),
        ("teste_api_coord_extrema", "/v1/funil?ano=2024", "candidatura"),
        ("teste_api_coord_extrema", "/v1/mercado?escopo=1", "mercado_mes"),
        ("teste_api_assist_braganca", "/v1/clientes?ano=2024", "posto_mes"),
        ("teste_api_assist_braganca", "/v1/filiais/2/resultado", "resultado_mes"),
    ],
)
def test_o_perfil_que_nao_le_a_tabela_recebe_403(
    cliente: TestClient, tokens: dict[str, str], papel: str, caminho: str, tabela: str
) -> None:
    resposta = cliente.get(caminho, headers=_como(tokens, papel))
    assert resposta.status_code == 403, resposta.text
    assert tabela in resposta.json()["detalhe"]


def test_o_papel_que_a_api_nao_pode_assumir_recebe_403(
    cliente: TestClient, tokens: dict[str, str]
) -> None:
    resposta = cliente.get("/v1/filiais", headers=_como(tokens, "teste_api_sem_grant"))
    assert resposta.status_code == 403 and "set role" in resposta.json()["detalhe"].lower()


# ------------------------------------------------------------- o RLS, conferido contra o parquet


def test_a_assistente_de_braganca_ve_o_funil_de_braganca_como_se_fosse_o_todo(
    cliente: TestClient, tokens: dict[str, str], gold: Any
) -> None:
    de_braganca = cliente.get(
        "/v1/funil?ano=2024", headers=_como(tokens, "teste_api_assist_braganca")
    ).json()
    do_socio = cliente.get("/v1/funil?ano=2024", headers=_como(tokens, "teste_api_socio")).json()
    assert sum(t["candidaturas"] for t in de_braganca) == _um(
        gold, "SELECT count(*) FROM gold.fato_candidatura WHERE ano = 2024 AND filial_id = 2"
    )
    assert sum(t["candidaturas"] for t in do_socio) == _um(
        gold, "SELECT count(*) FROM gold.fato_candidatura WHERE ano = 2024"
    )
    assert sum(t["candidaturas"] for t in de_braganca) < sum(t["candidaturas"] for t in do_socio)
    assert [t["trimestre"] for t in do_socio] == [1, 2, 3, 4]


def test_a_coordenacao_de_extrema_nao_ve_o_ponto_da_matriz(
    cliente: TestClient, tokens: dict[str, str], gold: Any
) -> None:
    posto_da_matriz, mes = gold.execute(
        "SELECT posto_id, data_id // 100 FROM gold.fato_ponto_dia WHERE filial_id = 1 "
        "GROUP BY 1, 2 ORDER BY count(*) DESC LIMIT 1"
    ).fetchone()
    posto_de_extrema = _um(
        gold,
        f"SELECT posto_id FROM gold.fato_ponto_dia WHERE filial_id = 3 AND data_id // 100 = {mes} "  # noqa: S608
        "GROUP BY 1 ORDER BY count(*) DESC LIMIT 1",
    )
    coord = _como(tokens, "teste_api_coord_extrema")
    assert cliente.get(f"/v1/postos/{posto_da_matriz}/ponto?mes={mes}", headers=coord).json() == []
    de_extrema = cliente.get(f"/v1/postos/{posto_de_extrema}/ponto?mes={mes}", headers=coord).json()
    assert sum(s["dias"] for s in de_extrema) == _um(
        gold,
        f"SELECT count(*) FROM gold.fato_ponto_dia WHERE posto_id = {posto_de_extrema} AND data_id // 100 = {mes}",  # noqa: S608
    )
    do_socio = cliente.get(
        f"/v1/postos/{posto_da_matriz}/ponto?mes={mes}", headers=_como(tokens, "teste_api_socio")
    ).json()
    assert sum(s["dias"] for s in do_socio) > 0


# ------------------------------------------------------------- o contrato, com os números da gold


def test_o_resultado_da_filial_e_o_da_gold(
    cliente: TestClient, tokens: dict[str, str], gold: Any
) -> None:
    resposta = cliente.get(
        "/v1/filiais/1/resultado?de=202501&ate=202503",
        headers=_como(tokens, "teste_api_financeiro"),
    )
    linhas = resposta.json()
    assert [m["mes_id"] for m in linhas] == [202501, 202502, 202503]
    esperado = gold.execute(
        "SELECT faturamento, resultado, pessoas_alocadas FROM gold.fato_resultado_mes WHERE filial_id = 1 AND mes_id = 202501"
    ).fetchone()
    assert (linhas[0]["faturamento"], linhas[0]["resultado"], linhas[0]["pessoas_alocadas"]) == (
        float(esperado[0]),
        float(esperado[1]),
        esperado[2],
    )
    assert (
        cliente.get(
            "/v1/filiais/1/resultado?de=202501&ate=202412", headers=_como(tokens, "teste_api_socio")
        ).json()
        == []
    )


def test_o_pareto_fecha_em_um_e_esta_em_ordem(
    cliente: TestClient, tokens: dict[str, str], gold: Any
) -> None:
    clientes = cliente.get("/v1/clientes?ano=2024", headers=_como(tokens, "teste_api_socio")).json()
    assert len(clientes) == _um(
        gold,
        "SELECT count(DISTINCT cliente_id) FROM gold.fato_posto_mes WHERE ano = 2024 AND receita > 0",
    )
    assert [c["posicao"] for c in clientes][:3] == [1, 2, 3]
    assert all(a["receita"] >= b["receita"] for a, b in zip(clientes, clientes[1:], strict=False))
    assert abs(sum(c["participacao"] for c in clientes) - 1.0) < 1e-9
    assert abs(clientes[-1]["participacao_acumulada"] - 1.0) < 1e-9
    assert (
        abs(
            sum(c["receita"] for c in clientes)
            - float(_um(gold, "SELECT sum(receita) FROM gold.fato_posto_mes WHERE ano = 2024"))
        )
        < 0.01
    )


def test_o_mercado_vem_inteiro_para_quem_o_le(
    cliente: TestClient, tokens: dict[str, str], gold: Any
) -> None:
    escopos = cliente.get(
        "/v1/mercado/escopos", headers=_como(tokens, "teste_api_assist_braganca")
    ).json()
    assert len(escopos) == _um(gold, "SELECT count(*) FROM gold.dim_escopo_mercado WHERE id > 0")
    serie = cliente.get(
        f"/v1/mercado?escopo={escopos[0]['id']}", headers=_como(tokens, "teste_api_assist_braganca")
    ).json()
    assert serie and all(m["saldo"] == m["admissoes"] - m["desligamentos"] for m in serie)


def test_a_consulta_do_contrato_e_a_mesma_do_servico() -> None:
    """O SQL que o teste vivo exercita é o declarado em `consultas`, com os schemas do warehouse."""
    assert '"fato"."candidatura"' in consultas.funil_do_ano(consultas.Esquemas()).as_string()


# ------------------------------------------------------------- o serviço de pé no Compose


@pytest.mark.skipif(not _de_pe("API_PORT"), reason="serviço api fora do ar")
def test_o_servico_do_compose_responde_e_recusa_sem_token() -> None:
    base = f"http://127.0.0.1:{PORTA_DA_API}"
    saude = httpx.get(f"{base}/saude", timeout=10).json()
    assert saude == {"situacao": "ok", "warehouse": True, "versao": "v1"}
    assert httpx.get(f"{base}/v1/filiais", timeout=10).status_code == 401
    caminhos = httpx.get(f"{base}/v1/openapi.json", timeout=10).json()["paths"]
    assert "/v1/funil" in caminhos and "/saude" in caminhos


# ------------------------------------------------------------- a trilha dos pedidos


def test_todo_pedido_vai_para_a_trilha_com_o_papel_e_o_codigo(
    cliente: TestClient, tokens: dict[str, str]
) -> None:
    """A API registra cada pedido a /v1 em acesso.pedido (o papel, o caminho, o código), por
    uma função que só insere: é o que a trilha de auditoria lê (`rh_fictalent.trilha`)."""
    dw = _admin()
    antes = dw.consultar("SELECT count(*) FROM acesso.pedido")[0][0]
    assert cliente.get("/v1/filiais", headers=_como(tokens, "teste_api_socio")).status_code == 200
    assert (
        cliente.get(
            "/v1/filiais/1/resultado", headers=_como(tokens, "teste_api_coord_extrema")
        ).status_code
        == 403
    )
    assert cliente.get("/v1/filiais").status_code == 401
    novos = dw.consultar(
        "SELECT papel, caminho, codigo FROM acesso.pedido ORDER BY id DESC LIMIT 3"
    )
    assert dw.consultar("SELECT count(*) FROM acesso.pedido")[0][0] == antes + 3
    assert novos[::-1] == [
        ("teste_api_socio", "/v1/filiais", 200),
        ("teste_api_coord_extrema", "/v1/filiais/1/resultado", 403),
        (None, "/v1/filiais", 401),
    ]
    # a trilha responde pela pergunta pronta, sem token nenhum
    from rh_fictalent.trilha import consultas as trilha

    pedidos = trilha.no_warehouse(dw, "pedidos_da_api_por_dia")
    do_socio = pedidos[
        (pedidos["papel"] == "teste_api_socio") & (pedidos["caminho"] == "/v1/filiais")
    ]
    assert int(do_socio["ok"].sum()) >= 1
    recusados = pedidos[pedidos["papel"] == "teste_api_coord_extrema"]
    assert int(recusados["recusados_pelo_banco"].sum()) >= 1
    assert "hash" not in trilha.no_warehouse(dw, "tokens_da_api").columns
