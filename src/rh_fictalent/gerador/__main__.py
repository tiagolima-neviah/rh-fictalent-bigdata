"""O gerador pela linha de comando, etapa a etapa.

    python -m rh_fictalent.gerador --etapa 1                   # gera e confere, não grava
    python -m rh_fictalent.gerador --etapa 1 --gravar          # grava na réplica (replicador)
    python -m rh_fictalent.gerador --etapa 1 --gravar --zerar  # zera a réplica inteira antes (root)
    python -m rh_fictalent.gerador --etapa 2 --gravar          # a etapa seguinte continua a base
    python -m rh_fictalent.gerador --etapa 3 --gravar          # funil e pessoas, ~1,3 mi de linhas
    python -m rh_fictalent.gerador --etapa 4 --gravar          # ponto e folha, ~6 mi de linhas
    python -m rh_fictalent.gerador --etapa 5 --gravar          # financeiro e as planilhas Excel
    python -m rh_fictalent.gerador --etapa 6 --gravar          # SST, treinamento e segurança
    python -m rh_fictalent.gerador --aceite --replica          # a régua inteira na base gravada

Gravar exige cada tabela exatamente no ponto em que a etapa a continua (gravar duas vezes, ou
fora de ordem, é recusado): regenerar é sempre "zera e grava de novo", nunca remendo. Zerar
esvazia a réplica inteira, porque toda etapa depende das anteriores. Quando a etapa já permite
tirar medidas, a régua parcial sai junto. A etapa 6 também preenche o entrevistador das
entrevistas da etapa 3 (o usuário só passa a existir nela): é o único retoque do gerador.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd
from dotenv import load_dotenv

from rh_fictalent.gerador import (
    aceite,
    etapa1_cadastro,
    etapa2_carteira,
    etapa3_pessoas,
    etapa4_ponto_folha,
    etapa5_financeiro,
    etapa6_conformidade,
)
from rh_fictalent.gerador.nucleo import SEMENTE, Tabelas, assinatura, replica_do_ambiente
from rh_fictalent.validacao.regua import Laudo


@dataclass(frozen=True)
class Etapa:
    nome: str
    gerar: Callable[[], Tabelas]
    adiadas: dict[str, list[str]] = field(default_factory=dict)
    laudo: Callable[[Tabelas], Laudo] | None = None  # a régua parcial, quando a etapa já mede
    retoques: Callable[[], dict[str, pd.DataFrame]] | None = None  # colunas de etapa anterior


def _etapa_3() -> Tabelas:
    tabelas, gabarito = etapa3_pessoas.gerar_com_gabarito()
    etapa3_pessoas.conferir(tabelas, gabarito)
    _GABARITO.update(gabarito)
    return tabelas


def _etapa_4() -> Tabelas:
    tabelas, base = etapa4_ponto_folha.gerar_com_base()
    etapa4_ponto_folha.conferir(tabelas, base)
    _BASE.update(base)
    return tabelas


def _etapa_5() -> Tabelas:
    tabelas, base = etapa5_financeiro.gerar_com_base()
    etapa5_financeiro.conferir(tabelas, base)
    _BASE.clear()
    _BASE.update(base)
    return tabelas


def _etapa_6() -> Tabelas:
    tabelas, base = etapa6_conformidade.gerar_com_base()
    etapa6_conformidade.conferir(tabelas, base)
    _BASE.clear()
    _BASE.update(base)
    return tabelas


def _retoques_da_etapa_6() -> dict[str, pd.DataFrame]:
    retoques: dict[str, pd.DataFrame] = _BASE["retoques"]  # type: ignore[assignment]
    return retoques


_GABARITO: dict[str, object] = {}
_BASE: dict[str, object] = {}


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
    4: Etapa(
        "ponto e folha",
        _etapa_4,
        {},
        lambda t: etapa4_ponto_folha.laudo_parcial(etapa4_ponto_folha.medir(t, _BASE)),
    ),
    5: Etapa(
        "financeiro",
        _etapa_5,
        {},
        lambda t: etapa5_financeiro.laudo_parcial(etapa5_financeiro.medir(t, _BASE)),
    ),
    6: Etapa(
        "conformidade e acesso",
        _etapa_6,
        {},
        lambda t: etapa6_conformidade.laudo_parcial(etapa6_conformidade.medir(t, _BASE)),
        _retoques_da_etapa_6,
    ),
}


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gerador determinístico da base sintética.")
    parser.add_argument("--etapa", type=int, choices=sorted(ETAPAS))
    parser.add_argument("--aceite", action="store_true", help="a base inteira contra a régua")
    parser.add_argument("--replica", action="store_true", help="no aceite, conta na réplica")
    parser.add_argument("--gravar", action="store_true", help="grava na réplica como replicador")
    parser.add_argument("--zerar", action="store_true", help="zera a réplica inteira antes (root)")
    args = parser.parse_args(argumentos)
    if args.zerar and not args.gravar:
        parser.error("--zerar só faz sentido com --gravar")
    if args.aceite:
        load_dotenv()
        return aceite.executar(replica_do_ambiente("replicador") if args.replica else None)
    if args.etapa is None:
        parser.error("informe --etapa ou --aceite")

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
        retoques = etapa.retoques() if etapa.retoques else {}
        gravadas = replica_do_ambiente("replicador").gravar(tabelas, etapa.adiadas, retoques)
        print(f"gravado na réplica: {sum(gravadas.values())} linhas em {len(gravadas)} tabelas")
        for nome, quadro in retoques.items():
            print(f"retocado: {nome}.{quadro.columns[-1]} em {len(quadro)} linhas")
        if args.etapa == 5:  # o consolidado também é arquivo: a fonte Excel do pipeline
            planilhas = etapa5_financeiro.escrever_planilhas(tabelas, _BASE)
            print(f"planilhas do consolidado: {len(planilhas)} arquivos em {planilhas[0].parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
