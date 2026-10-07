# ruff: noqa: E501
"""Linha de comando do backup.

    python -m rh_fictalent.backup --fazer backups                  # tudo, numa pasta nova backups/<AAAAMMDD-HHMMSS>/
    python -m rh_fictalent.backup --fazer backups --parte replica:seguranca,warehouse,lake:gold
    python -m rh_fictalent.backup --provar backups/20261007-180000  # restaura em alvos descartáveis e compara com o manifesto
    python -m rh_fictalent.backup --restaurar backups/20261007-180000 --sim   # nos alvos reais; destrutivo

As partes: `replica` (ou `replica:<database>`), `keyring`, `warehouse`, `dagster`, `lake` (ou
`lake:<camada>`). As senhas vêm do `.env`; nenhuma passa pela linha de comando. A pasta do
backup contém dado pessoal em claro (o dump lógico da réplica): guarde-a cifrada e fora da
máquina. Sai com 0 quando tudo conferiu; 1 quando alguma parte reprovou.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from rh_fictalent.backup import rotinas


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.backup")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--fazer", metavar="pasta", type=Path, help="faz o backup numa subpasta nova desta pasta"
    )
    grupo.add_argument(
        "--provar", metavar="pasta", type=Path, help="restaura em alvos descartáveis e confere"
    )
    grupo.add_argument(
        "--restaurar", metavar="pasta", type=Path, help="restaura nos alvos reais (pede --sim)"
    )
    parser.add_argument(
        "--parte",
        default=None,
        help="replica[:db],keyring,warehouse,dagster,lake[:camada]; sem isso, tudo",
    )
    parser.add_argument("--sim", action="store_true", help="confirma a restauração de verdade")
    args = parser.parse_args(argv)

    partes = rotinas.Partes.de_texto(args.parte)
    amb = rotinas.Ambiente.do_ambiente()
    if args.fazer:
        pasta = args.fazer / rotinas.nome_da_pasta()
        resultados = rotinas.fazer(amb, pasta, partes)
        print(f"backup em {pasta}")
    elif args.provar:
        resultados = rotinas.provar(amb, args.provar, partes)
    else:
        if not args.sim:
            print(
                "a restauração substitui o que está nos bancos e no lake; repita com --sim",
                file=sys.stderr,
            )
            return 2
        resultados = rotinas.restaurar(amb, args.restaurar, partes)
    print(rotinas.texto(resultados))
    return 0 if all(r.ok for r in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
