"""DuckDB sobre a bronze: as views com os nomes da réplica, e a conservação entre as camadas."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from dotenv import dotenv_values

from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao.conservacao import conferir_bronze
from rh_fictalent.orquestracao.recursos import Lake, Replica
from rh_fictalent.validacao import bandas

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def _viva(porta: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        return False
    return True


@pytest.fixture(scope="module")
def replica() -> Replica:
    senha, porta = ENV.get("PIPELINE_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta or not _viva(porta):
        pytest.skip("réplica fora do ar")
    return Replica(host="127.0.0.1", porta=porta, usuario="pipeline", senha=senha)


@pytest.fixture(scope="module")
def lake() -> Lake:
    chave, segredo = ENV.get("S3_ACCESS_KEY"), ENV.get("S3_SECRET_KEY")
    if not chave or not segredo or not _viva(8333):
        pytest.skip("lake fora do ar")
    return Lake(
        endpoint="http://127.0.0.1:8333",
        chave=chave,
        segredo=segredo,
        bucket=ENV.get("S3_BUCKET") or "fictalent-lake",
    )


@pytest.fixture(scope="module")
def duck(lake: Lake) -> Iterator[duckdb.DuckDBPyConnection]:
    con = consulta.abrir(lake)
    yield con
    con.close()


def test_o_catalogo_tem_tudo_o_que_a_bronze_tem(lake: Lake) -> None:
    views = consulta.catalogo(lake)
    nomes = {v.qualificado for v in views}
    assert len(views) == 79  # 75 de negócio, a trilha, a planilha, duas fontes públicas
    assert {"ats.candidato", "meta.exclusao_auditoria", "arquivo.consolidado_gerencial"} <= nomes
    assert {"fontes.municipios", "fontes.feriados"} <= nomes
    for v in views:
        assert v.caminho.startswith(f"s3://{lake.bucket}/")


def test_as_views_tem_os_nomes_da_replica_e_o_sql_do_mysql_roda(
    duck: duckdb.DuckDBPyConnection, replica: Replica
) -> None:
    """Quem sabe SQL não precisa aprender API: o mesmo SELECT dá o mesmo número nos dois lados."""
    pergunta = (
        "SELECT k.tipo_servico, COUNT(*) AS alocacoes FROM pessoas.alocacao a "
        "JOIN comercial.posto p ON p.id = a.posto_id "
        "JOIN comercial.contrato k ON k.id = p.contrato_id "
        "GROUP BY k.tipo_servico ORDER BY k.tipo_servico"
    )
    no_lake = [(str(t), int(n)) for t, n in duck.execute(pergunta).fetchall()]
    na_replica = [(str(t), int(n)) for t, n in replica.consultar(pergunta)]
    assert no_lake == na_replica and len(no_lake) >= 2


def test_sql_devolve_dataframe_com_parametros(duck: duckdb.DuckDBPyConnection) -> None:
    quadro = consulta.sql(duck, "SELECT id, razao_social FROM comercial.cliente WHERE id <= ?", 3)
    assert list(quadro.columns) == ["id", "razao_social"] and len(quadro) == 3


def test_as_views_sao_cruas_e_vivas_filtra_a_coluna_de_controle(
    duck: duckdb.DuckDBPyConnection,
) -> None:
    (todas,) = duck.execute("SELECT count(*) FROM comercial.contrato").fetchall()[0]
    (sem_marca,) = duck.execute(
        "SELECT count(*) FROM comercial.contrato WHERE excluido_em IS NULL"
    ).fetchall()[0]
    assert consulta.vivas(duck, "comercial", "contrato") == int(sem_marca) <= int(todas)
    assert "excluido_em" in [c[0] for c in duck.execute("DESCRIBE comercial.contrato").fetchall()]


def test_as_fontes_e_a_planilha_entram_como_views(duck: duckdb.DuckDBPyConnection) -> None:
    """As fontes públicas e a planilha não são tabelas da réplica, mas são bronze: entram com
    esquema próprio. A data dos feriados chega como texto da API, e a view é crua: é assim."""
    (municipios,) = duck.execute("SELECT count(*) FROM fontes.municipios").fetchall()[0]
    (feriados,) = duck.execute("SELECT count(*) FROM fontes.feriados").fetchall()[0]
    (consolidado,) = duck.execute("SELECT count(*) FROM arquivo.consolidado_gerencial").fetchall()[
        0
    ]
    assert int(municipios) > 1000 and int(feriados) >= 8 and int(consolidado) == 237


def test_a_conservacao_replica_bronze_fecha_em_todas_as_tabelas(
    replica: Replica, lake: Lake
) -> None:
    con = replica.conectar()
    try:
        conservacao = consulta.conservacao(con, lake)
    finally:
        con.close()
    assert len(conservacao) == 76
    assert consulta.divergentes(conservacao) == {}, consulta.divergentes(conservacao)
    assert sum(v for v, _ in conservacao.values()) > 8_000_000


def test_divergentes_aponta_so_o_que_difere() -> None:
    cons = {"a.b": (10, 10), "c.d": (9, 10), "e.f": (11, 10)}
    assert consulta.divergentes(cons) == {"c.d": (9, 10), "e.f": (11, 10)}


def test_o_c06_existe_na_regua_e_le_a_medida_de_conservacao() -> None:
    (c06,) = [c for c in bandas.checks() if c.codigo == "C-06"]
    assert (c06.familia, c06.medida, c06.chave) == ("coerencia", "conservacao", "bronze")
    assert "conservacao" in bandas.MEDIDAS
    assert len(bandas.checks()) == 166


def test_o_job_conferir_bronze_roda_verde(replica: Replica, lake: Lake) -> None:
    resultado = conferir_bronze.execute_in_process(
        run_config={"loggers": {"json": {"config": {"nivel": "INFO"}}}},
        resources={"replica": replica, "lake": lake},
    )
    assert resultado.success
