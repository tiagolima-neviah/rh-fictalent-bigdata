"""A etapa 1 é determinística, coerente por dentro e cabe na DDL; na réplica, é o que foi gerado."""

from __future__ import annotations

import re
import socket
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import catalogos, etapa1_cadastro, nucleo
from rh_fictalent.gerador.__main__ import main

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"
DDL = (RAIZ / "staging" / "ddl" / "01_cadastro.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tabelas() -> nucleo.Tabelas:
    return etapa1_cadastro.gerar(PUBLICOS)


def _colunas_da_ddl(tabela: str) -> list[str]:
    corpo = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\) ENCRYPTION", DDL, re.S)
    assert corpo, tabela
    linhas = [linha.strip() for linha in corpo.group(1).splitlines()]
    return [
        linha.split()[0]
        for linha in linhas
        if linha and not linha.startswith(("PRIMARY", "UNIQUE", "KEY", "CONSTRAINT"))
    ]


def _limites_da_ddl(tabela: str) -> dict[str, int]:
    corpo = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\) ENCRYPTION", DDL, re.S)
    assert corpo, tabela
    achados = re.findall(r"^\s+(\w+)\s+(?:VAR)?CHAR\((\d+)\)", corpo.group(1), re.M)
    return {coluna: int(tamanho) for coluna, tamanho in achados}


def test_todo_texto_cabe_na_coluna_da_ddl(tabelas: nucleo.Tabelas) -> None:
    for nome, quadro in tabelas.items():
        for coluna, limite in _limites_da_ddl(nome.split(".")[1]).items():
            maior = quadro[coluna].dropna().map(len).max()
            assert pd.isna(maior) or maior <= limite, (nome, coluna, maior, limite)


def test_gera_as_doze_tabelas_do_cadastro_com_as_colunas_da_ddl(tabelas: nucleo.Tabelas) -> None:
    assert len(tabelas) == 12 and all(nome.startswith("cadastro.") for nome in tabelas)
    for nome, quadro in tabelas.items():
        assert list(quadro.columns) == _colunas_da_ddl(nome.split(".")[1]), nome
        assert quadro["id"].tolist() == list(range(1, len(quadro) + 1))


def test_duas_execucoes_dao_a_mesma_base(tabelas: nucleo.Tabelas) -> None:
    de_novo = etapa1_cadastro.gerar(PUBLICOS)
    assert nucleo.assinatura(de_novo) == nucleo.assinatura(tabelas)
    a, b = nucleo.aleatorio("etapa1_cadastro"), nucleo.aleatorio("etapa2_carteira")
    assert a.integers(1 << 30) != b.integers(1 << 30)  # cada etapa tem o seu sorteio


def test_o_mundo_e_o_do_caso(tabelas: nucleo.Tabelas) -> None:
    filiais = tabelas["cadastro.filial"]
    assert filiais["codigo"].tolist() == ["ATB", "BRG", "EXT"]
    assert filiais["tipo"].tolist() == ["MATRIZ", "FILIAL", "FILIAL"]
    assert filiais["dt_abertura"].tolist() == [
        date(2018, 1, 2),
        date(2019, 3, 11),
        date(2022, 8, 1),
    ]
    municipios = tabelas["cadastro.municipio"]
    assert {"3504107", "3507605", "3125101"} <= set(municipios["codigo_ibge"])
    assert len(municipios) == 111 and set(municipios["uf"]) == {"SP", "MG"}
    assert len(tabelas["cadastro.regiao"]) == len(catalogos.REGIOES)
    assert len(tabelas["cadastro.funcao"]) == 45
    centros = tabelas["cadastro.centro_custo"]
    assert centros["tipo"].tolist() == ["FILIAL", "FILIAL", "FILIAL", "RETAGUARDA"]


def test_carimbos_contam_a_historia_e_nao_o_dia_da_geracao(tabelas: nucleo.Tabelas) -> None:
    filiais = tabelas["cadastro.filial"].set_index("codigo")
    assert filiais.loc["EXT", "criado_em"] == datetime(2022, 8, 1, 8, 0)
    for quadro in tabelas.values():
        assert (quadro["criado_em"] >= datetime(2018, 1, 2, 8, 0)).all()
        assert (quadro["atualizado_em"] <= nucleo.FIM).all()
    markup = tabelas["cadastro.parametro"].query("chave == 'MARKUP_PADRAO'")
    assert markup["valor"].tolist() == ["1.55", "1.50"]
    assert markup["vigencia_fim"].tolist() == [date(2021, 12, 31), None]
    assert markup["atualizado_em"].tolist()[0] == datetime(2022, 1, 1, 8, 0)  # encerrada depois


