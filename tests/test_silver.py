# ruff: noqa: E501
"""A silver provada sem o lake: as regras contra o catálogo aprovado, todo o SQL sobre tabelas
vazias criadas da DDL real, o comportamento das regras delicadas em poucas linhas plantadas, e
a conferência da construção reprovando o que foi adulterado.

A prova com o dado inteiro (as 34 regras reproduzindo os números da auditoria) é a
prestação de contas contra o lake: `python -m rh_fictalent.silver --prestar-contas`.
"""

from __future__ import annotations

import random
import re
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, cast

import duckdb
import fsspec
import pytest

from rh_fictalent.auditoria import catalogo, checagens, esquema
from rh_fictalent.ingestao.backfill import CONTROLE
from rh_fictalent.orquestracao import silver as orquestracao
from rh_fictalent.silver import construcao, contas, regras

if TYPE_CHECKING:
    from fsspec.spec import AbstractFileSystem

    from rh_fictalent.orquestracao.recursos import Lake

REFERENCIA = date(2026, 9, 24)
TIPOS = {
    "BIGINT": "BIGINT", "INT": "BIGINT", "INTEGER": "BIGINT", "SMALLINT": "BIGINT",
    "TINYINT": "BIGINT", "MEDIUMINT": "BIGINT", "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",
    "DATE": "DATE", "DATETIME": "TIMESTAMP", "TIMESTAMP": "TIMESTAMP", "TIME": "TIME",
    "DECIMAL": "DECIMAL(18, 4)", "FLOAT": "DOUBLE", "DOUBLE": "DOUBLE",
}  # fmt: skip
DDL = esquema.ler()


def _vazia(con: duckdb.DuckDBPyConnection) -> None:
    """As 75 tabelas de negócio da DDL, vazias, com os nomes da réplica e a coluna da bronze."""
    for tabela in DDL.values():
        colunas = ", ".join(f'"{c.nome}" {TIPOS.get(c.tipo, "VARCHAR")}' for c in tabela.colunas)
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{tabela.esquema}"')
        con.execute(f"CREATE TABLE {tabela.qualificado} ({colunas}, {CONTROLE} TIMESTAMP)")


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    _vazia(c)
    regras.preparar(c, REFERENCIA)
    return c


def _origem(tabela: str) -> str:
    return f"(SELECT *, 2024 AS {construcao.ANO} FROM {tabela})"  # noqa: S608


def _inserir(con: duckdb.DuckDBPyConnection, tabela: str, linhas: list[dict[str, object]]) -> None:
    for linha in linhas:
        colunas = ", ".join(linha)
        marcadores = ", ".join("?" for _ in linha)
        con.execute(f"INSERT INTO {tabela} ({colunas}) VALUES ({marcadores})", list(linha.values()))  # noqa: S608


# ------------------------------------------------------------------ as regras contra o catálogo


def test_o_catalogo_inteiro_foi_considerado() -> None:
    codigos = [r.codigo for r in regras.REGRAS]
    assert len(codigos) == len(set(codigos))
    assert not set(codigos) & set(regras.FORA_DA_SILVER)
    assert set(codigos) | set(regras.FORA_DA_SILVER) == {e.codigo for e in catalogo.ENTRADAS}


def test_a_silver_so_implementa_o_aprovado() -> None:
    situacao = {e.codigo: e.situacao for e in catalogo.ENTRADAS}
    assert {
        r.codigo: situacao[r.codigo] for r in regras.REGRAS if situacao[r.codigo] != contas.APROVADA
    } == {}


