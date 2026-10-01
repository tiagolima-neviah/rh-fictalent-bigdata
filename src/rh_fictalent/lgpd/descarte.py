# ruff: noqa: E501
"""O descarte: o dado pessoal que o pipeline não pode mais guardar sai da bronze, com registro.

Dois motivos, a mesma mecânica:

- **Eliminação** (LGPD, art. 16 e art. 18, VI). A linha apagada no sistema do cliente fica na
  bronze marcada como excluída (card 5.3), para o histórico agregado responder "quantos
  existiam". O agregado não precisa saber quem era: as colunas etiquetadas como pessoais
  dessa linha são apagadas, e a linha fica.
- **Retenção** (LGPD, art. 15 e art. 16). O candidato que nunca foi contratado tem prazo:
  `RETENCAO_CANDIDATO_DIAS` na `cadastro.parametro` da réplica, declarado pelo cliente (o
  Tiago, em 01/10/2026: 730 dias, contados da última atividade, cadastro ou candidatura).
  Vencido o prazo, as colunas pessoais do candidato são apagadas na bronze; a linha fica, para
  o funil histórico continuar contando inscrições por fonte e por vaga. Sem o parâmetro
  vigente, nada é descartado por retenção, e o registro diz por quê: prazo de retenção é
  decisão do controlador, não do pipeline.

**Apagar, aqui, é gravar nulo nas colunas etiquetadas** (`staging.lgpd`) das linhas-alvo, no
parquet da bronze. A silver, construída da bronze, herda o nulo: o descarte vale nas duas
cópias. A réplica é do cliente e o pipeline não escreve nela.

**O arquivo só é trocado depois de conferido**, como na silver: a versão descartada vai para
`bronze/_em_descarte/`, é comparada com a original (mesmas linhas; as linhas que não são alvo,
idênticas; nas linhas-alvo, as colunas pessoais nulas e o resto idêntico) e só então substitui a
original. O descarte é idempotente: a linha que já não tem dado pessoal não é alvo de novo.

**A carga traz o dado de volta, e o descarte o apaga de novo.** A carga incremental faz merge
por id: a linha que não mudou na réplica fica como está na bronze, descartada; a que mudou
volta inteira. Por isso o descarte roda depois de toda carga (sensor `descartar_depois_da_carga`).

**Cada descarte deixa registro** em `lgpd.descarte`, no warehouse, sem nenhum dado pessoal:
quando, sobre que data de referência, que tabela, quantas linhas por motivo, que colunas, e, para
cada regra da silver que lê a tabela, o número dela antes e depois de apagar, medido na data
da auditoria. É a cadeia de custódia que a prestação de contas da silver segue (`silver.contas`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from rh_fictalent.ingestao.backfill import CAMADA, CONTROLE
from rh_fictalent.silver import contas
from rh_fictalent.staging import lgpd

if TYPE_CHECKING:  # pragma: no cover
    from rh_fictalent.orquestracao.recursos import Lake, Warehouse

PARAMETRO = "RETENCAO_CANDIDATO_DIAS"
TABELA_DA_RETENCAO = "ats.candidato"
EM_DESCARTE = "_em_descarte"
ELIMINACAO = "eliminacao"
RETENCAO = "retencao"

DDL = """
CREATE SCHEMA IF NOT EXISTS lgpd;

CREATE TABLE IF NOT EXISTS lgpd.descarte (
  id               bigserial PRIMARY KEY,
  executado_em     timestamptz NOT NULL DEFAULT now(),
  run_id           text,
  referencia       date NOT NULL,
  tabela           text NOT NULL,
  eliminadas       integer NOT NULL DEFAULT 0,
  vencidas         integer NOT NULL DEFAULT 0,
  regra_retencao   text NOT NULL,
  colunas          text[] NOT NULL,
  contas           jsonb NOT NULL DEFAULT '{}'::jsonb
);
COMMENT ON TABLE lgpd.descarte IS
  'Cada descarte de dado pessoal na bronze: quantas linhas, por que motivo, e o efeito nas regras da silver (sem dado pessoal)';
