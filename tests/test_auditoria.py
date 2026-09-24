"""O pacote de auditoria provado sem o lake: DuckDB em memória com tabelas pequenas e
defeitos plantados de propósito, mais a DDL real para o esquema."""

from __future__ import annotations

from pathlib import Path

import duckdb
import nbformat
import pytest

from rh_fictalent.auditoria import achados, cadernos, checagens, esquema

CPF_VALIDO, CPF_INVALIDO = "529.982.247-25", "529.982.247-26"
CNPJ_VALIDO, CNPJ_INVALIDO = "11222333000181", "11222333000182"


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    c.execute("CREATE SCHEMA t")
    c.execute(
        "CREATE TABLE t.mae (id INTEGER, nome VARCHAR, tipo VARCHAR, inicio DATE, fim DATE, "
        "excluido_em TIMESTAMP)"
    )
    c.execute(
        "INSERT INTO t.mae VALUES "
        "(1, 'São Paulo', 'A', DATE '2020-01-01', DATE '2020-12-31', NULL), "
        "(2, 'SAO PAULO ', 'A', DATE '2020-06-01', NULL, NULL), "
        "(3, 'Atibaia', 'B', DATE '2021-01-01', DATE '2020-01-01', NULL), "
        "(4, 'Extrema', 'X', DATE '2021-01-01', NULL, NULL), "
        "(5, 'Morta', 'A', DATE '2021-01-01', NULL, TIMESTAMP '2024-01-01 00:00:00')"
    )
    c.execute(
        "CREATE TABLE t.filha (id INTEGER, mae_id INTEGER, grupo INTEGER, valor DOUBLE, "
        "cpf VARCHAR, inicio DATE, fim DATE, excluido_em TIMESTAMP)"
    )
    c.execute(
        "INSERT INTO t.filha VALUES "
        f"(1, 1, 1, 10.0, '{CPF_VALIDO}', DATE '2020-01-01', DATE '2020-03-01', NULL), "
        f"(2, 5, 1, -1.0, '{CPF_INVALIDO}', DATE '2020-02-01', DATE '2020-04-01', NULL), "
        f"(3, 9, 2, 5.0, '{CPF_INVALIDO}', DATE '2020-01-01', NULL, NULL), "
        "(4, NULL, 2, 200.0, NULL, DATE '2021-01-01', NULL, NULL)"
    )
    return c


def test_linhas_e_perfil_ignoram_as_excluidas(con: duckdb.DuckDBPyConnection) -> None:
    assert checagens.linhas(con, "t.mae") == 4
    perfil = checagens.perfil(con, "t.mae")
    assert set(perfil["coluna"]) == {"id", "nome", "tipo", "inicio", "fim"}
    por_coluna = perfil.set_index("coluna")
    assert por_coluna.at["fim", "nulos"] == 2
    assert por_coluna.at["fim", "pct_nulo"] == 50.0


def test_duplicatas_por_chave_e_por_conteudo(con: duckdb.DuckDBPyConnection) -> None:
    assert checagens.repetidos(con, "t.mae", ["nome"]) == (0, 0)
    assert checagens.repetidos(con, "t.mae", ["nome"], normalizar=True) == (1, 2)
    grupos = checagens.duplicatas(con, "t.mae", ["nome"], normalizar=True)
    assert list(grupos["nome"]) == ["sao paulo"]


def test_orfaos_contam_referencia_a_linha_morta(con: duckdb.DuckDBPyConnection) -> None:
    # filha 2 aponta para a mãe 5 (excluída) e filha 3 para a 9 (inexistente); nulo não conta
    assert checagens.orfaos(con, "t.filha", "mae_id", "t.mae") == 2


def test_dominio_ordem_temporal_faixa_e_sobreposicao(con: duckdb.DuckDBPyConnection) -> None:
    fora = checagens.fora_do_dominio(con, "t.mae", "tipo", ["A", "B"])
    assert list(fora["valor"]) == ["X"] and int(fora["linhas"].sum()) == 1
    assert checagens.ordem_temporal(con, "t.mae", "inicio", "fim") == 1
    assert checagens.fora_da_faixa(con, "t.filha", "valor", minimo=0) == 1
    assert checagens.fora_da_faixa(con, "t.filha", "valor", minimo=0, maximo=100) == 2
    # (1,2) no grupo 1 se cruzam; (3,4) no grupo 2 também, porque a 3 não terminou
    assert checagens.sobreposicoes(con, "t.filha", "grupo", "inicio", "fim") == 2
    assert checagens.sobreposicoes(con, "t.filha", ["grupo", "mae_id"], "inicio", "fim") == 0


