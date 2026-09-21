"""A etapa 6 inteira (é barata): cabe na DDL, responde "quem fez" com gente que estava na casa,
e o ASO vencido com a pessoa alocada aparece na proporção do catálogo, só quando a operação cede."""

from __future__ import annotations

import json
import re
import socket
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador import catalogos_conformidade as cc
from rh_fictalent.gerador import (
    etapa1_cadastro,
    etapa2_carteira,
    etapa3_pessoas,
    etapa4_ponto_folha,
    etapa5_financeiro,
    nucleo,
)
from rh_fictalent.gerador import etapa6_conformidade as e6
from rh_fictalent.gerador.__main__ import main
from rh_fictalent.validacao.regua import Veredito

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PUBLICOS = RAIZ / "dados" / "publicos"
DDL = "\n".join(
    (RAIZ / "staging" / "ddl" / nome).read_text(encoding="utf-8")
    for nome in ("08_treinamento.sql", "09_sst.sql", "10_seguranca.sql")
)
HOJE = e6.HOJE
Gerado = tuple[nucleo.Tabelas, dict[str, Any]]
Linhas = dict[str, list[dict[str, Any]]]


@pytest.fixture(scope="module")
def gerado() -> Gerado:
    return e6.gerar_com_base(PUBLICOS)


@pytest.fixture(scope="module")
def linhas(gerado: Gerado) -> Linhas:
    return {nome: e6._registros(quadro) for nome, quadro in gerado[0].items()}


@pytest.fixture(scope="module")
def etapa3(gerado: Gerado) -> Linhas:
    nomes = (
        "pessoas.contrato_trabalho",
        "pessoas.alocacao",
        "pessoas.afastamento",
        "ats.vaga",
    )
    return {nome: e6._registros(gerado[1]["etapa3"][nome]) for nome in nomes}


def test_tabelas_tem_as_colunas_da_ddl_e_os_textos_cabem(gerado: Gerado) -> None:
    tabelas = gerado[0]
    assert list(tabelas) == list(e6.ORDEM) and len(tabelas) == 16
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


def test_duas_execucoes_dao_a_mesma_base(gerado: Gerado) -> None:
    tabelas, base = gerado
    de_novo, outra_base = e6.montar(base["etapa3"], base)
    assert nucleo.assinatura(de_novo) == nucleo.assinatura(tabelas)
    assert outra_base["retoques"]["ats.entrevista"].equals(base["retoques"]["ats.entrevista"])


def test_a_regua_aprova_e_o_aso_vencido_so_aparece_quando_a_operacao_cede(
    gerado: Gerado, linhas: Linhas, etapa3: Linhas
) -> None:
    tabelas, base = gerado
    e6.conferir(tabelas, base)
    laudo = e6.laudo_parcial(e6.medir(tabelas, base))
    assert len(laudo.resultados) == 3 and laudo.veredito is Veredito.APROVADA
    vencido = e6.aso_vencido(linhas["sst.aso"], etapa3["pessoas.alocacao"])
    assert all(vencido[ano] < 0.01 for ano in range(2018, 2023))
    assert 0.01 < vencido[2023] < vencido[2024] and vencido[2026] > 0.025


def test_todo_contrato_tem_admissional_e_o_demissional_segue_a_dispensa(
    linhas: Linhas, etapa3: Linhas
) -> None:
    tipo = {i: c for i, (c, _) in enumerate(cc.TIPOS_DE_EXAME, start=1)}
    do_colaborador: dict[int, list[tuple[date, str]]] = {}
    for a in linhas["sst.aso"]:
        codigo = tipo[int(a["tipo_exame_id"])]
        do_colaborador.setdefault(int(a["colaborador_id"]), []).append((a["dt_exame"], codigo))
        assert a["dt_exame"] <= HOJE and codigo != "MUDANCA_FUNCAO"
        if codigo == "DEMISSIONAL":
            assert a["dt_validade"] is None
        else:
            esperada = etapa2_carteira._mais_meses(a["dt_exame"], cc.VALIDADE_DO_ASO_MESES)
            assert a["dt_validade"] == esperada
        assert a["resultado"] in ("APTO", "APTO_RESTRICAO") and "FIC-" in a["medico_crm"]
    for k in etapa3["pessoas.contrato_trabalho"]:
        exames = do_colaborador[int(k["colaborador_id"])]
        semana_antes = k["dt_admissao"] - timedelta(days=12)
        assert any(
            t == "ADMISSIONAL" and semana_antes <= d < k["dt_admissao"] for d, t in exames
        ), k["id"]
        if k["dt_rescisao"] is None:
            continue
        fez = any(
            t == "DEMISSIONAL" and k["dt_rescisao"] <= d <= k["dt_rescisao"] + timedelta(days=8)
            for d, t in exames
        )
        ultimo = max(  # o último exame deste contrato (o admissional do próximo não conta)
            d
            for d, t in exames
            if t != "DEMISSIONAL"
            and semana_antes <= d <= k["dt_rescisao"]
            and not (t == "ADMISSIONAL" and d >= k["dt_admissao"])
        )
        if (k["dt_rescisao"] - ultimo).days <= cc.DISPENSA_DO_DEMISSIONAL[True]:
            assert not fez, k["id"]  # exame recente dispensa, qualquer que seja o risco
        if (k["dt_rescisao"] - ultimo).days > cc.DISPENSA_DO_DEMISSIONAL[False]:
            assert fez, k["id"]