def test_pisos_sobem_todo_ano_e_a_cidade_muda_o_preco(tabelas: nucleo.Tabelas) -> None:
    pisos = tabelas["cadastro.piso_salarial"].merge(
        tabelas["cadastro.convencao_coletiva"][["id", "municipio_id"]],
        left_on="convencao_id",
        right_on="id",
        suffixes=("", "_convencao"),
    )
    assert len(pisos) == (10 + 10 + 9) * 45  # SP com a vigência de 2017; Extrema começa em 2018
    for _, serie in pisos.groupby(["municipio_id", "funcao_id"]):
        valores = serie.sort_values("vigencia_inicio")["valor_piso"].tolist()
        assert valores == sorted(valores) and valores[0] < valores[-1]
    auxiliar = pisos[(pisos["funcao_id"] == 1) & pisos["vigencia_fim"].isna()]
    assert auxiliar["valor_piso"].nunique() == 3  # três cidades, três pisos
    assert auxiliar["valor_piso"].between(1500, 2000).all()
    insalubres = {i + 1 for i, f in enumerate(catalogos.FUNCOES) if f.insalubre}
    com_adicional = set(pisos.loc[pisos["adicional_insalubridade_pct"] > 0, "funcao_id"])
    assert com_adicional == insalubres


def test_feriados_vem_da_fonte_publica_mais_os_locais(tabelas: nucleo.Tabelas) -> None:
    feriados = tabelas["cadastro.feriado"]
    assert len(feriados) == 120 + 4 * 9
    assert feriados["abrangencia"].value_counts().to_dict() == {
        "NACIONAL": 120,
        "MUNICIPAL": 27,
        "ESTADUAL": 9,
    }
    municipais = feriados[feriados["abrangencia"] == "MUNICIPAL"]
    assert municipais["municipio_id"].notna().all()
    assert feriados[feriados["abrangencia"] != "MUNICIPAL"]["municipio_id"].isna().all()
    assert feriados["data"].min().year == 2018 and feriados["data"].max().year == 2026


def test_valores_saem_em_tipos_nativos_para_o_driver(tabelas: nucleo.Tabelas) -> None:
    permitidos = (int, float, str, bool, date, datetime, type(None))
    for nome, quadro in tabelas.items():
        for linha in nucleo.valores(quadro):
            assert all(type(v) in permitidos for v in linha), (nome, linha)


def test_conferir_pega_chave_orfa_e_vigencia_dupla(tabelas: nucleo.Tabelas) -> None:
    quebrada = {nome: quadro.copy() for nome, quadro in tabelas.items()}
    quebrada["cadastro.filial"].loc[0, "endereco_id"] = 999
    quebrada["cadastro.convencao_coletiva"].loc[0, "vigencia_fim"] = None
    with pytest.raises(ValueError) as erro:
        etapa1_cadastro.conferir(quebrada)
    assert "endereco_id" in str(erro.value) and "convenções em" in str(erro.value)


def test_nome_de_tabela_nunca_vira_sql_sem_conferencia() -> None:
    with pytest.raises(ValueError):
        nucleo.Replica("h", 1, "u", "s").contar(["cadastro.regiao; DROP TABLE x"])


def test_cli_gera_e_confere_sem_gravar(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(RAIZ)
    assert main(["--etapa", "1"]) == 0
    saida = capsys.readouterr().out
    assert "cadastro.piso_salarial" in saida and "assinatura" in saida and "gravado" not in saida
    with pytest.raises(SystemExit):
        main(["--etapa", "1", "--zerar"])


# ───────────────────────────── contra a réplica ───────────────────────────────
def _replica() -> nucleo.Replica | None:
    senha = ENV.get("REPLICADOR_PASSWORD")
    porta = int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        return None
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        return None
    return nucleo.Replica("127.0.0.1", porta, "replicador", senha)


def _normal(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return round(float(valor), 4)
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, float):
        return round(valor, 4)
    return valor


def test_replica_tem_exatamente_o_que_a_etapa_gera(tabelas: nucleo.Tabelas) -> None:
    replica = _replica()
    if replica is None:
        pytest.skip("réplica fora do ar ou .env ausente")
    if replica.contar(["cadastro.regiao"])["cadastro.regiao"] == 0:
        pytest.skip("réplica ainda sem a etapa 1 (rode o gerador com --gravar)")
    for nome, quadro in tabelas.items():
        na_replica = [
            [_normal(v) for v in linha] for linha in replica.ler(nome, list(quadro.columns))
        ]
        gerado = [[_normal(v) for v in linha] for linha in nucleo.valores(quadro)]
        assert na_replica == gerado, nome
    assert isinstance(tabelas["cadastro.regiao"], pd.DataFrame)
