"""Dias correntes: a réplica se mexe, a carga acompanha, e o teste devolve tudo ao lugar.

Devolver é mais trabalhoso do que escrever, e é o que torna estes testes possíveis: sem isso,
cada execução afastaria a réplica da base que a régua aprovou. A restauração usa **a bronze**
como estado anterior, o que é o backfill provando para que serve.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values

from rh_fictalent.ingestao.backfill import copiar_ano
from rh_fictalent.ingestao.exclusoes import ler_trilha
from rh_fictalent.ingestao.incremental import agora_na_replica, sincronizar
from rh_fictalent.orquestracao.recursos import Lake, Replica, Warehouse
from rh_fictalent.orquestracao.simulacao import MAXIMO_DE_DIAS, agenda_simulacao, simular_dias
from rh_fictalent.simulacao import registro
from rh_fictalent.simulacao.dia import (
    FIM_DA_HISTORIA,
    Movimento,
    _trabalha,
    aleatorio,
    dias_a_simular,
    ja_simulado,
    simular,
)

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
DIA = FIM_DA_HISTORIA + timedelta(days=1)
INSERIDAS = ("ponto.marcacao", "ponto.apontamento", "ponto.ocorrencia_ponto")
ALTERADAS = {"ats.vaga": ("status", "dt_fechamento"), "pessoas.alocacao": ("dt_fim",)}


def _replica(usuario: str, variavel: str) -> Replica:
    senha, porta = ENV.get(variavel), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        pytest.skip(f"{variavel} ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    return Replica(host="127.0.0.1", porta=porta, usuario=usuario, senha=senha)


@pytest.fixture(scope="module")
def leitor() -> Replica:
    return _replica("pipeline", "PIPELINE_PASSWORD")


@pytest.fixture(scope="module")
def escritor() -> Replica:
    return _replica("replicador", "REPLICADOR_PASSWORD")


@pytest.fixture(scope="module")
def lake() -> Lake:
    chave, segredo = ENV.get("S3_ACCESS_KEY"), ENV.get("S3_SECRET_KEY")
    if not chave or not segredo:
        pytest.skip("credenciais do lake ausentes")
    try:
        socket.create_connection(("127.0.0.1", 8333), timeout=1).close()
    except OSError:
        pytest.skip("lake fora do ar")
    return Lake(
        endpoint="http://127.0.0.1:8333",
        chave=chave,
        segredo=segredo,
        bucket=ENV.get("S3_BUCKET") or "fictalent-lake",
    )


@pytest.fixture(scope="module")
def warehouse() -> Warehouse:
    senha, porta = ENV.get("DW_ADMIN_PASSWORD"), int(ENV.get("DW_PORT") or 0)
    if not senha or not porta:
        pytest.skip("warehouse ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("warehouse fora do ar")
    dw = Warehouse(
        host="127.0.0.1",
        porta=porta,
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=senha,
    )
    registro.criar(dw)
    return dw


@dataclass
class Estado:
    """O maior id de cada tabela antes da simulação: o que vier depois é da simulação."""

    maiores: dict[str, int]


def _maiores(con: Any) -> dict[str, int]:
    maiores = {}
    with con.cursor() as cur:
        for tabela in INSERIDAS:
            cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {tabela}")  # noqa: S608 # nosec B608
            (maior,) = cur.fetchone()
            maiores[tabela] = int(maior)
    return maiores


def _restaurar(root: Replica, lake: Lake, estado: Estado) -> None:
    """Devolve réplica **e** bronze ao estado anterior.

    Restaurar só a réplica não basta: a bronze guardaria um dia que já não existe na origem, e
    o teste seguinte encontraria a divergência sem entender de onde veio. A partição do ano é
    recopiada no fim, que é o mesmo caminho do `refazer` do card 5.2.
    """
    hoje = date.today()
    con = root.conectar()
    try:
        with con.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for tabela in reversed(INSERIDAS):
                cur.execute(
                    f"DELETE FROM {tabela} WHERE id > %s",  # noqa: S608 # nosec B608
                    (estado.maiores[tabela],),
                )
            for nome, colunas in ALTERADAS.items():
                modulo, tabela = nome.split(".")
                cur.execute(
                    f"SELECT id FROM {nome} WHERE DATE(atualizado_em) = %s",  # noqa: S608 # nosec B608
                    (hoje,),
                )
                ids = [int(i) for (i,) in cur.fetchall()]
                for identificador, linha in _da_bronze(lake, modulo, tabela, ids).items():
                    atribuicoes = ", ".join(f"{c} = %s" for c in colunas)
                    cur.execute(
                        f"UPDATE {nome} SET {atribuicoes}, atualizado_em = %s WHERE id = %s",  # noqa: S608 # nosec B608
                        (*[linha[c] for c in colunas], linha["atualizado_em"], identificador),
                    )
            cur.execute("DELETE FROM meta.exclusao_auditoria")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        con.commit()
        for nome in (*INSERIDAS, *ALTERADAS):
            modulo, tabela = nome.split(".")
            copiar_ano(con, lake, modulo, tabela, DIA.year)
    finally:
        con.close()


def _da_bronze(lake: Lake, modulo: str, tabela: str, ids: list[int]) -> dict[int, dict[str, Any]]:
    """As linhas como a bronze as viu no backfill: o estado anterior, guardado em parquet."""
    if not ids:
        return {}
    achadas: dict[int, dict[str, Any]] = {}
    fs = lake.sistema()
    for ano in range(2018, 2027):
        caminho = lake.caminho("bronze", modulo, tabela, f"ano={ano}.parquet")
        if not fs.exists(caminho):
            continue
        quadro = lake.ler_parquet(caminho)
        for linha in quadro[quadro["id"].isin(ids)].to_dict("records"):
            achadas[int(linha["id"])] = {str(c): v for c, v in linha.items()}
    return achadas


@pytest.fixture
def dia_simulado(
    leitor: Replica, escritor: Replica, lake: Lake, warehouse: Warehouse
) -> Iterator[Movimento]:
    """Simula um dia e, no fim, devolve réplica, trilha e registro ao estado anterior."""
    root = _replica("root", "STAGING_ROOT_PASSWORD")
    con = leitor.conectar()
    estado = Estado(_maiores(con))
    con.close()
    movimento = simular(escritor, DIA)
    if movimento.ja_simulado:
        pytest.skip(f"{DIA} já tem movimento na réplica; limpe antes de rodar este teste")
    registro.gravar(warehouse, movimento)
    try:
        yield movimento
    finally:
        _restaurar(root, lake, estado)
        registro.esquecer(warehouse, DIA)


def test_a_escala_decide_quem_trabalha_no_dia() -> None:
    segunda, sabado, domingo = date(2026, 9, 14), date(2026, 9, 19), date(2026, 9, 20)
    assert _trabalha("5X2", segunda, feriado=False, colaborador=1)
    assert not _trabalha("5X2", sabado, feriado=False, colaborador=1)
    assert _trabalha("6X1", sabado, feriado=False, colaborador=1)
    assert not _trabalha("6X1", domingo, feriado=False, colaborador=1)
    assert not _trabalha("5X2", segunda, feriado=True, colaborador=1)  # feriado é folga
    assert _trabalha("12X36", segunda, feriado=True, colaborador=1) != _trabalha(
        "12X36", segunda, feriado=True, colaborador=2
    )  # plantão: metade trabalha, metade folga, e trocam no dia seguinte


def test_o_mesmo_dia_da_sempre_o_mesmo_movimento() -> None:
    """Determinismo, como no gerador: a semente do dia vem da semente do projeto e da data."""
    primeiro = aleatorio(DIA).random(5).tolist()
    assert primeiro == aleatorio(DIA).random(5).tolist()
    assert primeiro != aleatorio(DIA + timedelta(days=1)).random(5).tolist()


def test_a_simulacao_so_olha_para_depois_do_fim_da_historia() -> None:
    assert dias_a_simular(FIM_DA_HISTORIA) == []
    assert dias_a_simular(FIM_DA_HISTORIA + timedelta(days=3)) == [
        FIM_DA_HISTORIA + timedelta(days=n) for n in (1, 2, 3)
    ]
    assert len(dias_a_simular(FIM_DA_HISTORIA + timedelta(days=40))) > MAXIMO_DE_DIAS


def test_um_dia_de_operacao_escreve_ponto_e_mexe_na_carteira(
    dia_simulado: Movimento, leitor: Replica
) -> None:
    movimento = dia_simulado
    assert movimento.inseridas["ponto.apontamento"] > 500  # os alocados que trabalham no dia
    assert movimento.inseridas["ponto.marcacao"] > movimento.inseridas["ponto.apontamento"] * 3
    con = leitor.conectar()
    try:
        with con.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ponto.apontamento WHERE data = %s", (DIA,))
            (apontados,) = cur.fetchone()
            cur.execute(
                "SELECT status, COUNT(*) FROM ponto.apontamento WHERE data = %s GROUP BY 1",
                (DIA,),
            )
            por_status = {str(s): int(n) for s, n in cur.fetchall()}
    finally:
        con.close()
    assert apontados == movimento.inseridas["ponto.apontamento"]
    assert por_status["NORMAL"] > por_status.get("FALTA", 0)  # o dia normal é o caso comum
    assert "FALTA" in por_status  # mas falta existe, como no catálogo de sujeira


def test_simular_o_mesmo_dia_duas_vezes_nao_duplica(
    dia_simulado: Movimento, escritor: Replica, leitor: Replica
) -> None:
    de_novo = simular(escritor, DIA)
    assert de_novo.ja_simulado and de_novo.total_inserido == 0
    con = leitor.conectar()
    try:
        assert ja_simulado(con, DIA)
    finally:
        con.close()


def test_a_carga_incremental_traz_o_dia_que_a_operacao_escreveu(
    dia_simulado: Movimento, leitor: Replica, lake: Lake
) -> None:
    """O fecho da fase: a operação escreve, a marca d'água encontra, a bronze recebe."""
    con = leitor.conectar()
    try:
        corte = agora_na_replica(con)
        desde = corte - timedelta(hours=6)
        resultado = sincronizar(con, lake, "ponto", "apontamento", desde, corte)
    finally:
        con.close()
    assert resultado.alteradas >= dia_simulado.inseridas["ponto.apontamento"]
    assert resultado.confere, resultado.divergencias
    ano = DIA.year
    quadro = lake.ler_parquet(lake.caminho("bronze", "ponto", "apontamento", f"ano={ano}.parquet"))
    do_dia = quadro[quadro["data"] == DIA]
    assert len(do_dia) == dia_simulado.inseridas["ponto.apontamento"]


