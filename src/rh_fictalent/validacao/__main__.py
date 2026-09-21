"""A régua pela linha de comando: confere um arquivo de medidas e imprime o laudo.

    python -m rh_fictalent.validacao --contrato                 # o que a régua espera receber
    python -m rh_fictalent.validacao --medidas medidas.json     # o laudo; sai 0, 1 ou 2
    python -m rh_fictalent.validacao --medidas m.json --familia escala --familia historia

Código de saída: 0 aprovada, 1 reprovada (regenera), 2 incompleta (faltam medidas). O arquivo de
medidas é um JSON {medida: {chave: valor}}; o gerador o escreve ao fim de cada etapa.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rh_fictalent.validacao.bandas import MEDIDAS, checks
from rh_fictalent.validacao.regua import FAMILIAS, Veredito, avaliar

SAIDA = {Veredito.APROVADA: 0, Veredito.REPROVADA: 1, Veredito.INCOMPLETA: 2}


def contrato() -> str:
    """O contrato em texto: cada medida, o que significa e quantos checks a consomem."""
    todos = checks()
    linhas = [f"A régua tem {len(todos)} checks em {len(FAMILIAS)} famílias.", ""]
    for familia, titulo in FAMILIAS.items():
        linhas.append(f"{titulo}: {sum(1 for c in todos if c.familia == familia)} checks")
    linhas += ["", "Medidas que a base precisa entregar (JSON {medida: {chave: valor}}):"]
    for medida, significado in MEDIDAS.items():
        n = sum(1 for c in todos if c.medida == medida)
        linhas.append(f"  {medida:<28} {n:>3} checks  {significado}")
    return "\n".join(linhas)


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Régua de validação do dado sintético.")
    parser.add_argument("--medidas", type=Path, help="JSON {medida: {chave: valor}}")
    parser.add_argument("--familia", action="append", choices=list(FAMILIAS), help="só estas")
    parser.add_argument("--so-problemas", action="store_true", help="esconde os aprovados")
    parser.add_argument("--json", action="store_true", help="laudo em JSON")
    parser.add_argument("--contrato", action="store_true", help="mostra o que a régua espera")
    args = parser.parse_args(argumentos)
    if args.contrato:
        print(contrato())
        return 0
    if args.medidas is None:
        parser.error("informe --medidas ou --contrato")
    medidas = json.loads(args.medidas.read_text(encoding="utf-8"))
    laudo = avaliar(checks(), medidas, args.familia)
    print(laudo.para_json() if args.json else laudo.texto(so_problemas=args.so_problemas))
    return SAIDA[laudo.veredito]


if __name__ == "__main__":
    sys.exit(main())