def test_toda_coluna_citada_na_regra_aprovada_existe() -> None:
    """O texto aprovado cita colunas entre crases; cada uma ou é criada pela regra ou já existe
    numa das tabelas dela. Mudou o nome no código sem mudar no catálogo (ou o contrário), reprova."""
    texto = {e.codigo: e.regra for e in catalogo.ENTRADAS}
    for regra in regras.REGRAS:
        # o texto pode citar a coluna que outra regra da mesma tabela cria (o grupo_pessoa do ATS-01)
        criadas = {n.nome for t in regra.tabelas for n in construcao.novas(t)}
        existentes = {c.nome for t in regra.tabelas for c in DDL[t].colunas}
        citadas = set(re.findall(r"`(\w+)`", texto[regra.codigo]))
        assert citadas - criadas - existentes == set(), regra.codigo
        assert {c for c in citadas if c.startswith("q_")} <= {regra.marca}, regra.codigo
        propria = {c for d in regra.derivacoes for c in d.colunas}
        assert {c for c in citadas if c.startswith("q_")} <= propria, regra.codigo


def test_cada_regra_so_cria_a_propria_marca() -> None:
    for regra in regras.REGRAS:
        for derivacao in regra.derivacoes:
            assert set(derivacao.marcas) <= {regra.marca}, regra.codigo


def test_colunas_novas_nao_se_repetem_nem_colidem_com_a_ddl() -> None:
    for tabela in regras.por_tabela():
        nomes = [n.nome for n in construcao.novas(tabela)]
        assert len(nomes) == len(set(nomes)), tabela
        assert not set(nomes) & {c.nome for c in DDL[tabela].colunas}, tabela


def test_a_linhagem_declarada_cobre_o_que_o_sql_le() -> None:
    for regra in regras.REGRAS:
        for derivacao in regra.derivacoes:
            lidas = regras.tabelas_lidas(derivacao) & set(DDL)
            assert lidas <= {derivacao.tabela, *derivacao.le}, (regra.codigo, lidas)
            assert set(derivacao.le) <= set(DDL), regra.codigo


# ------------------------------------------------------------------ todo o SQL sobre a DDL real


def test_todo_sql_das_regras_roda_sobre_a_ddl(con: duckdb.DuckDBPyConnection) -> None:
    for regra in regras.REGRAS:
        for derivacao in regra.derivacoes:
            nome = regras.derivar(con, regra, derivacao)
            colunas = [linha[0] for linha in con.execute(f"DESCRIBE {nome}").fetchall()]
            assert colunas == ["id", *derivacao.colunas], regra.codigo
        assert con.execute(regra.sql_da_contagem).fetchall()[0][0] == 0, regra.codigo


def test_toda_tabela_com_regra_monta_e_se_confere_vazia(con: duckdb.DuckDBPyConnection) -> None:
    for tabela in regras.por_tabela():
        nome = construcao.construir(con, tabela, _origem(tabela), REFERENCIA)
        resultado = construcao.conferir(con, tabela, _origem(tabela), nome)
        assert resultado.aprovada, (tabela, resultado.problemas)


# ------------------------------------------------------------------ o dígito do CPF e a grafia


def _com_digitos(base: str) -> str:
    n = [int(c) for c in base]
    for pesos in (range(10, 1, -1), range(11, 1, -1)):
        resto = sum(a * b for a, b in zip(n, pesos, strict=False)) % 11
        n.append(0 if resto < 2 else 11 - resto)
    return "".join(map(str, n))


def test_o_cpf_da_silver_e_o_mesmo_da_auditoria(con: duckdb.DuckDBPyConnection) -> None:
    sorteio = random.Random(20260924)  # noqa: S311 - amostra de teste, não segredo
    validos = [_com_digitos(f"{sorteio.randrange(10**9):09d}") for _ in range(300)]
    aleatorios = [f"{sorteio.randrange(10**11):011d}" for _ in range(700)]
    casos = [
        *validos, *aleatorios, "529.982.247-25", "529.982.247-26", "111.111.111-11",
        "00000000000", "5299822472", "529982247250", "abc", "", "529 982 247 25",
    ]  # fmt: skip
    for caso in casos:
        (resultado,) = con.execute("SELECT cpf_valido(?)", [caso]).fetchall()[0]
        assert resultado == checagens.cpf_valido(caso), caso
    assert con.execute("SELECT cpf_valido(NULL)").fetchall()[0][0] is None


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("MARIA DA SILVA", "Maria da Silva"),
        ("  joão   p. souza ", "João P. Souza"),
        ("Ana Dos Santos E Lima", "Ana dos Santos e Lima"),
    ],
)
def test_caixa_de_titulo_nao_inventa(
    con: duckdb.DuckDBPyConnection, nome: str, esperado: str
) -> None:
    assert con.execute("SELECT caixa_de_titulo(?)", [nome]).fetchall()[0][0] == esperado


