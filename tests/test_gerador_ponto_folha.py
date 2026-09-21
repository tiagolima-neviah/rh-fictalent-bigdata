"""O ponto e a folha numa amostra de 5% das alocações: cabem na DDL, fecham entre si, têm a
sujeira do relógio na medida, e a réplica (quando gravada) tem a base inteira."""

from __future__ import annotations

import re
import socket
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import catalogos_folha as cf
from rh_fictalent.gerador import etapa4_ponto_folha as e4
from rh_fictalent.gerador import nucleo

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"
FRACAO = 0.05
DDL = "\n".join(
    (RAIZ / "staging" / "ddl" / nome).read_text(encoding="utf-8")
    for nome in ("05_ponto.sql", "06_folha.sql")
)


@pytest.fixture(scope="module")
def gerado() -> tuple[nucleo.Tabelas, dict[str, Any]]:
    return e4.gerar_com_base(PUBLICOS, FRACAO)


@pytest.fixture(scope="module")
def tabelas(gerado: tuple[nucleo.Tabelas, dict[str, Any]]) -> nucleo.Tabelas:
    return gerado[0]


def test_tabelas_tem_as_colunas_da_ddl_e_os_textos_cabem(tabelas: nucleo.Tabelas) -> None:
    assert list(tabelas) == list(e4.ORDEM) and len(tabelas) == 12
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
            maior = quadro[coluna].dropna().map(len).max()
            assert pd.isna(maior) or maior <= int(limite), (nome, coluna)


def test_o_aceite_da_etapa_passa_na_amostra(gerado: tuple[nucleo.Tabelas, dict[str, Any]]) -> None:
    tabelas, base = gerado
    e4.conferir(tabelas, base, FRACAO)  # chaves, unicidade, carimbos, coerência e sujeira
    medidas = e4.medir(tabelas, base)
    assert medidas["violacoes"] == {"C-02": 0.0, "C-04": 0.0}
    # na base inteira os volumes caem na banda; aqui, a amostra vezes 20 dá a ordem de grandeza
    assert 3_000_000 < medidas["linhas_tabela"]["ponto.marcacao"] / FRACAO < 5_800_000
    assert 750_000 < medidas["linhas_tabela"]["ponto.apontamento"] / FRACAO < 1_450_000


def test_o_relogio_tem_a_sujeira_do_catalogo(gerado: tuple[nucleo.Tabelas, dict[str, Any]]) -> None:
    sujeira = e4.medir(*gerado)["sujeira"]
    assert 0.020 <= sujeira["PON-01"] <= 0.030  # falta uma batida em ~2,5% dos dias
    assert 0.004 <= sujeira["PON-02"] <= 0.008  # batida repetida no mesmo minuto em ~0,6%
    marcacao = gerado[0]["ponto.marcacao"]
    assert set(marcacao["tipo"]) == set(cf.TIPOS_DE_MARCACAO)
    assert marcacao["origem"].value_counts(normalize=True)["MANUAL"] == pytest.approx(
        0.03, abs=0.01
    )
    assert marcacao["criado_em"].is_monotonic_increasing  # o id segue o relógio


def test_dia_normal_tem_batidas_e_dia_de_falta_nao_tem(tabelas: nucleo.Tabelas) -> None:
    apontamento, marcacao = tabelas["ponto.apontamento"], tabelas["ponto.marcacao"]

    def dia(quadro: pd.DataFrame) -> pd.Series[str]:
        return quadro["colaborador_id"].astype(str) + "|" + quadro["data"].astype(str)

    com_batida = set(dia(marcacao))
    normais = apontamento[apontamento["status"] == "NORMAL"]
    ausentes = apontamento[apontamento["status"].isin(["FALTA", "ATESTADO", "FERIADO"])]
    assert dia(normais).isin(com_batida).mean() > 0.999
    assert not dia(ausentes).isin(com_batida).any()
    assert (ausentes["horas_trabalhadas"] == 0).all() and (normais["horas_trabalhadas"] > 0).all()
    assert apontamento["status"].value_counts(normalize=True)["FALTA"] < 0.06
    ocorrencia = tabelas["ponto.ocorrencia_ponto"]
    faltas = ocorrencia["tipo"].isin(["FALTA_JUSTIFICADA", "FALTA_INJUSTIFICADA"]).sum()
    assert faltas == (apontamento["status"] == "FALTA").sum()


