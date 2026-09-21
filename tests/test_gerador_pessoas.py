"""O funil e as pessoas: determinísticos, cabem na DDL, passam na régua e contam a história."""

from __future__ import annotations

import re
import socket
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import etapa2_carteira, etapa3_pessoas, nucleo
from rh_fictalent.gerador import etapa3_ocupacao as motor
from rh_fictalent.validacao.regua import Veredito

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"
DDL = "\n".join(
    (RAIZ / "staging" / "ddl" / nome).read_text(encoding="utf-8")
    for nome in ("01_cadastro.sql", "03_ats.sql", "04_pessoas.sql")
)
Linhas = dict[str, list[dict[str, Any]]]


@pytest.fixture(scope="module")
def gerado() -> tuple[nucleo.Tabelas, dict[str, Any]]:
    return etapa3_pessoas.gerar_com_gabarito(PUBLICOS)


@pytest.fixture(scope="module")
def tabelas(gerado: tuple[nucleo.Tabelas, dict[str, Any]]) -> nucleo.Tabelas:
    return gerado[0]


@pytest.fixture(scope="module")
def linhas(tabelas: nucleo.Tabelas) -> Linhas:
    pequenas = [n for n, q in tabelas.items() if len(q) < 100_000]
    return {nome: etapa2_carteira._registros(tabelas[nome]) for nome in pequenas}


def test_tabelas_tem_as_colunas_da_ddl_e_os_textos_cabem(tabelas: nucleo.Tabelas) -> None:
    assert len(tabelas) == 18
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
            assert maior <= int(limite), (nome, coluna, maior, limite)


def test_duas_execucoes_dao_a_mesma_base(tabelas: nucleo.Tabelas) -> None:
    de_novo, _ = etapa3_pessoas.gerar_com_gabarito(PUBLICOS)
    for nome in ("ats.vaga", "ats.candidato", "pessoas.contrato_trabalho", "pessoas.desligamento"):
        assert nucleo.assinatura({nome: de_novo[nome]}) == nucleo.assinatura({nome: tabelas[nome]})
    assert {n: len(q) for n, q in de_novo.items()} == {n: len(q) for n, q in tabelas.items()}


def test_a_regua_aprova_tudo_o_que_ja_da_para_medir(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]],
) -> None:
    tabelas, gabarito = gerado
    etapa3_pessoas.conferir(tabelas, gabarito)  # chaves, unicidade, carimbos e régua: não levanta
    medidas = etapa3_pessoas.medir(tabelas, gabarito)
    laudo = etapa3_pessoas.laudo_parcial(medidas)
    assert laudo.veredito == Veredito.APROVADA, laudo.texto(so_problemas=True)
    assert len(laudo.resultados) >= 130
    assert medidas["violacoes"] == {"C-01": 0.0, "C-05": 0.0}
    assert 1_000_000 < sum(len(q) for q in tabelas.values()) < 1_600_000


def test_a_operacao_cede_a_partir_de_2023(gerado: tuple[nucleo.Tabelas, dict[str, Any]]) -> None:
    medidas = etapa3_pessoas.medir(*gerado)
    for medida in (
        "ttf_temporario_mediana",
        "no_show_entrevista",
        "turnover_90d",
        "posto_descoberto_dias",
    ):
        serie = medidas[medida]
        assert serie["2025"] > serie["2024"] > serie["2023"] > serie["2021"], medida
    assert (
        medidas["fill_rate"]["2025"] < medidas["fill_rate"]["2023"] < medidas["fill_rate"]["2021"]
    )
    assert medidas["headcount_medio"]["2024"] > 4 * medidas["headcount_medio"]["2021"]


def test_quem_trabalha_passou_pelo_funil_e_e_uma_pessoa_so(
    linhas: Linhas, tabelas: nucleo.Tabelas
) -> None:
    colaboradores = linhas["pessoas.colaborador"]
    assert all(etapa3_pessoas.cpf_valido(c["cpf"]) for c in colaboradores)
    assert len({c["cpf"] for c in colaboradores}) == len(colaboradores)
    candidato_do_colaborador = {c["id"]: c["candidato_id"] for c in colaboradores}
    candidaturas = tabelas["ats.candidatura"]
    aprovadas = set(candidaturas.loc[candidaturas["status"] == "APROVADA", "candidato_id"])
    assert set(candidato_do_colaborador.values()) <= aprovadas
    # a mesma pessoa volta: mais de um contrato por colaborador, nunca dois ao mesmo tempo
    por_pessoa: dict[int, list[tuple[date, date]]] = {}
    for k in linhas["pessoas.contrato_trabalho"]:
        fim = k["dt_rescisao"] or date.max
        por_pessoa.setdefault(k["colaborador_id"], []).append((k["dt_admissao"], fim))
    assert sum(1 for v in por_pessoa.values() if len(v) > 1) > 500
    for periodos in por_pessoa.values():
        ordenados = sorted(periodos)
        assert all(a[1] <= b[0] for a, b in zip(ordenados, ordenados[1:], strict=False))


