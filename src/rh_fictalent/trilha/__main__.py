# ruff: noqa: E501
"""Linha de comando da trilha de auditoria.

    python -m rh_fictalent.trilha --lista                                  # as consultas, com a pergunta de cada uma
    python -m rh_fictalent.trilha --consulta acoes_sem_permissao           # uma resposta, em tabela
    python -m rh_fictalent.trilha --consulta execucoes_por_job --dias 30   # os últimos 30 dias
    python -m rh_fictalent.trilha --relatorio dados/auditoria/trilha       # todas, em CSV, com um relatorio.md

`--desde` e `--ate` recebem datas (AAAA-MM-DD); `--dias N` é o atalho para "os últimos N dias".
As do lake abrem a bronze e a silver pelo DuckDB; as do warehouse entram como o administrador.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from rh_fictalent.lake import consulta as lake_consulta
from rh_fictalent.orquestracao.recursos import lake_do_ambiente, warehouse_do_ambiente
from rh_fictalent.trilha import consultas


def _janela(args: argparse.Namespace) -> tuple[date, date]:
    ate = args.ate or date.today()
    desde = args.desde or (ate - timedelta(days=args.dias) if args.dias else consultas.INICIO)
    return desde, ate


def _responder(nome: str, desde: date, ate: date) -> pd.DataFrame:
    c = consultas.consulta(nome)
    if c.fonte == "lake":
        lake = lake_do_ambiente()
        con = lake_consulta.abrir(lake)  # a bronze, com a trilha de exclusões
        try:
            caminhos = {  # e a silver, só linhas vivas, como abrir_silver a monta
                tabela: lake.caminho(
                    lake_consulta.CAMADA_SILVER, *tabela.split("."), "ano=*.parquet"
                )
                for tabela in lake_consulta.tabelas_da_silver()
            }
            lake_consulta.criar_views_da_silver(con, caminhos)
            return consultas.no_lake(con, nome, desde, ate)
        finally:
            con.close()
    return consultas.no_warehouse(warehouse_do_ambiente(), nome, desde, ate)


def _relatorio(pasta: Path, desde: date, ate: date) -> int:
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = [
        "# Trilha de auditoria",
        "",
        f"Gerado em {datetime.now(UTC).isoformat(timespec='seconds')}, janela de {desde} a {ate}. "
        "Nenhum dado pessoal: o usuário é a chave do login; o token nunca aparece.",
        "",
        "| consulta | pergunta | fonte | linhas | arquivo |",
        "|---|---|---|---:|---|",
    ]
    for c in consultas.CONSULTAS:
        tabela = _responder(c.nome, desde, ate)
        arquivo = pasta / f"{c.nome}.csv"
        tabela.to_csv(arquivo, index=False)
        linhas.append(
            f"| `{c.nome}` | {c.pergunta} | {c.fonte} | {len(tabela)} | `{arquivo.name}` |"
        )
        print(f"{c.nome:32} {len(tabela):>7} linhas -> {arquivo}")
    (pasta / "relatorio.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"relatório em {pasta / 'relatorio.md'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.trilha")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--lista", action="store_true", help="as consultas e as perguntas")
    grupo.add_argument("--consulta", metavar="nome", help="responde uma consulta em tabela")
    grupo.add_argument(
        "--relatorio", metavar="pasta", type=Path, help="todas, em CSV, com relatorio.md"
    )
    parser.add_argument("--desde", type=date.fromisoformat, default=None)
    parser.add_argument("--ate", type=date.fromisoformat, default=None)
    parser.add_argument("--dias", type=int, default=None, help="os últimos N dias")
    args = parser.parse_args(argv)

    if args.lista:
        for c in consultas.CONSULTAS:
            print(f"{c.nome:32} [{c.fonte:9}] {c.pergunta}")
        return 0
    desde, ate = _janela(args)
    if args.relatorio:
        return _relatorio(args.relatorio, desde, ate)
    if args.consulta not in {c.nome for c in consultas.CONSULTAS}:
        print(f"consulta desconhecida: {args.consulta} (veja --lista)", file=sys.stderr)
        return 2
    tabela = _responder(args.consulta, desde, ate)
    with pd.option_context(
        "display.max_rows", 200, "display.max_columns", 30, "display.width", 200
    ):
        print(tabela.to_string(index=False) if len(tabela) else "(sem linhas na janela)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
