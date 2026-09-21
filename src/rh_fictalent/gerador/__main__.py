"""O gerador pela linha de comando, etapa a etapa.

    python -m rh_fictalent.gerador --etapa 1                   # gera e confere, não grava
    python -m rh_fictalent.gerador --etapa 1 --gravar          # grava na réplica (replicador)
    python -m rh_fictalent.gerador --etapa 1 --gravar --zerar  # zera a réplica inteira antes (root)
    python -m rh_fictalent.gerador --etapa 2 --gravar          # a etapa seguinte continua a base
    python -m rh_fictalent.gerador --etapa 3 --gravar          # funil e pessoas, ~1,3 mi de linhas

Gravar exige cada tabela exatamente no ponto em que a etapa a continua (gravar duas vezes, ou
fora de ordem, é recusado): regenerar é sempre "zera e grava de novo", nunca remendo. Zerar
esvazia a réplica inteira, porque toda etapa depende das anteriores. Quando a etapa já permite
tirar medidas, a régua parcial sai junto.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from dotenv import load_dotenv

from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, etapa3_pessoas
from rh_fictalent.gerador.nucleo import SEMENTE, Tabelas, assinatura, replica_do_ambiente
from rh_fictalent.validacao.regua import Laudo


@dataclass(frozen=True)
class Etapa:
    nome: str
    gerar: Callable[[], Tabelas]
    adiadas: dict[str, list[str]] = field(default_factory=dict)
    laudo: Callable[[Tabelas], Laudo] | None = None  # a régua parcial, quando a etapa já mede


def _etapa_3() -> Tabelas:
    tabelas, gabarito = etapa3_pessoas.gerar_com_gabarito()
    etapa3_pessoas.conferir(tabelas, gabarito)
    _GABARITO.update(gabarito)
    return tabelas


_GABARITO: dict[str, object] = {}


ETAPAS = {
    1: Etapa("mundo cadastral", etapa1_cadastro.gerar),
    2: Etapa(
        "carteira comercial",
        etapa2_carteira.gerar,
        etapa2_carteira.ADIADAS,
        lambda t: etapa2_carteira.laudo_parcial(etapa2_carteira.medir(t)),
    ),
    3: Etapa(
        "funil e pessoas",
        _etapa_3,
        {},
        lambda t: etapa3_pessoas.laudo_parcial(etapa3_pessoas.medir(t, _GABARITO)),
    ),
}


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gerador determinístico da base sintética.")
    parser.add_argument("--etapa", type=int, choices=sorted(ETAPAS), required=True)
    parser.add_argument("--gravar", action="store_true", help="grava na réplica como replicador")
    parser.add_argument("--zerar", action="store_true", help="zera a réplica inteira antes (root)")
    args = parser.parse_args(argumentos)
    if args.zerar and not args.gravar:
        parser.error("--zerar só faz sentido com --gravar")

    etapa = ETAPAS[args.etapa]
    tabelas = etapa.gerar()
    print(f"etapa {args.etapa} · {etapa.nome} · semente {SEMENTE}")
    for tabela, quadro in tabelas.items():
        print(f"  {tabela:<32} {len(quadro):>7} linhas")
    print(f"  assinatura {assinatura(tabelas)[:16]}")
    if etapa.laudo is not None:
        print(etapa.laudo(tabelas).texto(so_problemas=True))

    if args.gravar:
        load_dotenv()
        if args.zerar:
            zeradas = replica_do_ambiente("root").zerar()
            print(f"réplica zerada: {zeradas} tabelas")
        gravadas = replica_do_ambiente("replicador").gravar(tabelas, etapa.adiadas)
        print(f"gravado na réplica: {sum(gravadas.values())} linhas em {len(gravadas)} tabelas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
