"""A gold pela linha de comando, fora do Dagster (lê o `.env`).

    python -m rh_fictalent.gold --matriz                  # gera docs/15_matriz_de_barramento.md
    python -m rh_fictalent.gold --publicar                # todas as tabelas, dimensões primeiro
    python -m rh_fictalent.gold --publicar dim_posto fato_posto_mes
    python -m rh_fictalent.gold --analitico                   # lista as consultas analíticas
    python -m rh_fictalent.gold --analitico pareto_de_clientes  # roda uma sobre a gold publicada
    python -m rh_fictalent.gold --notebook                    # executa e verifica notebooks/gold

No dia a dia quem publica é o job `construir_gold` do Dagster; este caminho existe para a
prova e para o estudo.
"""

from __future__ import annotations

import argparse
import sys
import time

from dotenv import load_dotenv

from rh_fictalent.auditoria import cadernos
from rh_fictalent.gold import analitico, barramento, construcao, modelo
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


def _analitico(nomes: list[str]) -> int:
    if not nomes:
        for c in analitico.CONSULTAS:
            print(f"{c.nome:<32} {c.origem}")
            print(f"{'':<32} {c.pergunta}")
        return 0
    con = consulta.abrir_gold(lake_do_ambiente())
    try:
        for nome in nomes:
            c = analitico.consulta(nome)
            print(f"== {c.nome}: {c.pergunta}")
            for janela in c.janelas:
                print(f"   janela: {janela}")
            print(analitico.executar(con, nome).to_string())
    finally:
        con.close()
    return 0


NOTEBOOKS = cadernos.PASTA.parent / "gold"


def _notebook() -> int:
    """Executa os notebooks da gold de cima a baixo e confere o padrão (o mesmo da auditoria)."""
    reprovados = 0
    for caminho in cadernos.listar(NOTEBOOKS):
        inicio = time.monotonic()
        cadernos.executar(caminho)
        problemas = cadernos.verificar(caminho)
        sinal = "ok " if not problemas else "NÃO"
        print(f"{sinal} {caminho.name:<28} {time.monotonic() - inicio:5.1f} s")
        for problema in problemas:
            print(f"      {problema}")
        reprovados += bool(problemas)
    return 1 if reprovados else 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.gold")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--matriz", action="store_true", help="gera o docs/15")
    grupo.add_argument("--publicar", nargs="*", metavar="tabela", help="monta, confere e publica")
    grupo.add_argument(
        "--analitico", nargs="*", metavar="consulta", help="o SQL analítico sobre a gold"
    )
    grupo.add_argument("--notebook", action="store_true", help="executa e verifica notebooks/gold")
    args = parser.parse_args(argv)
    if args.matriz:
        return _matriz()
    if args.analitico is not None:
        return _analitico(args.analitico)
    if args.notebook:
        return _notebook()
    return _publicar(args.publicar)


if __name__ == "__main__":
    sys.exit(main())
