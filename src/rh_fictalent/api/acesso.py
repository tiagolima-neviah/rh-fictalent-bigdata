# ruff: noqa: E501
"""Quem consome a API: o usuário `api`, os papéis dos consumidores e os tokens.

O usuário `api` não lê tabela nenhuma: ele só pode conectar, perguntar de quem é um token e
assumir (`SET ROLE`) o papel do consumidor, porque é membro dele. O consumidor é um papel sem
login do Postgres dentro de um perfil de negócio (`perfil_coordenacao`, ...), com as filiais
dele em `acesso.filial_do_papel` quando o perfil é de filial (`gold.rls`). O token é guardado
só como hash SHA-256: o token tem 32 bytes aleatórios, então o hash puro basta e não precisa
de sal nem de função lenta (a entropia está no token, não numa senha escolhida).

Todo SQL daqui é gerado e idempotente; quem o aplica é o administrador, pela linha de comando
(`python -m rh_fictalent.api`). O serviço nunca tem a senha do administrador.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import TYPE_CHECKING

from psycopg import sql

from rh_fictalent.gold import dcl, rls

if TYPE_CHECKING:
    from rh_fictalent.orquestracao.recursos import Warehouse

ESQUEMA = rls.ESQUEMA_ACESSO
TABELA = "token"
FUNCAO = "papel_do_token"
USUARIO = "api"
PAPEL_VALIDO = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


def hash_do_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _papel(papel: str) -> str:
    if not PAPEL_VALIDO.match(papel):
        raise ValueError(
            f"papel inválido: {papel!r} (minúsculas, dígitos e _, começando por letra)"
        )
    return papel


def sql_de_preparo(usuario: str = USUARIO, esquema: str = ESQUEMA) -> str:
    """A tabela de tokens, a função que a lê e o que o usuário `api` pode; sem a senha."""
    tabela, funcao = f"{esquema}.{TABELA}", f"{esquema}.{FUNCAO}"
    return (
        "\n".join(
            [
                "-- acesso da API: GERADO por rh_fictalent.api.acesso; repetir não muda nada.",
                f"CREATE SCHEMA IF NOT EXISTS {esquema};",
                f"REVOKE ALL ON SCHEMA {esquema} FROM PUBLIC;",
                f"CREATE TABLE IF NOT EXISTS {tabela} (hash char(64) PRIMARY KEY, papel text NOT NULL, descricao text NOT NULL DEFAULT '', criado_em timestamptz NOT NULL DEFAULT now(), valido_ate date);",
                f"COMMENT ON TABLE {tabela} IS 'Os tokens da API, só como hash SHA-256, e o papel de cada um; só o administrador lê e escreve.';",
                f"REVOKE ALL ON {tabela} FROM PUBLIC;",
                # SECURITY DEFINER: a API pergunta de quem é o hash sem poder ler a tabela
                f"CREATE OR REPLACE FUNCTION {funcao}(h text) RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp",
                f"  AS $$ SELECT papel FROM {tabela} WHERE hash = $1 AND (valido_ate IS NULL OR valido_ate >= current_date) $$;",  # noqa: S608 # nosec B608
                f"REVOKE ALL ON FUNCTION {funcao}(text) FROM PUBLIC;",
                f"GRANT USAGE ON SCHEMA {esquema} TO {usuario};",
                f"GRANT EXECUTE ON FUNCTION {funcao}(text) TO {usuario};",
            ]
        )
        + "\n"
    )


def preparar(dw: Warehouse, senha: str, usuario: str = USUARIO, esquema: str = ESQUEMA) -> None:
    """Cria (ou atualiza a senha de) o usuário `api` e aplica o SQL de preparo; idempotente."""
    _papel(usuario)
    with dw.conectar() as con, con.cursor() as cur:
        cur.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{usuario}') THEN "  # noqa: S608 # nosec B608
            f"CREATE ROLE {usuario} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$;"
        )
        # a senha entra como literal citado pelo driver (DDL não aceita parâmetro)
        cur.execute(
            sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(usuario), sql.Literal(senha))
        )
        cur.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(dw.banco), sql.Identifier(usuario)
            )
        )
        cur.execute(sql_de_preparo(usuario, esquema))
        con.commit()


def sql_do_consumidor(
    papel: str,
    perfil: str,
    filiais: tuple[int, ...] = (),
    usuario: str = USUARIO,
    esquema: str = ESQUEMA,
) -> str:
    """Um consumidor: o papel sem login no perfil, as filiais dele, e o `api` como membro."""
    _papel(papel)
    p = dcl.perfil(perfil)  # StopIteration se o perfil não existe
    if p.alcance == dcl.FILIAL and not filiais:
        raise ValueError(f"o perfil {perfil} é de filial: informe ao menos uma filial")
    if p.alcance == dcl.EMPRESA and filiais:
        raise ValueError(f"o perfil {perfil} é da empresa inteira: não leva filial")
    acesso = f"{esquema}.{rls.TABELA_DE_ACESSO}"
    modelo_de_insercao = f"INSERT INTO {acesso} (papel, {rls.COLUNA}) VALUES ('{papel}', %d);"  # noqa: S608 # nosec B608
    insercoes = [modelo_de_insercao % int(f) for f in filiais]
    linhas = [
        f"-- consumidor {papel} no perfil {p.papel}; GERADO por rh_fictalent.api.acesso.",
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{papel}') THEN CREATE ROLE {papel} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE; END IF; END $$;",  # noqa: S608 # nosec B608
        *(f"REVOKE {q.papel} FROM {papel};" for q in dcl.PERFIS if q.papel != p.papel),
        f"GRANT {p.papel} TO {papel};",
        f"GRANT {papel} TO {usuario};",  # a API pode assumir o papel
        f"DELETE FROM {acesso} WHERE papel = '{papel}';",  # noqa: S608 # nosec B608
        *insercoes,
    ]
    return "\n".join(linhas) + "\n"


def cadastrar_consumidor(
    dw: Warehouse, papel: str, perfil: str, filiais: tuple[int, ...] = ()
) -> int:
    texto = sql_do_consumidor(papel, perfil, filiais)
    with dw.conectar() as con, con.cursor() as cur:
        cur.execute(texto)
        con.commit()
    return sum(1 for linha in texto.splitlines() if linha and not linha.startswith("--"))


def cadastrar_token(
    dw: Warehouse,
    papel: str,
    token: str,
    valido_ate: date | None = None,
    descricao: str = "",
    esquema: str = ESQUEMA,
) -> str:
    """Guarda o hash do token para o papel; devolve o começo do hash, para referência."""
    _papel(papel)
    if len(token) < 32:
        raise ValueError("token curto demais: gere com openssl rand -hex 32")
    h = hash_do_token(token)
    tabela = sql.Identifier(esquema, TABELA)
    with dw.conectar() as con, con.cursor() as cur:
        cur.execute(
            sql.SQL(
                "INSERT INTO {} (hash, papel, descricao, valido_ate) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (hash) DO UPDATE SET papel = EXCLUDED.papel, descricao = EXCLUDED.descricao, valido_ate = EXCLUDED.valido_ate"
            ).format(tabela),
            (h, papel, descricao, valido_ate),
        )
        con.commit()
    return h[:8]


def revogar_tokens(dw: Warehouse, papel: str, esquema: str = ESQUEMA) -> int:
    """Apaga todos os tokens do papel; devolve quantos eram."""
    _papel(papel)
    with dw.conectar() as con, con.cursor() as cur:
        cur.execute(
            sql.SQL("DELETE FROM {} WHERE papel = %s").format(sql.Identifier(esquema, TABELA)),
            (papel,),
        )
        quantos = cur.rowcount
        con.commit()
    return quantos
