"""`python -m rh_fictalent.auditoria --executar [nomes]` roda os notebooks de cima a baixo e
os regrava com as saídas; `--verificar` confere todos contra o padrão e sai com erro se
algum reprovar; `--catalogo` gera `docs/13_catalogo_de_achados.md` das entradas do catálogo e
dos registros gravados. Sem nomes, `--executar` roda todos, na ordem da numeração."""

from __future__ import annotations

import argparse
import sys

from rh_fictalent.auditoria import cadernos, catalogo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rh_fictalent.auditoria")
    parser.add_argument("--executar", nargs="*", metavar="NOME", help="executa os notebooks")
    parser.add_argument("--verificar", action="store_true", help="confere o padrão")
    parser.add_argument("--catalogo", action="store_true", help="gera o docs/13")
    args = parser.parse_args(argv)
    if args.executar is None and not args.verificar and not args.catalogo:
        parser.print_help()
        return 2
    codigo = 0
    if args.executar is not None:
        escolhidos = [
            c
            for c in cadernos.listar()
            if not args.executar or any(n in c.name for n in args.executar)
        ]
        for caminho in escolhidos:
            print(f"executando {caminho.name} ...", flush=True)
            cadernos.executar(caminho)
            print("  gravado com as saídas")
    if args.verificar:
        for caminho in cadernos.listar():
            problemas = cadernos.verificar(caminho)
            print(
                f"{caminho.name}: {'ok' if not problemas else str(len(problemas)) + ' problema(s)'}"
            )
            for p in problemas:
                print(f"  - {p}")
                codigo = 1
    if args.catalogo:
        destino = catalogo.gerar()
        print(f"catálogo gerado em {destino.name}: {len(catalogo.ENTRADAS)} entradas")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