def test_texto_inconsistente_e_variantes(con: duckdb.DuckDBPyConnection) -> None:
    vicios = checagens.texto_inconsistente(con, "t.mae", "nome")
    assert vicios["espacos_nas_pontas"] == 1 and vicios["caixa_alta"] == 1
    assert vicios["valores_com_mais_de_uma_grafia"] == 1
    assert vicios["linhas_em_grafia_multipla"] == 2
    variantes = checagens.variantes(con, "t.mae", "nome")
    assert len(variantes) == 1 and int(variantes.iloc[0]["quantas"]) == 2


def test_cpf_cnpj_e_documentos_invalidos(con: duckdb.DuckDBPyConnection) -> None:
    assert checagens.cpf_valido(CPF_VALIDO) and not checagens.cpf_valido(CPF_INVALIDO)
    assert not checagens.cpf_valido("111.111.111-11") and not checagens.cpf_valido("123")
    assert checagens.cnpj_valido(CNPJ_VALIDO) and not checagens.cnpj_valido(CNPJ_INVALIDO)
    assert checagens.documentos_invalidos(con, "t.filha", "cpf", checagens.cpf_valido) == (2, 1)


def test_o_esquema_le_a_ddl_real() -> None:
    tabelas = esquema.ler()
    assert len(tabelas) == 75 and "meta.exclusao_auditoria" not in tabelas
    alocacao = tabelas["pessoas.alocacao"]
    assert [c.alvo for c in alocacao.chaves] == [
        "pessoas.colaborador",
        "pessoas.contrato_trabalho",
        "comercial.posto",
        "cadastro.motivo",
        "pessoas.alocacao",
    ]
    assert alocacao.coluna("dt_fim").nulo and not alocacao.coluna("dt_inicio").nulo
    assert alocacao.temporais == ["dt_inicio", "dt_fim", "criado_em", "atualizado_em"]
    contrato = tabelas["comercial.contrato"]
    assert contrato.dominios["status"] == ("ATIVO", "SUSPENSO", "ENCERRADO")
    assert ("numero",) in contrato.unicas
    assert [t.nome for t in esquema.do_modulo("ponto", tabelas)] == [
        "escala_colaborador",
        "marcacao",
        "apontamento",
        "ocorrencia_ponto",
        "banco_horas",
    ]


def test_integridade_e_dominios_pelo_esquema(con: duckdb.DuckDBPyConnection) -> None:
    filha = esquema.Tabela(
        "t",
        "filha",
        (esquema.Coluna("id", "BIGINT", False),),
        chaves=(esquema.Chave("mae_id", "t", "mae"),),
    )
    quadro = checagens.integridade(con, filha)
    assert quadro.to_dict("records") == [
        {"tabela": "t.filha", "coluna": "mae_id", "alvo": "t.mae", "orfaos": 2}
    ]
    mae = esquema.Tabela("t", "mae", (), dominios={"tipo": ("A", "B")})
    dominios = checagens.dominios(con, mae)
    assert int(dominios.iloc[0]["fora"]) == 1 and dominios.iloc[0]["exemplos"] == "X"


def test_tipos_da_bronze_contra_a_ddl(con: duckdb.DuckDBPyConnection) -> None:
    mae = esquema.Tabela(
        "t",
        "mae",
        (
            esquema.Coluna("id", "BIGINT", False),
            esquema.Coluna("nome", "VARCHAR", False),
            esquema.Coluna("tipo", "BOOLEAN", False),  # a bronze gravou VARCHAR: incompatível
            esquema.Coluna("inicio", "DATE", False),
            esquema.Coluna("sumida", "DATE", True),
        ),
    )
    quadro = checagens.tipos(con, mae).set_index("coluna")
    assert quadro.loc["id", "bronze"] == "INTEGER" and bool(quadro.loc["id", "compativel"])
    assert not bool(quadro.loc["tipo", "compativel"])
    assert quadro.loc["sumida", "bronze"] == "AUSENTE"
    assert not bool(quadro.loc["sumida", "compativel"])
    assert checagens.compativel("DATETIME", "TIMESTAMP")
    assert checagens.compativel("TIME", "TIME")
    # os dois defeitos de ingestão que a auditoria da v0.6.0 achou
    assert not checagens.compativel("TINYINT", "BOOLEAN")
    assert not checagens.compativel("TIME", "BIGINT")