def test_o_risco_do_posto_e_o_adicional_que_a_folha_paga(gerado: Gerado, linhas: Linhas) -> None:
    base = gerado[1]
    funcao_por_id = {
        int(f["id"]): {x.codigo: x for x in cat.FUNCOES}[f["codigo"]]
        for f in e6._registros(base["mundo"]["cadastro.funcao"])
    }
    postos = {int(p["id"]): p for p in e6._registros(base["carteira"]["comercial.posto"])}
    programas = {i: p for i, p in enumerate(linhas["sst.programa_sst"], start=1)}
    riscos: dict[int, list[dict[str, Any]]] = {}
    for r in linhas["sst.risco_posto"]:
        riscos.setdefault(int(r["posto_id"]), []).append(r)
        programa = programas[int(r["programa_sst_id"])]
        assert programa["tipo"] == "PGR"
        assert programa["contrato_id"] == postos[int(r["posto_id"])]["contrato_id"]
    assert set(riscos) == set(postos)
    for posto_id, do_posto in riscos.items():
        funcao = funcao_por_id[int(postos[posto_id]["funcao_id"])]
        assert any(r["insalubridade_pct"] > 0 for r in do_posto) == funcao.insalubre
        assert any(r["fl_periculosidade"] for r in do_posto) == funcao.periculosidade
    com_ltcat = {p["contrato_id"] for p in programas.values() if p["tipo"] == "LTCAT"}
    de_risco = {
        p["contrato_id"]
        for p in postos.values()
        if funcao_por_id[int(p["funcao_id"])].insalubre
        or funcao_por_id[int(p["funcao_id"])].periculosidade
    }
    assert com_ltcat == de_risco
    for p in programas.values():
        assert p["dt_elaboracao"] <= HOJE and p["dt_validade"] > p["dt_elaboracao"]


def test_acidente_com_afastamento_tem_registro_e_todo_acidente_tem_cat(
    linhas: Linhas, etapa3: Linhas
) -> None:
    acidentes = linhas["sst.acidente"]
    afastados = {int(f["id"]) for f in etapa3["pessoas.afastamento"] if f["tipo"] == "ACIDENTE"}
    assert {int(a["afastamento_id"]) for a in acidentes if a["afastamento_id"]} == afastados
    assert all(a["dias_afastamento"] == 0 for a in acidentes if not a["afastamento_id"])
    assert all(a["gravidade"] != "FATAL" for a in acidentes)
    assert sum(1 for a in acidentes if a["alocacao_id"]) >= 0.95 * len(acidentes)
    pessoa_anos = (
        sum(((a["dt_fim"] or HOJE) - a["dt_inicio"]).days + 1 for a in etapa3["pessoas.alocacao"])
        / 365
    )
    assert 0.015 < len(acidentes) / pessoa_anos < 0.035  # "cerca de 2 por 100 alocados por ano"
    iniciais = {int(c["acidente_id"]): c for c in linhas["sst.cat"] if c["tipo_cat"] == "INICIAL"}
    for i, a in enumerate(acidentes, start=1):
        if a["dt_acidente"] < HOJE - timedelta(days=15):
            assert iniciais[i]["dt_emissao"] > a["dt_acidente"]
    for c in linhas["sst.cat"]:
        assert c["dt_emissao"] <= HOJE
        if c["tipo_cat"] == "REABERTURA":
            dias = acidentes[int(c["acidente_id"]) - 1]["dias_afastamento"]
            assert dias >= cc.REABERTURA_A_PARTIR_DE_DIAS


