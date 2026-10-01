"""A prestação de contas da silver: cada regra reproduz, na data da auditoria, o número que a
auditoria gravou para o achado.

O catálogo (card 6.3) foi aprovado com números: "457 CPFs inválidos", "263 temporários além
do prazo". A silver promete marcar exatamente essas linhas. Esta prestação roda cada regra
sobre a bronze **na data de referência que a auditoria usou** (a regra com prazo depende do
dia: o ASO vencido hoje não é o vencido de ontem), conta do jeito que a regra diz que se
conta, e compara com o registro em `dados/auditoria/<dominio>.json`. Qualquer diferença
reprova.

Ela reprova também quando a regra implementa uma entrada que não está aprovada no catálogo:
a silver só faz o que foi decidido.

Quando reprova sem que ninguém tenha mexido nas regras, a causa é a bronze: a réplica se moveu
depois da auditoria (um dia simulado, uma correção na origem). Aí o caminho é refazer a
auditoria (`python -m rh_fictalent.auditoria --executar`), revisar o catálogo e aprovar de novo,
nunca ajustar a regra para bater: o número aprovado é o contrato.

Junto com a conferência da construção (`silver.construcao.conferir`: a silver é a bronze mais
as colunas das regras), fecha a prova: o arquivo é a regra aplicada à bronze, e a regra
aplicada à bronze da auditoria dá o número da auditoria.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

from rh_fictalent.auditoria import achados, catalogo
from rh_fictalent.silver import regras

APROVADA = "aprovada"


@dataclass(frozen=True)
class Conta:
    codigo: str
    dominio: str
    tabela: str  # a tabela do achado, como a auditoria gravou
    referencia: str  # a data da auditoria, em que a regra foi rodada
    auditoria: int  # o número gravado no achado
    regra: int  # o número que a regra deu
    situacao: str  # a situação da entrada no catálogo

    @property
    def confere(self) -> bool:
        return self.regra == self.auditoria and self.situacao == APROVADA


def referencias(pasta: Path = achados.PASTA) -> dict[str, date]:
    """A data de referência de cada domínio auditado, lida do registro gravado."""
    datas = {}
    for caminho in sorted(pasta.glob("*.json")):
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        datas[conteudo["dominio"]] = datetime.fromisoformat(conteudo["referencia"]).date()
    return datas


def prestar(con: duckdb.DuckDBPyConnection, pasta: Path = achados.PASTA) -> list[Conta]:
    """Roda cada regra na data da auditoria do domínio dela e compara com o registro.

    A conexão precisa ter a bronze pelos nomes da réplica (`lake.consulta.abrir`).
    """
    pares = {entrada.codigo: (entrada, achado) for entrada, achado in catalogo.casar()}
    datas = referencias(pasta)
    contas = []
    for regra in regras.REGRAS:
        entrada, achado = pares[regra.codigo]
        referencia = datas[achado.dominio]
        regras.preparar(con, referencia)
        for derivacao in regra.derivacoes:
            regras.derivar(con, regra, derivacao)
        numero = int(con.execute(regra.sql_da_contagem).fetchall()[0][0])
        contas.append(
            Conta(
                codigo=regra.codigo,
                dominio=achado.dominio,
                tabela=achado.tabela,
                referencia=referencia.isoformat(),
                auditoria=achado.linhas,
                regra=numero,
                situacao=entrada.situacao,
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
