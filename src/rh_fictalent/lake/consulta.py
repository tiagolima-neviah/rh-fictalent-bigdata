"""DuckDB sobre a bronze: o lake lido como um banco, com os nomes da réplica.

A bronze é parquet no lake. Ler parquet com pandas funciona para uma tabela; para perguntar
"quantos alocados por posto e mês, com o preço vigente" é preciso SQL sobre várias tabelas de
uma vez, e é isso que o DuckDB dá ([ADR-0005](../../docs/adr/0005-duckdb-parquet-medalhao.md)):
um motor SQL embarcado que lê os arquivos onde estão e não guarda nada.

A conexão que este módulo abre tem **uma view por tabela, com o nome que a tabela tem na
réplica**: `ats.candidato`, `pessoas.alocacao`, `financeiro.fatura`. O SQL escrito para o MySQL
roda aqui quase sem mexer, e quem sabe SQL (que é o caso de quem vai auditar) não precisa
aprender uma API para começar. As fontes públicas entram como `fontes.municipios` e
`fontes.feriados`, a planilha como `arquivo.consolidado_gerencial`, a trilha de exclusões como
`meta.exclusao_auditoria`.

Três escolhas ditas:

- **As views são cruas.** Toda linha da bronze aparece, inclusive as marcadas como excluídas
  (`excluido_em` preenchido). Filtrar é do consulente: `WHERE excluido_em IS NULL`. A bronze é
  o espelho, e esconder a linha morta na view seria a silver começando cedo demais.
- **O DuckDB fala com o S3 pela extensão `httpfs` dele**, configurada a partir do mesmo recurso
  `Lake` que escreve os parquets (endpoint, chave, segredo, bucket: um lugar só). A alternativa
  era registrar o `fsspec` do `Lake` no DuckDB, e a primeira medição, com uma tabela, dizia que
  a diferença era de 270 ms. Com o lake inteiro ela vira outra coisa: contar as linhas vivas
  das 76 tabelas leva 0,3 s pelo `httpfs` e 14 s pelo `fsspec` (cada arquivo é uma ida ao
  Python), e um join de 4,3 milhões por 1,2 milhão de linhas leva 0,09 s contra 2,7 s. A
  extensão é instalada na imagem do Dagster em tempo de build, para o container não depender
  de rede na primeira consulta.
- **As conexões com o lake são reaproveitadas** (`httpfs_connection_caching`). Criar as 79
  views lê a lista e o rodapé de cerca de 700 arquivos, e por padrão o `httpfs` abre uma
  conexão TCP nova para cada pedido. Cada conexão fechada fica um minuto em espera no sistema
  (`TIME_WAIT`) segurando uma porta, e há 28 mil portas: abrir as views umas 37 vezes em menos
  de um minuto esgota as portas, e o lake passa a recusar pedidos ("Failure when receiving data
  from the peer") até a fila esvaziar. Foi a queda de 24/09, que parecia aleatória e não era.
  Medido em 01/10/2026: 1.421 sockets em espera por abertura sem o reaproveitamento, 18 com ele.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import duckdb
import pandas as pd

from rh_fictalent.ingestao.backfill import CAMADA, CONTROLE, identificador
from rh_fictalent.ingestao.exclusoes import TRILHA
from rh_fictalent.ingestao.planilhas import MODULO as MODULO_ARQUIVO
from rh_fictalent.ingestao.planilhas import TABELA as TABELA_ARQUIVO
from rh_fictalent.staging.gatilhos import tabelas_por_modulo

if TYPE_CHECKING:  # pragma: no cover
    import pymysql

    from rh_fictalent.orquestracao.recursos import Lake

ESQUEMA_FONTES = "fontes"
FONTES = {  # view -> caminho no lake, relativo ao bucket
    "municipios": "fontes/ibge/municipios.parquet",
    "feriados": "fontes/brasilapi/feriados/ano=*.parquet",
    "caged_movimentacao": "fontes/caged/movimentacao.parquet",
}
ASSETS_DAS_FONTES = {  # view -> (provedor, conjunto) do asset que a grava, para a linhagem da gold
    "municipios": ("ibge", "municipios"),
    "feriados": ("brasilapi", "feriados"),
    "caged_movimentacao": ("caged", "movimentacao"),
}
VARIAVEL_DAS_EXTENSOES = "DUCKDB_EXTENSION_DIRECTORY"  # onde a imagem pré-instala o httpfs
VARIAVEL_DA_MEMORIA = "DUCKDB_MEMORY_LIMIT"  # ex.: 512MB; ausente = o DuckDB decide sozinho
VARIAVEL_DO_TEMPORARIO = "DUCKDB_TEMP_DIRECTORY"
PASTA_TEMPORARIA = "/tmp/duckdb"  # noqa: S108 # nosec B108 - dentro do container, só do processo


@dataclass(frozen=True)
class View:
    esquema: str
    nome: str
    caminho: str  # o glob dos parquets, com s3://

    @property
    def qualificado(self) -> str:
        return f"{self.esquema}.{self.nome}"


def catalogo(lake: Lake) -> list[View]:
    """Tudo o que a bronze tem, na ordem da DDL: as tabelas de negócio, a trilha, a planilha e
    as fontes públicas. Tabela nova na DDL vira view sozinha, como virou asset."""
    views = [
        View(modulo, tabela, lake.caminho(CAMADA, modulo, tabela, "ano=*.parquet"))
        for modulo, tabelas in tabelas_por_modulo().items()
        for tabela in tabelas
    ]
    views.append(View(TRILHA[0], TRILHA[1], lake.caminho(CAMADA, *TRILHA, "ano=*.parquet")))
    views.append(
        View(
            MODULO_ARQUIVO,
            TABELA_ARQUIVO,
            lake.caminho(CAMADA, MODULO_ARQUIVO, TABELA_ARQUIVO, "ano=*.parquet"),
        )
    )
    views += [View(ESQUEMA_FONTES, nome, f"s3://{lake.bucket}/{c}") for nome, c in FONTES.items()]
    return views


def _apontar_para_o_lake(con: duckdb.DuckDBPyConnection, lake: Lake) -> None:
    """O `httpfs` do DuckDB com a credencial e o endereço do recurso `Lake`, e nada além."""
    pasta = os.environ.get(VARIAVEL_DAS_EXTENSOES)
    if pasta:
        con.execute("SET extension_directory = ?", [pasta])
    con.execute("INSTALL httpfs")  # já instalada: não faz nada; senão baixa uma vez
    con.execute("LOAD httpfs")
    endereco = urlparse(lake.endpoint)
    con.execute("SET s3_endpoint = ?", [endereco.netloc])
    con.execute("SET s3_use_ssl = ?", [endereco.scheme == "https"])
    con.execute("SET s3_url_style = 'path'")  # o SeaweedFS não resolve bucket como subdomínio
    con.execute("SET s3_access_key_id = ?", [lake.chave])
    con.execute("SET s3_secret_access_key = ?", [lake.segredo])
    # reaproveitar a conexão TCP entre pedidos (ver "Três escolhas ditas", no topo)
    con.execute("SET httpfs_connection_caching = true")
    _limitar_a_memoria(con)


def _limitar_a_memoria(con: duckdb.DuckDBPyConnection) -> None:
    """O teto de memória do DuckDB, quando o ambiente o declara (os containers do Dagster).

    Sem teto, o DuckDB assume 80% da memória do container inteiro, e não do que sobra nele: no
    daemon do Dagster, que já ocupa uns 600 MB parado, o passo da maior tabela foi morto pelo
    kernel cinco vezes em 01/10/2026 (`oom_kill` no cgroup). Com o teto, o que não cabe vai
    para a pasta temporária, em disco. Fora do container a variável não existe e nada muda.
    """
    limite = os.environ.get(VARIAVEL_DA_MEMORIA)
    if not limite:
        return
    con.execute("SET memory_limit = ?", [limite])
    con.execute(
        "SET temp_directory = ?", [os.environ.get(VARIAVEL_DO_TEMPORARIO, PASTA_TEMPORARIA)]
    )


def abrir(lake: Lake) -> duckdb.DuckDBPyConnection:
    """Uma conexão DuckDB em memória com uma view por tabela da bronze, pelos nomes da réplica.

    `union_by_name` deixa o DuckDB juntar as nove partições de um ano mesmo que uma delas tenha
    nascido antes de a bronze ganhar a coluna de controle; hoje todas têm, e a opção é a rede
    de segurança para a próxima coluna que a bronze acrescentar. Os nomes vêm da DDL, não de
    quem consulta: por isso a montagem por f-string é aceitável aqui.
    """
    con = duckdb.connect()
    _apontar_para_o_lake(con, lake)
    for view in catalogo(lake):
        alvo = f'"{view.esquema}"."{view.nome}"'
        origem = f"read_parquet('{view.caminho}', union_by_name = true)"
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{view.esquema}"')
        ddl = f"CREATE OR REPLACE VIEW {alvo} AS SELECT * FROM {origem}"  # noqa: S608 # nosec B608
        con.execute(ddl)
    return con


CAMADA_SILVER = "silver"


def tabelas_da_silver() -> list[str]:
    """As tabelas que a silver publica: as de negócio da DDL e a planilha do consolidado."""
    nomes = [f"{m}.{t}" for m, tabelas in tabelas_por_modulo().items() for t in tabelas]
    return [*nomes, f"{MODULO_ARQUIVO}.{TABELA_ARQUIVO}"]


def criar_views_da_silver(
    con: duckdb.DuckDBPyConnection, caminhos: dict[str, str], catalogo: str = CAMADA_SILVER
) -> None:
    """Uma view por tabela da silver, em `silver.<modulo>.<tabela>`, **só com as linhas vivas**.

    A gold lê por aqui. A linha excluída no sistema do cliente não existe para o negócio
    (decisão 5 da matriz de barramento): filtrá-la na view, uma vez, é o que impede cada
    consulta da gold de esquecer o filtro. A coluna de controle sai junto, porque depois do
    filtro ela é sempre nula.
    """
    anexados = {
        r[0] for r in con.execute("SELECT database_name FROM duckdb_databases()").fetchall()
    }
    if catalogo not in anexados:
        con.execute(f"ATTACH ':memory:' AS {catalogo}")
    for tabela, caminho in caminhos.items():
        modulo, nome = tabela.split(".")
        origem = f"read_parquet('{caminho}', union_by_name = true)"
        con.execute(f'CREATE SCHEMA IF NOT EXISTS {catalogo}."{modulo}"')
        colunas = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {origem}").fetchall()}  # noqa: S608 # nosec B608
        if CONTROLE in colunas:
            vivas = f'SELECT * EXCLUDE ("{CONTROLE}") FROM {origem} WHERE "{CONTROLE}" IS NULL'  # noqa: S608 # nosec B608
        else:  # a planilha da gerência não vem da réplica: não tem linha excluída
            vivas = f"SELECT * FROM {origem}"  # noqa: S608 # nosec B608
        con.execute(f'CREATE OR REPLACE VIEW {catalogo}."{modulo}"."{nome}" AS {vivas}')


def criar_views_das_fontes(con: duckdb.DuckDBPyConnection, caminhos: dict[str, str]) -> None:
    """Uma view por fonte pública, em `fontes.<nome>`: dado de fora, sem linha excluída."""
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{ESQUEMA_FONTES}"')
    for nome, caminho in caminhos.items():
        origem = f"read_parquet('{caminho}', union_by_name = true)"
        con.execute(f'CREATE OR REPLACE VIEW "{ESQUEMA_FONTES}"."{nome}" AS SELECT * FROM {origem}')  # noqa: S608 # nosec B608


def abrir_silver(lake: Lake) -> duckdb.DuckDBPyConnection:
    """Uma conexão DuckDB com a silver, e só ela: `silver.ats.candidato`, `silver.pessoas.alocacao`.

    As fontes públicas entram junto, em `fontes.<nome>`: não têm dado pessoal e a gold precisa
    delas (o CAGED é a régua de fora). Não há view da bronze nesta conexão, de propósito: quem
    constrói a gold não alcança o dado pessoal em claro nem por engano.
    """
    con = duckdb.connect()
    _apontar_para_o_lake(con, lake)
    caminhos = {
        tabela: lake.caminho(CAMADA_SILVER, *tabela.split("."), "ano=*.parquet")
        for tabela in tabelas_da_silver()
    }
    criar_views_da_silver(con, caminhos)
    criar_views_das_fontes(con, {n: f"s3://{lake.bucket}/{c}" for n, c in FONTES.items()})
    return con


def sql(con: duckdb.DuckDBPyConnection, consulta: str, *parametros: Any) -> pd.DataFrame:
    """A consulta como DataFrame. Parâmetros posicionais viram `?` no SQL."""
    return con.execute(consulta, list(parametros) if parametros else None).df()


def vivas(con: duckdb.DuckDBPyConnection, esquema: str, tabela: str) -> int:
    """Linhas da tabela na bronze que não foram marcadas como excluídas."""
    alvo = f'"{esquema}"."{tabela}"'
    pergunta = f'SELECT count(*) FROM {alvo} WHERE "{CONTROLE}" IS NULL'  # noqa: S608 # nosec B608
    return int(con.execute(pergunta).fetchall()[0][0])


def contagens(con: duckdb.DuckDBPyConnection, lake: Lake) -> dict[str, int]:
    """Linhas vivas de cada tabela de negócio (e da trilha), pelo nome `modulo.tabela`."""
    return {
        v.qualificado: vivas(con, v.esquema, v.nome)
        for v in catalogo(lake)
        if v.esquema not in (ESQUEMA_FONTES, MODULO_ARQUIVO)
    }


def conservacao(
    con_replica: pymysql.connections.Connection[Any], lake: Lake
) -> dict[str, tuple[int, int]]:
    """Por tabela, (linhas vivas na bronze, linhas na réplica): o C-06 da régua.

    A bronze é lida com DuckDB e a réplica com a mesma conexão que o resto do pipeline usa.
    Não há foto consistente entre os dois lados (são dois sistemas), então uma carga em
    andamento pode acusar diferença momentânea; a conferência vale para a réplica parada ou
    logo depois de uma carga.
    """
    duck = abrir(lake)
    try:
        na_bronze = contagens(duck, lake)
    finally:
        duck.close()
    resultado: dict[str, tuple[int, int]] = {}
    with con_replica.cursor() as cur:
        for nome, vivas_na_bronze in na_bronze.items():
            modulo, tabela = nome.split(".")
            alvo = f"{identificador(modulo)}.{identificador(tabela)}"
            cur.execute(f"SELECT COUNT(*) FROM {alvo}")  # noqa: S608 # nosec B608
            (na_replica,) = cur.fetchone()
            resultado[nome] = (vivas_na_bronze, int(na_replica))
    return resultado


def divergentes(conservacao: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    return {nome: par for nome, par in conservacao.items() if par[0] != par[1]}