COMMENT ON COLUMN lgpd.descarte.contas IS
  'Por regra da silver que le a tabela: [antes, depois] do descarte, medido na data da auditoria';
"""


@dataclass(frozen=True)
class Prazo:
    dias: int
    desde: date

    @property
    def texto(self) -> str:
        return f"{PARAMETRO}={self.dias} (vigente desde {self.desde:%d/%m/%Y})"


@dataclass
class Resultado:
    tabela: str
    eliminadas: int = 0
    vencidas: int = 0
    colunas: list[str] = field(default_factory=list)
    arquivos: int = 0
    contas: dict[str, tuple[int, int]] = field(default_factory=dict)  # regra -> (antes, depois)
    problemas: list[str] = field(default_factory=list)

    @property
    def linhas(self) -> int:
        return self.eliminadas + self.vencidas


def prazo(con: duckdb.DuckDBPyConnection, referencia: date) -> Prazo | None:
    """O prazo de retenção vigente na data, lido da bronze da `cadastro.parametro`."""
    sql = (  # noqa: S608
        "SELECT valor, vigencia_inicio FROM cadastro.parametro "  # nosec B608
        f"WHERE chave = ? AND {CONTROLE} IS NULL AND vigencia_inicio <= ? "
        "AND (vigencia_fim IS NULL OR vigencia_fim >= ?) ORDER BY vigencia_inicio DESC LIMIT 1"
    )
    linhas = con.execute(sql, [PARAMETRO, referencia, referencia]).fetchall()
    if not linhas:
        return None
    valor, desde = linhas[0]
    return Prazo(int(valor), desde)


def _ainda_tem(colunas: list[str], apelido: str = "t") -> str:
    return " OR ".join(f"{apelido}.{c} IS NOT NULL" for c in colunas)


def alvos(
    con: duckdb.DuckDBPyConnection, referencia: date, vigente: Prazo | None
) -> dict[str, dict[str, set[int]]]:
    """Por tabela, os ids a descartar por motivo; só linhas que ainda têm dado pessoal."""
    por_tabela: dict[str, dict[str, set[int]]] = {}
    for tabela, etiquetadas in lgpd.colunas().items():
        colunas = sorted(etiquetadas)
        sql = (  # noqa: S608
            f"SELECT t.id FROM {tabela} t WHERE t.{CONTROLE} IS NOT NULL "  # nosec B608
            f"AND ({_ainda_tem(colunas)})"
        )
        eliminadas = {int(i) for (i,) in con.execute(sql).fetchall()}
        if eliminadas:
            por_tabela.setdefault(tabela, {})[ELIMINACAO] = eliminadas
    if vigente is not None:
        colunas = sorted(lgpd.colunas()[TABELA_DA_RETENCAO])
        limite = referencia - timedelta(days=vigente.dias)
        sql = f"""
            WITH atividade AS (
              SELECT candidato_id, max(CAST(coalesce(dt_conclusao, dt_inscricao) AS DATE)) AS dia
              FROM ats.candidatura WHERE {CONTROLE} IS NULL GROUP BY 1)
            SELECT t.id FROM {TABELA_DA_RETENCAO} t LEFT JOIN atividade a ON a.candidato_id = t.id
            WHERE t.{CONTROLE} IS NULL AND ({_ainda_tem(colunas)})
              AND greatest(t.dt_cadastro, coalesce(a.dia, t.dt_cadastro)) < ?
              AND NOT EXISTS (SELECT 1 FROM pessoas.colaborador p WHERE p.candidato_id = t.id)
        """  # noqa: S608 # nosec B608
        vencidas = {int(i) for (i,) in con.execute(sql, [limite]).fetchall()}
        if vencidas:
            por_tabela.setdefault(TABELA_DA_RETENCAO, {})[RETENCAO] = vencidas
    return por_tabela


def caminho(lake: Lake, tabela: str, ano: str = "*", em_descarte: bool = False) -> str:
    etapa = (EM_DESCARTE,) if em_descarte else ()
    return lake.caminho(CAMADA, *etapa, *tabela.split("."), f"ano={ano}.parquet")


def _apagado(original: pa.Table, alvo: pa.Array, colunas: list[str]) -> pa.Table:
    """A partição com as colunas pessoais nulas nas linhas-alvo (e aceitando nulo)."""
    nova = original
    for coluna in colunas:
        posicao = nova.schema.get_field_index(coluna)
        campo = nova.schema.field(posicao).with_nullable(True)
        nulos = pa.nulls(nova.num_rows, type=campo.type)
        nova = nova.set_column(posicao, campo, pc.if_else(alvo, nulos, nova[coluna]))
    return nova


def _conferir(
    con: duckdb.DuckDBPyConnection, original: str, descartado: str, colunas: list[str]
) -> list[str]:
    """A versão descartada é a original com nulo nas colunas pessoais das linhas-alvo, e só."""
    problemas = []
    o = f"read_parquet('{original}')"
    d = f"read_parquet('{descartado}')"
    linhas_o = con.execute(f"SELECT count(*) FROM {o}").fetchall()[0][0]  # noqa: S608 # nosec B608
    linhas_d = con.execute(f"SELECT count(*) FROM {d}").fetchall()[0][0]  # noqa: S608 # nosec B608
    if linhas_o != linhas_d:
        problemas.append(f"{descartado}: {linhas_d} linhas, a original tem {linhas_o}")
    fora = "id NOT IN (SELECT id FROM alvo_do_descarte)"
    dentro = "id IN (SELECT id FROM alvo_do_descarte)"
    resto = f"* EXCLUDE ({', '.join(colunas)})"
    for sentido, de, para in (("na original", o, d), ("na descartada", d, o)):
        intactas = f"SELECT * FROM {de} WHERE {fora} EXCEPT ALL SELECT * FROM {para} WHERE {fora}"  # noqa: S608 # nosec B608
        if con.execute(f"SELECT count(*) FROM ({intactas})").fetchall()[0][0]:  # noqa: S608 # nosec B608
            problemas.append(f"{descartado}: linha que não era alvo mudou ({sentido})")
        alvo = f"SELECT {resto} FROM {de} WHERE {dentro} EXCEPT ALL SELECT {resto} FROM {para} WHERE {dentro}"  # noqa: S608 # nosec B608
        if con.execute(f"SELECT count(*) FROM ({alvo})").fetchall()[0][0]:  # noqa: S608 # nosec B608
            problemas.append(f"{descartado}: coluna não pessoal mudou numa linha-alvo ({sentido})")
    preenchidas = " OR ".join(f"{c} IS NOT NULL" for c in colunas)
    restantes = f"SELECT count(*) FROM {d} WHERE {dentro} AND ({preenchidas})"  # noqa: S608 # nosec B608
    sobra = con.execute(restantes).fetchall()[0][0]
    if sobra:
        problemas.append(f"{descartado}: {sobra} linhas-alvo ainda com dado pessoal")
    return problemas


def descartar_tabela(
    con: duckdb.DuckDBPyConnection, lake: Lake, tabela: str, por_motivo: dict[str, set[int]]
) -> Resultado:
    """Apaga o dado pessoal das linhas-alvo na bronze da tabela, conferindo antes de trocar."""
    colunas = sorted(lgpd.colunas()[tabela])
    resultado = Resultado(
        tabela,
        eliminadas=len(por_motivo.get(ELIMINACAO, set())),
        vencidas=len(por_motivo.get(RETENCAO, set())),
        colunas=colunas,
    )
    ids = sorted(set().union(*por_motivo.values()))
    con.execute("CREATE OR REPLACE TEMP TABLE alvo_do_descarte (id BIGINT)")
    con.executemany("INSERT INTO alvo_do_descarte VALUES (?)", [[i] for i in ids])
    antes = contas.contar_afetadas(con, tabela)

    sistema = lake.sistema()
    sobras = sistema.glob(caminho(lake, tabela, em_descarte=True))
    if sobras:
        sistema.rm(sobras)
    trocas = []
    valores = pa.array(ids, type=pa.int64())
    for arquivo in sorted(sistema.glob(caminho(lake, tabela))):
        original = f"s3://{arquivo}" if not arquivo.startswith(("s3://", "/")) else arquivo
        with sistema.open(original, "rb") as entrada:
            tabela_arrow = pq.read_table(entrada)
        alvo = pc.is_in(tabela_arrow["id"], value_set=valores)
        if not pc.any(alvo).as_py():
            continue
        ano = original.rsplit("ano=", 1)[1].split(".")[0]
        provisorio = caminho(lake, tabela, ano, em_descarte=True)
        sistema.makedirs(provisorio.rsplit("/", 1)[0], exist_ok=True)  # no S3 não faz nada
        with sistema.open(provisorio, "wb") as saida:
            pq.write_table(_apagado(tabela_arrow, alvo, colunas), saida, compression="zstd")
        resultado.problemas += _conferir(con, original, provisorio, colunas)
        trocas.append((provisorio, original))
    if resultado.problemas:
        return resultado  # a original fica; a descartada fica em _em_descarte para investigar
    for provisorio, original in trocas:
        sistema.mv(provisorio, original)
    resultado.arquivos = len(trocas)
    depois = contas.contar_afetadas(con, tabela)
    resultado.contas = {codigo: (antes[codigo], depois[codigo]) for codigo in antes}
    return resultado


def aplicar(
    con: duckdb.DuckDBPyConnection, lake: Lake, referencia: date
) -> tuple[Prazo | None, list[Resultado]]:
    """Descarta tudo o que é alvo na data; devolve o prazo usado e o resultado por tabela."""
    vigente = prazo(con, referencia)
    return vigente, [
        descartar_tabela(con, lake, tabela, por_motivo)
        for tabela, por_motivo in sorted(alvos(con, referencia, vigente).items())
    ]


def criar(warehouse: Warehouse) -> None:
    with warehouse.conectar() as conexao, conexao.cursor() as cur:
        cur.execute(DDL)
        conexao.commit()


def registrar(
    warehouse: Warehouse,
    referencia: date,
    vigente: Prazo | None,
    resultados: list[Resultado],
    run_id: str | None = None,
) -> int:
    """Uma linha por tabela descartada; devolve quantas foram gravadas."""
    criar(warehouse)
    regra = vigente.texto if vigente else f"{PARAMETRO} não declarado: nada descartado por retenção"
    gravadas = 0
    with warehouse.conectar() as conexao, conexao.cursor() as cur:
        for r in resultados:
            if r.problemas or not r.linhas:
                continue
            cur.execute(
                "INSERT INTO lgpd.descarte (run_id, referencia, tabela, eliminadas, vencidas, "
                "regra_retencao, colunas, contas) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)",
                (
                    run_id,
                    referencia,
                    r.tabela,
                    r.eliminadas,
                    r.vencidas,
                    regra,
                    r.colunas,
                    json.dumps({c: list(par) for c, par in r.contas.items()}),
                ),
            )
            gravadas += 1
        conexao.commit()
    return gravadas


def elos(warehouse: Warehouse) -> list[contas.Elo]:
    """Os descartes registrados, como elos da cadeia de custódia de cada regra."""
    criar(warehouse)
    linhas = warehouse.consultar("SELECT id, executado_em, contas FROM lgpd.descarte ORDER BY id")
    cadeia = []
    for identificador, quando, por_regra in linhas:
        dados = por_regra if isinstance(por_regra, dict) else json.loads(por_regra)
        rotulo = f"{quando:%d/%m/%Y %H:%M} (#{identificador})"
        cadeia += [
            contas.Elo(rotulo, codigo, int(antes), int(depois), int(identificador))
            for codigo, (antes, depois) in dados.items()
        ]
    return cadeia
