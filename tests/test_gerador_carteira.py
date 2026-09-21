"""A carteira comercial é determinística, cabe na DDL, passa na régua e conta a história do caso."""

from __future__ import annotations

import re
import socket
from datetime import date
from decimal import Decimal
from pathlib import Path
from statistics import fmean
from typing import Any

import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, historia, nucleo
from rh_fictalent.gerador.__main__ import main
from rh_fictalent.validacao.regua import Veredito

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"
DDL = "\n".join(
    (RAIZ / "staging" / "ddl" / nome).read_text(encoding="utf-8")
    for nome in ("01_cadastro.sql", "02_comercial.sql")
)


@pytest.fixture(scope="module")
def tabelas() -> nucleo.Tabelas:
    return etapa2_carteira.gerar(PUBLICOS)


@pytest.fixture(scope="module")
def linhas(tabelas: nucleo.Tabelas) -> dict[str, list[dict[str, Any]]]:
    return {nome: etapa2_carteira._registros(quadro) for nome, quadro in tabelas.items()}


def _corpo_da_ddl(tabela: str) -> str:
    corpo = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\) ENCRYPTION", DDL, re.S)
    assert corpo, tabela
    return corpo.group(1)


def test_tabelas_tem_as_colunas_da_ddl_e_os_textos_cabem(tabelas: nucleo.Tabelas) -> None:
    assert len(tabelas) == 10
    for nome, quadro in tabelas.items():
        corpo = _corpo_da_ddl(nome.split(".")[1])
        colunas = [
            linha.split()[0]
            for linha in (bruta.strip() for bruta in corpo.splitlines())
            if linha and not linha.startswith(("PRIMARY", "UNIQUE", "KEY", "CONSTRAINT"))
        ]
        assert list(quadro.columns) == colunas, nome
        for coluna, limite in re.findall(r"^\s+(\w+)\s+(?:VAR)?CHAR\((\d+)\)", corpo, re.M):
            maior = max((len(v) for v in quadro[coluna] if v is not None), default=0)
            assert maior <= int(limite), (nome, coluna, maior, limite)


def test_duas_execucoes_dao_a_mesma_carteira(tabelas: nucleo.Tabelas) -> None:
    assert nucleo.assinatura(etapa2_carteira.gerar(PUBLICOS)) == nucleo.assinatura(tabelas)


def test_ids_continuam_os_da_etapa_1(tabelas: nucleo.Tabelas) -> None:
    mundo = etapa1_cadastro.gerar(PUBLICOS)
    for nome in ("cadastro.endereco", "cadastro.centro_custo"):
        esperado = list(range(len(mundo[nome]) + 1, len(mundo[nome]) + len(tabelas[nome]) + 1))
        assert tabelas[nome]["id"].tolist() == esperado, nome
    centros = tabelas["cadastro.centro_custo"]
    assert centros["tipo"].eq("CONTRATO").all() and centros["contrato_id"].notna().all()
    assert etapa2_carteira.ADIADAS == {"cadastro.centro_custo": ["contrato_id"]}


def test_a_regua_aprova_tudo_o_que_a_carteira_ja_permite_medir(tabelas: nucleo.Tabelas) -> None:
    medidas = etapa2_carteira.medir(tabelas)
    laudo = etapa2_carteira.laudo_parcial(medidas)
    assert laudo.veredito == Veredito.APROVADA, laudo.texto(so_problemas=True)
    assert len(laudo.resultados) == 22  # 9 anos de clientes, 3 de naturalidade, 9 de reclamações, 1
    assert 6 <= medidas["defasagem_qualidade_perda"]["mediana_meses"] <= 9
    assert 80 <= len(tabelas["comercial.cliente"]) <= 110  # "cerca de 90 clientes ao longo do arco"


def test_a_pandemia_reduz_postos_e_poupa_os_clientes_ancora(
    linhas: dict[str, list[dict[str, Any]]],
) -> None:
    def posicoes(dia: date) -> int:
        return sum(
            p["quantidade"]
            for p in linhas["comercial.posto"]
            if p["vigencia_inicio"] <= dia
            and (p["vigencia_fim"] is None or p["vigencia_fim"] >= dia)
        )

    assert posicoes(date(2020, 5, 15)) < 0.8 * posicoes(date(2020, 2, 14))
    fundadores = {1, 2, 3}
    saiu_em_2020 = {
        k["cliente_id"]
        for k in linhas["comercial.contrato"]
        if k["dt_encerramento"] is not None and k["dt_encerramento"].year == 2020
    }
    assert not fundadores & saiu_em_2020


def test_a_crise_comeca_no_fim_de_2025_e_tem_cara_de_servico(
    linhas: dict[str, list[dict[str, Any]]],
) -> None:
    mundo = etapa1_cadastro.gerar(PUBLICOS)
    motivo = {
        m["id"]: (m["codigo"], m["grupo"])
        for m in etapa2_carteira._registros(mundo["cadastro.motivo"])
    }
    clientes = {c["id"]: c for c in linhas["comercial.cliente"]}
    perdas: dict[int, tuple[date, str]] = {}
    for k in linhas["comercial.contrato"]:
        if k["dt_encerramento"] is not None and not clientes[k["cliente_id"]]["ativo"]:
            anterior = perdas.get(k["cliente_id"], (date.min, ""))
            if k["dt_encerramento"] >= anterior[0]:
                perdas[k["cliente_id"]] = (
                    k["dt_encerramento"],
                    motivo[k["motivo_encerramento_id"]][1],
                )
    antes = [d for d, _ in perdas.values() if date(2023, 1, 1) <= d < date(2025, 10, 1)]
    crise = [(d, grupo) for d, grupo in perdas.values() if d >= date(2025, 10, 1)]
    assert len(crise) > 2 * len(antes) / 2.75  # por ano, a crise perde mais que o dobro
    assert sum(1 for _, grupo in crise if grupo == "SERVICO") >= 0.4 * len(crise)
    advertidos = {
        o["contrato_id"]
        for o in linhas["comercial.contrato_ocorrencia"]
        if o["tipo"] == "ADVERTENCIA"
    }
    primeira = min(
        o["dt_ocorrencia"]
        for o in linhas["comercial.contrato_ocorrencia"]
        if o["tipo"] == "ADVERTENCIA"
    )
    assert advertidos and primeira.year == 2025  # ninguém formalizou nada antes de a operação ceder