def test_quem_opera_empilhadeira_fez_a_nr11_e_certificado_so_para_aprovado(
    gerado: Gerado, linhas: Linhas, etapa3: Linhas
) -> None:
    curso = {i: c for i, c in enumerate(cc.CURSOS, start=1)}
    turmas = {i: t for i, t in enumerate(linhas["treinamento.turma"], start=1)}
    participantes = linhas["treinamento.turma_participante"]
    fez: dict[tuple[int, str], list[date]] = {}
    for p in participantes:
        turma = turmas[int(p["turma_id"])]
        codigo = curso[int(turma["curso_id"])][0]
        fez.setdefault((int(p["colaborador_id"]), codigo), []).append(turma["dt_inicio"])
        assert turma["dt_inicio"] <= turma["dt_fim"] <= HOJE
    empilhadeira = next(
        int(f["id"])
        for f in e6._registros(gerado[1]["mundo"]["cadastro.funcao"])
        if f["codigo"] == "L003"
    )
    operadores = [
        k
        for k in etapa3["pessoas.contrato_trabalho"]
        if k["funcao_id"] == empilhadeira
        and ((k["dt_rescisao"] or HOJE) - k["dt_admissao"]).days >= 15
    ]
    assert len(operadores) > 100
    for k in operadores:
        assert (int(k["colaborador_id"]), "NR11") in fez, k["id"]
        assert (int(k["colaborador_id"]), "INTEGRA") in fez, k["id"]
    aprovados = {i for i, p in enumerate(participantes, start=1) if p["fl_aprovado"]}
    certificados = linhas["treinamento.certificado"]
    assert {int(c["turma_participante_id"]) for c in certificados} == aprovados
    for c in certificados:
        turma = turmas[int(participantes[int(c["turma_participante_id"]) - 1]["turma_id"])]
        meses = curso[int(turma["curso_id"])][4]
        assert c["dt_emissao"] == turma["dt_fim"]
        esperada = etapa2_carteira._mais_meses(turma["dt_fim"], meses) if meses else None
        assert c["dt_validade"] == esperada
    assert 10 < sum(1 for t in turmas.values() if t["cliente_id"]) < 100  # as vendidas a cliente
    for turma in turmas.values():  # curso de norma é comprado do centro de treinamento
        assert (turma["fornecedor_id"] is not None) == curso[int(turma["curso_id"])][5]


def test_os_usuarios_sao_os_do_caso_e_o_perfil_tem_vigencia(gerado: Gerado, linhas: Linhas) -> None:
    usuarios = linhas["seguranca.usuario"]
    assert len(usuarios) == 40 == len({u["login"] for u in usuarios})
    assert [u["nome"].split()[0] for u in usuarios[:3]] == ["Romeu", "Janaína", "Sabrina"]
    assert all(u["email"].endswith("@fictalent.example") for u in usuarios)
    assert all(u["colaborador_id"] is None for u in usuarios)
    assert sum(u["dt_criacao"].year == 2026 for u in usuarios) == 5  # D5: fevereiro e maio
    ativos = [u for u in usuarios if u["ativo"]]
    assert 30 <= len(ativos) < 40
    assert all(u["ultimo_acesso"].date() >= HOJE - timedelta(days=30) for u in ativos)
    perfil = {i: c for i, (c, _) in enumerate(cc.PERFIS, start=1)}
    por_usuario: dict[int, list[dict[str, Any]]] = {}
    for v in linhas["seguranca.usuario_perfil"]:
        por_usuario.setdefault(int(v["usuario_id"]), []).append(v)
        assert (v["filial_id"] is not None) == (perfil[int(v["perfil_id"])] == "ASSISTENTE")
    assert set(por_usuario) == set(range(1, 41))
    for vinculos in por_usuario.values():
        vinculos.sort(key=lambda v: v["vigencia_inicio"])
        for antes, depois in zip(vinculos, vinculos[1:], strict=False):
            assert antes["vigencia_fim"] == depois["vigencia_inicio"] - timedelta(days=1)
    sabrina = [perfil[int(v["perfil_id"])] for v in por_usuario[3]]
    assert sabrina == ["COORDENADOR", "GERENTE"]
    permissoes = linhas["seguranca.permissao"]
    assert len(permissoes) == len(cc.PERFIS) * len(cc.MODULOS) * len(cc.ACOES) == 300
    pode = {
        (perfil[int(p["perfil_id"])], p["modulo"], p["acao"])
        for p in permissoes
        if p["fl_permitido"]
    }
    assert ("ASSISTENTE", "ats", "CRIAR") in pode and ("FINANCEIRO", "financeiro", "EDITAR") in pode
    assert not any(
        p == "ASSISTENTE" and m in ("financeiro", "folha", "seguranca") for p, m, _ in pode
    )
    assert all(p in ("TI", "COORDENADOR") for p, _, a in pode if a == "EXCLUIR")


