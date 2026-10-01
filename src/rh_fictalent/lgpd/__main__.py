"""O descarte pela linha de comando, fora do Dagster (lê o `.env`).

    python -m rh_fictalent.lgpd --simular     # o que seria apagado, sem apagar nada
    python -m rh_fictalent.lgpd --aplicar     # apaga, confere, registra

No dia a dia quem descarta é o job `aplicar_descarte`, disparado depois de toda carga.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from rh_fictalent.lake import consulta
from rh_fictalent.lgpd import descarte
from rh_fictalent.orquestracao.recursos import lake_do_ambiente, warehouse_do_ambiente
from rh_fictalent.silver import construcao


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rh_fictalent.lgpd")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--simular", action="store_true", help="mostra os alvos, não apaga")
    grupo.add_argument("--aplicar", action="store_true", help="apaga, confere e registra")
    args = parser.parse_args(argv)

    lake = lake_do_ambiente()
    warehouse = warehouse_do_ambiente()
    referencia = construcao.referencia_atual(warehouse)
    con = consulta.abrir(lake)
    try:
        vigente = descarte.prazo(con, referencia)
        print(f"data de referência: {referencia:%d/%m/%Y}")
        print(f"retenção: {vigente.texto if vigente else 'parâmetro não declarado'}")
        if args.simular:
            for tabela, por_motivo in sorted(descarte.alvos(con, referencia, vigente).items()):
                motivos = ", ".join(f"{m} {len(ids)}" for m, ids in sorted(por_motivo.items()))
                print(f"  {tabela:<34} {motivos}")
            return 0
        vigente, resultados = descarte.aplicar(con, lake, referencia)
    finally:
        con.close()
    for r in resultados:
        sinal = "ok " if not r.problemas else "NÃO"
        mudou = {c: par for c, par in r.contas.items() if par[0] != par[1]}
        print(
            f"{sinal} {r.tabela:<34} eliminadas {r.eliminadas:>6}  vencidas {r.vencidas:>6}  "
            f"{r.arquivos} arquivos  regras que mudaram: {mudou}"
        )
        for problema in r.problemas:
            print(f"      {problema}")
    gravadas = descarte.registrar(warehouse, referencia, vigente, resultados)
    print(
        f"\n{len(resultados)} tabelas com alvo; {gravadas} descartes registrados em lgpd.descarte"
    )
    return 1 if any(r.problemas for r in resultados) else 0


if __name__ == "__main__":
    sys.exit(main())
