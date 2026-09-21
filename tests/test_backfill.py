"""O backfill: espelho fiel da réplica em parquet, com a contagem conferida na mesma foto."""

from __future__ import annotations

import socket
from datetime import date, datetime
from pathlib import Path
from typing import Any

import dagster as dg
import pyarrow as pa
import pytest
from dotenv import dotenv_values

from rh_fictalent.ingestao import backfill
from rh_fictalent.orquestracao.bronze import ASSETS, ORIGENS, TABELAS
from rh_fictalent.orquestracao.recursos import Lake, Replica
from rh_fictalent.staging.gatilhos import MODULOS_DE_NEGOCIO

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
# uma tabela pequena, uma com booleano, uma grande: cobre tipo, volume e leitura em lote
AMOSTRA = (
    ("cadastro", "filial", 2018),
    ("comercial", "cliente", 2019),
    ("ponto", "apontamento", 2024),
)


def _replica() -> Replica | None:
    senha, porta = ENV.get("PIPELINE_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        return None
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        return None
    return Replica(host="127.0.0.1", porta=porta, usuario="pipeline", senha=senha)


def _lake() -> Lake | None:
    chave, segredo = ENV.get("S3_ACCESS_KEY"), ENV.get("S3_SECRET_KEY")
    if not chave or not segredo:
        return None
    try:
        socket.create_connection(("127.0.0.1", 8333), timeout=1).close()
    except OSError:
        return None
    return Lake(
        endpoint="http://127.0.0.1:8333",
        chave=chave,
        segredo=segredo,
        bucket=ENV.get("S3_BUCKET") or "fictalent-lake",
    )


@pytest.fixture(scope="module")
def plataforma() -> tuple[Replica, Lake]:
    replica, lake = _replica(), _lake()
    if replica is None or lake is None:
        pytest.skip("réplica ou lake fora do ar")
    return replica, lake


def test_um_asset_por_tabela_da_ddl_com_a_origem_correspondente() -> None:
    esperadas = sum(len(t) for t in TABELAS.values())
    assert esperadas == 75 and list(TABELAS) == list(MODULOS_DE_NEGOCIO)
    assert len(ASSETS) == len(ORIGENS) == esperadas
    chaves = {tuple(k.path) for a in ASSETS for k in a.keys}
    origens = {tuple(o.key.path) for o in ORIGENS}
    assert ("bronze", "ponto", "marcacao") in chaves
    assert ("replica", "ponto", "marcacao") in origens
    for camada, modulo, tabela in chaves:  # a bronze pendura na réplica, tabela a tabela
        assert camada == "bronze" and ("replica", modulo, tabela) in origens
    for asset in ASSETS:  # toda partição é um ano da história
        assert asset.partitions_def is not None
        assert "2018" in asset.partitions_def.get_partition_keys()


def test_nome_de_tabela_nunca_vira_sql_sem_conferencia() -> None:
    assert backfill.identificador("ponto_marcacao") == "`ponto_marcacao`"
    for nome in ("ponto marcacao", "x; DROP TABLE y", "Ponto", "1tabela", ""):
        with pytest.raises(ValueError, match="identificador inválido"):
            backfill.identificador(nome)


def test_o_tipo_do_mysql_vira_o_tipo_declarado_do_parquet() -> None:
    assert backfill._tipo_arrow("bigint", "id", None, None) == pa.int64()
    assert backfill._tipo_arrow("tinyint", "ativo", 3, 0) == pa.bool_()
    assert backfill._tipo_arrow("decimal", "valor", 14, 2) == pa.decimal128(14, 2)
    assert backfill._tipo_arrow("date", "dt", None, None) == pa.date32()
    assert backfill._tipo_arrow("datetime", "criado_em", None, None) == pa.timestamp("us")
    assert backfill._tipo_arrow("json", "valor_novo", None, None) == pa.string()
    with pytest.raises(ValueError, match="sem correspondência"):
        backfill._tipo_arrow("geometry", "area", None, None)


def test_booleano_do_mysql_chega_como_inteiro_e_vira_booleano() -> None:
    campo = pa.field("ativo", pa.bool_())
    assert backfill._coluna((1, 0, None), campo).to_pylist() == [True, False, None]
    numero = pa.field("id", pa.int64())
    assert backfill._coluna((1, None), numero).to_pylist() == [1, None]
    with pytest.raises(ValueError, match="coluna id"):
        backfill._coluna(("nao é número",), numero)


def test_o_esquema_do_parquet_e_o_da_ddl(plataforma: tuple[Replica, Lake]) -> None:
    replica, _ = plataforma
    con = replica.conectar()
    try:
        campos = backfill.esquema(con, "comercial", "contrato")
        with pytest.raises(ValueError, match="sem colunas"):
            backfill.esquema(con, "comercial", "tabela_que_nao_existe")
    finally:
        con.close()
    tipos = dict(zip(campos.names, campos.types, strict=True))
    assert tipos["id"] == pa.int64()
    assert tipos["dt_assinatura"] == pa.date32()
    assert tipos["criado_em"] == pa.timestamp("us")
    assert campos.field("vigencia_fim").nullable  # NULL = contrato sem fim previsto
    assert not campos.field("id").nullable


def test_a_copia_confere_a_contagem_e_le_de_volta_o_que_gravou(
    plataforma: tuple[Replica, Lake],
) -> None:
    replica, lake = plataforma
    con = replica.conectar()
    try:
        for modulo, tabela, ano in AMOSTRA:
            copia = backfill.copiar_ano(con, lake, modulo, tabela, ano, lote=1000)
            assert copia.confere, (modulo, tabela, ano, copia.linhas, copia.esperadas)
            assert copia.caminho.endswith(f"bronze/{modulo}/{tabela}/ano={ano}.parquet")
            quadro = lake.ler_parquet(copia.caminho)
            assert len(quadro) == copia.linhas
            assert (quadro["criado_em"].dt.year == ano).all()  # a partição é o ano de criação
    finally:
        con.close()


def test_a_copia_e_idempotente_e_o_conteudo_bate_linha_a_linha(
    plataforma: tuple[Replica, Lake],
) -> None:
    replica, lake = plataforma
    modulo, tabela, ano = "comercial", "contrato", 2019
    con = replica.conectar()
    try:
        primeira = backfill.copiar_ano(con, lake, modulo, tabela, ano)
        de_novo = backfill.copiar_ano(con, lake, modulo, tabela, ano)
        with con.cursor() as cur:
            cur.execute(
                "SELECT id, numero, status, dt_assinatura FROM `comercial`.`contrato` "
                "WHERE criado_em >= %s AND criado_em < %s ORDER BY id",
                (date(ano, 1, 1), date(ano + 1, 1, 1)),
            )
            na_replica = [tuple(linha) for linha in cur.fetchall()]
    finally:
        con.close()
    assert primeira.linhas == de_novo.linhas == len(na_replica)
    quadro = lake.ler_parquet(de_novo.caminho)
    no_lake = [
        (int(linha["id"]), linha["numero"], linha["status"], linha["dt_assinatura"])
        for linha in quadro.to_dict("records")
    ]
    assert no_lake == na_replica  # espelho fiel: mesma linha, mesmo valor, mesma ordem


def test_a_foto_da_copia_e_repetivel_e_a_conexao_volta_utilizavel(
    plataforma: tuple[Replica, Lake],
) -> None:
    """A conferência só vale se contar e ler enxergarem o mesmo banco, e a cópia não pode deixar
    transação pendurada. Como o `pipeline` é só leitura (nem `PROCESS` ele tem, e é assim que
    deve ser), a prova possível aqui é de comportamento: duas cópias seguidas dão o mesmo
    número, e a conexão continua servindo. A prova com escrita concorrente é do card 5.5."""
    replica, lake = plataforma
    con = replica.conectar()
    try:
        antes = backfill.copiar_ano(con, lake, "ats", "vaga", 2023)
        depois = backfill.copiar_ano(con, lake, "ats", "vaga", 2023)
        with con.cursor() as cur:
            cur.execute("SELECT 1")
            (viva,) = cur.fetchone()
    finally:
        con.close()
    assert antes.linhas == depois.linhas == antes.esperadas > 0
    assert int(viva) == 1


def test_particao_sem_linha_grava_arquivo_vazio_com_o_mesmo_esquema(
    plataforma: tuple[Replica, Lake],
) -> None:
    """Ano sem linha nenhuma vira parquet vazio, com as colunas certas, em vez de arquivo
    faltando: quem lê a tabela inteira encontra sempre as nove partições."""
    replica, lake = plataforma
    con = replica.conectar()
    try:
        # as filiais abrem em 2018, 2019 e 2022: os outros anos do arco não têm linha nenhuma
        with con.cursor() as cur:
            cur.execute("SELECT DISTINCT YEAR(criado_em) FROM `cadastro`.`filial`")
            com_linhas = {int(a) for (a,) in cur.fetchall()}
        vazios = [a for a in range(2018, 2027) if a not in com_linhas]
        assert vazios, "toda partição de cadastro.filial tem linha: escolha outra tabela"
        vazia = backfill.copiar_ano(con, lake, "cadastro", "filial", vazios[0])
    finally:
        con.close()
    assert vazia.linhas == vazia.esperadas == 0
    quadro = lake.ler_parquet(vazia.caminho)
    assert len(quadro) == 0
    assert list(quadro.columns) == [
        "id",
        "codigo",
        "nome",
        "tipo",
        "endereco_id",
        "dt_abertura",
        "ativo",
        "criado_em",
        "atualizado_em",
    ]


def test_a_data_de_negocio_pode_cair_fora_do_ano_da_particao(
    plataforma: tuple[Replica, Lake],
) -> None:
    """A partição é técnica: o ano em que a linha entrou, não o ano do fato. A marcação da noite
    de 31/12 é gravada em 01/01 e mora na partição do ano seguinte. Quem quiser fato por ano
    usa a data de negócio, na silver."""
    replica, lake = plataforma
    con = replica.conectar()
    try:
        copia = backfill.copiar_ano(con, lake, "ponto", "marcacao", 2024)
    finally:
        con.close()
    quadro = lake.ler_parquet(copia.caminho)
    datas = [d for d in quadro["data"] if isinstance(d, date | datetime)]
    assert any(d.year == 2023 for d in datas)
    assert (quadro["criado_em"].dt.year == 2024).all()


def test_asset_bronze_materializa_e_publica_o_que_conferiu(
    plataforma: tuple[Replica, Lake],
) -> None:
    replica, lake = plataforma
    alvo = ("bronze", "cadastro", "filial")
    (asset,) = [a for a in ASSETS if tuple(next(iter(a.keys)).path) == alvo]
    resultado = dg.materialize(
        [asset], partition_key="2019", resources={"replica": replica, "lake": lake}
    )
    assert resultado.success
    (evento,) = [
        e.materialization
        for e in resultado.get_asset_materialization_events()
        if e.asset_key is not None and tuple(e.asset_key.path) == alvo
    ]
    metadados: dict[str, Any] = {k: v.value for k, v in evento.metadata.items()}
    assert metadados["linhas"] == metadados["conferidas_na_replica"]
    assert metadados["ano"] == 2019
    assert str(metadados["caminho"]).endswith("bronze/cadastro/filial/ano=2019.parquet")
