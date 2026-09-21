"""O financeiro numa amostra de 5%: cabe na DDL, fecha a margem do caso sem nunca ir ao vermelho,
e o consolidado gerencial diverge da operação do jeito que o catálogo de sujeira diz."""

from __future__ import annotations

import re
import socket
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import catalogos_financeiro as fin
from rh_fictalent.gerador import etapa2_carteira, nucleo
from rh_fictalent.gerador import etapa5_financeiro as e5
from rh_fictalent.validacao import bandas

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"
PLANILHAS = RAIZ / "dados" / "gerencial"
FRACAO = 0.05
DDL = (RAIZ / "staging" / "ddl" / "07_financeiro.sql").read_text(encoding="utf-8")
Linhas = dict[str, list[dict[str, Any]]]


@pytest.fixture(scope="module")
def gerado() -> tuple[nucleo.Tabelas, dict[str, Any]]:
    return e5.gerar_com_base(PUBLICOS, FRACAO)


@pytest.fixture(scope="module")
def linhas(gerado: tuple[nucleo.Tabelas, dict[str, Any]]) -> Linhas:
    return {nome: etapa2_carteira._registros(quadro) for nome, quadro in gerado[0].items()}


def test_tabelas_tem_as_colunas_da_ddl_e_os_textos_cabem(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]],
) -> None:
    tabelas = gerado[0]
    assert list(tabelas) == list(e5.ORDEM) and len(tabelas) == 10
    for nome, quadro in tabelas.items():
        tabela = nome.split(".")[1]
        corpo = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\) ENCRYPTION", DDL, re.S)
        assert corpo, nome
        colunas = [
            linha.split()[0]
            for linha in (bruta.strip() for bruta in corpo.group(1).splitlines())
            if linha and not linha.startswith(("PRIMARY", "UNIQUE", "KEY", "CONSTRAINT"))
        ]
        assert list(quadro.columns) == colunas, nome
        for coluna, limite in re.findall(
            r"^\s+(\w+)\s+(?:VAR)?CHAR\((\d+)\)", corpo.group(1), re.M
        ):
            maior = max((len(v) for v in quadro[coluna] if v is not None), default=0)
            assert maior <= int(limite), (nome, coluna)


def test_a_empresa_nunca_fecha_no_vermelho_e_a_margem_e_a_do_caso(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]],
) -> None:
    tabelas, base = gerado
    e5.conferir(tabelas, base, FRACAO)  # chaves, fatura com itens, carimbos, retaguarda e régua
    margem = e5.medir(tabelas, base)["margem_liquida"]
    assert set(margem) == {str(a) for a in bandas.ANOS}
    for ano in bandas.ANOS:
        assert margem[str(ano)] > 0
        assert margem[str(ano)] == pytest.approx(bandas.MARGEM_LIQUIDA[ano], abs=0.002)
    # a retaguarda fecha a conta e sai sempre positiva; a faixa fina (2% a 20%) é da base inteira
    assert all(0 < parte < 0.5 for parte in base["despesa_da_retaguarda"].values())


