"""A ingestão de arquivo: a planilha da gerência entra com esquema declarado, ou não entra.

Metade destes testes escreve uma planilha **estragada** de propósito, numa pasta temporária, e
exige que a carga pare nela. É o ponto do card: planilha de gente muda de forma sozinha, e o
pipeline tem de descobrir no arquivo, não três camadas adiante.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import dagster as dg
import pandas as pd
import pandera.errors
import pytest
from dotenv import dotenv_values
from openpyxl import load_workbook

from rh_fictalent.ingestao import planilhas
from rh_fictalent.orquestracao.planilhas import consolidado_em_planilha
from rh_fictalent.orquestracao.recursos import Lake

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PASTA = RAIZ / "dados" / "gerencial"
ANO = 2022
OP = "bronze__arquivo__consolidado_gerencial"  # o nome do op que o asset gera


def _checks_que_falharam(erro: pandera.errors.SchemaErrors) -> set[str]:
    """Os checks que o pandera reprovou. O relatório vem como JSON com escape unicode, então
    comparar a mensagem por substring não funciona com acento: lê-se o JSON."""
    relatorio = json.loads(str(erro))
    return {
        caso["check"]
        for grupos in relatorio.values()
        for casos in grupos.values()
        for caso in casos
    }


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


@pytest.fixture
def estragar(tmp_path: Path) -> Callable[[Callable[[Any], None]], Path]:
    """Copia a planilha de 2022 para uma pasta temporária e deixa o teste estragá-la."""

    def fabricar(mexer: Callable[[Any], None]) -> Path:
        livro = load_workbook(PASTA / f"consolidado_gerencial_{ANO}.xlsx")
        mexer(livro["Consolidado"])
        destino = tmp_path / f"consolidado_gerencial_{ANO}.xlsx"
        livro.save(destino)
        return destino

    return fabricar


def test_as_nove_planilhas_estao_versionadas_e_no_padrao_do_nome() -> None:
    achadas = planilhas.planilhas(PASTA)
    assert len(achadas) == 9
    assert [planilhas.ano_do_arquivo(p) for p in achadas] == list(range(2018, 2027))
    with pytest.raises(ValueError, match="fora do padrão"):
        planilhas.ano_do_arquivo(Path("consolidado.xlsx"))
    with pytest.raises(FileNotFoundError, match="não há planilha"):
        planilhas.caminho_do_ano(PASTA, 2017)


def test_preparar_tira_o_enfeite_da_planilha_e_conserta_os_tipos() -> None:
    caminho = planilhas.caminho_do_ano(PASTA, ANO)
    cru = pd.read_excel(caminho, sheet_name="Consolidado", header=2)
    quadro = planilhas.preparar(caminho)

    assert len(quadro) == len(cru) - 1  # a linha de TOTAL não é observação
    assert not (quadro["competencia"].astype(str).str.upper() == "TOTAL").any()
    assert list(quadro.columns) == [*planilhas.COLUNAS.values(), "arquivo"]
    # a planilha entrega competência como texto (a palavra TOTAL contamina a coluna) e headcount
    # como decimal (a célula vazia do total); a preparação devolve data e inteiro
    assert cru["Competência"].dtype == object and str(cru["Headcount"].dtype) == "float64"
    assert str(quadro["competencia"].dtype).startswith("datetime64")
    assert str(quadro["headcount"].dtype) == "int64"
    assert (quadro["arquivo"] == caminho.name).all()


def test_o_esquema_aprova_as_nove_planilhas() -> None:
    for caminho in planilhas.planilhas(PASTA):
        quadro = planilhas.validar(planilhas.preparar(caminho))
        assert len(quadro) > 0
        assert set(quadro["competencia"].dt.year) == {planilhas.ano_do_arquivo(caminho)}


def test_a_soma_das_linhas_bate_com_o_total_que_a_planilha_declara() -> None:
    """O total é descartado na ingestão, mas serve de conferência: se a soma das linhas não bate
    com ele, alguém editou a planilha à mão depois de fechada."""
    caminho = planilhas.caminho_do_ano(PASTA, ANO)
    quadro = planilhas.preparar(caminho)
    declarado = planilhas.total_declarado(caminho)
    assert int(quadro["vagas_abertas"].sum()) == int(declarado["vagas_abertas"])
    assert round(float(quadro["faturamento"].sum()), 2) == round(declarado["faturamento"], 2)
    assert round(float(quadro["custo"].sum()), 2) == round(declarado["custo"], 2)


def test_coluna_renomeada_na_planilha_para_a_carga(
    estragar: Callable[[Callable[[Any], None]], Path],
) -> None:
    def renomear(folha: Any) -> None:
        folha["C3"] = "Head count"  # alguém "arrumou" o cabeçalho

    with pytest.raises(ValueError, match="a planilha não tem"):
        planilhas.preparar(estragar(renomear))


def test_coluna_a_mais_na_planilha_para_a_carga(
    estragar: Callable[[Callable[[Any], None]], Path],
) -> None:
    """`strict=True`: coluna que ninguém declarou é erro, não curiosidade. Uma coluna nova pode
    mudar o significado das outras, e quem lê o parquet não vai saber disso."""
    caminho = planilhas.caminho_do_ano(PASTA, ANO)
    quadro = planilhas.preparar(caminho)
    quadro["observacao"] = "ajustado pelo financeiro"
    with pytest.raises(pandera.errors.SchemaErrors, match="observacao"):
        planilhas.validar(quadro)


@pytest.mark.parametrize(
    ("estrago", "mensagem"),
    [
        (lambda q: q.assign(filial=q["filial"].replace({"Extrema": "Extrema II"})), "isin"),
        (lambda q: q.assign(headcount=q["headcount"] * -1), "greater_than_or_equal_to"),
        (lambda q: q.assign(faturamento=q["faturamento"] * -1), "greater_than_or_equal_to"),
        (
            lambda q: q.assign(competencia=q["competencia"] + pd.offsets.Day(3)),
            "competência não é o 1º do mês",
        ),
        (
            lambda q: q.assign(lancado_em=q["competencia"] - pd.offsets.Day(1)),
            "lançado antes da competência",
        ),
        (
            lambda q: q.assign(
                competencia=q["competencia"].mask(q.index == 0, pd.Timestamp("2019-01-01"))
            ),
            "competência de outro ano",
        ),
    ],
)
def test_o_esquema_barra_cada_estrago_conhecido(
    estrago: Callable[[pd.DataFrame], pd.DataFrame], mensagem: str
) -> None:
    quadro = planilhas.preparar(planilhas.caminho_do_ano(PASTA, ANO))
    with pytest.raises(pandera.errors.SchemaErrors) as erro:
        planilhas.validar(estrago(quadro))
    reprovados = _checks_que_falharam(erro.value)
    assert any(mensagem in c for c in reprovados), reprovados


def test_o_esquema_barra_a_linha_repetida() -> None:
    """Uma competência e filial só podem aparecer uma vez: linha duplicada dobra o faturamento
    de um mês sem que ninguém perceba."""
    quadro = planilhas.preparar(planilhas.caminho_do_ano(PASTA, ANO))
    with pytest.raises(pandera.errors.SchemaErrors, match="unique"):
        planilhas.validar(pd.concat([quadro, quadro.head(1)], ignore_index=True))


def test_a_carga_grava_na_bronze_e_o_parquet_tem_a_proveniencia(lake: Lake) -> None:
    caminho = planilhas.caminho_do_ano(PASTA, ANO)
    linhas, destino = planilhas.ingerir(lake, caminho)
    assert destino.endswith(f"bronze/arquivo/consolidado_gerencial/ano={ANO}.parquet")
    quadro = lake.ler_parquet(destino)
    assert len(quadro) == linhas
    assert (quadro["arquivo"] == caminho.name).all()  # de qual planilha veio cada número
    assert set(quadro["competencia"].dt.year) == {ANO}


def test_a_planilha_e_a_replica_contam_a_mesma_coisa(lake: Lake) -> None:
    """As duas fontes do consolidado têm de bater entre si. Elas divergem da **operação** a
    partir de 2022, de propósito (GER-01), mas isso é outra discordância: aqui o que se confere
    é que o arquivo e a tabela dizem o mesmo, porque são a mesma planilha por dois caminhos."""
    do_arquivo = lake.ler_parquet(
        lake.caminho("bronze", "arquivo", "consolidado_gerencial", f"ano={ANO}.parquet")
    )
    # a bronze da réplica é particionada pelo ano de CRIAÇÃO da linha, e o fechamento de
    # dezembro é lançado em janeiro: a competência de um ano mora em duas partições
    da_replica = pd.concat(
        lake.ler_parquet(
            lake.caminho("bronze", "financeiro", "consolidado_gerencial", f"ano={ano}.parquet")
        )
        for ano in (ANO, ANO + 1)
    )
    # o parquet guarda DATE, que volta como `datetime.date`: sem isto o `.dt` não existe
    competencia = pd.to_datetime(da_replica["competencia"])
    da_replica = da_replica[competencia.dt.year == ANO]
    assert len(do_arquivo) == len(da_replica)
    assert int(do_arquivo["headcount"].sum()) == int(da_replica["headcount_informado"].sum())
    assert round(float(do_arquivo["faturamento"].sum()), 2) == round(
        float(da_replica["faturamento_informado"].sum()), 2
    )


def test_o_asset_materializa_a_particao_do_ano_e_publica_o_total_declarado(lake: Lake) -> None:
    resultado = dg.materialize(
        [consolidado_em_planilha],
        partition_key=str(ANO),
        resources={"lake": lake},
        run_config={"ops": {OP: {"config": {"pasta": str(PASTA)}}}},
    )
    assert resultado.success
    (evento,) = resultado.get_asset_materialization_events()
    metadados: dict[str, Any] = {k: v.value for k, v in evento.materialization.metadata.items()}
    assert metadados["ano"] == ANO
    assert metadados["arquivo"] == f"consolidado_gerencial_{ANO}.xlsx"
    assert metadados["linhas"] > 0
    assert metadados["total_declarado_faturamento"] > 0


def test_planilha_que_nao_existe_faz_o_asset_falhar(lake: Lake, tmp_path: Path) -> None:
    """Pasta sem a planilha do ano: o asset falha em vez de gravar um parquet vazio."""
    resultado = dg.materialize(
        [consolidado_em_planilha],
        partition_key="2018",
        resources={"lake": lake},
        run_config={"ops": {OP: {"config": {"pasta": str(tmp_path)}}}},
        raise_on_error=False,
    )
    assert not resultado.success
    falhas = [str(e) for e in resultado.all_events if e.event_type_value == "STEP_FAILURE"]
    assert falhas and "não há planilha do consolidado" in " ".join(falhas)


def test_o_total_declarado_precisa_existir(
    estragar: Callable[[Callable[[Any], None]], Path],
) -> None:
    def apagar_total(folha: Any) -> None:
        folha.delete_rows(folha.max_row)

    with pytest.raises(ValueError, match="esperava uma linha de TOTAL"):
        planilhas.total_declarado(estragar(apagar_total))


def test_carimbo_de_lancamento_conta_a_demora_do_fechamento() -> None:
    """O que a planilha diz sobre o processo: o fechamento de cada mês é lançado dias depois, e
    é esse atraso que a análise vai usar para falar de tempestividade."""
    quadro = planilhas.preparar(planilhas.caminho_do_ano(PASTA, ANO))
    atraso = (quadro["lancado_em"] - quadro["competencia"]).dt.days
    assert (atraso > 0).all() and atraso.max() < 90
    assert isinstance(quadro["lancado_em"].iloc[0], datetime | pd.Timestamp)
