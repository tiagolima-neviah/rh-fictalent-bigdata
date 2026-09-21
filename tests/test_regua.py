"""A régua aprova o que está na banda, reprova o que saiu e não decide sem medida."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from rh_fictalent.validacao import bandas, derivadas
from rh_fictalent.validacao.__main__ import contrato, main
from rh_fictalent.validacao.regua import FAMILIAS, Banda, Check, Situacao, Veredito, avaliar

RAIZ = Path(__file__).resolve().parents[1]
INDICE_CAGED = RAIZ / "dados" / "publicos" / "caged" / "indice_sazonal.csv"


def medidas_no_centro() -> dict[str, dict[str, float]]:
    """Uma base perfeita: cada medida no centro da sua banda."""
    medidas: dict[str, dict[str, float]] = {}
    for check in bandas.checks():
        medidas.setdefault(check.medida, {})[check.chave] = check.banda.centro()
    return medidas


# ───────────────────────────── a banda ────────────────────────────────────────
def test_banda_inclui_os_limites_e_recusa_nan() -> None:
    banda = Banda(1.0, 2.0)
    assert banda.contem(1.0) and banda.contem(2.0) and banda.contem(1.5)
    assert not banda.contem(0.999) and not banda.contem(2.001) and not banda.contem(math.nan)
    assert Banda(minimo=0.7).contem(10) and not Banda(minimo=0.7).contem(0.69)
    assert Banda(maximo=2).contem(-5) and not Banda(maximo=2).contem(3)
    assert Banda.exatamente(0).contem(0) and not Banda.exatamente(0).contem(1)


def test_banda_em_torno_usa_a_maior_tolerancia() -> None:
    assert Banda.em_torno(100, relativa=0.10) == Banda(90, 110)
    assert Banda.em_torno(12, absoluta=2, relativa=0.15) == Banda(10, 14)  # 15% de 12 é 1,8
    assert Banda.em_torno(66, absoluta=2, relativa=0.15).contem(57)  # 15% de 66 é 9,9


def test_banda_invalida_nao_nasce() -> None:
    with pytest.raises(ValueError):
        Banda()
    with pytest.raises(ValueError):
        Banda(2, 1)
    with pytest.raises(ValueError):
        Check("X", "inexistente", "d", "m", "k", Banda(0, 1))


def test_banda_se_descreve() -> None:
    assert str(Banda(90, 110)) == "[90, 110]"
    assert str(Banda(maximo=0.35)) == "<= 0,35"
    assert str(Banda(minimo=0.7)) == ">= 0,7"
    assert str(Banda.exatamente(0)) == "= 0"


# ───────────────────────────── o contrato ─────────────────────────────────────
def test_checks_cobrem_as_seis_familias_com_codigos_unicos() -> None:
    todos = bandas.checks()
    codigos = [c.codigo for c in todos]
    assert len(codigos) == len(set(codigos))
    assert {c.familia for c in todos} == set(FAMILIAS)
    assert len(todos) > 150


def test_toda_medida_consumida_esta_no_contrato_e_vice_versa() -> None:
    consumidas = {c.medida for c in bandas.checks()}
    assert consumidas == set(bandas.MEDIDAS)


def test_bandas_dizem_o_que_o_plano_diz() -> None:
    por_codigo = {c.codigo: c.banda for c in bandas.checks()}
    assert por_codigo["E-01/2024"].contem(66) and not por_codigo["E-01/2024"].contem(80)
    assert por_codigo["E-02/2025"].contem(1000) and not por_codigo["E-02/2025"].contem(1200)
    assert por_codigo["E-03/2026"].contem(800)  # 2026: o headcount de setembro
    assert por_codigo["H-01/2019"].contem(5) and por_codigo["H-01/2019"].contem(6)
    assert por_codigo["H-01/2025"].contem(11) and not por_codigo["H-01/2025"].contem(8)
    assert por_codigo["H-07/2024"].contem(0.87) and not por_codigo["H-07/2024"].contem(0.95)
    assert por_codigo["H-09"] == Banda(6, 9)
    assert por_codigo["GER-01/2022"].contem(0.005) and por_codigo["GER-01/2026"].contem(0.09)
    assert por_codigo["C-05"] == Banda.exatamente(0)


def test_nenhum_ano_pode_fechar_com_prejuizo() -> None:
    for ano in bandas.ANOS:
        banda = {c.codigo: c.banda for c in bandas.checks()}[f"H-10/{ano}"]
        assert banda.minimo is not None and banda.minimo > 0
        assert not banda.contem(0.0) and not banda.contem(-0.01)
        assert banda.contem(bandas.MARGEM_LIQUIDA[ano])


# ───────────────────────────── o laudo ────────────────────────────────────────
def test_base_no_centro_das_bandas_e_aprovada() -> None:
    laudo = avaliar(bandas.checks(), medidas_no_centro())
    assert laudo.veredito == Veredito.APROVADA
    assert not laudo.com_situacao(Situacao.REPROVADO) and not laudo.com_situacao(Situacao.PENDENTE)
    assert "RÉGUA APROVADA" in laudo.texto()


def test_um_ano_no_vermelho_reprova_a_base_e_o_laudo_diz_qual() -> None:
    medidas = medidas_no_centro()
    medidas["margem_liquida"]["2026"] = -0.01
    medidas["violacoes"]["C-05"] = 3
    laudo = avaliar(bandas.checks(), medidas)
    assert laudo.veredito == Veredito.REPROVADA
    assert {r.check.codigo for r in laudo.com_situacao(Situacao.REPROVADO)} == {"H-10/2026", "C-05"}
    texto = laudo.texto(so_problemas=True)
    assert "✗ H-10/2026" in texto and "✗ C-05" in texto
    assert not any(linha.startswith("  ✓") for linha in texto.splitlines())
    assert "Reprovou, regenera" in texto


def test_medida_ausente_deixa_o_laudo_incompleto_e_reprovado_vence_pendente() -> None:
    medidas = medidas_no_centro()
    del medidas["sujeira"]
    laudo = avaliar(bandas.checks(), medidas)
    assert laudo.veredito == Veredito.INCOMPLETA
    assert all(r.check.familia == "sujeira" for r in laudo.com_situacao(Situacao.PENDENTE))
    medidas["headcount_medio"]["2024"] = 5000
    assert avaliar(bandas.checks(), medidas).veredito == Veredito.REPROVADA
    assert avaliar([], {}).veredito == Veredito.INCOMPLETA  # régua vazia não aprova nada


def test_regua_por_familia_so_olha_a_familia_pedida() -> None:
    medidas = {"violacoes": {c: 0.0 for c in bandas.INVARIANTES}}
    laudo = avaliar(bandas.checks(), medidas, familias=["coerencia"])
    assert laudo.veredito == Veredito.APROVADA and len(laudo.resultados) == len(bandas.INVARIANTES)
    assert laudo.resumo() == {"coerencia": {"APROVADO": 5, "REPROVADO": 0, "PENDENTE": 0}}
    with pytest.raises(ValueError):
        avaliar(bandas.checks(), medidas, familias=["inexistente"])


def test_laudo_em_json_e_legivel_por_maquina() -> None:
    corpo = json.loads(avaliar(bandas.checks(), medidas_no_centro()).para_json())
    assert corpo["veredito"] == "APROVADA" and len(corpo["resultados"]) == len(bandas.checks())
    assert {"codigo", "banda", "valor", "situacao"} <= set(corpo["resultados"][0])


# ───────────────────────────── as derivadas ───────────────────────────────────
def _serie(anos: range, valor_do_mes: dict[int, float]) -> dict[str, float]:
    return {f"{a}-{m:02d}": v for a in anos for m, v in valor_do_mes.items()}


def test_desvio_da_media_movel_ignora_os_choques_declarados() -> None:
    plano = dict.fromkeys(range(1, 13), 100.0)
    serie = _serie(range(2021, 2023), plano)
    assert derivadas.desvio_maximo_da_media_movel(serie) == 0.0
    serie["2022-01"] = 40.0  # janeiro desaba: é a história, não conta
    assert derivadas.desvio_maximo_da_media_movel(serie) == pytest.approx(0.25)  # março, por tabela
    serie["2022-07"] = 200.0  # julho dobra do nada: conta
    assert derivadas.desvio_maximo_da_media_movel(serie) == pytest.approx(1.0)
    assert "2020-04" in derivadas.meses_de_choque(serie)


def test_indice_sazonal_tem_media_um_e_ignora_ano_incompleto() -> None:
    forma = {m: 100.0 for m in range(1, 13)} | {11: 160.0, 1: 40.0}
    serie = _serie(range(2023, 2026), forma) | {"2026-01": 999.0}
    indice = derivadas.indice_sazonal(serie)
    assert sum(indice.values()) / 12 == pytest.approx(1.0)
    assert indice[11] == pytest.approx(1.6) and indice[1] == pytest.approx(0.4)


def test_comparar_indices_mede_desvio_e_correlacao() -> None:
    referencia = {m: 1.0 for m in range(1, 13)} | {11: 1.3, 12: 0.7}
    igual = derivadas.comparar_indices(referencia, referencia)
    assert igual["desvio_maximo"] == 0 and igual["correlacao"] == pytest.approx(1.0)
    invertido = {m: 2 - v for m, v in referencia.items()}
    contra = derivadas.comparar_indices(invertido, referencia)
    assert contra["desvio_maximo"] == pytest.approx(0.6) and contra["correlacao"] < -0.99
    with pytest.raises(ValueError):
        derivadas.comparar_indices({1: 1.0}, referencia)


def test_naturalidade_separa_crise_de_combinacao() -> None:
    meses = [f"{a}-{m:02d}" for a in range(2019, 2027) for m in range(1, 13)]
    headcount = dict.fromkeys(meses, 500.0)
    entradas = dict.fromkeys(meses, 1.0)
    saidas = dict.fromkeys(meses, 0.0) | {"2020-04": 4.0, "2025-12": 5.0, "2023-06": 2.0}
    medida = derivadas.naturalidade(headcount, entradas, saidas)
    assert medida["saidas_max_mes_fora_crise"] == 2.0  # pandemia e crise não contam
    assert medida["entradas_max_mes"] == 1.0
    assert medida["entradas_concentracao_max"] == pytest.approx(1 / 12)
    entradas["2024-08"] = 9.0  # "todos os clientes combinaram de entrar em agosto"
    medida = derivadas.naturalidade(headcount, entradas, saidas)
    laudo = avaliar(bandas.checks(), {"naturalidade": medida}, familias=["naturalidade"])
    assert {r.check.codigo for r in laudo.com_situacao(Situacao.REPROVADO)} == {"N-03", "N-04"}


@pytest.mark.skipif(not INDICE_CAGED.exists(), reason="índice do CAGED ausente")
def test_base_com_o_ritmo_do_caged_passa_na_familia_de_sazonalidade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(RAIZ)
    referencia = derivadas.referencia_caged()
    assert sorted(referencia) == list(range(1, 13))
    assert sum(referencia.values()) / 12 == pytest.approx(1.0, abs=1e-3)
    assert referencia[11] > 1.1 and referencia[10] > 1.1  # o pico do segundo semestre é público
    admissoes = _serie(range(2023, 2026), {m: 300 * v for m, v in referencia.items()})
    medida = derivadas.sazonalidade_contra_caged(admissoes)
    assert medida["desvio_maximo"] == pytest.approx(0, abs=1e-9)
    plana = _serie(range(2023, 2026), dict.fromkeys(range(1, 13), 300.0))
    laudo = avaliar(
        bandas.checks(),
        {"sazonalidade_admissoes": derivadas.sazonalidade_contra_caged(plana)},
        familias=["sazonalidade"],
    )
    reprovados = {r.check.codigo for r in laudo.com_situacao(Situacao.REPROVADO)}
    assert reprovados == {"S-01/correlacao"}  # base sem ritmo: os desvios passam, o ritmo não


# ───────────────────────────── a linha de comando ─────────────────────────────
def test_cli_devolve_o_veredito_no_codigo_de_saida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = tmp_path / "medidas.json"
    medidas = medidas_no_centro()
    arquivo.write_text(json.dumps(medidas), encoding="utf-8")
    assert main(["--medidas", str(arquivo)]) == 0
    assert "RÉGUA APROVADA" in capsys.readouterr().out
    medidas["fill_rate"]["2019"] = 0.5
    arquivo.write_text(json.dumps(medidas), encoding="utf-8")
    assert main(["--medidas", str(arquivo), "--so-problemas"]) == 1
    assert "H-07/2019" in capsys.readouterr().out
    del medidas["fill_rate"]
    arquivo.write_text(json.dumps(medidas), encoding="utf-8")
    assert main(["--medidas", str(arquivo), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["veredito"] == "INCOMPLETA"


def test_contrato_lista_todas_as_medidas() -> None:
    texto = contrato()
    assert all(medida in texto for medida in bandas.MEDIDAS)
    assert f"{len(bandas.checks())} checks" in texto
