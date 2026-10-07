"""A aplicação FastAPI: `/saude` sem token e o contrato `/v1` com o token do consumidor.

Toda rota de `/v1` passa por `consumidor`: lê `Authorization: Bearer <token>`, pergunta ao
warehouse de quem é o hash e entrega o papel; sem token ou com token desconhecido, 401. A
consulta roda como esse papel (`Leitor.consultar_como`), e o que o banco recusar vira 403. O
que o RLS esconde não vem, e a resposta é uma lista menor, não um erro: é assim que a
coordenação de uma filial vê só a filial dela sem a API saber disso.
"""

# ruff: noqa: E501
# sem `from __future__ import annotations`: o FastAPI resolve as anotações em tempo de execução,
# e `Papel` é um nome local de `criar_app`
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import sql

from rh_fictalent.api import consultas, modelos
from rh_fictalent.api.servico import AcessoNegado, Leitor, LeitorDoWarehouse

VERSAO = "v1"
TITULO = "Fictalent · API dos indicadores"
_bearer = HTTPBearer(
    auto_error=False, description="o token do consumidor, cadastrado pelo administrador"
)


def criar_app(
    leitor: LeitorDoWarehouse | None = None, esquemas: consultas.Esquemas | None = None
) -> FastAPI:
    """A aplicação; o leitor vem do ambiente quando não é dado (os testes dão o deles)."""
    e = esquemas or consultas.Esquemas()
    app = FastAPI(
        title=TITULO,
        version="0.8.0",
        description=(
            "Os indicadores da gold da Fictalent, servidos do warehouse. Quem lê o quê é decisão do "
            "banco (perfil de negócio e filial do consumidor), não desta API: a mesma pergunta devolve "
            "para cada consumidor só o que ele pode ver. Dado 100 % sintético; não usar em produção."
        ),
        docs_url=f"/{VERSAO}/docs",
        openapi_url=f"/{VERSAO}/openapi.json",
        redoc_url=None,
    )
    app.state.leitor = leitor

    def leitor_atual() -> LeitorDoWarehouse:
        if app.state.leitor is None:
            app.state.leitor = _leitor_do_ambiente()
        return app.state.leitor  # type: ignore[no-any-return]

    def consumidor(
        credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    ) -> str:
        if credenciais is None or not credenciais.credentials:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "token ausente: envie Authorization: Bearer <token>"
            )
        papel = leitor_atual().papel_do_token(credenciais.credentials)
        if papel is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token desconhecido ou vencido")
        return papel

    Papel = Annotated[str, Depends(consumidor)]

    def como(papel: str, consulta: sql.Composed, **parametros: Any) -> list[dict[str, Any]]:
        try:
            return leitor_atual().consultar_como(papel, consulta, parametros)
        except AcessoNegado as erro:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"o perfil de {papel} não lê isto: {erro}"
            ) from erro

    respostas: dict[int | str, dict[str, Any]] = {
        401: {"model": modelos.Erro, "description": "sem token, ou token desconhecido ou vencido"},
        403: {"model": modelos.Erro, "description": "o perfil do consumidor não lê esta tabela"},
    }

    @app.get(
        "/saude",
        response_model=modelos.Saude,
        tags=["saúde"],
        summary="O serviço está vivo e alcança o warehouse?",
    )
    def saude() -> Any:
        vivo = leitor_atual().saudavel()
        return modelos.Saude(situacao="ok" if vivo else "degradada", warehouse=vivo, versao=VERSAO)

    @app.get(
        f"/{VERSAO}/filiais",
        response_model=list[modelos.Filial],
        responses=respostas,
        tags=["filiais"],
    )
    def filiais(papel: Papel) -> Any:
        return como(papel, consultas.filiais(e))

    @app.get(
        f"/{VERSAO}/filiais/{{filial_id}}/resultado",
        response_model=list[modelos.ResultadoDoMes],
        responses=respostas,
        tags=["filiais"],
        summary="O resultado de uma filial, mês a mês",
    )
    def resultado_da_filial(
        papel: Papel,
        filial_id: int,
        de: Annotated[int, Query(description="o primeiro mês, AAAAMM", ge=201801)] = 201801,
        ate: Annotated[int, Query(description="o último mês, AAAAMM", le=209912)] = 209912,
    ) -> Any:
        return como(papel, consultas.resultado_da_filial(e), filial=filial_id, de=de, ate=ate)

    @app.get(
        f"/{VERSAO}/clientes",
        response_model=list[modelos.ClienteDoAno],
        responses=respostas,
        tags=["clientes"],
        summary="O Pareto dos clientes de um ano: receita, margem, posição e participação acumulada",
    )
    def clientes(papel: Papel, ano: Annotated[int, Query(ge=2018, le=2099)]) -> Any:
        return como(papel, consultas.clientes_do_ano(e), ano=ano)

    @app.get(
        f"/{VERSAO}/postos/{{posto_id}}/ponto",
        response_model=list[modelos.PontoDoPosto],
        responses=respostas,
        tags=["postos"],
        summary="O ponto de um posto num mês, por situação do dia",
    )
    def ponto_do_posto(
        papel: Papel,
        posto_id: int,
        mes: Annotated[int, Query(description="AAAAMM", ge=201801, le=209912)],
    ) -> Any:
        return como(papel, consultas.ponto_do_posto(e), posto=posto_id, mes=mes)

    @app.get(
        f"/{VERSAO}/funil",
        response_model=list[modelos.FunilDoTrimestre],
        responses=respostas,
        tags=["funil"],
        summary="O funil de um ano, trimestre a trimestre",
    )
    def funil(papel: Papel, ano: Annotated[int, Query(ge=2018, le=2099)]) -> Any:
        return como(papel, consultas.funil_do_ano(e), ano=ano)

    @app.get(
        f"/{VERSAO}/mercado/escopos",
        response_model=list[modelos.Escopo],
        responses=respostas,
        tags=["mercado"],
    )
    def escopos(papel: Papel) -> Any:
        return como(papel, consultas.escopos(e))

    @app.get(
        f"/{VERSAO}/mercado",
        response_model=list[modelos.MercadoDoMes],
        responses=respostas,
        tags=["mercado"],
        summary="O mercado formal de um escopo do CAGED, mês a mês",
    )
    def mercado(
        papel: Papel, escopo: Annotated[int, Query(description="o id em /v1/mercado/escopos", ge=1)]
    ) -> Any:
        return como(papel, consultas.mercado_do_escopo(e), escopo=escopo)

    @app.exception_handler(HTTPException)
    async def _erro(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detalhe": exc.detail}, headers=exc.headers
        )

    return app


@lru_cache(maxsize=1)
def _leitor_do_ambiente() -> Leitor:
    return Leitor.do_ambiente()


app = criar_app()  # o que o uvicorn sobe: rh_fictalent.api.app:app
