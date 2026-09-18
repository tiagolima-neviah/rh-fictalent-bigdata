"""O gerador pela linha de comando, etapa a etapa.

    python -m rh_fictalent.gerador --etapa 1                   # gera e confere, não grava
    python -m rh_fictalent.gerador --etapa 1 --gravar          # grava na réplica (replicador)
    python -m rh_fictalent.gerador --etapa 1 --gravar --zerar  # zera a réplica inteira antes (root)

Gravar recusa tabela que já tem linhas: regenerar é sempre "zera e grava de novo", nunca
remendo. Zerar esvazia a réplica inteira, porque toda etapa depende das anteriores.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from dotenv import load_dotenv

from rh_fictalent.gerador import etapa1_cadastro
from rh_fictalent.gerador.nucleo import SEMENTE, Tabelas, assinatura, replica_do_ambiente

ETAPAS: dict[int, tuple[str, Callable[[], Tabelas]]] = {
    1: ("mundo cadastral", etapa1_cadastro.gerar),
}


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gerador determinístico da base sintética.")
    parser.add_argument("--etapa", type=int, choices=sorted(ETAPAS), required=True)
    parser.add_argument("--gravar", action="store_true", help="grava na réplica como replicador")
    parser.add_argument("--zerar", action="store_true", help="zera a réplica inteira antes (root)")
    args = parser.parse_args(argumentos)
    if args.zerar and not args.gravar:
        parser.error("--zerar só faz sentido com --gravar")

    nome, gerar = ETAPAS[args.etapa]
    tabelas = gerar()
    print(f"etapa {args.etapa} · {nome} · semente {SEMENTE}")
    for tabela, quadro in tabelas.items():
        print(f"  {tabela:<32} {len(quadro):>7} linhas")
    print(f"  assinatura {assinatura(tabelas)[:16]}")

    if args.gravar:
        load_dotenv()
        if args.zerar:
            zeradas = replica_do_ambiente("root").zerar()
            print(f"réplica zerada: {zeradas} tabelas")
        gravadas = replica_do_ambiente("replicador").gravar(tabelas)
        print(f"gravado na réplica: {sum(gravadas.values())} linhas em {len(gravadas)} tabelas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
