"""A silver de uma tabela: a bronze, linha a linha, mais as colunas que o catálogo aprovou.

A silver tem o mesmo grão da bronze (uma linha da réplica, uma linha da silver) e as mesmas
colunas, com os mesmos valores, na mesma ordem. Depois delas vêm as colunas das regras
(`silver.regras`), na ordem do catálogo. Tabela sem regra atravessa igual: a silver é a
camada que o resto do pipeline lê, e a gold não precisa saber quais tabelas tinham defeito.

A construção se prova sozinha, tabela a tabela (`conferir`), e reprova se:

1. a silver não tem o mesmo número de linhas da bronze, no total e em cada ano;
2. alguma coluna original mudou de valor ou de tipo em alguma linha (a comparação é da
   tabela inteira, `EXCEPT ALL` nos dois sentidos, não de uma amostra);
3. as colunas não são as da bronze seguidas das novas, na ordem;
4. alguma marca `q_` está preenchida em linha excluída, ou vazia em linha viva.

A prestação de contas contra a auditoria (a marca atinge o número de linhas que o achado
gravou) é de outro módulo, `silver.contas`, porque depende da data da auditoria, e não da
data de hoje.

No lake, a silver repete o endereço da bronze trocando a camada: `silver/<modulo>/<tabela>/
ano=<ano>.parquet`, o mesmo arquivo por ano de criação da linha. A tabela só chega a esse
endereço depois de aprovada (`publicar`): antes, ela é gravada e conferida em
`silver/_em_conferencia/`, e a reprovada nunca substitui a que a gold já lê.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import duckdb

from rh_fictalent.ingestao import marca_dagua
from rh_fictalent.ingestao.backfill import CAMADA as CAMADA_BRONZE
from rh_fictalent.ingestao.backfill import CONTROLE
from rh_fictalent.ingestao.planilhas import MODULO as MODULO_ARQUIVO
from rh_fictalent.ingestao.planilhas import TABELA as TABELA_ARQUIVO
from rh_fictalent.silver import regras
from rh_fictalent.staging.gatilhos import tabelas_por_modulo

if TYPE_CHECKING:  # pragma: no cover
    from rh_fictalent.orquestracao.recursos import Lake, Warehouse

CAMADA = "silver"
EM_CONFERENCIA = "_em_conferencia"  # onde a tabela espera a conferência antes de publicar
ANO = "_ano"  # a coluna de trabalho com o ano do arquivo; não vai para o lake
ARQUIVO = "ano=*.parquet"

# as tabelas de negócio da DDL, na ordem dos arquivos, e a planilha do consolidado; a trilha
# de exclusões é infraestrutura da carga e as fontes públicas não são do cliente
TABELAS: tuple[str, ...] = (
    *(f"{m}.{t}" for m, tabelas in tabelas_por_modulo().items() for t in tabelas),
    f"{MODULO_ARQUIVO}.{TABELA_ARQUIVO}",
)


@dataclass(frozen=True)
class Nova:
    """Uma coluna que a silver acrescenta: de que regra, e se é marca."""

    nome: str
    codigo: str
    tabela_da_regra: str  # regra.<nome>, onde a derivação foi materializada

    @property
    def marca(self) -> bool:
        return self.nome.startswith("q_")


@dataclass
class Resultado:
    tabela: str
    linhas: int = 0
    por_ano: dict[int, int] = field(default_factory=dict)
    marcas: dict[str, int] = field(default_factory=dict)  # q_ -> linhas marcadas
    problemas: list[str] = field(default_factory=list)

    @property
    def aprovada(self) -> bool:
        return not self.problemas


def novas(tabela: str) -> list[Nova]:
    """As colunas que as regras acrescentam à tabela, na ordem do catálogo."""
    return [
        Nova(coluna, regra.codigo, f"regra.{regra.nome(derivacao)}")
        for regra, derivacao in regras.por_tabela().get(tabela, [])
        for coluna in derivacao.colunas
    ]


def _q(identificador: str) -> str:
    return f'"{identificador}"'


def alvo(tabela: str) -> str:
    """O nome da tabela da silver dentro da conexão: `silver."modulo"."tabela"`."""
    modulo, nome = tabela.split(".")
    return f"silver.{_q(modulo)}.{_q(nome)}"


def com_ano(caminho: str) -> str:
    """Os parquets de um glob como relação, com o ano tirado do nome do arquivo."""
    # o caminho vem do recurso Lake e dos nomes da DDL, nunca de quem consulta
    return (
        "(SELECT * EXCLUDE (filename), "  # nosec B608
        f"CAST(regexp_extract(filename, 'ano=(\\d+)', 1) AS INTEGER) AS {ANO} "
        f"FROM read_parquet('{caminho}', union_by_name = true, filename = true))"
    )


def sql_da_silver(tabela: str, origem: str) -> str:
    """O SELECT que monta a silver: a origem inteira e as colunas das derivações, pelo `id`."""
    partes = ["b.*"]
    juncoes = []
    apelidos: dict[str, str] = {}
    for coluna in novas(tabela):
        apelido = apelidos.setdefault(coluna.tabela_da_regra, f"d{len(apelidos)}")
        if coluna.marca:
            valor = f"coalesce({apelido}.{coluna.nome}, FALSE)"
            partes.append(f"CASE WHEN b.{CONTROLE} IS NULL THEN {valor} END AS {coluna.nome}")
        else:
            partes.append(f"{apelido}.{coluna.nome} AS {coluna.nome}")
    for tabela_da_regra, apelido in apelidos.items():
        juncoes.append(f"LEFT JOIN {tabela_da_regra} {apelido} ON {apelido}.id = b.id")
    return f"SELECT {', '.join(partes)} FROM {origem} b {' '.join(juncoes)}"  # noqa: S608 # nosec B608


def construir(con: duckdb.DuckDBPyConnection, tabela: str, origem: str, referencia: date) -> str:
    """Monta a silver da tabela na conexão (sem gravar) e devolve o nome dela.

    `origem` é a bronze da tabela com a coluna `_ano`; as regras leem a bronze pelas views com
    os nomes da réplica, que a conexão já precisa ter (`lake.consulta.abrir`, ou tabelas de
    teste com os mesmos nomes).
    """
    regras.preparar(con, referencia)
    for regra, derivacao in regras.por_tabela().get(tabela, []):
        regras.derivar(con, regra, derivacao)
    anexados = {
        linha[0] for linha in con.execute("SELECT database_name FROM duckdb_databases()").fetchall()
    }
    if CAMADA not in anexados:
        con.execute(f"ATTACH ':memory:' AS {CAMADA}")
    modulo = tabela.split(".")[0]
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {CAMADA}.{_q(modulo)}")
    nome = alvo(tabela)
    con.execute(f"CREATE OR REPLACE TABLE {nome} AS {sql_da_silver(tabela, origem)}")  # noqa: S608 # nosec B608
    return nome


def _colunas(con: duckdb.DuckDBPyConnection, relacao: str) -> list[tuple[str, str]]:
    descricao = con.execute(f"DESCRIBE SELECT * FROM {relacao}").fetchall()  # noqa: S608 # nosec B608
    return [(str(linha[0]), str(linha[1])) for linha in descricao]


def _numero(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    return int(con.execute(sql).fetchall()[0][0])


def conferir(con: duckdb.DuckDBPyConnection, tabela: str, bronze: str, silver: str) -> Resultado:
    """As quatro provas da construção (ver o topo do módulo), sobre duas relações com `_ano`."""
    resultado = Resultado(tabela)
    colunas_bronze = [c for c in _colunas(con, bronze) if c[0] != ANO]
    colunas_silver = [c for c in _colunas(con, silver) if c[0] != ANO]
    esperadas = [n.nome for n in novas(tabela)]
    nomes_bronze = [c for c, _ in colunas_bronze]
    vieram = [c for c, _ in colunas_silver]
    if vieram != nomes_bronze + esperadas:
        resultado.problemas.append(
            f"colunas: esperadas as da bronze e depois {esperadas}, vieram {vieram}"
        )
        return resultado  # sem as colunas certas, as outras provas não fazem sentido
    tipos_silver = dict(colunas_silver)
    mudou = [f"{c} ({t} -> {tipos_silver[c]})" for c, t in colunas_bronze if tipos_silver[c] != t]
    if mudou:
        resultado.problemas.append(f"tipo mudou: {', '.join(mudou)}")

    anos_bronze = dict(con.execute(f"SELECT {ANO}, count(*) FROM {bronze} GROUP BY 1").fetchall())  # noqa: S608 # nosec B608
    anos_silver = dict(con.execute(f"SELECT {ANO}, count(*) FROM {silver} GROUP BY 1").fetchall())  # noqa: S608 # nosec B608
    resultado.por_ano = {int(a): int(n) for a, n in sorted(anos_silver.items())}
    resultado.linhas = sum(resultado.por_ano.values())
    if anos_bronze != anos_silver:
        resultado.problemas.append(
            f"linhas por ano: bronze {sorted(anos_bronze.items())}, "
            f"silver {sorted(anos_silver.items())}"
        )

    originais = ", ".join(_q(c) for c in nomes_bronze)
    for de, para, sentido in (
        (bronze, silver, "na bronze e não na silver"),
        (silver, bronze, "na silver e não na bronze"),
    ):
        diferenca = f"SELECT {originais} FROM {de} EXCEPT ALL SELECT {originais} FROM {para}"  # noqa: S608 # nosec B608
        sql = f"SELECT count(*) FROM ({diferenca})"  # noqa: S608 # nosec B608
        diferentes = _numero(con, sql)
        if diferentes:
            resultado.problemas.append(f"valores originais: {diferentes} linhas {sentido}")

    for coluna in (n for n in novas(tabela) if n.marca):
        sql = (  # noqa: S608
            f"SELECT count(*) FILTER (WHERE {coluna.nome}), "  # nosec B608
            f"count(*) FILTER (WHERE ({CONTROLE} IS NULL) <> ({coluna.nome} IS NOT NULL)) "
            f"FROM {silver}"
        )
        marcadas, fora_do_lugar = con.execute(sql).fetchall()[0]
        resultado.marcas[coluna.nome] = int(marcadas)
        if fora_do_lugar:
            resultado.problemas.append(
                f"{coluna.nome}: {fora_do_lugar} linhas com a marca vazia em linha viva "
                "ou preenchida em linha excluída"
            )
    return resultado


def referencia_atual(warehouse: Warehouse) -> date:
    """O "hoje" do dado: o dia da marca d'água mais recente da carga, como na auditoria."""
    marcas = marca_dagua.ler(warehouse)
    return max(m.marca for m in marcas.values()).date()


