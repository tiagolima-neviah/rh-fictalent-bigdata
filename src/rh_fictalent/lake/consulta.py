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

Duas escolhas ditas:

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
}
VARIAVEL_DAS_EXTENSOES = "DUCKDB_EXTENSION_DIRECTORY"  # onde a imagem pré-instala o httpfs


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