def test_a_folha_fecha_com_os_itens_e_o_rateio_com_a_folha(tabelas: nucleo.Tabelas) -> None:
    folha, item = tabelas["folha.folha_competencia"], tabelas["folha.folha_item"]
    tipo = np.array(["", *[e[2] for e in cf.EVENTOS]], dtype=object)[item["evento_id"].to_numpy()]
    for coluna, qual in (
        ("total_proventos", "PROVENTO"),
        ("total_descontos", "DESCONTO"),
        ("total_encargos", "ENCARGO"),
    ):
        somado = item[tipo == qual].groupby("folha_competencia_id")["valor"].sum()
        esperado = folha.set_index("id")[coluna]
        assert np.allclose(somado.reindex(esperado.index, fill_value=0.0), esperado, atol=0.01), (
            coluna
        )
    abertas = folha[folha["status"] == "ABERTA"]
    assert set(abertas["competencia"].astype(str)) == {"2026-09-01"}  # só o mês corrente
    assert abertas["dt_fechamento"].isna().all() and (abertas["total_proventos"] == 0).all()
    rateio = tabelas["folha.rateio_custo"]
    partes = rateio[["valor_salario", "valor_encargos", "valor_provisoes", "valor_beneficios"]].sum(
        axis=1
    )
    assert np.allclose(partes, rateio["custo_total"], atol=0.01)
    # encargos patronais de 35,8% sobre a remuneração, em toda linha
    assert np.allclose(rateio["valor_encargos"], rateio["valor_salario"] * 0.358, atol=0.05)


def test_a_provisao_acumula_e_e_baixada_na_rescisao(tabelas: nucleo.Tabelas) -> None:
    provisao = tabelas["folha.provisao"]
    assert set(provisao["tipo"]) == {"DECIMO_TERCEIRO", "FERIAS", "ENCARGOS"}
    assert (provisao["saldo_acumulado"] >= -0.01).all()
    assert (provisao["valor_mes"] < 0).any() and (
        provisao["valor_mes"] > 0
    ).any()  # acumula e baixa
    item = tabelas["folha.folha_item"]
    codigo = np.array(["", *[e[0] for e in cf.EVENTOS]], dtype=object)[item["evento_id"].to_numpy()]
    assert {"RESC_13", "RESC_FER", "DEC_TERC", "PROV_13", "INSS", "FGTS", "VT_EMP"} <= set(codigo)
    assert (item["valor"] > 0).all()


def test_banco_de_horas_encadeia_o_saldo(tabelas: nucleo.Tabelas) -> None:
    banco = tabelas["ponto.banco_horas"].sort_values(["colaborador_id", "competencia"])
    calculado = banco["saldo_anterior"] + banco["creditos"] - banco["debitos"]
    assert np.allclose(calculado, banco["saldo_final"], atol=0.01)
    anterior = banco.groupby("colaborador_id")["saldo_final"].shift(1).fillna(0.0)
    assert np.allclose(anterior, banco["saldo_anterior"], atol=0.01)


def test_valores_tipados_viram_tipos_nativos_para_o_driver(tabelas: nucleo.Tabelas) -> None:
    from datetime import date, datetime

    for nome in (
        "ponto.marcacao",
        "ponto.apontamento",
        "folha.folha_competencia",
        "folha.provisao",
    ):
        linha = nucleo.valores(tabelas[nome].head(50))
        for valores in linha:
            assert all(
                type(v) in (int, float, str, bool, date, type(None)) or isinstance(v, datetime)
                for v in valores
            ), nome
    (primeira,) = nucleo.valores(tabelas["ponto.apontamento"].head(1))
    assert type(primeira[3]) is date and isinstance(primeira[-1], datetime)


# ───────────────────────────── contra a réplica ───────────────────────────────
def test_replica_tem_a_base_inteira_do_ponto_e_da_folha() -> None:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        pytest.skip(".env ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    replica = nucleo.Replica("127.0.0.1", porta, "replicador", senha)
    contagem = replica.contar(list(e4.ORDEM))
    if contagem["ponto.marcacao"] == 0:
        pytest.skip("réplica ainda sem a etapa 4 (rode o gerador com --gravar)")
    assert 3_080_000 <= contagem["ponto.marcacao"] <= 5_720_000
    assert 770_000 <= contagem["ponto.apontamento"] <= 1_430_000
    assert 602_000 <= contagem["folha.folha_item"] <= 1_118_000
    assert contagem["folha.evento_folha"] == len(cf.EVENTOS)
    assert all(quantas > 0 for quantas in contagem.values())
