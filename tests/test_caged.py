"""Agregação e índice do CAGED certos numa amostra; tabelas versionadas coerentes."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import pytest

from rh_fictalent.fontes import caged

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "dados" / "publicos" / "caged"
CABECALHO = (
    "competênciamov;região;uf;município;seção;subclasse;saldomovimentação;cbo2002ocupação;"
    "categoria;graudeinstrução;idade;horascontratuais;raçacor;sexo;tipoempregador;"
    "tipoestabelecimento;tipomovimentação;tipodedeficiência;indtrabintermitente;indtrabparcial;"
    "salário;tamestabjan;indicadoraprendiz;origemdainformação;competênciadec;"
    "indicadordeforadoprazo;unidadesaláriocódigo;valorsaláriofixo"
)


def _linha(comp: str, uf: str, mun: str, secao: str, sub: str, saldo: str) -> str:
    resto = ";411010;101;7;30;44,00;3;1;0;1;97;0;0;0;1800,00;5;0;1;202401;0;5;1800,00"
    return f"{comp};3;{uf};{mun};{secao};{sub};{saldo}{resto}"


def _amostra() -> io.StringIO:
    linhas = [
        CABECALHO,
        _linha("202401", "35", "350410", "N", "7820500", "1"),  # Atibaia, 78.20, admissão
        _linha("202401", "35", "350410", "N", "7820500", "1"),
        _linha("202401", "35", "350410", "N", "7820500", "-1"),  # desligamento
        _linha("202401", "35", "350410", "G", "4711302", "1"),  # Atibaia, comércio
        _linha(
            "202401", "35", "355030", "N", "7810800", "1"
        ),  # São Paulo capital, 78.10: só estado
        _linha("202401", "35", "355030", "G", "4711302", "1"),  # capital, comércio: fora de tudo
        _linha("202401", "31", "312510", "C", "1091101", "-1"),  # Extrema, indústria
        _linha(
            "202312", "31", "312510", "N", "7830200", "1"
        ),  # competência anterior, Extrema, 78.30
    ]
    return io.StringIO("\n".join(linhas) + "\n")


def test_agregacao_por_municipio_secao_grupo_78_e_estado() -> None:
    acumulado = caged.agregar(_amostra(), sinal=1)
    assert acumulado[("2024-01", "350410", "N")] == [2, 1]
    assert acumulado[("2024-01", "350410", "78")] == [2, 1]
    assert acumulado[("2024-01", "350410", "G")] == [1, 0]
    assert acumulado[("2024-01", "35", "78")] == [3, 1], "estado soma capital e Atibaia no grupo 78"
    assert ("2024-01", "355030", "G") not in acumulado, "capital fora do grupo 78 não entra"
    assert acumulado[("2024-01", "312510", "C")] == [0, 1]
    assert acumulado[("2023-12", "312510", "78")] == [1, 0]


def test_exclusao_inverte_o_saldo() -> None:
    acumulado = caged.agregar(_amostra(), sinal=1)
    caged.agregar(_amostra(), sinal=-1, acumulado=acumulado)
    assert all(v == [0, 0] for v in acumulado.values())


def test_tabela_mensal_recorta_o_periodo_e_calcula_o_saldo() -> None:
    acumulado = caged.agregar(_amostra(), sinal=1)
    tabela = caged.tabela_mensal(acumulado, "2024-01", "2024-12")
    assert set(tabela["competencia"]) == {"2024-01"}
    linha = tabela[(tabela["escopo"] == "350410") & (tabela["grupo"] == "N")].iloc[0]
    assert linha["saldo"] == 1 and linha["nome_escopo"] == "Atibaia"


def test_indice_sazonal_e_um_na_media_e_sobe_no_mes_forte() -> None:
    meses = [f"2024-{m:02d}" for m in range(1, 13)] + [f"2025-{m:02d}" for m in range(1, 13)]
    admissoes = [100] * 24
    admissoes[10] = admissoes[22] = 200  # novembro dobrado nos dois anos
    mensal = pd.DataFrame(
        {
            "competencia": meses,
            "escopo": "350410",
            "grupo": "78",
            "admissoes": admissoes,
            "desligamentos": 50,
        }
    )
    indice = caged.indice_sazonal(mensal)
    assert len(indice) == 12 and set(indice["anos"]) == {2}
    assert indice["indice_admissoes"].mean() == pytest.approx(1.0, abs=1e-3)  # 4 casas
    novembro = indice[indice["mes"] == 11].iloc[0]
    assert novembro["indice_admissoes"] > 1.7 and novembro["indice_desligamentos"] == pytest.approx(
        1.0
    )


def test_ano_incompleto_fica_fora_do_indice() -> None:
    mensal = pd.DataFrame(
        {
            "competencia": [f"2024-{m:02d}" for m in range(1, 7)],
            "escopo": "35",
            "grupo": "78",
            "admissoes": 10,
            "desligamentos": 5,
        }
    )
    assert caged.indice_sazonal(mensal).empty


def test_competencias_inclusivas() -> None:
    assert caged.competencias("2023-11", "2024-02") == ["202311", "202312", "202401", "202402"]


@pytest.mark.skipif(
    not (SAIDA / "indice_sazonal.csv").exists(), reason="tabelas derivadas ainda não geradas"
)
def test_tabelas_versionadas_sao_coerentes() -> None:
    mensal = pd.read_csv(SAIDA / "movimentacao_mensal.csv", dtype={"escopo": str, "grupo": str})
    indice = pd.read_csv(SAIDA / "indice_sazonal.csv", dtype={"escopo": str, "grupo": str})
    fonte = json.loads((SAIDA / "fonte.json").read_text(encoding="utf-8"))
    assert set(caged.MUNICIPIOS) <= set(mensal["escopo"]) and set(caged.UFS) <= set(
        mensal["escopo"]
    )
    assert mensal["competencia"].min() == "2023-01" and mensal["competencia"].max() == "2025-12"
    grupo78 = mensal[(mensal["grupo"] == "78") & (mensal["escopo"] == "35")]
    assert len(grupo78) == 36 and (grupo78["admissoes"] > 0).all()
    for (escopo, grupo), bloco in indice.groupby(["escopo", "grupo"]):
        assert len(bloco) == 12, (escopo, grupo)
        assert bloco["indice_admissoes"].mean() == pytest.approx(1.0, abs=1e-3), (escopo, grupo)
    assert fonte["agregacao"].startswith("por competência da movimentação")
    assert len(fonte["competencias_declaracao"]) == 36