def test_o_registro_diz_o_que_a_operacao_acrescentou(
    dia_simulado: Movimento, warehouse: Warehouse
) -> None:
    """Sem este registro, ligar a simulação tornaria impossível conferir a base gerada contra o
    laudo da régua: não daria para saber se a diferença é operação ou defeito."""
    saldo = registro.acrescentado(warehouse)
    assert saldo["ponto.apontamento"] == dia_simulado.inseridas["ponto.apontamento"]
    assert saldo["ponto.marcacao"] == dia_simulado.inseridas["ponto.marcacao"] - (
        dia_simulado.excluidas.get("ponto.marcacao", 0)
    )
    assert DIA in registro.simulados(warehouse)


def test_a_agenda_nasce_desligada_e_roda_antes_da_carga() -> None:
    """Ligar a simulação é decisão consciente: a partir daí a réplica deixa de ser exatamente a
    base que a régua aprovou. Por isso ela nasce parada, ao contrário da carga incremental."""
    assert agenda_simulacao.default_status.value == "STOPPED"
    assert agenda_simulacao.cron_schedule == "0 4 * * *"  # uma hora antes da carga das 5h
    assert agenda_simulacao.job.name == "simular_dias"
    assert "json" in simular_dias.loggers


def test_o_job_recusa_escrever_um_mes_inteiro_de_uma_vez(
    leitor: Replica, warehouse: Warehouse
) -> None:
    """Trava de segurança: escrever muitos dias sem olhar é como rodar um backfill sem conferir."""
    resultado = simular_dias.execute_in_process(
        run_config={
            "ops": {"rodar_os_dias": {"config": {"ate": "2027-12-31"}}},
            "loggers": {"json": {"config": {"nivel": "INFO"}}},
        },
        resources={"replica": leitor, "warehouse": warehouse},
        raise_on_error=False,
    )
    assert not resultado.success
    falhas = " ".join(str(e) for e in resultado.all_events if e.event_type_value == "STEP_FAILURE")
    assert "acima do limite" in falhas


def test_a_trilha_registra_a_batida_apagada_quando_ela_acontece(
    dia_simulado: Movimento, leitor: Replica
) -> None:
    """A exclusão é rara de propósito (15% dos dias). Quando acontece, tem de estar na trilha:
    é o único jeito de a carga saber, porque `DELETE` não deixa `atualizado_em`."""
    apagadas = dia_simulado.excluidas.get("ponto.marcacao", 0)
    con = leitor.conectar()
    try:
        corte = agora_na_replica(con)
        trilha = ler_trilha(con, corte - timedelta(hours=6), corte)
    finally:
        con.close()
    registradas = len(trilha.get(("ponto", "marcacao"), {}))
    assert registradas == apagadas