# ------------------------------------------------------------------ regras em poucas linhas


def test_duplicidade_de_candidato_agrupa_elege_e_nunca_funde(
    con: duckdb.DuckDBPyConnection,
) -> None:
    valido, invalido = "529.982.247-25", "529.982.247-26"
    base = {"dt_nascimento": date(1990, 5, 1), "excluido_em": None}
    _inserir(
        con,
        "ats.candidato",
        [
            {**base, "id": 1, "nome": "Maria Souza", "cpf": valido, "dt_cadastro": date(2022, 1, 1)},
            {**base, "id": 2, "nome": "MARIA SOUZA", "cpf": valido, "dt_cadastro": date(2020, 1, 1)},
            {**base, "id": 3, "nome": "maria  souza", "cpf": None, "dt_cadastro": date(2023, 1, 1)},
            {**base, "id": 4, "nome": "Jose Lima", "cpf": invalido, "dt_cadastro": date(2021, 1, 1)},
            {**base, "id": 5, "nome": "Jose Lima", "cpf": invalido, "dt_cadastro": date(2021, 2, 1)},
            {**base, "id": 6, "nome": "Morta", "cpf": valido, "dt_cadastro": date(2019, 1, 1),
             "excluido_em": date(2024, 1, 1)},
        ],
    )  # fmt: skip
    nome = construcao.construir(con, "ats.candidato", _origem("ats.candidato"), REFERENCIA)
    linhas = {
        r[0]: r[1:]
        for r in con.execute(
            f"SELECT id, q_ats_01, grupo_pessoa, cadastro_canonico, q_ats_03, q_ats_05, q_ats_06, nome_conformado FROM {nome}"  # noqa: S608
        ).fetchall()
    }
    grupo = "529.982.247-25"
    assert linhas[1][:3] == (True, grupo, 2)  # o repetido aponta o mais antigo com CPF válido
    assert linhas[2][:3] == (True, grupo, 2)
    assert linhas[3][:3] == (False, grupo, 2) and linhas[3][5] is True  # sem CPF: entra pelo nome
    assert linhas[4][:4] == (True, None, None, True)  # CPF inválido repetido: marcado, sem grupo
    assert linhas[2][4] is True and linhas[2][6] == "Maria Souza"  # caixa alta conformada
    assert linhas[6][0] is None and linhas[6][3] is None  # a excluída não é avaliada
    assert con.execute(f"SELECT count(*) FROM {nome}").fetchall()[0][0] == 6  # noqa: S608


def test_batida_repetida_elege_a_primeira_e_nao_apaga(con: duckdb.DuckDBPyConnection) -> None:
    dia = {"colaborador_id": 7, "data": date(2026, 9, 1), "excluido_em": None}
    _inserir(
        con,
        "ponto.marcacao",
        [
            {**dia, "id": 1, "tipo": "ENTRADA", "hora": "08:02:00"},
            {**dia, "id": 2, "tipo": "ENTRADA", "hora": "08:00:00"},
            {**dia, "id": 3, "tipo": "SAIDA", "hora": "17:00:00"},
        ],
    )
    nome = construcao.construir(con, "ponto.marcacao", _origem("ponto.marcacao"), REFERENCIA)
    linhas = dict(con.execute(f"SELECT id, (q_pon_02, batida_valida) FROM {nome}").fetchall())  # noqa: S608
    assert linhas == {1: (True, False), 2: (True, True), 3: (False, True)}