def test_a_trilha_aponta_para_registro_que_existe_feito_por_quem_estava_na_casa(
    gerado: Gerado, linhas: Linhas, etapa3: Linhas
) -> None:
    usuarios: list[e6.Usuario] = gerado[1]["usuarios"]
    eventos = linhas["seguranca.log_auditoria"]
    assert [e["dt_evento"] for e in eventos] == sorted(e["dt_evento"] for e in eventos)
    existentes = {
        tuple(nome.split("."))
        for etapa in (
            etapa1_cadastro,
            etapa2_carteira,
            etapa3_pessoas,
            etapa4_ponto_folha,
            etapa5_financeiro,
            e6,
        )
        for nome in getattr(etapa, "ORDEM", ())
    }
    existentes |= {tuple(n.split(".")) for n in gerado[1]["etapa3"]}
    existentes |= {tuple(n.split(".")) for n in gerado[1]["carteira"]}
    for e in eventos:
        assert e["dt_evento"] <= nucleo.FIM
        assert usuarios[int(e["usuario_id"]) - 1].ativo_em(e["dt_evento"].date()), e
        assert (e["modulo"], e["tabela"]) in existentes, e
    vagas = {int(v["id"]): v for v in etapa3["ats.vaga"]}
    criadas = [e for e in eventos if e["tabela"] == "vaga" and e["acao"] == "CRIAR"]
    assert len(criadas) == len(vagas)
    for e in criadas:
        assert e["dt_evento"] == vagas[int(e["registro_id"])]["criado_em"]
        setor, _ = usuarios[int(e["usuario_id"]) - 1].papel_em(e["dt_evento"].date())
        assert setor in ("RECRUTAMENTO", "DIRECAO")
    editadas = [e for e in eventos if e["tabela"] == "vaga" and e["acao"] == "EDITAR"]
    assert editadas
    for e in editadas[:500]:
        vaga = vagas[int(e["registro_id"])]
        assert e["dt_evento"] == vaga["atualizado_em"]
        assert json.loads(e["valor_novo"])["status"] == vaga["status"]
        assert json.loads(e["valor_anterior"]) == {"status": "ABERTA"}
    exportou = {ano: 0 for ano in range(2018, 2027)}
    for e in eventos:
        exportou[e["dt_evento"].year] += e["acao"] == "EXPORTAR"
    assert exportou[2025] > 5 * exportou[2019]  # exportar e cruzar à mão cresce com a degradação


def test_toda_entrevista_ganha_um_entrevistador_que_estava_na_casa(gerado: Gerado) -> None:
    base = gerado[1]
    usuarios: list[e6.Usuario] = base["usuarios"]
    retoque = base["retoques"]["ats.entrevista"]
    entrevistas = base["etapa3"]["ats.entrevista"]
    assert list(retoque.columns) == ["id", "usuario_id"]
    assert sorted(retoque["id"]) == list(entrevistas["id"])
    quando = dict(zip(entrevistas["id"], entrevistas["dt_agendada"], strict=True))
    tipo = dict(zip(entrevistas["id"], entrevistas["tipo"], strict=True))
    da_coordenacao = 0
    for entrevista, usuario_id in zip(retoque["id"], retoque["usuario_id"], strict=True):
        dia = min(max(quando[entrevista].date(), nucleo.INICIO), HOJE)
        usuario = usuarios[int(usuario_id) - 1]
        assert usuario.ativo_em(dia)
        setor, cargo = usuario.papel_em(dia)
        assert setor == "RECRUTAMENTO"
        da_coordenacao += tipo[entrevista] == "CLIENTE" and cargo == "COORDENADOR"
    assert da_coordenacao == sum(1 for t in tipo.values() if t == "CLIENTE")
    assert retoque["usuario_id"].nunique() >= 12


def test_coluna_de_retoque_nunca_vira_sql_sem_conferencia() -> None:
    assert nucleo._coluna("usuario_id") == "`usuario_id`"
    with pytest.raises(ValueError, match="inválido"):
        nucleo._coluna("usuario_id = 1; DROP TABLE x")


def test_cli_mostra_a_regua_parcial_da_etapa(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(RAIZ)
    assert main(["--etapa", "6"]) == 0
    saida = capsys.readouterr().out
    assert "seguranca.log_auditoria" in saida and "RÉGUA APROVADA: 3 de 3" in saida


def test_replica_tem_a_etapa_6_e_as_entrevistas_retocadas(gerado: Gerado) -> None:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        pytest.skip(".env ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    replica = nucleo.Replica("127.0.0.1", porta, "replicador", senha)
    if replica.contar(["sst.aso"])["sst.aso"] == 0:
        pytest.skip("réplica ainda sem a etapa 6 (rode o gerador com --gravar)")
    tabelas, base = gerado
    assert replica.contar(list(tabelas)) == {n: len(q) for n, q in tabelas.items()}
    retoque = base["retoques"]["ats.entrevista"].sort_values("id")
    na_replica = replica.ler("ats.entrevista", ["id", "usuario_id"])
    assert na_replica == list(
        zip(retoque["id"].tolist(), retoque["usuario_id"].tolist(), strict=True)
    )
