"""A prestação de contas da silver: cada regra reproduz, na data da auditoria, o número que a
auditoria gravou para o achado, ou o que o último descarte registrado deixou.

O catálogo (card 6.3) foi aprovado com números: "457 CPFs inválidos", "263 temporários além
do prazo". A silver promete marcar exatamente essas linhas. Esta prestação roda cada regra
sobre a bronze **na data de referência que a auditoria usou** (a regra com prazo depende do
dia: o ASO vencido hoje não é o vencido de ontem), conta do jeito que a regra diz que se
conta, e compara com o número esperado. Qualquer diferença reprova.

**O número esperado tem cadeia de custódia** (card 6.5). A LGPD manda apagar o dado pessoal
do candidato vencido, e apagar o CPF muda quantos CPFs repetidos existem: a medida da
auditoria deixa de ser reproduzível, por força de lei. Por isso cada descarte
(`rh_fictalent.lgpd.descarte`) mede as regras afetadas antes e depois de apagar e registra os
dois números no warehouse. O esperado de uma regra é o da auditoria, trocado pelo "depois" de
cada descarte, em ordem; e cada "antes" tem de ser o esperado até ali, ou o número da
auditoria, que é o caso da tabela recopiada da réplica (a recópia traz o dado pessoal de volta,
e o descarte seguinte o apaga de novo). Se um elo não fecha (alguém apagou sem registrar, ou a
bronze mudou entre dois descartes), a prestação reprova dizendo onde a cadeia quebrou.

Ela reprova também quando a regra implementa uma entrada que não está aprovada no catálogo:
a silver só faz o que foi decidido.

Quando reprova sem que ninguém tenha mexido nas regras nem descartado, a causa é a bronze: a
réplica se moveu depois da auditoria (um dia simulado, uma correção na origem). Aí o caminho é
refazer a auditoria (`python -m rh_fictalent.auditoria --executar`), revisar o catálogo e
aprovar de novo, nunca ajustar a regra para bater: o número aprovado é o contrato.

Junto com a conferência da construção (`silver.construcao.conferir`: a silver é a bronze
pseudonimizada mais as colunas das regras), fecha a prova: o arquivo é a regra aplicada à
bronze, e a regra aplicada à bronze da auditoria dá o número da auditoria, ou o da cadeia.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

from rh_fictalent.auditoria import achados, catalogo
from rh_fictalent.silver import regras

APROVADA = "aprovada"
AUDITORIA = "auditoria"


@dataclass(frozen=True)
class Elo:
    """Um descarte registrado, visto por uma regra: o número antes e depois de apagar."""

    quando: str  # o descarte, como o registro o identifica (data, hora e número)
    codigo: str
    antes: int
    depois: int
    ordem: int = 0  # a ordem do registro: é ela, não o relógio, que encadeia os elos


@dataclass(frozen=True)
class Conta:
    codigo: str
    dominio: str
    tabela: str  # a tabela do achado, como a auditoria gravou
    referencia: str  # a data da auditoria, em que a regra foi rodada
    auditoria: int  # o número gravado no achado
    regra: int  # o número que a regra deu
    situacao: str  # a situação da entrada no catálogo
    esperado: int = -1  # o número que a regra tem de dar: o da auditoria ou o da cadeia
    origem: str = AUDITORIA  # de onde veio o esperado
    cadeia: str = ""  # vazio se a cadeia de descartes fecha; senão, onde ela quebrou

    @property
    def confere(self) -> bool:
        esperado = self.auditoria if self.esperado < 0 else self.esperado
        return self.regra == esperado and self.situacao == APROVADA and not self.cadeia


def referencias(pasta: Path = achados.PASTA) -> dict[str, date]:
    """A data de referência de cada domínio auditado, lida do registro gravado."""
    datas = {}
    for caminho in sorted(pasta.glob("*.json")):
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        datas[conteudo["dominio"]] = datetime.fromisoformat(conteudo["referencia"]).date()
    return datas


def contar(con: duckdb.DuckDBPyConnection, regra: regras.Regra, referencia: date) -> int:
    """O número da regra sobre a bronze da conexão, na data dada."""
    regras.preparar(con, referencia)
    for derivacao in regra.derivacoes:
        regras.derivar(con, regra, derivacao)
    return int(con.execute(regra.sql_da_contagem).fetchall()[0][0])


def afetadas(tabela: str) -> list[regras.Regra]:
    """As regras que leem a tabela: as que um descarte nela pode mudar."""
    return [
        r for r in regras.REGRAS if any(tabela == d.tabela or tabela in d.le for d in r.derivacoes)
    ]


def contar_afetadas(
    con: duckdb.DuckDBPyConnection, tabela: str, pasta: Path = achados.PASTA
) -> dict[str, int]:
    """O número de cada regra afetada pela tabela, na data da auditoria do domínio dela."""
    dominio = {e.codigo: a.dominio for e, a in catalogo.casar()}
    datas = referencias(pasta)
    return {r.codigo: contar(con, r, datas[dominio[r.codigo]]) for r in afetadas(tabela)}


def _esperado(auditoria: int, elos: list[Elo]) -> tuple[int, str, str]:
    """(esperado, origem, onde a cadeia quebrou) a partir da auditoria e dos descartes.

    O "antes" de um descarte fecha a cadeia de dois jeitos: é o esperado até ali (a bronze
    estava como o descarte anterior deixou), ou é o número da auditoria (a tabela foi recopiada
    da réplica, por `refazer` ou backfill, e voltou ao estado auditado, com o dado pessoal
    de volta). Qualquer outro número é mudança sem registro.
    """
    esperado, origem = auditoria, AUDITORIA
    for elo in sorted(elos, key=lambda e: e.ordem):
        if elo.antes not in (esperado, auditoria):
            quebra = (
                f"o descarte de {elo.quando} mediu {elo.antes} antes de apagar, "
                f"mas o esperado até ali era {esperado} ({origem}) e a auditoria mediu {auditoria}"
            )
            return esperado, origem, quebra
        recopiada = elo.antes == auditoria and esperado != auditoria
        origem = f"descarte de {elo.quando}" + (
            ", depois de recópia da réplica" if recopiada else ""
        )
        esperado = elo.depois
    return esperado, origem, ""


def prestar(
    con: duckdb.DuckDBPyConnection,
    pasta: Path = achados.PASTA,
    elos: Iterable[Elo] = (),
) -> list[Conta]:
    """Roda cada regra na data da auditoria do domínio dela e compara com o esperado.

    A conexão precisa ter a bronze pelos nomes da réplica (`lake.consulta.abrir`); `elos` são
    os descartes registrados (`lgpd.descarte.elos`), vazio se nunca houve descarte.
    """
    pares = {entrada.codigo: (entrada, achado) for entrada, achado in catalogo.casar()}
    datas = referencias(pasta)
    por_regra: dict[str, list[Elo]] = {}
    for elo in elos:
        por_regra.setdefault(elo.codigo, []).append(elo)
    contas = []
    for regra in regras.REGRAS:
        entrada, achado = pares[regra.codigo]
        referencia = datas[achado.dominio]
        esperado, origem, cadeia = _esperado(achado.linhas, por_regra.get(regra.codigo, []))
        contas.append(
            Conta(
                codigo=regra.codigo,
                dominio=achado.dominio,
                tabela=achado.tabela,
                referencia=referencia.isoformat(),
                auditoria=achado.linhas,
                regra=contar(con, regra, referencia),
                situacao=entrada.situacao,
                esperado=esperado,
                origem=origem,
                cadeia=cadeia,
            )
        )
    return contas


def reprovadas(contas: list[Conta]) -> list[Conta]:
    return [c for c in contas if not c.confere]


def relatorio(contas: list[Conta]) -> dict[str, object]:
    """A prestação como documento: o que se conferiu, o que bateu e o que não bateu."""
    return {
        "conferidas": len(contas),
        "reprovadas": [c.codigo for c in reprovadas(contas)],
        "contas": [{**asdict(c), "confere": c.confere} for c in contas],
    }