def caminho_bronze(lake: Lake, tabela: str) -> str:
    return lake.caminho(CAMADA_BRONZE, *tabela.split("."), ARQUIVO)


def caminho_silver(
    lake: Lake, tabela: str, ano: int | str = "*", em_conferencia: bool = False
) -> str:
    etapa = (EM_CONFERENCIA,) if em_conferencia else ()
    return lake.caminho(CAMADA, *etapa, *tabela.split("."), f"ano={ano}.parquet")


def gravar(
    con: duckdb.DuckDBPyConnection, lake: Lake, tabela: str, em_conferencia: bool = True
) -> list[str]:
    """Escreve a silver montada na conexão no lake, um parquet por ano, ordenado pela chave.

    Por padrão escreve na área de conferência, nunca direto no endereço que a gold lê; antes,
    apaga o que uma conferência anterior da mesma tabela tenha deixado lá.
    """
    sistema = lake.sistema()
    if em_conferencia:
        sobras = sistema.glob(caminho_silver(lake, tabela, em_conferencia=True))
        if sobras:
            sistema.rm(sobras)
    nome = alvo(tabela)
    colunas = [c for c, _ in _colunas(con, nome)]
    ordem = "id" if "id" in colunas else "ALL"
    caminhos = []
    for (ano,) in con.execute(f"SELECT DISTINCT {ANO} FROM {nome} ORDER BY 1").fetchall():  # noqa: S608 # nosec B608
        caminho = caminho_silver(lake, tabela, int(ano), em_conferencia)
        sistema.makedirs(caminho.rsplit("/", 1)[0], exist_ok=True)  # no S3 não faz nada
        do_ano = f"SELECT * EXCLUDE ({ANO}) FROM {nome} WHERE {ANO} = {int(ano)} ORDER BY {ordem}"  # noqa: S608 # nosec B608
        con.execute(f"COPY ({do_ano}) TO '{caminho}' (FORMAT parquet, COMPRESSION zstd)")
        caminhos.append(caminho)
    return caminhos