def test_prazo_depende_da_data_de_referencia(con: duckdb.DuckDBPyConnection) -> None:
    _inserir(
        con,
        "pessoas.contrato_trabalho",
        [{"id": 1, "tipo": "TEMPORARIO", "dt_admissao": date(2026, 1, 1), "dt_rescisao": None,
          "prazo_legal_dias": 180, "dt_prevista_termino": None, "criado_em": date(2026, 1, 5), "excluido_em": None}],
    )  # fmt: skip
    for referencia, alem, marcado in ((date(2026, 6, 1), 0, False), (REFERENCIA, 86, True)):
        nome = construcao.construir(
            con, "pessoas.contrato_trabalho", _origem("pessoas.contrato_trabalho"), referencia
        )
        sql = f"SELECT dias_alem_do_prazo, q_pes_01, dt_prevista_termino_derivada, q_pes_03, dias_de_atraso_do_lancamento FROM {nome}"  # noqa: S608
        assert con.execute(sql).fetchall()[0] == (alem, marcado, date(2026, 6, 30), True, 4)


# ------------------------------------------------------------------ a conferência reprova


@pytest.fixture
def montada(con: duckdb.DuckDBPyConnection) -> tuple[duckdb.DuckDBPyConnection, str]:
    _inserir(
        con,
        "cadastro.funcao",
        [
            {"id": 1, "nome": "Vigilante", "cbo": "517330", "excluido_em": None},
            {"id": 2, "nome": "Porteiro", "cbo": None, "excluido_em": None},
            {"id": 3, "nome": "Antiga", "cbo": None, "excluido_em": date(2024, 1, 1)},
        ],
    )
    return con, construcao.construir(con, "cadastro.funcao", _origem("cadastro.funcao"), REFERENCIA)


def test_a_conferencia_aprova_a_silver_certa(
    montada: tuple[duckdb.DuckDBPyConnection, str],
) -> None:
    con, nome = montada
    resultado = construcao.conferir(con, "cadastro.funcao", _origem("cadastro.funcao"), nome)
    assert resultado.aprovada and resultado.linhas == 3 and resultado.marcas == {"q_cad_01": 1}


@pytest.mark.parametrize(
    ("adulteracao", "acusa"),
    [
        ("UPDATE {t} SET nome = 'Vigia' WHERE id = 1", "valores originais"),
        ("DELETE FROM {t} WHERE id = 3", "linhas por ano"),
        ("UPDATE {t} SET q_cad_01 = TRUE WHERE id = 3", "q_cad_01"),
        ("UPDATE {t} SET q_cad_01 = NULL WHERE id = 1", "q_cad_01"),
        ("ALTER TABLE {t} DROP COLUMN q_cad_01", "colunas"),
    ],
)
def test_a_conferencia_reprova_o_que_foi_adulterado(
    montada: tuple[duckdb.DuckDBPyConnection, str], adulteracao: str, acusa: str
) -> None:
    con, nome = montada
    con.execute(adulteracao.format(t=nome))
    resultado = construcao.conferir(con, "cadastro.funcao", _origem("cadastro.funcao"), nome)
    assert not resultado.aprovada
    assert any(acusa in p for p in resultado.problemas), resultado.problemas


def test_construir_de_novo_da_o_mesmo_resultado(
    montada: tuple[duckdb.DuckDBPyConnection, str],
) -> None:
    con, nome = montada
    antes = con.execute(f"SELECT * FROM {nome} ORDER BY id").fetchall()  # noqa: S608
    construcao.construir(con, "cadastro.funcao", _origem("cadastro.funcao"), REFERENCIA)
    assert con.execute(f"SELECT * FROM {nome} ORDER BY id").fetchall() == antes  # noqa: S608


# ------------------------------------------------------------------ auditar antes de publicar