def test_fatura_fecha_com_itens_impostos_e_titulo(
    linhas: Linhas, gerado: tuple[nucleo.Tabelas, dict[str, Any]]
) -> None:
    contrato = {
        k["id"]: k for k in etapa2_carteira._registros(gerado[1]["carteira"]["comercial.contrato"])
    }
    codigo_da_filial = {1: "ATB", 2: "BRG", 3: "EXT"}
    itens: dict[int, float] = {}
    for i in linhas["financeiro.fatura_item"]:
        assert i["valor_total"] == pytest.approx(
            i["valor_postos"] + i["valor_horas_extras"] - i["valor_descontos"], abs=0.011
        )
        itens[i["fatura_id"]] = itens.get(i["fatura_id"], 0.0) + i["valor_total"]
    titulo = {x["fatura_id"]: x for x in linhas["financeiro.titulo_receber"]}
    for f in linhas["financeiro.fatura"]:
        k = contrato[f["contrato_id"]]
        retido = fin.ISS_DA_FILIAL[codigo_da_filial[k["filial_id"]]] + fin.PIS + fin.COFINS
        assert f["valor_impostos"] == pytest.approx(f["valor_bruto"] * retido, abs=0.011)
        assert f["valor_liquido"] == pytest.approx(
            f["valor_bruto"] - f["valor_impostos"], abs=0.011
        )
        if k["tipo_servico"] == "RECRUTAMENTO":
            assert f["id"] not in itens  # honorário: sem posto, sem item
        else:
            assert itens[f["id"]] == pytest.approx(f["valor_bruto"], abs=0.05)
        assert f["dt_emissao"] > f["competencia"] and f["dt_emissao"].weekday() < 5
        assert titulo[f["id"]]["valor"] == f["valor_liquido"]
        assert (f["status"] == "QUITADA") == (titulo[f["id"]]["status"] == "PAGO")


def test_quem_nao_paga_e_quem_paga_diferente(linhas: Linhas) -> None:
    hoje = nucleo.FIM.date()
    titulos = linhas["financeiro.titulo_receber"]
    for x in titulos:
        if x["status"] == "PAGO":
            assert (
                x["dt_pagamento"] is not None
                and x["dt_pagamento"] <= hoje
                and x["valor_pago"] is not None
            )
        else:
            assert x["dt_pagamento"] is None and x["valor_pago"] is None
            assert (x["status"] == "ATRASADO") == (x["dt_vencimento"] < hoje)
    pagos = [x for x in titulos if x["status"] == "PAGO"]
    diferentes = [x for x in pagos if abs(x["valor_pago"] - x["valor"]) > 0.005]
    assert 0.004 <= len(diferentes) / len(pagos) <= 0.025  # FIN-01, ~1,2%
    atrasados = [x for x in titulos if x["status"] == "ATRASADO"]
    assert (
        atrasados and sum(x["dt_vencimento"].year >= 2025 for x in atrasados) > len(atrasados) / 2
    )


def test_impostos_do_lucro_presumido(linhas: Linhas) -> None:
    tributo = {t["id"]: t["codigo"] for t in linhas["financeiro.tributo"]}
    a_pagar = {p["id"]: p for p in linhas["financeiro.titulo_pagar"]}
    for a in linhas["financeiro.imposto_apurado"]:
        codigo = tributo[a["tributo_id"]]
        assert (a["municipio_id"] is not None) == (codigo == "ISS")
        if codigo in ("IRPJ", "CSLL"):
            assert a["competencia"].month % 3 == 0  # apuração trimestral
        titulo = a_pagar[a["titulo_pagar_id"]]
        assert titulo["tipo"] == "IMPOSTOS" and titulo["valor"] == pytest.approx(
            a["valor_devido"], abs=0.5
        )
    assert {p["tipo"] for p in a_pagar.values()} == {
        "FOLHA",
        "ENCARGOS",
        "BENEFICIOS",
        "FORNECEDOR",
        "IMPOSTOS",
    }
    hoje = nucleo.FIM.date()
    assert all((p["status"] == "PAGO") == (p["dt_vencimento"] <= hoje) for p in a_pagar.values())


