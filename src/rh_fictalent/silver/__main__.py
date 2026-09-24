"""A silver pela linha de comando, fora do Dagster: para construir, conferir e prestar contas
com o ambiente de desenvolvimento (lê o `.env`).

    python -m rh_fictalent.silver --prestar-contas
    python -m rh_fictalent.silver --publicar                     # as 76 tabelas
    python -m rh_fictalent.silver --publicar ats.candidato ponto.marcacao

No dia a dia quem publica é o job `construir_silver` do Dagster; este caminho existe para a
prova e para o estudo.
"""

from __future__ import annotations

import argparse
import sys
import time

import duckdb
from dotenv import load_dotenv

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.recursos import lake_do_ambiente, warehouse_do_ambiente
from rh_fictalent.silver import construcao, contas


def _prestar_contas() -> int:
    lake = lake_do_ambiente()
    con = consulta.abrir(lake)
    try:
        resultado = contas.prestar(con)
    finally:
        con.close()
    for c in resultado:
        sinal = "ok " if c.confere else "NÃO"
        numeros = f"auditoria {c.auditoria:>7}  regra {c.regra:>7}"
        print(f"{sinal} {c.codigo:<7} {c.tabela:<34} {numeros}  em {c.referencia}  ({c.situacao})")
    ruins = contas.reprovadas(resultado)
    print(f"\n{len(resultado)} regras conferidas; {len(ruins)} reprovadas")
    return 1 if ruins else 0


def _publicar(tabelas: list[str]) -> int:
    lake = lake_do_ambiente()
    referencia = construcao.referencia_atual(warehouse_do_ambiente())
    print(f"data de referência: {referencia:%d/%m/%Y}")
    reprovadas = 0
    # uma conexão para todas: abrir as views custa uma ida ao lake por tabela
    con = consulta.abrir(lake)
    try:
        for tabela in tabelas or list(construcao.TABELAS):
            inicio = time.monotonic()
            try:
                resultado = construcao.publicar(con, lake, tabela, referencia)
            except duckdb.IOException as erro:
                # a queda de conexão com o lake vista em 24/09: uma nova tentativa, com conexão nova
                print(f"    {tabela}: conexão com o lake caiu ({erro}); tentando de novo")
                con.close()
                con = consulta.abrir(lake)
                resultado = construcao.publicar(con, lake, tabela, referencia)
            marcas = ", ".join(f"{m}={n}" for m, n in resultado.marcas.items())
            sinal = "ok " if resultado.aprovada else "NÃO"
            tempo = time.monotonic() - inicio
            print(f"{sinal} {tabela:<38} {resultado.linhas:>9} linhas  {tempo:5.1f} s  {marcas}")
            for problema in resultado.problemas:
                print(f"      {problema}")
            reprovadas += not resultado.aprovada
    finally:
        con.close()
    return 1 if reprovadas else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.silver")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--prestar-contas", action="store_true", help="cada regra contra o número da auditoria"
    )
    grupo.add_argument(
        "--publicar", nargs="*", metavar="modulo.tabela", help="monta, grava e confere"
    )
    args = parser.parse_args(argv)
    if args.prestar_contas:
        return _prestar_contas()
    return _publicar(args.publicar)


if __name__ == "__main__":
    sys.exit(main())