class _LakeLocal:
    """O recurso `Lake` sobre uma pasta: o mesmo contrato (`caminho`, `sistema`), sem S3."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz

    def caminho(self, camada: str, *partes: str) -> str:
        return "/".join((str(self.raiz), camada, *partes))

    def sistema(self) -> AbstractFileSystem:
        return fsspec.filesystem("file")


@pytest.fixture
def lake_local(
    montada: tuple[duckdb.DuckDBPyConnection, str], tmp_path: Path
) -> tuple[duckdb.DuckDBPyConnection, Lake]:
    con, _ = montada
    bronze = tmp_path / "bronze" / "cadastro" / "funcao"
    bronze.mkdir(parents=True)
    con.execute(f"COPY cadastro.funcao TO '{bronze / 'ano=2024.parquet'}' (FORMAT parquet)")
    return con, cast("Lake", _LakeLocal(tmp_path))


def test_a_tabela_aprovada_sai_da_conferencia_e_e_publicada(
    lake_local: tuple[duckdb.DuckDBPyConnection, Lake],
) -> None:
    con, lake = lake_local
    resultado = construcao.publicar(con, lake, "cadastro.funcao", REFERENCIA)
    assert resultado.aprovada and resultado.marcas == {"q_cad_01": 1}
    publicada = construcao.caminho_silver(lake, "cadastro.funcao", 2024)
    assert Path(publicada).exists()
    assert not Path(construcao.caminho_silver(lake, "cadastro.funcao", 2024, True)).exists()
    assert con.execute(f"SELECT count(*) FROM '{publicada}'").fetchall()[0][0] == 3  # noqa: S608


def test_a_tabela_reprovada_fica_na_conferencia_e_nao_substitui_a_publicada(
    lake_local: tuple[duckdb.DuckDBPyConnection, Lake], monkeypatch: pytest.MonkeyPatch
) -> None:
    con, lake = lake_local
    construcao.publicar(con, lake, "cadastro.funcao", REFERENCIA)
    publicada = Path(construcao.caminho_silver(lake, "cadastro.funcao", 2024))
    antes = publicada.read_bytes()
    reprovada = construcao.Resultado("cadastro.funcao", problemas=["valores originais: 1 linha"])
    monkeypatch.setattr(construcao, "conferir", lambda *_: reprovada)
    con.execute("UPDATE cadastro.funcao SET cbo = '000000' WHERE id = 2")  # a regra muda de ideia
    assert not construcao.publicar(con, lake, "cadastro.funcao", REFERENCIA).aprovada
    assert publicada.read_bytes() == antes
    assert Path(construcao.caminho_silver(lake, "cadastro.funcao", 2024, True)).exists()


# ------------------------------------------------------------------ prestação de contas e Dagster


def test_as_datas_da_auditoria_sao_lidas_dos_registros() -> None:
    datas = contas.referencias()
    assert {a.dominio for _, a in catalogo.casar()} <= set(datas)
    assert all(isinstance(d, date) for d in datas.values())


def test_a_conta_so_confere_com_o_numero_e_a_aprovacao() -> None:
    base = {"codigo": "X-01", "dominio": "d", "tabela": "t", "referencia": "2026-09-24"}
    assert contas.Conta(**base, auditoria=5, regra=5, situacao="aprovada").confere
    assert not contas.Conta(**base, auditoria=5, regra=6, situacao="aprovada").confere
    assert not contas.Conta(**base, auditoria=5, regra=5, situacao="proposta").confere
    relatorio = contas.relatorio([contas.Conta(**base, auditoria=5, regra=6, situacao="aprovada")])
    assert relatorio["reprovadas"] == ["X-01"]


def test_um_asset_por_tabela_com_a_linhagem_das_regras() -> None:
    chaves = {a.key.to_user_string() for a in orquestracao.ASSETS}
    assert len(chaves) == len(construcao.TABELAS) == 76
    assert "silver/ats/candidato" in chaves and "silver/arquivo/consolidado_gerencial" in chaves
    alocacao = next(
        a for a in orquestracao.ASSETS if a.key.path == ["silver", "pessoas", "alocacao"]
    )
    dependencias = {k.to_user_string() for k in alocacao.dependency_keys}
    assert {
        "bronze/pessoas/alocacao",
        "bronze/sst/aso",
        "bronze/treinamento/certificado",
    } <= dependencias
    assert set(orquestracao.prestacao_de_contas.dependency_keys) == {
        a.key for a in orquestracao.ASSETS
    }