def publicar(
    con: duckdb.DuckDBPyConnection, lake: Lake, tabela: str, referencia: date
) -> Resultado:
    """Monta, grava na área de conferência, confere e só então publica.

    É o padrão auditar antes de publicar: a conferência lê de volta o arquivo gravado (não o
    que ficou na memória), e só a tabela aprovada é movida para `silver/<modulo>/<tabela>`, o
    endereço que a gold lê. A reprovada fica em `silver/_em_conferencia/` para quem for
    investigar, e a silver publicada antes dela continua como estava.
    """
    nome = construir(con, tabela, com_ano(caminho_bronze(lake, tabela)), referencia)
    escritos = gravar(con, lake, tabela, em_conferencia=True)
    con.execute(f"DROP TABLE {nome}")  # já está no lake; a memória fica para a próxima tabela
    resultado = conferir(
        con,
        tabela,
        com_ano(caminho_bronze(lake, tabela)),
        com_ano(caminho_silver(lake, tabela, em_conferencia=True)),
    )
    if resultado.aprovada:
        sistema = lake.sistema()
        for origem in escritos:
            ano = origem.rsplit("ano=", 1)[1].split(".")[0]
            destino = caminho_silver(lake, tabela, ano)
            sistema.makedirs(destino.rsplit("/", 1)[0], exist_ok=True)  # no S3 não faz nada
            sistema.mv(origem, destino)
    return resultado
