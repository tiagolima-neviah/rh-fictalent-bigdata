"""A gold pela linha de comando.

python -m rh_fictalent.gold --matriz     # gera docs/15_matriz_de_barramento.md
"""

from __future__ import annotations

import argparse
import sys

from rh_fictalent.gold import barramento


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.gold")
    parser.add_argument("--matriz", action="store_true", required=True, help="gera o docs/15")
    parser.parse_args(argv)
    destino = barramento.gerar()
    print(
        f"matriz gerada em {destino.name}: {len(barramento.FATOS)} fatos, "
        f"{len(barramento.DIMENSOES)} dimensões"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
