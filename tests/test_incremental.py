"""A carga incremental: a marca d'água, a foto que precisa ser renovada, e o merge por partição.

Os testes que mexem na réplica alteram uma linha, conferem, e devolvem tudo ao lugar: o valor
original, o carimbo original e a partição recopiada. A base sintética continua sendo a que a
régua aprovou.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dagster as dg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from dotenv import dotenv_values

from rh_fictalent.ingestao import marca_dagua
from rh_fictalent.ingestao.incremental import (
    SOBREPOSICAO,
    agora_na_replica,
    marca_da_bronze,
    nova_foto,
    refazer,
    sincronizar,
)
from rh_fictalent.orquestracao.incremental import agenda_incremental, carga_incremental
from rh_fictalent.orquestracao.recursos import Lake, Replica, Warehouse

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
MODULO, TABELA = "comercial", "contrato"
TABELA_TESTE = "teste.marca_dagua_do_pytest"


def _porta(nome: str, padrao: int) -> int:
    return int(ENV.get(nome) or padrao)


def _viva(porta: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        return False
    return True


@pytest.fixture(scope="module")
def replica() -> Replica:
    senha, porta = ENV.get("PIPELINE_PASSWORD"), _porta("STAGING_PORT", 0)
    if not senha or not porta or not _viva(porta):
        pytest.skip("réplica fora do ar")
    return Replica(host="127.0.0.1", porta=porta, usuario="pipeline", senha=senha)


@pytest.fixture(scope="module")
def escritor() -> Replica:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), _porta("STAGING_PORT", 0)
    if not senha or not porta or not _viva(porta):
        pytest.skip("réplica fora do ar")
    return Replica(host="127.0.0.1", porta=porta, usuario="replicador", senha=senha)


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
def warehouse() -> Warehouse:
    senha, porta = ENV.get("DW_ADMIN_PASSWORD"), _porta("DW_PORT", 0)
    if not senha or not porta or not _viva(porta):
        pytest.skip("warehouse fora do ar")
    dw = Warehouse(
        host="127.0.0.1",
        porta=porta,
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=senha,
    )
    marca_dagua.criar(dw)
    return dw


@pytest.fixture
def alteracao(replica: Replica, escritor: Replica, lake: Lake) -> Iterator[dict[str, Any]]:
    """Altera um contrato de verdade e, no fim, devolve réplica e bronze ao estado anterior."""
    con, ec = replica.conectar(), escritor.conectar()
    with ec.cursor() as cur:
        cur.execute(
            "SELECT id, indice_reajuste, atualizado_em, YEAR(criado_em) FROM comercial.contrato "
            "WHERE YEAR(criado_em) = 2019 ORDER BY id LIMIT 1"
        )
        contrato, original, carimbo, ano = cur.fetchone()
    try:
        yield {
            "con": con,
            "ec": ec,
            "id": int(contrato),
            "original": original,
            "carimbo": carimbo,
            "ano": int(ano),
        }
    finally:
        with ec.cursor() as cur:
            cur.execute(
                "UPDATE comercial.contrato SET indice_reajuste = %s, atualizado_em = %s "
                "WHERE id = %s",
                (original, carimbo, contrato),
            )
            ec.commit()
        ec.close()
        refazer(con, lake, MODULO, TABELA)  # a bronze volta a ser o espelho do que a régua aprovou
        con.close()


def test_a_marca_dagua_mora_no_warehouse_e_e_um_upsert(warehouse: Warehouse) -> None:
    instante = datetime(2026, 9, 22, 10, 0, 0)
    marca_dagua.gravar(warehouse, marca_dagua.Marca(TABELA_TESTE, instante, 7, 2), "run-1")
    lida = marca_dagua.ler(warehouse)[TABELA_TESTE]
    assert (lida.marca, lida.linhas, lida.particoes) == (instante, 7, 2)
    depois = instante + timedelta(hours=1)
    marca_dagua.gravar(warehouse, marca_dagua.Marca(TABELA_TESTE, depois, 3, 1), "run-2")
    de_novo = marca_dagua.ler(warehouse)
    assert de_novo[TABELA_TESTE].marca == depois  # uma linha por tabela, sempre a última
    assert marca_dagua.apagar(warehouse, TABELA_TESTE) == 1
    assert TABELA_TESTE not in marca_dagua.ler(warehouse)


def test_o_corte_vem_do_relogio_da_replica(replica: Replica) -> None:
    con = replica.conectar()
    try:
        instante = agora_na_replica(con)
        with con.cursor() as cur:
            cur.execute("SELECT NOW(6)")
            (agora,) = cur.fetchone()
    finally:
        con.close()
    assert isinstance(instante, datetime) and instante.tzinfo is None
    assert abs((agora - instante).total_seconds()) < 60


def test_a_marca_inicial_e_o_maior_carimbo_que_a_bronze_tem(lake: Lake) -> None:
    derivada = marca_da_bronze(lake, MODULO, TABELA)
    assert derivada is not None
    quadro = lake.ler_parquet(lake.caminho("bronze", MODULO, TABELA, "ano=2019.parquet"))
    assert derivada >= quadro["atualizado_em"].max()
    assert marca_da_bronze(lake, MODULO, "tabela_que_nao_tem_bronze") is None


def test_a_foto_precisa_ser_renovada_entre_cargas(alteracao: dict[str, Any]) -> None:
    """O InnoDB lê em REPEATABLE READ: a transação que o driver abre na primeira leitura congela
    o que a conexão enxerga. Sem renovar a foto, a carga seguinte juraria que nada mudou. Este
    teste existe porque foi exatamente isso que aconteceu na primeira prova contra a réplica."""
    con, ec, contrato = alteracao["con"], alteracao["ec"], alteracao["id"]

    def lido() -> str:
        with con.cursor() as cur:
            cur.execute("SELECT indice_reajuste FROM comercial.contrato WHERE id = %s", (contrato,))
            (valor,) = cur.fetchone()
        return str(valor)

    antes = lido()  # esta leitura abre a foto
    with ec.cursor() as cur:
        cur.execute(
            "UPDATE comercial.contrato SET indice_reajuste = %s WHERE id = %s",
            ("IGPM_TESTE", contrato),
        )
        ec.commit()
    assert lido() == antes  # commitado lá fora, invisível aqui dentro: a foto é de antes
    nova_foto(con)
    assert lido() == "IGPM_TESTE"  # foto nova, mundo novo
    con.rollback()


def test_a_carga_traz_a_alteracao_e_a_bronze_volta_a_bater(
    alteracao: dict[str, Any], lake: Lake
) -> None:
    con, ec, contrato, ano = (
        alteracao["con"],
        alteracao["ec"],
        alteracao["id"],
        alteracao["ano"],
    )
    marca = agora_na_replica(con)
    with ec.cursor() as cur:
        cur.execute(
            "UPDATE comercial.contrato SET indice_reajuste = %s WHERE id = %s",
            ("IPCA_TESTE", contrato),
        )
        ec.commit()
    corte = agora_na_replica(con)
    resultado = sincronizar(con, lake, MODULO, TABELA, marca, corte)
    assert resultado.alteradas == 1
    assert list(resultado.particoes) == [ano]
    assert resultado.confere, resultado.divergencias
    quadro = lake.ler_parquet(lake.caminho("bronze", MODULO, TABELA, f"ano={ano}.parquet"))
    linha = quadro.loc[quadro["id"] == contrato]
    assert linha["indice_reajuste"].iloc[0] == "IPCA_TESTE"
    assert len(quadro) == resultado.particoes[ano]
    assert quadro["id"].is_monotonic_increasing  # o merge devolve a partição ordenada por id


def test_reaplicar_a_mesma_janela_nao_duplica(alteracao: dict[str, Any], lake: Lake) -> None:
    """A sobreposição faz a carga reler o que já leu. Reler tem de ser inofensivo, porque a
    aplicação é por id: a linha entra no lugar dela, não ao lado dela."""
    con, ec, contrato, ano = (
        alteracao["con"],
        alteracao["ec"],
        alteracao["id"],
        alteracao["ano"],
    )
    marca = agora_na_replica(con)
    with ec.cursor() as cur:
        cur.execute(
            "UPDATE comercial.contrato SET indice_reajuste = %s WHERE id = %s",
            ("INPC_TESTE", contrato),
        )
        ec.commit()
    corte = agora_na_replica(con)
    primeira = sincronizar(con, lake, MODULO, TABELA, marca, corte)
    segunda = sincronizar(con, lake, MODULO, TABELA, marca, corte)
    assert primeira.particoes == segunda.particoes
    assert segunda.confere
    quadro = lake.ler_parquet(lake.caminho("bronze", MODULO, TABELA, f"ano={ano}.parquet"))
    assert (quadro["id"] == contrato).sum() == 1
    assert quadro["id"].is_unique


def _adulterar(lake: Lake, caminho: str, id_novo: int | None) -> None:
    """Põe no parquet uma cópia da primeira linha: com o mesmo id (duplicata) ou com um id que
    não existe na réplica (a linha fantasma que um DELETE na origem deixaria para trás)."""
    with lake.sistema().open(caminho, "rb") as arquivo:
        tabela = pq.read_table(arquivo)
    copia = tabela.slice(0, 1).to_pydict()
    if id_novo is not None:
        copia["id"] = [id_novo]
    extra = pa.Table.from_pydict(copia, schema=tabela.schema)
    with lake.sistema().open(caminho, "wb") as arquivo:
        pq.write_table(pa.concat_tables([tabela, extra]), arquivo, compression="zstd")


def test_a_carga_conserta_sozinha_uma_linha_repetida_na_bronze(
    replica: Replica, lake: Lake
) -> None:
    """Merge por id: antes de gravar a versão nova, **todas** as linhas com aquele id saem. Uma
    duplicata que tenha entrado por qualquer motivo desaparece na primeira carga que a tocar."""
    con = replica.conectar()
    caminho = lake.caminho("bronze", MODULO, TABELA, "ano=2019.parquet")
    try:
        antes = len(lake.ler_parquet(caminho))
        _adulterar(lake, caminho, id_novo=None)
        assert len(lake.ler_parquet(caminho)) == antes + 1
        marca = agora_na_replica(con) - timedelta(days=3650)  # janela larga: relê a tabela toda
        resultado = sincronizar(con, lake, MODULO, TABELA, marca, agora_na_replica(con))
        assert resultado.confere, resultado.divergencias
        quadro = lake.ler_parquet(caminho)
        assert len(quadro) == antes and quadro["id"].is_unique
    finally:
        refazer(con, lake, MODULO, TABELA)
        con.close()


def test_a_conferencia_acusa_a_linha_que_so_existe_na_bronze(replica: Replica, lake: Lake) -> None:
    """Linha que existe na bronze e não na réplica, sem uma exclusão na trilha que a explique:
    a carga não conserta (ela não sabe de onde veio) e não finge que consertou, acusa. Quando a
    causa é um `DELETE` de verdade, a trilha explica e a marcação resolve (card 5.3); quando não
    há trilha que explique, como aqui, o que sobra é a conferência dizendo que algo está errado."""
    con = replica.conectar()
    caminho = lake.caminho("bronze", MODULO, TABELA, "ano=2019.parquet")
    try:
        antes = len(lake.ler_parquet(caminho))
        _adulterar(lake, caminho, id_novo=10_000_000)
        marca = agora_na_replica(con) - timedelta(days=3650)
        resultado = sincronizar(con, lake, MODULO, TABELA, marca, agora_na_replica(con))
        assert not resultado.confere
        (divergencia,) = [d for d in resultado.divergencias if "/2019" in d]
        assert "linhas vivas na bronze" in divergencia and "diferença de 1" in divergencia
    finally:
        refazer(con, lake, MODULO, TABELA)
        assert len(lake.ler_parquet(caminho)) == antes
        con.close()


def test_refazer_recopia_a_tabela_inteira(replica: Replica, lake: Lake) -> None:
    con = replica.conectar()
    try:
        resultado = refazer(con, lake, MODULO, TABELA)
    finally:
        con.close()
    assert resultado.confere and len(resultado.particoes) == 9
    assert sum(resultado.particoes.values()) == resultado.alteradas > 0


def test_a_agenda_roda_de_madrugada_e_o_job_conhece_o_logger_json() -> None:
    assert agenda_incremental.cron_schedule == "0 5 * * *"
    assert agenda_incremental.execution_timezone == "America/Sao_Paulo"
    assert agenda_incremental.job.name == "carga_incremental"
    assert "json" in carga_incremental.loggers  # um @job não herda os loggers das Definitions


def test_o_job_materializa_as_particoes_que_tocou_e_grava_a_marca(
    alteracao: dict[str, Any], replica: Replica, lake: Lake, warehouse: Warehouse
) -> None:
    con, ec, contrato, ano = (
        alteracao["con"],
        alteracao["ec"],
        alteracao["id"],
        alteracao["ano"],
    )
    marca_dagua.apagar(warehouse, f"{MODULO}.{TABELA}")
    with ec.cursor() as cur:
        cur.execute(
            "UPDATE comercial.contrato SET indice_reajuste = %s WHERE id = %s",
            ("TR_TESTE", contrato),
        )
        ec.commit()
    resultado = carga_incremental.execute_in_process(
        run_config={
            "ops": {"sincronizar_bronze": {"config": {"tabelas": [f"{MODULO}.{TABELA}"]}}},
            "loggers": {"json": {"config": {"nivel": "INFO"}}},
        },
        resources={"replica": replica, "lake": lake, "warehouse": warehouse},
    )
    assert resultado.success
    eventos = resultado.get_asset_materialization_events()
    assert eventos, "a carga tem de publicar o que reescreveu"
    chaves = {
        (tuple(e.asset_key.path), e.materialization.partition)
        for e in eventos
        if e.asset_key is not None
    }
    assert (("bronze", MODULO, TABELA), str(ano)) in chaves
    marca = marca_dagua.ler(warehouse)[f"{MODULO}.{TABELA}"]
    assert marca.linhas >= 1 and marca.marca <= agora_na_replica(con)


def test_carga_com_tabela_desconhecida_falha_em_vez_de_nao_fazer_nada(
    replica: Replica, lake: Lake, warehouse: Warehouse
) -> None:
    with pytest.raises(dg.Failure, match="nenhuma tabela conhecida"):
        carga_incremental.execute_in_process(
            run_config={
                "ops": {"sincronizar_bronze": {"config": {"tabelas": ["cadastro.inexistente"]}}},
                "loggers": {"json": {"config": {"nivel": "INFO"}}},
            },
            resources={"replica": replica, "lake": lake, "warehouse": warehouse},
        )


def test_a_sobreposicao_e_declarada_e_generosa() -> None:
    """Não é número mágico: é a folga contra a transação que grava antes e commita depois."""
    assert timedelta(minutes=30) <= SOBREPOSICAO