def test_o_consolidado_bate_ate_2021_e_diverge_cada_vez_mais_depois(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]], linhas: Linhas
) -> None:
    real: dict[tuple[date, int], tuple[int, float]] = gerado[1]["real_do_consolidado"]
    for c in linhas["financeiro.consolidado_gerencial"]:
        pessoas, faturado = real[(c["competencia"], c["filial_id"])]
        bate = c["headcount_informado"] == pessoas and c["faturamento_informado"] == pytest.approx(
            faturado, abs=0.005
        )
        assert bate == (c["competencia"].year < 2022), c["competencia"]
        assert c["dt_lancamento"] > c["competencia"] and c["origem"] == "PLANILHA"
    # a divergência do faturamento cresce ano a ano (o headcount por filial, na amostra, é pequeno
    # demais para medir em percentual; na base inteira a régua confere os dois)
    erro: dict[int, list[float]] = {}
    for c in linhas["financeiro.consolidado_gerencial"]:
        _, faturado = real[(c["competencia"], c["filial_id"])]
        soma = erro.setdefault(c["competencia"].year, [0.0, 0.0])
        soma[0] += abs(c["faturamento_informado"] - faturado)
        soma[1] += faturado
    serie = [erro[ano][0] / erro[ano][1] for ano in range(2022, 2027)]
    assert serie == sorted(serie) and serie[0] < 0.01 and serie[-1] > 0.07
    assert e5.medir(*gerado)["sujeira"]["GER-01/competencias_sem_divergencia"] == 0


def test_a_planilha_da_gerente_geral_e_o_consolidado_em_excel(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]], linhas: Linhas, tmp_path: Path
) -> None:
    escritas = e5.escrever_planilhas(*gerado, pasta=tmp_path)
    assert [p.name for p in escritas] == [f"consolidado_gerencial_{a}.xlsx" for a in bandas.ANOS]
    lida = pd.read_excel(escritas[6], sheet_name="Consolidado", header=2)  # cabeçalho na 3ª linha
    assert list(lida.columns) == [
        "Competência",
        "Filial",
        "Headcount",
        "Vagas abertas",
        "Faturamento (R$)",
        "Custo (R$)",
        "Lançado em",
    ]
    assert lida.iloc[-1]["Competência"] == "TOTAL"
    corpo = lida.iloc[:-1]
    de_2024 = [
        c for c in linhas["financeiro.consolidado_gerencial"] if c["competencia"].year == 2024
    ]
    assert len(corpo) == len(de_2024) == 36  # 12 meses, 3 filiais
    assert corpo["Faturamento (R$)"].sum() == pytest.approx(
        sum(c["faturamento_informado"] for c in de_2024), abs=0.01
    )
    assert lida.iloc[-1]["Faturamento (R$)"] == pytest.approx(
        corpo["Faturamento (R$)"].sum(), abs=0.01
    )
    assert set(corpo["Filial"]) == {"Atibaia (matriz)", "Bragança Paulista", "Extrema"}


@pytest.mark.skipif(not PLANILHAS.exists(), reason="planilhas versionadas ausentes")
def test_planilhas_versionadas_cobrem_a_historia() -> None:
    arquivos = sorted(PLANILHAS.glob("consolidado_gerencial_*.xlsx"))
    assert [a.stem[-4:] for a in arquivos] == [str(a) for a in bandas.ANOS]
    for arquivo in arquivos:
        lida = pd.read_excel(arquivo, header=2)
        assert lida.iloc[-1]["Competência"] == "TOTAL" and len(lida) >= 9
        assert (lida.iloc[:-1]["Headcount"] >= 0).all()


def test_replica_tem_o_financeiro_e_bate_com_as_planilhas() -> None:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta or not PLANILHAS.exists():
        pytest.skip(".env ou planilhas ausentes")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    replica = nucleo.Replica("127.0.0.1", porta, "replicador", senha)
    if replica.contar(["financeiro.fatura"])["financeiro.fatura"] == 0:
        pytest.skip("réplica ainda sem a etapa 5 (rode o gerador com --gravar)")
    na_replica = replica.ler(
        "financeiro.consolidado_gerencial",
        ["competencia", "headcount_informado", "faturamento_informado"],
    )
    nas_planilhas = pd.concat(
        pd.read_excel(a, header=2).iloc[:-1] for a in sorted(PLANILHAS.glob("*.xlsx"))
    )
    assert len(na_replica) == len(nas_planilhas)
    assert sum(int(x[1]) for x in na_replica) == int(nas_planilhas["Headcount"].sum())
    assert float(sum(x[2] for x in na_replica)) == pytest.approx(
        float(nas_planilhas["Faturamento (R$)"].sum()), abs=0.05
    )
