"""As exclusões: o que o `DELETE` apaga na réplica vira marcação na bronze, não sumiço.

O teste apaga uma linha de verdade, para o gatilho disparar de verdade, e depois devolve tudo:
a linha volta com os mesmos valores e a trilha é limpa (só o `root` mexe nela). A base sintética
continua sendo a que a régua aprovou.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from dotenv import dotenv_values

from rh_fictalent.ingestao import exclusoes
from rh_fictalent.ingestao.backfill import CONTROLE, esquema, esquema_bronze
from rh_fictalent.ingestao.incremental import (
    agora_na_replica,
    conferir,
    refazer,
    sincronizar,
)
from rh_fictalent.orquestracao.bronze import TABELAS
from rh_fictalent.orquestracao.convencoes import chave
from rh_fictalent.orquestracao.recursos import Lake, Replica

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
MODULO, TABELA = "seguranca", "log_auditoria"  # folha: nada aponta para ela por chave estrangeira


def _porta() -> int:
    return int(ENV.get("STAGING_PORT") or 0)


def _usuario(nome: str, variavel: str) -> Replica:
    senha, porta = ENV.get(variavel), _porta()
    if not senha or not porta:
        pytest.skip(f"{variavel} ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    return Replica(host="127.0.0.1", porta=porta, usuario=nome, senha=senha)


@pytest.fixture(scope="module")
def replica() -> Replica:
    return _usuario("pipeline", "PIPELINE_PASSWORD")


@pytest.fixture(scope="module")
def lake() -> Lake:
    chave_s3, segredo = ENV.get("S3_ACCESS_KEY"), ENV.get("S3_SECRET_KEY")
    if not chave_s3 or not segredo:
        pytest.skip("credenciais do lake ausentes")
    try:
        socket.create_connection(("127.0.0.1", 8333), timeout=1).close()
    except OSError:
        pytest.skip("lake fora do ar")
    return Lake(
        endpoint="http://127.0.0.1:8333",
        chave=chave_s3,
        segredo=segredo,
        bucket=ENV.get("S3_BUCKET") or "fictalent-lake",
    )


@pytest.fixture
def apagada(replica: Replica, lake: Lake) -> Iterator[dict[str, Any]]:
    """Apaga a última linha de `seguranca.log_auditoria` e, no fim, devolve linha e trilha.

    Reinserir com o id original e limpar a trilha exigem `root`: o `replicador` escreve o
    negócio mas não toca `meta`, e é assim que tem de ser (a trilha é prova, não rascunho).
    """
    escritor = _usuario("replicador", "REPLICADOR_PASSWORD")
    root = _usuario("root", "STAGING_ROOT_PASSWORD")
    con, ec, rc = replica.conectar(), escritor.conectar(), root.conectar()
    with ec.cursor() as cur:
        cur.execute(f"SELECT * FROM `{MODULO}`.`{TABELA}` ORDER BY id DESC LIMIT 1")  # noqa: S608 # nosec B608
        linha = cur.fetchone()
        cur.execute(f"SHOW COLUMNS FROM `{MODULO}`.`{TABELA}`")  # noqa: S608 # nosec B608
        colunas = [str(c[0]) for c in cur.fetchall()]
    registro = dict(zip(colunas, linha, strict=True))
    alvo, ano = int(registro["id"]), registro["criado_em"].year
    marca = agora_na_replica(con)
    with ec.cursor() as cur:
        cur.execute(f"DELETE FROM `{MODULO}`.`{TABELA}` WHERE id = %s", (alvo,))  # noqa: S608 # nosec B608
        ec.commit()
    try:
        yield {"con": con, "id": alvo, "ano": ano, "marca": marca, "vivas_antes": None}
    finally:
        nomes = ", ".join(f"`{c}`" for c in colunas)
        marcas = ", ".join(["%s"] * len(colunas))
        with rc.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            cur.execute(f"INSERT INTO `{MODULO}`.`{TABELA}` ({nomes}) VALUES ({marcas})", linha)  # noqa: S608 # nosec B608
            cur.execute(
                "DELETE FROM meta.exclusao_auditoria WHERE banco = %s AND tabela = %s "
                "AND registro_id = %s",
                (MODULO, TABELA, alvo),
            )
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            rc.commit()
        refazer(con, lake, MODULO, TABELA)
        ec.close()
        rc.close()
        con.close()


def test_a_bronze_acrescenta_uma_coluna_so_e_ela_fica_no_fim(replica: Replica) -> None:
    con = replica.conectar()
    try:
        da_origem = esquema(con, "comercial", "contrato")
    finally:
        con.close()
    na_bronze = esquema_bronze(da_origem)
    assert na_bronze.names == [*da_origem.names, CONTROLE]
    assert na_bronze.field(CONTROLE).type == pa.timestamp("us")
    assert na_bronze.field(CONTROLE).nullable  # nula enquanto a linha existe na réplica


def test_o_backfill_grava_a_coluna_de_controle_vazia(lake: Lake) -> None:
    quadro = lake.ler_parquet(lake.caminho("bronze", "comercial", "contrato", "ano=2019.parquet"))
    assert CONTROLE in quadro.columns
    assert quadro[CONTROLE].isna().all()  # ninguém apagou nada: todas vivas


def test_a_trilha_tem_asset_na_bronze_como_qualquer_tabela() -> None:
    assert TABELAS["meta"] == ["exclusao_auditoria"]
    assert sum(len(t) for t in TABELAS.values()) == 76  # 75 de negócio mais a trilha
    assert chave("bronze", "meta", "exclusao_auditoria").path == [
        "bronze",
        "meta",
        "exclusao_auditoria",
    ]
    with pytest.raises(ValueError, match="módulo desconhecido"):
        chave("bronze", "inventado", "x")


def test_a_trilha_registra_o_delete_e_a_marcacao_baixa_as_vivas(
    apagada: dict[str, Any], lake: Lake
) -> None:
    con, alvo, ano, marca = apagada["con"], apagada["id"], apagada["ano"], apagada["marca"]
    antes = exclusoes.vivas(lake, MODULO, TABELA, ano)
    corte = agora_na_replica(con)
    trilha = exclusoes.ler_trilha(con, marca - timedelta(minutes=1), corte)
    assert (MODULO, TABELA) in trilha and alvo in trilha[(MODULO, TABELA)]

    aplicacao = exclusoes.marcar(lake, MODULO, TABELA, trilha[(MODULO, TABELA)])
    assert (aplicacao.pedidas, aplicacao.marcadas, aplicacao.ausentes) == (1, 1, 0)
    assert exclusoes.vivas(lake, MODULO, TABELA, ano) == antes - 1

    quadro = lake.ler_parquet(lake.caminho("bronze", MODULO, TABELA, f"ano={ano}.parquet"))
    linha = quadro.loc[quadro["id"] == alvo]
    assert len(linha) == 1, "marcar, não apagar: a linha continua na bronze"
    assert linha[CONTROLE].iloc[0] is not pa.NA and not linha[CONTROLE].isna().iloc[0]


def test_marcar_duas_vezes_nao_muda_nada(apagada: dict[str, Any], lake: Lake) -> None:
    con, ano, marca = apagada["con"], apagada["ano"], apagada["marca"]
    trilha = exclusoes.ler_trilha(con, marca - timedelta(minutes=1), agora_na_replica(con))
    pedidas = trilha[(MODULO, TABELA)]
    primeira = exclusoes.marcar(lake, MODULO, TABELA, pedidas)
    depois_da_primeira = exclusoes.vivas(lake, MODULO, TABELA, ano)
    segunda = exclusoes.marcar(lake, MODULO, TABELA, pedidas)
    assert (primeira.marcadas, primeira.ja_marcadas) == (1, 0)
    assert (segunda.marcadas, segunda.ja_marcadas) == (0, 1)
    assert exclusoes.vivas(lake, MODULO, TABELA, ano) == depois_da_primeira


def test_com_a_exclusao_marcada_a_conferencia_volta_a_bater(
    apagada: dict[str, Any], lake: Lake
) -> None:
    """Uma linha apagada some da réplica e fica na bronze: a contagem de vivas acusa, e a
    marcação explica. Note que o `sincronizar` sozinho **não** vê: um `DELETE` não gera
    alteração nenhuma, então a partição dele não é tocada pelo merge, e por isso a conferência
    virou função própria, chamada também depois da marcação."""
    con, ano, marca = apagada["con"], apagada["ano"], apagada["marca"]
    corte = agora_na_replica(con)
    so_o_merge = sincronizar(con, lake, MODULO, TABELA, marca, corte)
    assert so_o_merge.confere and not so_o_merge.particoes, "o DELETE não altera nada"

    (divergencia,) = conferir(con, lake, MODULO, TABELA, [ano], corte)
    assert "diferença de 1" in divergencia

    trilha = exclusoes.ler_trilha(con, marca - timedelta(minutes=1), corte)
    exclusoes.marcar(lake, MODULO, TABELA, trilha[(MODULO, TABELA)])
    assert conferir(con, lake, MODULO, TABELA, [ano], agora_na_replica(con)) == []


def test_id_que_nunca_chegou_a_bronze_nao_e_erro(apagada: dict[str, Any], lake: Lake) -> None:
    """Apagar algo que a bronze nunca viu (exclusão anterior ao backfill) não tem o que marcar."""
    inventado = {999_999_999: datetime(2026, 9, 23, 10, 0, 0)}
    aplicacao = exclusoes.marcar(lake, MODULO, TABELA, inventado)
    assert (aplicacao.pedidas, aplicacao.marcadas, aplicacao.ausentes) == (1, 0, 1)


def test_refazer_perde_a_marcacao_e_e_por_isso_que_a_trilha_vai_para_a_bronze(
    apagada: dict[str, Any], lake: Lake
) -> None:
    """Limite honesto: a bronze com marcação não é reconstruível só a partir da réplica. A linha
    apagada não existe mais lá, então recopiar a tabela traz o presente e esquece o que morreu.
    O que sobrevive é a trilha, que a carga copia para a bronze como qualquer outra tabela."""
    con, alvo, ano, marca = apagada["con"], apagada["id"], apagada["ano"], apagada["marca"]
    trilha = exclusoes.ler_trilha(con, marca - timedelta(minutes=1), agora_na_replica(con))
    exclusoes.marcar(lake, MODULO, TABELA, trilha[(MODULO, TABELA)])
    quadro = lake.ler_parquet(lake.caminho("bronze", MODULO, TABELA, f"ano={ano}.parquet"))
    assert alvo in set(quadro["id"])

    refazer(con, lake, MODULO, TABELA)
    quadro = lake.ler_parquet(lake.caminho("bronze", MODULO, TABELA, f"ano={ano}.parquet"))
    assert alvo not in set(quadro["id"]), "recopiar traz só o que existe hoje"

    da_trilha = refazer(con, lake, *exclusoes.TRILHA)
    assert da_trilha.confere
    registros = lake.ler_parquet(
        lake.caminho("bronze", "meta", "exclusao_auditoria", f"ano={ano}.parquet")
    )
    assert alvo in set(registros["registro_id"])  # o registro do que sumiu sobrevive