def test_o_ano_tem_a_forma_do_negocio_pico_em_dezembro_vale_em_fevereiro(
    linhas: dict[str, list[dict[str, Any]]],
) -> None:
    def posicoes(dia: date) -> int:
        return sum(
            p["quantidade"]
            for p in linhas["comercial.posto"]
            if p["vigencia_inicio"] <= dia
            and (p["vigencia_fim"] is None or p["vigencia_fim"] >= dia)
        )

    for ano in (2019, 2021, 2022, 2023, 2024):
        pico = posicoes(date(ano, 12, 18))
        assert pico > 1.5 * posicoes(date(ano, 2, 15)), ano  # o vale do mesmo ano
        assert pico > posicoes(date(ano + 1, 2, 15)), ano  # e a queda depois do Natal
    alvo = historia.posicoes_alvo()
    for mes in ("2019-12", "2022-07", "2024-12", "2026-09"):
        dia = date(int(mes[:4]), int(mes[5:]), 10 if mes == "2026-09" else 19)
        assert abs(posicoes(dia) / alvo[mes] - 1) < 0.12, mes


def test_cliente_grande_paga_menos_por_posto_e_demora_mais(
    linhas: dict[str, list[dict[str, Any]]],
) -> None:
    porte = {c["id"]: c["porte"] for c in linhas["comercial.cliente"]}
    contrato = {k["id"]: k for k in linhas["comercial.contrato"]}
    posto = {p["id"]: p for p in linhas["comercial.posto"]}
    markups: dict[str, list[float]] = {}
    for preco in linhas["comercial.posto_preco"]:
        dono = porte[contrato[posto[preco["posto_id"]]["contrato_id"]]["cliente_id"]]
        markups.setdefault(dono, []).append(preco["markup_aplicado"])
    assert fmean(markups["GRANDE"]) < fmean(markups["MEDIA"]) < fmean(markups["EPP"])
    assert all(1.35 <= m <= 1.65 for lista in markups.values() for m in lista)
    prazos = {porte[k["cliente_id"]]: k["prazo_pagamento_dias"] for k in contrato.values()}
    assert prazos["GRANDE"] == 45 and prazos["MEDIA"] == 28


def test_identidades_sao_validas_e_obviamente_ficticias(
    linhas: dict[str, list[dict[str, Any]]],
) -> None:
    for cliente in linhas["comercial.cliente"]:
        cnpj = cliente["cnpj"]
        for posicao, pesos in (
            (12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
            (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
        ):
            resto = sum(int(d) * p for d, p in zip(cnpj[:posicao], pesos, strict=True)) % 11
            assert int(cnpj[posicao]) == (0 if resto < 2 else 11 - resto), cnpj
    assert all(c["email"].endswith(".example") for c in linhas["comercial.cliente_contato"])
    assert all("90000-" in c["telefone"] for c in linhas["comercial.cliente_contato"])


def test_nada_acontece_depois_do_fim_da_historia(
    tabelas: nucleo.Tabelas, linhas: dict[str, list[dict[str, Any]]]
) -> None:
    hoje = nucleo.FIM.date()
    for quadro in tabelas.values():
        assert (quadro["atualizado_em"] <= nucleo.FIM).all()
    assert all(k["dt_assinatura"] <= hoje for k in linhas["comercial.contrato"])
    assert all(p["vigencia_inicio"] <= hoje for p in linhas["comercial.posto"])
    assert all(o["dt_ocorrencia"] <= hoje for o in linhas["comercial.contrato_ocorrencia"])
    encerrados = [k for k in linhas["comercial.contrato"] if k["status"] == "ENCERRADO"]
    assert encerrados and all(k["dt_encerramento"] <= hoje for k in encerrados)


def test_cli_mostra_a_regua_parcial_da_etapa(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(RAIZ)
    assert main(["--etapa", "2"]) == 0
    saida = capsys.readouterr().out
    assert "comercial.posto_preco" in saida and "RÉGUA APROVADA: 22 de 22" in saida


# ───────────────────────────── contra a réplica ───────────────────────────────
def _normal(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return round(float(valor), 4)
    if isinstance(valor, bool):
        return int(valor)
    if isinstance(valor, float):
        return round(valor, 4)
    return valor


def test_replica_tem_exatamente_a_carteira_gerada(tabelas: nucleo.Tabelas) -> None:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        pytest.skip(".env ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    replica = nucleo.Replica("127.0.0.1", porta, "replicador", senha)
    if replica.contar(["comercial.cliente"])["comercial.cliente"] == 0:
        pytest.skip("réplica ainda sem a etapa 2 (rode o gerador com --gravar)")
    for nome, quadro in tabelas.items():
        ids = (int(quadro["id"].iloc[0]), int(quadro["id"].iloc[-1]))
        na_replica = [
            [_normal(v) for v in linha] for linha in replica.ler(nome, list(quadro.columns), ids)
        ]
        gerado = [[_normal(v) for v in linha] for linha in nucleo.valores(quadro)]
        assert na_replica == gerado, nome
