"""A leitura do warehouse como um consumidor: o papel do token e o `SET LOCAL ROLE` por pedido.

O `Leitor` é a única porta da API para o banco. Ele conecta como o usuário `api`, pergunta de
quem é o token (pela função `SECURITY DEFINER`, nunca lendo a tabela) e roda cada consulta
dentro de uma transação que começa com `SET LOCAL ROLE <papel>`: o Postgres aplica o DCL e o
RLS do consumidor, e no fim da transação o papel volta a ser o `api`. O que o banco recusar
(tabela que o perfil não lê, papel que a API não pode assumir) vira `AcessoNegado`, que a
API traduz em 403; a linha que o RLS esconde simplesmente não vem.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from rh_fictalent.api import acesso


class AcessoNegado(Exception):
    """O banco recusou: o papel não lê a tabela, ou a API não pode assumir o papel."""


class LeitorDoWarehouse(Protocol):
    def papel_do_token(self, token: str) -> str | None: ...
    def consultar_como(
        self, papel: str, consulta: sql.Composed, parametros: dict[str, Any]
    ) -> list[dict[str, Any]]: ...
    def saudavel(self) -> bool: ...
    def registrar_pedido(self, papel: str | None, caminho: str, codigo: int) -> None: ...


class Leitor:
    """O warehouse visto pelo usuário `api`."""

    def __init__(
        self,
        host: str,
        porta: int,
        banco: str,
        usuario: str,
        senha: str,
        esquema_acesso: str = acesso.ESQUEMA,
    ) -> None:
        self.host, self.porta, self.banco = host, porta, banco
        self.usuario, self.senha = usuario, senha
        self.esquema_acesso = esquema_acesso

    @classmethod
    def do_ambiente(cls) -> Leitor:
        return cls(
            host=os.environ.get("DW_HOST", "127.0.0.1"),
            porta=int(os.environ.get("DW_PORT", "5441")),
            banco=os.environ.get("DW_DB", "dw_fictalent"),
            usuario=os.environ.get("API_DB_USER", acesso.USUARIO),
            senha=os.environ["API_DB_PASSWORD"],
        )

    def conectar(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            host=self.host,
            port=self.porta,
            dbname=self.banco,
            user=self.usuario,
            password=self.senha,
            connect_timeout=5,
        )

    def papel_do_token(self, token: str) -> str | None:
        funcao = sql.Identifier(self.esquema_acesso, acesso.FUNCAO)
        with self.conectar() as con, con.cursor() as cur:
            cur.execute(sql.SQL("SELECT {}(%s)").format(funcao), (acesso.hash_do_token(token),))
            linha = cur.fetchone()
        return str(linha[0]) if linha and linha[0] else None

    def consultar_como(
        self, papel: str, consulta: sql.Composed, parametros: dict[str, Any]
    ) -> list[dict[str, Any]]:
        try:
            with self.conectar() as con, con.transaction(), con.cursor(row_factory=dict_row) as cur:
                cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(papel)))
                cur.execute(consulta, parametros)
                return [dict(linha) for linha in cur.fetchall()]
        except psycopg.errors.InsufficientPrivilege as erro:
            raise AcessoNegado(str(erro).splitlines()[0]) from erro

    def saudavel(self) -> bool:
        try:
            with self.conectar() as con, con.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() is not None
        except psycopg.Error:
            return False

    def registrar_pedido(self, papel: str | None, caminho: str, codigo: int) -> None:
        """A trilha: quem pediu o quê, com que resposta. Falha na trilha não derruba o pedido."""
        funcao = sql.Identifier(self.esquema_acesso, acesso.REGISTRO)
        try:
            with self.conectar() as con, con.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT {}(%s, %s, %s)").format(funcao), (papel, caminho, codigo)
                )
                con.commit()
        except (
            psycopg.Error
        ) as erro:  # pragma: no cover - só com o banco fora do ar no meio do pedido
            logging.getLogger(__name__).warning("trilha da API sem registro: %s", erro)
