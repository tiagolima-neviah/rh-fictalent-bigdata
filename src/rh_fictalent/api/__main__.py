# ruff: noqa: E501
"""Linha de comando da API: o preparo (administrador), os consumidores, os tokens e o serviço.

    python -m rh_fictalent.api --preparar                       # o usuário api, a tabela de tokens, a função
    python -m rh_fictalent.api --consumidor ana --perfil coordenacao --filial 3
    python -m rh_fictalent.api --token ana [--valido-ate 2027-12-31] [--descricao "painel"]
    python -m rh_fictalent.api --revogar ana                    # apaga os tokens do papel
    python -m rh_fictalent.api --sql-consumidor ana --perfil socio   # só imprime o SQL
    python -m rh_fictalent.api --servir [--porta 8000]          # o serviço, como o Compose o sobe

O token nunca passa pela linha de comando nem fica no histórico do terminal: `--token` o pede
escondido (como uma senha) e guarda só o hash. O preparo e os cadastros usam o administrador
(`DW_ADMIN_PASSWORD`); o preparo lê a senha do usuário `api` de `API_DB_PASSWORD`. O serviço
só conhece a senha do `api`.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import date

from dotenv import load_dotenv

from rh_fictalent.api import acesso
from rh_fictalent.gold import dcl
from rh_fictalent.orquestracao.recursos import warehouse_do_ambiente


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.api")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--preparar", action="store_true", help="o usuário api e a tabela de tokens (administrador)"
    )
    grupo.add_argument(
        "--consumidor", metavar="papel", help="cadastra um consumidor (papel do Postgres)"
    )
    grupo.add_argument(
        "--sql-consumidor", metavar="papel", help="imprime o SQL do consumidor sem aplicar"
    )
    grupo.add_argument(
        "--token", metavar="papel", help="cadastra um token para o papel (pedido escondido)"
    )
    grupo.add_argument("--revogar", metavar="papel", help="apaga todos os tokens do papel")
    grupo.add_argument("--servir", action="store_true", help="sobe o serviço (uvicorn)")
    parser.add_argument(
        "--perfil", choices=[p.nome for p in dcl.PERFIS], help="o perfil de negócio do consumidor"
    )
    parser.add_argument(
        "--filial",
        type=int,
        action="append",
        default=[],
        help="uma filial do consumidor (repita para mais de uma)",
    )
    parser.add_argument(
        "--valido-ate",
        type=date.fromisoformat,
        default=None,
        help="AAAA-MM-DD; sem isso, não vence",
    )
    parser.add_argument(
        "--descricao", default="", help="para que serve o token (o painel, um teste)"
    )
    parser.add_argument("--porta", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.servir:
        import uvicorn

        host = os.environ.get("API_HOST", "0.0.0.0")  # noqa: S104 # nosec B104: dentro do container; a porta publicada é só em 127.0.0.1
        uvicorn.run("rh_fictalent.api.app:app", host=host, port=args.porta, log_level="info")
        return 0
    if args.sql_consumidor:
        if not args.perfil:
            parser.error("--sql-consumidor pede --perfil")
        print(acesso.sql_do_consumidor(args.sql_consumidor, args.perfil, tuple(args.filial)))
        return 0

    dw = warehouse_do_ambiente()
    if args.preparar:
        senha = os.environ.get("API_DB_PASSWORD") or ""
        if len(senha) < 16:
            print("defina API_DB_PASSWORD no .env (openssl rand -hex 24)", file=sys.stderr)
            return 2
        acesso.preparar(dw, senha)
        print(
            f"preparado: usuário {acesso.USUARIO}, tabela {acesso.ESQUEMA}.{acesso.TABELA}, função {acesso.FUNCAO}"
        )
        return 0
    if args.consumidor:
        if not args.perfil:
            parser.error("--consumidor pede --perfil")
        comandos = acesso.cadastrar_consumidor(dw, args.consumidor, args.perfil, tuple(args.filial))
        print(f"consumidor {args.consumidor} no perfil {args.perfil}: {comandos} comandos")
        return 0
    if args.token:
        token = getpass.getpass("cole o token (não aparece): ")
        prefixo = acesso.cadastrar_token(
            dw, args.token, token.strip(), args.valido_ate, args.descricao
        )
        print(f"token de {args.token} guardado (hash {prefixo}...)")
        return 0
    if args.revogar:
        print(f"{acesso.revogar_tokens(dw, args.revogar)} tokens de {args.revogar} apagados")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
