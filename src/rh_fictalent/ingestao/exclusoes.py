"""As exclusões: o que foi apagado na réplica vira marcação na bronze, nunca sumiço.

Uma linha apagada não tem `atualizado_em` para ser encontrada, então a marca d'água nunca a
veria. Quem a vê é a trilha `meta.exclusao_auditoria`, que os gatilhos `BEFORE DELETE` da v0.2.0
alimentam com banco, tabela, id e usuário, na mesma transação do `DELETE`.

**Marcar, não apagar.** A linha continua na bronze com `excluido_em` preenchido. Quem perguntar
"quantos contratos existem" filtra as vivas; quem perguntar "o que sumiu, quando e por quem" tem
resposta. Apagar da bronze responderia a primeira pergunta e destruiria a segunda, que é a que
interessa numa auditoria.

Duas consequências que precisam estar ditas:

- **A bronze deixa de ser reconstruível só a partir da réplica.** A linha apagada não existe
  mais lá: recopiar a tabela (o `refazer`) traz o presente e perde as linhas que morreram. Por
  isso a própria trilha é copiada para a bronze, como qualquer outra tabela: o registro do que
  foi apagado sobrevive mesmo quando a marcação não sobrevive.
- **A conferência de contagem passa a contar as vivas.** Foi o que o card 5.2 acusava: linha na
  bronze que não existe na réplica. Agora ela é explicada, em vez de ser um buraco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from rh_fictalent.ingestao.backfill import CAMADA, CONTROLE

if TYPE_CHECKING:  # pragma: no cover
    import pymysql

    from rh_fictalent.orquestracao.recursos import Lake

TRILHA = ("meta", "exclusao_auditoria")
NOME_DA_TRILHA = ".".join(TRILHA)
ANOS = tuple(range(2018, 2027))


@dataclass
class Aplicacao:
    """O que a aplicação das exclusões fez numa tabela."""

    modulo: str
    tabela: str
    pedidas: int = 0  # linhas que a trilha diz que foram apagadas
    marcadas: int = 0  # as que estavam na bronze e foram marcadas agora
    ja_marcadas: int = 0  # as que a bronze já sabia
    ausentes: int = 0  # as que nunca chegaram à bronze (apagadas antes do backfill)
    particoes: dict[int, int] = field(default_factory=dict)  # ano -> vivas depois

    @property
    def nome(self) -> str:
        return f"{self.modulo}.{self.tabela}"


def ler_trilha(
    con: pymysql.connections.Connection[Any], desde: datetime, ate: datetime
) -> dict[tuple[str, str], dict[int, datetime]]:
    """As exclusões da janela, agrupadas por tabela: id apagado -> quando sumiu.

    O `pipeline` tem `SELECT` em `meta` e nada mais: ler a trilha é leitura, como o resto.
    """
    sql = (
        "SELECT banco, tabela, registro_id, dt_exclusao FROM meta.exclusao_auditoria "
        "WHERE dt_exclusao > %s AND dt_exclusao <= %s ORDER BY id"
    )
    por_tabela: dict[tuple[str, str], dict[int, datetime]] = {}
    with con.cursor() as cur:
        cur.execute(sql, (desde, ate))
        for banco, tabela, registro, quando in cur.fetchall():
            por_tabela.setdefault((str(banco), str(tabela)), {})[int(registro)] = quando
    return por_tabela


def marcar(lake: Lake, modulo: str, tabela: str, excluidos: dict[int, datetime]) -> Aplicacao:
    """Procura cada id apagado nas partições da tabela e carimba `excluido_em`.

    O id não diz em que ano a linha foi criada, e a trilha não guarda `criado_em` (a linha já não
    existe para ser consultada). Por isso a procura passa pelas partições, lendo só a coluna de
    id de cada uma: nove leituras baratas por tabela, contra manter um índice à parte que
    poderia divergir.
    """
    resultado = Aplicacao(modulo, tabela, pedidas=len(excluidos))
    fs = lake.sistema()
    restantes = dict(excluidos)
    for ano in ANOS:
        caminho = lake.caminho(CAMADA, modulo, tabela, f"ano={ano}.parquet")
        if not restantes or not fs.exists(caminho):
            continue
        with fs.open(caminho, "rb") as arquivo:
            quadro = pq.read_table(arquivo)
        if not quadro.num_rows:
            continue
        ids = quadro["id"].to_pylist()
        aqui = {i: q for i, q in restantes.items() if i in set(ids)}
        if aqui:
            antes = quadro[CONTROLE].to_pylist()
            depois = [
                aqui.get(int(linha), carimbo) for linha, carimbo in zip(ids, antes, strict=True)
            ]
            resultado.ja_marcadas += sum(
                1 for i, c in zip(ids, antes, strict=True) if int(i) in aqui and c is not None
            )
            resultado.marcadas += sum(
                1 for i, c in zip(ids, antes, strict=True) if int(i) in aqui and c is None
            )
            indice = quadro.schema.get_field_index(CONTROLE)
            quadro = quadro.set_column(
                indice, quadro.schema.field(indice), pa.array(depois, type=pa.timestamp("us"))
            )
            with fs.open(caminho, "wb") as arquivo:
                pq.write_table(quadro, arquivo, compression="zstd")
            for i in aqui:
                restantes.pop(i, None)
        resultado.particoes[ano] = int(
            pc.sum(pc.is_null(quadro[CONTROLE]).cast(pa.int64())).as_py() or 0
        )
    resultado.ausentes = len(restantes)  # apagadas antes de a bronze existir: nada a marcar
    return resultado


def vivas(lake: Lake, modulo: str, tabela: str, ano: int) -> int:
    """Quantas linhas da partição não estão marcadas como excluídas."""
    caminho = lake.caminho(CAMADA, modulo, tabela, f"ano={ano}.parquet")
    fs = lake.sistema()
    if not fs.exists(caminho):
        return 0
    with fs.open(caminho, "rb") as arquivo:
        coluna = pq.read_table(arquivo, columns=[CONTROLE])[CONTROLE]
    return int(pc.sum(pc.is_null(coluna).cast(pa.int64())).as_py() or 0)