def test_registro_de_achados_valida_grava_e_recarrega(tmp_path: Path) -> None:
    registro = achados.Registro("teste")
    registro.anotar(
        secao="5",
        tabela="t.mae",
        coluna="nome",
        achado="grafia múltipla",
        linhas=2,
        total=4,
        severidade="media",
        impacto="conta a mesma cidade duas vezes",
        acao="conformar",
    )
    registro.anotar(
        secao="6",
        tabela="t.mae",
        coluna="tipo",
        achado="hipótese refutada",
        linhas=0,
        total=4,
        severidade="nenhuma",
        impacto="",
        acao="nenhuma",
        declaracao="D1",
    )
    with pytest.raises(ValueError):
        registro.anotar(
            secao="7",
            tabela="t",
            coluna="c",
            achado="zero com severidade",
            linhas=0,
            total=4,
            severidade="alta",
            impacto="",
            acao="",
        )
    with pytest.raises(ValueError):
        registro.anotar(
            secao="7",
            tabela="t",
            coluna="c",
            achado="mais que o total",
            linhas=5,
            total=4,
            severidade="alta",
            impacto="",
            acao="",
        )
    caminho = registro.salvar("2026-09-10", pasta=tmp_path)
    assert caminho.name == "teste.json"
    de_volta = achados.carregar(tmp_path)
    assert [a.pct for a in de_volta] == [50.0, 0.0]
    quadro = achados.consolidar(de_volta)
    assert list(quadro["severidade"]) == ["media", "nenhuma"]
    assert achados.resumir(de_volta).set_index("severidade")["achados"].to_dict() == {
        "alta": 0,
        "media": 1,
        "baixa": 0,
        "nenhuma": 1,
    }


def _caderno(*celulas: tuple[str, str], executado: bool = True) -> nbformat.NotebookNode:
    nb = nbformat.v4.new_notebook()  # type: ignore[no-untyped-call]
    for tipo, fonte in celulas:
        if tipo == "md":
            nb.cells.append(nbformat.v4.new_markdown_cell(fonte))  # type: ignore[no-untyped-call]
        else:
            celula = nbformat.v4.new_code_cell(fonte)  # type: ignore[no-untyped-call]
            if executado:
                celula.execution_count = 1
            nb.cells.append(celula)
    return nb  # type: ignore[no-any-return]


def test_o_verificador_aprova_o_padrao_e_reprova_o_que_foge(tmp_path: Path) -> None:
    cabecalho = "# Auditoria\n\n**Autor:** X\n\n**Objetivo:** y\n\n**Base analisada:** z"
    nota = "## Nota Técnica\n\n**Observado:** a\n\n**Por que importa:** b\n\n**Ação:** c"
    bom = _caderno(
        ("md", cabecalho),
        ("md", "# 1. Perfil"),
        ("code", "x = 1"),
        ("md", nota),
        ("md", "## Nota Técnica de fechamento\n\ntudo certo"),
    )
    caminho = tmp_path / "00_bom.ipynb"
    nbformat.write(bom, caminho)  # type: ignore[no-untyped-call]
    assert cadernos.verificar(caminho) == []

    ruim = _caderno(
        ("md", "# Auditoria"),
        ("md", "# 1. Perfil"),
        ("code", "from rh_fictalent.gerador import nucleo\nprint('/home/fulano/x')"),
        ("md", "# 2. Outra"),
        ("md", "## Nota Técnica\n\n**Observado:** só um campo"),
        executado=False,
    )
    caminho = tmp_path / "01_ruim.ipynb"
    nbformat.write(ruim, caminho)  # type: ignore[no-untyped-call]
    problemas = cadernos.verificar(caminho)
    assert any("cabeçalho sem **Objetivo:**" in p for p in problemas)
    assert any("seção 1 sem Nota Técnica" in p for p in problemas)
    assert any("não executada" in p for p in problemas)
    assert any("às cegas" in p for p in problemas)
    assert any("caminho de máquina" in p for p in problemas)
    assert any("sem **Por que importa:**" in p for p in problemas)
    assert any("sem Nota Técnica de fechamento" in p for p in problemas)


def test_os_notebooks_do_repositorio_seguem_o_padrao() -> None:
    """O teste que a CI roda sem lake: os notebooks versionados estão executados, com Nota
    Técnica em toda seção e sem consultar o gerador."""
    notebooks = cadernos.listar()
    assert notebooks, "nenhum notebook em notebooks/auditoria"
    for caminho in notebooks:
        assert cadernos.verificar(caminho) == [], caminho.name
