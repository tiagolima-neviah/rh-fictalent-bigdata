"""A construção da gold: montar da silver, gravar em conferência, conferir e só então publicar.

É o mesmo padrão da silver (auditar antes de publicar), com as provas que cabem a um modelo
dimensional. Uma tabela da gold só chega ao endereço que o warehouse lê se:

1. **o grão se confirma**: a chave declarada não se repete nem vem vazia;
2. **toda referência existe**: cada chave de dimensão do fato está na dimensão publicada
   (a linha 0, "não se aplica", inclusive);
3. **os totais se conservam**: o que o modelo declara em `conservacoes` dá, na gold, o mesmo
   número que na silver, sem tolerância. Join que multiplica linha ou perde linha muda a soma;
4. **a dimensão de pessoa não identifica ninguém** e toda dimensão tem a linha 0;
5. **a partição é coerente**: fato sem ano vazio, e o que foi lido de volta do arquivo tem
   as linhas que foram montadas.

No lake, a dimensão é um arquivo (`gold/dim_cliente/dim_cliente.parquet`) e o fato é um arquivo
por ano da data de negócio (`gold/fato_faturamento/ano=2024.parquet`). A reprovada fica em
`gold/_em_conferencia/` e a publicada antes continua como estava.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rh_fictalent.gold import modelo
from rh_fictalent.gold.modelo import Tabela

if TYPE_CHECKING:
    import duckdb

    from rh_fictalent.orquestracao.recursos import Lake

CAMADA = "gold"
EM_CONFERENCIA = "_em_conferencia"
ESQUEMA = "gold"  # onde as tabelas da gold ficam na conexão


@dataclass
class Resultado:
    tabela: str
    linhas: int = 0
    conservado: dict[str, str] = field(default_factory=dict)  # o que se conserva -> o valor
    problemas: list[str] = field(default_factory=list)

    @property
    def aprovada(self) -> bool:
        return not self.problemas


def alvo(nome: str) -> str:
    return f"{ESQUEMA}.{nome}"


def montar(con: duckdb.DuckDBPyConnection, tabela: Tabela) -> str:
    """Roda o SQL do modelo sobre a silver e deixa o resultado em `gold.<nome>` na conexão."""
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {ESQUEMA}")
    con.execute(f"CREATE OR REPLACE TABLE {alvo(tabela.nome)} AS {tabela.sql}")
    return alvo(tabela.nome)


def _um(con: duckdb.DuckDBPyConnection, sql: str) -> object:
    return con.execute(sql).fetchall()[0][0]


def conferir(
    con: duckdb.DuckDBPyConnection, tabela: Tabela, relacao: str, montadas: int | None = None
) -> Resultado:
    """As provas da tabela em `relacao`; as dimensões referenciadas são lidas de `gold.<dim>`."""
    r = Resultado(tabela.nome)
    r.linhas = int(_um(con, f"SELECT count(*) FROM {relacao}"))  # type: ignore[call-overload]  # noqa: S608 # nosec B608
    if montadas is not None and montadas != r.linhas:
        r.problemas.append(f"montadas {montadas} linhas, lidas de volta {r.linhas}")
    colunas = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM {relacao}").fetchall()]  # noqa: S608 # nosec B608

    chave = ", ".join(tabela.chave)
    grupos = f"SELECT {chave} FROM {relacao} GROUP BY ALL HAVING count(*) > 1"  # noqa: S608 # nosec B608
    repetidas = _um(con, f"SELECT count(*) FROM ({grupos})")  # noqa: S608 # nosec B608
    if repetidas:
        r.problemas.append(f"grão quebrado: {repetidas} chaves ({chave}) repetidas")
    vazia = " OR ".join(f"{c} IS NULL" for c in tabela.chave)
    sem_chave = _um(con, f"SELECT count(*) FROM {relacao} WHERE {vazia}")  # noqa: S608 # nosec B608
    if sem_chave:
        r.problemas.append(f"{sem_chave} linhas com a chave ({chave}) vazia")

    for coluna, dimensao in tabela.referencias.items():
        orfas = _um(
            con,
            f"SELECT count(*) FROM {relacao} f WHERE f.{coluna} IS NULL "  # noqa: S608 # nosec B608
            f"OR NOT EXISTS (SELECT 1 FROM {alvo(dimensao)} d WHERE d.id = f.{coluna})",
        )
        if orfas:
            r.problemas.append(f"{orfas} linhas com {coluna} fora de {dimensao}")

    for c in tabela.conservacoes:
        na_gold = _um(con, f"SELECT {c.na_gold} FROM {relacao}")  # noqa: S608 # nosec B608
        na_silver = _um(con, c.na_silver)
        r.conservado[c.o_que] = str(na_gold)
        if (na_gold or 0) != (na_silver or 0):
            r.problemas.append(f"{c.o_que} não se conserva: gold {na_gold}, silver {na_silver}")

    if tabela.fato:
        sem_ano = _um(con, f"SELECT count(*) FROM {relacao} WHERE {tabela.particao} IS NULL")  # noqa: S608 # nosec B608
        if sem_ano:
            r.problemas.append(f"{sem_ano} linhas sem {tabela.particao}")
    else:
        zeros = _um(con, f"SELECT count(*) FROM {relacao} WHERE id = 0")  # noqa: S608 # nosec B608
        if zeros != 1:
            r.problemas.append(f'a linha 0 ("{modelo.NAO_SE_APLICA}") aparece {zeros} vezes')
    if tabela.nome in modelo.DIMENSOES_DE_PESSOA:
        identidade = sorted(set(colunas) & set(modelo.IDENTIDADE))
        if identidade:
            r.problemas.append(f"dimensão de pessoa com coluna de identidade: {identidade}")
    return r


def construir(
    con: duckdb.DuckDBPyConnection, tabelas: tuple[Tabela, ...] = modelo.TABELAS
) -> dict[str, Resultado]:  # noqa: E501
    """Monta e confere tudo na conexão, sem lake: é o que os testes e a exploração usam."""
    modelo.preparar(con)
    resultados = {}
    for tabela in tabelas:
        resultados[tabela.nome] = conferir(con, tabela, montar(con, tabela))
    return resultados


# ------------------------------------------------------------------ o lake


def pasta(lake: Lake, nome: str, em_conferencia: bool = False) -> str:
    etapa = (EM_CONFERENCIA,) if em_conferencia else ()
    return lake.caminho(CAMADA, *etapa, nome)


def leitura(lake: Lake, nome: str, em_conferencia: bool = False) -> str:
    """A expressão que lê a tabela do lake (o ano do fato já é coluna do arquivo)."""
    return f"read_parquet('{pasta(lake, nome, em_conferencia)}/*.parquet', union_by_name = true)"


def gravar(con: duckdb.DuckDBPyConnection, lake: Lake, tabela: Tabela) -> list[str]:
    """Escreve `gold.<nome>` na área de conferência; antes, limpa o que houver lá da tabela."""
    sistema = lake.sistema()
    destino = pasta(lake, tabela.nome, em_conferencia=True)
    sobras = sistema.glob(f"{destino}/*.parquet")
    if sobras:
        sistema.rm(sobras)
    sistema.makedirs(destino, exist_ok=True)  # no S3 não faz nada
    nome = alvo(tabela.nome)
    ordem = ", ".join(tabela.chave)
    if not tabela.fato:
        partes = [(f"{tabela.nome}.parquet", "")]
    else:
        anos = con.execute(f"SELECT DISTINCT {tabela.particao} FROM {nome} ORDER BY 1").fetchall()  # noqa: S608 # nosec B608
        partes = [(f"ano={int(a)}.parquet", f"WHERE {tabela.particao} = {int(a)}") for (a,) in anos]
    caminhos = []
    for arquivo, filtro in partes:
        caminho = f"{destino}/{arquivo}"
        con.execute(
            f"COPY (SELECT * FROM {nome} {filtro} ORDER BY {ordem}) "  # noqa: S608 # nosec B608
            f"TO '{caminho}' (FORMAT parquet, COMPRESSION zstd)"
        )
        caminhos.append(caminho)
    # quem escreveu foi o DuckDB: o fsspec guarda a listagem da pasta e não sabe do arquivo novo
    sistema.invalidate_cache()
    return caminhos


def ler_dimensoes(con: duckdb.DuckDBPyConnection, lake: Lake, tabela: Tabela) -> None:
    """As dimensões que a tabela referencia, lidas do endereço publicado, como `gold.<dim>`."""
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {ESQUEMA}")
    for dimensao in sorted(set(tabela.referencias.values())):
        publicada = f"SELECT * FROM {leitura(lake, dimensao)}"  # noqa: S608 # nosec B608
        con.execute(f"CREATE OR REPLACE VIEW {alvo(dimensao)} AS {publicada}")


def publicar(con: duckdb.DuckDBPyConnection, lake: Lake, tabela: Tabela) -> Resultado:
    """Monta, grava em conferência, confere o arquivo gravado e só então publica.

    A conexão é a de `lake.consulta.abrir_silver`. As dimensões referenciadas têm de estar
    publicadas (no Dagster, a dependência entre os assets garante a ordem).
    """
    modelo.preparar(con)
    ler_dimensoes(con, lake, tabela)
    nome = montar(con, tabela)
    montadas = int(_um(con, f"SELECT count(*) FROM {nome}"))  # type: ignore[call-overload]  # noqa: S608 # nosec B608
    escritos = gravar(con, lake, tabela)
    con.execute(f"DROP TABLE {nome}")
    if not escritos:  # fato sem linha nenhuma: não há arquivo a ler de volta
        return Resultado(tabela.nome, problemas=["nenhuma linha montada: a silver está vazia?"])
    resultado = conferir(con, tabela, leitura(lake, tabela.nome, em_conferencia=True), montadas)
    if resultado.aprovada:
        sistema = lake.sistema()
        destino = pasta(lake, tabela.nome)
        sistema.makedirs(destino, exist_ok=True)
        novos = {c.rsplit("/", 1)[1] for c in escritos}
        for origem in escritos:
            sistema.mv(origem, f"{destino}/{origem.rsplit('/', 1)[1]}")
        # o ano que deixou de existir não pode continuar publicado ao lado dos novos
        velhos = [
            c for c in sistema.glob(f"{destino}/*.parquet") if c.rsplit("/", 1)[1] not in novos
        ]
        if velhos:
            sistema.rm(velhos)
    return resultado
