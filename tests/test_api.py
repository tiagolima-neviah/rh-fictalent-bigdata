"""A API dos indicadores sem o banco: o contrato, o token e a tradução do que o banco recusa.

O `LeitorFalso` faz o papel do warehouse: diz de quem é cada token, devolve linhas prontas e
anota como quem (`SET ROLE`) cada consulta rodou. O que exige o banco de verdade (o `SET ROLE`
pelo Postgres, o RLS pela porta HTTP) é o card 8.2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from rh_fictalent.api import acesso, consultas
from rh_fictalent.api import app as modulo_app
from rh_fictalent.api.servico import AcessoNegado

if TYPE_CHECKING:
    from psycopg import sql

TOKENS = {"token-da-ana-" + "a" * 20: "ana", "token-do-socio-" + "s" * 20: "socio_paulo"}
LINHAS: dict[str, list[dict[str, Any]]] = {
    "resultado_mes": [
        {
            "mes_id": 202501,
            "mes_parcial": False,
            "faturamento": 1000.5,
            "faturamento_liquido": 900.5,
            "custo_pessoal": 600,
            "impostos": 100,
            "despesas": 50,
            "resultado": 250.5,
            "margem_liquida": 0.25,
            "pessoas_alocadas": 12,
            "clientes_ativos": 3,
            "vagas_abertas": 1,
        }
    ],
    "posto_mes": [
        {
            "cliente_id": 7,
            "cliente": "Hotel Serra",
            "porte": "MEDIO",
            "receita": 100.0,
            "margem": 20.0,
            "posicao": 1,
            "participacao": 1.0,
            "participacao_acumulada": 1.0,
        }
    ],
    "ponto_dia": [{"status": "NORMAL", "dias": 20, "pessoas": 1, "horas_trabalhadas": 160}],
    "candidatura": [
        {
            "trimestre": 1,
            "candidaturas": 10,
            "triadas": 8,
            "entrevistadas": 5,
            "encaminhadas": 3,
            "aprovadas": 2,
            "admitidas": 1,
            "reprovadas": 6,
            "desistencias": 1,
            "dias_medios_no_funil": 12.5,
        }
    ],
    "escopo_mercado": [
        {
            "id": 1,
            "territorio": "Atibaia",
            "nivel": "municipio",
            "grupo": "78",
            "segmento_da_fictalent": True,
        }
    ],
    "mercado_mes": [{"mes_id": 202401, "admissoes": 10, "desligamentos": 8, "saldo": 2}],
    "filial": [
        {
            "id": 1,
            "codigo": "F1",
            "nome": "Matriz",
            "tipo": "MATRIZ",
            "municipio": "Atibaia",
            "uf": "SP",
            "ativo": True,
        }
    ],
}


class LeitorFalso:
    def __init__(self, vivo: bool = True) -> None:
        self.vivo = vivo
        self.chamadas: list[tuple[str, str, dict[str, Any]]] = []  # papel, SQL, parâmetros

    def papel_do_token(self, token: str) -> str | None:
        return TOKENS.get(token)

    def consultar_como(
        self, papel: str, consulta: sql.Composed, parametros: dict[str, Any]
    ) -> list[dict[str, Any]]:
        texto = consulta.as_string()  # os identificadores já citados: "fato"."resultado_mes"
        self.chamadas.append((papel, texto, parametros))
        if papel == "ana" and "resultado_mes" in texto:
            raise AcessoNegado("permission denied for table resultado_mes")
        for tabela, linhas in LINHAS.items():
            if f'"{tabela}"' in texto:
                return linhas
        raise AssertionError(f"consulta sem linhas prontas: {texto[:60]}")

    def saudavel(self) -> bool:
        return self.vivo


@pytest.fixture
def leitor() -> LeitorFalso:
    return LeitorFalso()


@pytest.fixture
def cliente(leitor: LeitorFalso) -> TestClient:
    return TestClient(modulo_app.criar_app(leitor))


def _como(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_sem_token_ou_com_token_desconhecido_e_401(
    cliente: TestClient, leitor: LeitorFalso
) -> None:
    assert cliente.get("/v1/filiais").status_code == 401
    resposta = cliente.get("/v1/filiais", headers=_como("x" * 40))
    assert resposta.status_code == 401 and "desconhecido" in resposta.json()["detalhe"]
    assert leitor.chamadas == []  # sem token válido, o banco nem é consultado


def test_a_consulta_roda_como_o_papel_do_token(cliente: TestClient, leitor: LeitorFalso) -> None:
    token_da_ana = next(t for t, p in TOKENS.items() if p == "ana")
    resposta = cliente.get("/v1/postos/42/ponto?mes=202409", headers=_como(token_da_ana))
    assert resposta.status_code == 200
    assert resposta.json() == [
        {"status": "NORMAL", "dias": 20, "pessoas": 1, "horas_trabalhadas": 160.0}
    ]
    papel, consulta, parametros = leitor.chamadas[-1]
    assert papel == "ana" and parametros == {"posto": 42, "mes": 202409}
    assert consulta == consultas.ponto_do_posto(consultas.Esquemas()).as_string()
    assert '"fato"."ponto_dia"' in consulta  # o schema vem citado pelo driver


def test_o_que_o_banco_recusa_vira_403(cliente: TestClient) -> None:
    token_da_ana = next(t for t, p in TOKENS.items() if p == "ana")
    resposta = cliente.get("/v1/filiais/1/resultado", headers=_como(token_da_ana))
    assert resposta.status_code == 403 and "ana" in resposta.json()["detalhe"]
    token_do_socio = next(t for t, p in TOKENS.items() if p == "socio_paulo")
    resposta = cliente.get(
        "/v1/filiais/1/resultado?de=202501&ate=202512", headers=_como(token_do_socio)
    )
    assert resposta.status_code == 200 and resposta.json()[0]["resultado"] == 250.5


def test_todo_ponto_do_contrato_responde_e_valida_os_parametros(cliente: TestClient) -> None:
    token = next(iter(TOKENS))
    for caminho in (
        "/v1/filiais",
        "/v1/clientes?ano=2024",
        "/v1/funil?ano=2024",
        "/v1/mercado/escopos",
        "/v1/mercado?escopo=1",
    ):
        assert cliente.get(caminho, headers=_como(token)).status_code == 200, caminho
    assert cliente.get("/v1/clientes", headers=_como(token)).status_code == 422  # ano é obrigatório
    assert cliente.get("/v1/clientes?ano=1999", headers=_como(token)).status_code == 422
    assert cliente.get("/v1/postos/1/ponto?mes=20240", headers=_como(token)).status_code == 422


def test_saude_nao_pede_token_e_diz_se_o_warehouse_responde() -> None:
    assert TestClient(modulo_app.criar_app(LeitorFalso())).get("/saude").json() == {
        "situacao": "ok",
        "warehouse": True,
        "versao": "v1",
    }
    assert (
        TestClient(modulo_app.criar_app(LeitorFalso(vivo=False))).get("/saude").json()["situacao"]
        == "degradada"
    )


def test_a_openapi_sai_do_codigo_com_o_contrato_inteiro(cliente: TestClient) -> None:
    esquema = cliente.get("/v1/openapi.json").json()
    assert set(esquema["paths"]) == {
        "/saude",
        "/v1/filiais",
        "/v1/filiais/{filial_id}/resultado",
        "/v1/clientes",
        "/v1/postos/{posto_id}/ponto",
        "/v1/funil",
        "/v1/mercado/escopos",
        "/v1/mercado",
    }
    assert "não usar em produção" in esquema["info"]["description"]
    campo = esquema["components"]["schemas"]["ResultadoDoMes"]["properties"]["mes_parcial"]
    assert "horizonte" in campo["description"]


# ------------------------------------------------------------------ o acesso


def test_o_token_vira_hash_e_o_sql_de_preparo_nao_da_a_tabela_a_api() -> None:
    assert acesso.hash_do_token("abc") == acesso.hash_do_token("abc") != acesso.hash_do_token("abd")
    assert len(acesso.hash_do_token("abc")) == 64
    sql = acesso.sql_de_preparo()
    assert "CREATE TABLE IF NOT EXISTS acesso.token" in sql and "SECURITY DEFINER" in sql
    assert "GRANT EXECUTE ON FUNCTION acesso.papel_do_token(text) TO api;" in sql
    assert "GRANT SELECT" not in sql and "TO PUBLIC" not in sql
    assert "valido_ate IS NULL OR valido_ate >= current_date" in sql


def test_o_sql_do_consumidor_poe_o_papel_no_perfil_e_a_api_como_membro() -> None:
    sql = acesso.sql_do_consumidor("ana", "coordenacao", (3,))
    assert "CREATE ROLE ana NOLOGIN" in sql and "GRANT perfil_coordenacao TO ana;" in sql
    assert "GRANT ana TO api;" in sql
    assert "DELETE FROM acesso.filial_do_papel WHERE papel = 'ana';" in sql
    assert "INSERT INTO acesso.filial_do_papel (papel, filial_id) VALUES ('ana', 3);" in sql
    assert "REVOKE perfil_socio FROM ana;" in sql  # mudar de perfil tira o anterior
    with pytest.raises(ValueError, match="de filial"):
        acesso.sql_do_consumidor("ana", "coordenacao")
    with pytest.raises(ValueError, match="empresa inteira"):
        acesso.sql_do_consumidor("paulo", "socio", (1,))
    with pytest.raises(ValueError, match="papel inválido"):
        acesso.sql_do_consumidor("Ana; DROP", "socio")
    with pytest.raises(StopIteration):
        acesso.sql_do_consumidor("ana", "diretoria")
