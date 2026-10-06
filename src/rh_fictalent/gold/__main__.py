"""A gold pela linha de comando, fora do Dagster (lê o `.env`).

    python -m rh_fictalent.gold --matriz                  # gera docs/15_matriz_de_barramento.md
    python -m rh_fictalent.gold --publicar                # todas as tabelas, dimensões primeiro
    python -m rh_fictalent.gold --publicar dim_posto fato_posto_mes

No dia a dia quem publica é o job `construir_gold` do Dagster; este caminho existe para a
prova e para o estudo.
"""

from __future__ import annotations

import argparse
import sys
import time

from dotenv import load_dotenv

from rh_fictalent.gold import barramento, construcao, modelo
from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.recursos import lake_do_ambiente


def _matriz() -> int:
    destino = barramento.gerar()
    print(
        f"matriz gerada em {destino.name}: {len(barramento.FATOS)} fatos, "
        f"{len(barramento.DIMENSOES)} dimensões"
    )
    return 0


def _publicar(nomes: list[str]) -> int:
    desconhecidas = set(nomes) - {t.nome for t in modelo.TABELAS}
    if desconhecidas:
        print(f"tabela que o modelo não tem: {sorted(desconhecidas)}")
        return 2
    lake = lake_do_ambiente()
    con = consulta.abrir_silver(lake)
    reprovadas = 0
    try:
        print(f"horizonte: {modelo.preparar(con)}")
        for tabela in modelo.TABELAS:  # a ordem do modelo: dimensões antes dos fatos
            if nomes and tabela.nome not in nomes:
                continue
            inicio = time.monotonic()
            resultado = construcao.publicar(con, lake, tabela)
            sinal = "ok " if resultado.aprovada else "NÃO"
            tempo = time.monotonic() - inicio
            print(f"{sinal} {tabela.nome:<22} {resultado.linhas:>8} linhas  {tempo:5.1f} s")
            for o_que, valor in resultado.conservado.items():
                print(f"      conservado: {o_que} = {valor}")
            for problema in resultado.problemas:
                print(f"      {problema}")
            reprovadas += not resultado.aprovada
    finally:
        con.close()
    return 1 if reprovadas else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.gold")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--matriz", action="store_true", help="gera o docs/15")
    grupo.add_argument("--publicar", nargs="*", metavar="tabela", help="monta, confere e publica")
    args = parser.parse_args(argv)
    if args.matriz:
        return _matriz()
    return _publicar(args.publicar)


if __name__ == "__main__":
    sys.exit(main())