def test_alocacao_cabe_no_posto_e_a_reposicao_aponta_para_quem_saiu(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]], linhas: Linhas
) -> None:
    postos = {
        p["id"]: p for p in etapa2_carteira._registros(gerado[1]["carteira"]["comercial.posto"])
    }
    alocacoes = {a["id"]: a for a in linhas["pessoas.alocacao"]}
    for a in alocacoes.values():
        posto = postos[a["posto_id"]]
        assert a["dt_inicio"] >= posto["vigencia_inicio"]
        if posto["vigencia_fim"] is not None and a["dt_fim"] is not None:
            assert a["dt_fim"] <= posto["vigencia_fim"]
        anterior = alocacoes.get(a["substituindo_alocacao_id"])
        if anterior is not None:
            assert anterior["posto_id"] == a["posto_id"] and anterior["dt_fim"] <= a["dt_inicio"]
    assert sum(1 for a in alocacoes.values() if a["substituindo_alocacao_id"]) > 5000


def test_temporario_respeita_o_prazo_legal_menos_na_sujeira_catalogada(linhas: Linhas) -> None:
    prorrogados = {
        p["contrato_trabalho_id"] for p in linhas["pessoas.contrato_trabalho_prorrogacao"]
    }
    hoje = nucleo.FIM.date()
    passou = 0
    for k in linhas["pessoas.contrato_trabalho"]:
        if k["tipo"] != "TEMPORARIO":
            assert k["prazo_legal_dias"] is None and k["dt_prevista_termino"] is None
            continue
        dias = ((k["dt_rescisao"] or hoje) - k["dt_admissao"]).days + 1
        limite = motor.PRAZO_PRORROGADO if k["id"] in prorrogados else motor.PRAZO_TEMPORARIO
        passou += dias > limite
    assert 0 < passou < 0.03 * len(linhas["pessoas.contrato_trabalho"])  # é o PES-02, e só ele


def test_sujeira_de_cadastro_esta_onde_o_catalogo_diz(
    gerado: tuple[nucleo.Tabelas, dict[str, Any]], linhas: Linhas
) -> None:
    candidatos = {c["id"]: c for c in linhas["ats.candidato"]}
    duplicatas: dict[int, int] = gerado[1]["duplicata_de"]
    assert 0.028 <= len(duplicatas) / len(candidatos) <= 0.042
    contratados = {c["candidato_id"] for c in linhas["pessoas.colaborador"]}
    assert not contratados & set(duplicatas)  # duplicata nunca é contratada
    for copia, original in list(duplicatas.items())[:500]:
        assert candidatos[copia]["dt_nascimento"] == candidatos[original]["dt_nascimento"]
        assert candidatos[copia]["nome"] != candidatos[original]["nome"]
    assert all(
        str(c["email"]).endswith("@email.example") for c in candidatos.values() if c["email"]
    )
    assert all("90000-" in c["telefone"] for c in candidatos.values())


def test_o_funil_afunila(tabelas: nucleo.Tabelas) -> None:
    etapas = Counter(tabelas["ats.candidatura_etapa"]["etapa_id"])
    assert etapas[1] > etapas[2] > etapas[3] > etapas[5]
    situacoes = Counter(tabelas["ats.candidatura"]["status"])
    assert situacoes["REPROVADA"] > situacoes["APROVADA"] > situacoes["DESISTENCIA"] > 0
    vagas = tabelas["ats.vaga"]
    abertas = vagas[vagas["status"].isin(["ABERTA", "EM_TRIAGEM"])]
    assert 0 < len(abertas) < 400 and abertas["dt_fechamento"].isna().all()
    preenchidas = vagas[vagas["status"] == "PREENCHIDA"]
    pares = zip(preenchidas["dt_abertura"], preenchidas["dt_fechamento"], strict=True)
    tempos = [(fechou - abriu).days for abriu, fechou in pares]
    assert 5 <= median(tempos) <= 20


def test_nada_acontece_depois_do_fim_da_historia(tabelas: nucleo.Tabelas, linhas: Linhas) -> None:
    hoje = nucleo.FIM.date()
    for quadro in tabelas.values():
        assert (quadro["atualizado_em"] <= nucleo.FIM).all()
    assert all(k["dt_admissao"] <= hoje for k in linhas["pessoas.contrato_trabalho"])
    assert all(d["dt_desligamento"] <= hoje for d in linhas["pessoas.desligamento"])
    assert all(v["dt_abertura"] <= hoje for v in linhas["ats.vaga"])
    assert (tabelas["ats.candidatura"]["dt_inscricao"] <= hoje).all()


# ───────────────────────────── contra a réplica ───────────────────────────────
def _normal(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return round(float(valor), 4)
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, float):
        return round(valor, 4)
    return valor


def test_replica_tem_exatamente_o_funil_e_as_pessoas_gerados(tabelas: nucleo.Tabelas) -> None:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        pytest.skip(".env ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    replica = nucleo.Replica("127.0.0.1", porta, "replicador", senha)
    if replica.contar(["pessoas.colaborador"])["pessoas.colaborador"] == 0:
        pytest.skip("réplica ainda sem a etapa 3 (rode o gerador com --gravar)")
    contagem = replica.contar([n for n in tabelas if n != "cadastro.endereco"])
    assert contagem == {n: len(q) for n, q in tabelas.items() if n != "cadastro.endereco"}
    for nome in (
        "ats.vaga",
        "pessoas.colaborador",
        "pessoas.contrato_trabalho",
        "pessoas.alocacao",
        "cadastro.endereco",
    ):
        quadro = tabelas[nome]
        faixa = (int(quadro["id"].iloc[0]), int(quadro["id"].iloc[-1]))
        lidas = [
            [_normal(v) for v in linha] for linha in replica.ler(nome, list(quadro.columns), faixa)
        ]
        assert lidas == [[_normal(v) for v in linha] for linha in nucleo.valores(quadro)], nome
