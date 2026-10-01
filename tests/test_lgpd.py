# ruff: noqa: E501
"""A LGPD no pipeline provada sem o lake: o inventário das etiquetas, a decisão para cada coluna
pessoal, a chave por HMAC, a silver pseudonimizada se conferindo, a bronze aceitando o nulo do
descarte, o descarte numa pasta local fazendo as vezes do lake, e a cadeia de custódia que a
prestação de contas segue.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import duckdb
import fsspec
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rh_fictalent.auditoria import esquema
from rh_fictalent.ingestao import backfill
from rh_fictalent.ingestao.backfill import CONTROLE
from rh_fictalent.lgpd import descarte
from rh_fictalent.orquestracao import lgpd as orquestracao_lgpd
from rh_fictalent.orquestracao import silver as orquestracao_silver
from rh_fictalent.silver import construcao, contas, pseudonimizacao, regras
from rh_fictalent.silver.pseudonimizacao import DECISOES, Tratamento
from rh_fictalent.staging import lgpd

if TYPE_CHECKING:
    from fsspec.spec import AbstractFileSystem

    from rh_fictalent.orquestracao.recursos import Lake, Warehouse

SEGREDO = b"segredo-de-teste-com-mais-de-trinta-e-dois"
OUTRO = b"outro-segredo-de-teste-com-mais-de-trinta"
CPF = "529.982.247-25"
REFERENCIA = date(2026, 10, 1)
DDL = esquema.ler()
TIPOS = {
    "BIGINT": "BIGINT", "INT": "BIGINT", "INTEGER": "BIGINT", "SMALLINT": "BIGINT",
    "TINYINT": "BIGINT", "MEDIUMINT": "BIGINT", "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",
    "DATE": "DATE", "DATETIME": "TIMESTAMP", "TIMESTAMP": "TIMESTAMP", "TIME": "TIME",
    "DECIMAL": "DECIMAL(18, 4)", "FLOAT": "DOUBLE", "DOUBLE": "DOUBLE",
}  # fmt: skip


def _ddl(con: duckdb.DuckDBPyConnection, exceto: tuple[str, ...] = ()) -> None:
    """As tabelas de negócio da DDL, vazias, com a coluna da bronze."""
    for tabela in DDL.values():
        if tabela.qualificado in exceto:
            continue
        colunas = ", ".join(f'"{c.nome}" {TIPOS.get(c.tipo, "VARCHAR")}' for c in tabela.colunas)
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{tabela.esquema}"')
        con.execute(f"CREATE TABLE {tabela.qualificado} ({colunas}, {CONTROLE} TIMESTAMP)")


def _inserir(con: duckdb.DuckDBPyConnection, tabela: str, linhas: list[dict[str, object]]) -> None:
    for linha in linhas:
        marcadores = ", ".join("?" for _ in linha)
        con.execute(
            f"INSERT INTO {tabela} ({', '.join(linha)}) VALUES ({marcadores})", list(linha.values())
        )  # noqa: S608


# ------------------------------------------------------------------ o inventário e as decisões


def test_o_inventario_le_as_etiquetas_da_ddl() -> None:
    etiquetadas = lgpd.colunas()
    assert etiquetadas["ats.candidato"]["cpf"] == lgpd.PESSOAL
    assert etiquetadas["sst.aso"]["resultado"] == lgpd.SENSIVEL
    assert "id" not in etiquetadas["ats.candidato"]
    assert sum(len(c) for c in etiquetadas.values()) == 28


def test_toda_coluna_pessoal_tem_decisao_com_motivo() -> None:
    """Coluna pessoal nova na DDL, com etiqueta, reprova aqui até alguém decidir o que fazer."""
    for tabela, colunas in lgpd.colunas().items():
        for coluna in colunas:
            decisao = DECISOES.get(tabela, {}).get(coluna)
            assert decisao is not None, f"{tabela}.{coluna} sem decisão de pseudonimização"
            assert decisao.motivo, f"{tabela}.{coluna} sem motivo"


def test_as_decisoes_valem_para_colunas_que_existem() -> None:
    for tabela, decisoes in DECISOES.items():
        for coluna, decisao in decisoes.items():
            assert coluna in DDL[tabela].nomes, f"{tabela}.{coluna} não existe na DDL"
            etiquetada = coluna in lgpd.da_tabela(*tabela.split("."))
            assert etiquetada or (tabela, coluna) in pseudonimizacao.FORA_DA_ETIQUETA, (
                tabela,
                coluna,
            )
            if decisao.tratamento is Tratamento.ANO:
                assert DDL[tabela].coluna(coluna).tipo == "DATE", (tabela, coluna)
            if decisao.tratamento is Tratamento.CHAVE:
                assert decisao.dominio, (tabela, coluna)


def test_decisoes_do_tiago_em_01_10() -> None:
    candidato = DECISOES["ats.candidato"]
    assert candidato["nome"].tratamento is Tratamento.REMOVER
    assert candidato["dt_nascimento"].tratamento is Tratamento.ANO
    assert candidato["cpf"].dominio == DECISOES["pessoas.colaborador"]["cpf"].dominio == "cpf"
    assert "nome_conformado" not in {
        c for r in regras.REGRAS for d in r.derivacoes for c in d.colunas
    }


# ------------------------------------------------------------------ a chave


def test_a_chave_e_estavel_normalizada_e_separada_por_dominio() -> None:
    chave = pseudonimizacao.chave(SEGREDO, "cpf", CPF)
    assert chave is not None and len(chave) == 64 and int(chave, 16) >= 0
    assert pseudonimizacao.chave(SEGREDO, "cpf", "52998224725") == chave  # pontuação não muda
    assert pseudonimizacao.chave(SEGREDO, "pis", CPF) != chave  # o mesmo número noutro domínio
    assert pseudonimizacao.chave(OUTRO, "cpf", CPF) != chave  # sem o segredo, outra chave
    assert pseudonimizacao.chave(SEGREDO, "cpf", None) is None
    assert pseudonimizacao.chave(SEGREDO, "cpf", " .-") is None


def test_a_funcao_sql_e_a_mesma_chave_do_python() -> None:
    con = duckdb.connect()
    pseudonimizacao.registrar(con, SEGREDO)
    assert con.execute("SELECT pseudonimo('cpf', ?)", [CPF]).fetchall()[0][
        0
    ] == pseudonimizacao.chave(SEGREDO, "cpf", CPF)
    assert con.execute("SELECT pseudonimo('cpf', NULL)").fetchall()[0][0] is None
    pseudonimizacao.registrar(con, OUTRO)  # registrar de novo troca o segredo
    assert con.execute("SELECT pseudonimo('cpf', ?)", [CPF]).fetchall()[0][
        0
    ] == pseudonimizacao.chave(OUTRO, "cpf", CPF)


def test_sem_segredo_a_silver_nao_nasce(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(pseudonimizacao.VARIAVEL, raising=False)
    with pytest.raises(RuntimeError, match=pseudonimizacao.VARIAVEL):
        pseudonimizacao.segredo_do_ambiente()
    monkeypatch.setenv(pseudonimizacao.VARIAVEL, "curto")
    with pytest.raises(RuntimeError):
        pseudonimizacao.segredo_do_ambiente()
    monkeypatch.setenv(pseudonimizacao.VARIAVEL, "x" * 40)
    assert pseudonimizacao.segredo_do_ambiente() == b"x" * 40
    con = duckdb.connect()
    _ddl(con)
    with pytest.raises(RuntimeError, match="pseudonimização"):
        construcao.construir(
            con, "cadastro.funcao", "(SELECT *, 2024 AS _ano FROM cadastro.funcao)", REFERENCIA
        )


# ------------------------------------------------------------------ a silver pseudonimizada


@pytest.fixture
def colaborador() -> tuple[duckdb.DuckDBPyConnection, str]:
    con = duckdb.connect()
    _ddl(con)
    pseudonimizacao.registrar(con, SEGREDO)
    _inserir(
        con,
        "pessoas.colaborador",
        [
            {
                "id": 1,
                "nome": "Ana Lima",
                "cpf": CPF,
                "dt_nascimento": date(1990, 5, 1),
                "pis": "120.5463.211-4",
                "matricula": "M1",
            },
            {
                "id": 2,
                "nome": "Bia Reis",
                "cpf": None,
                "dt_nascimento": None,
                "pis": None,
                "matricula": "M2",
            },
        ],
    )
    origem = f"(SELECT *, 2024 AS {construcao.ANO} FROM pessoas.colaborador)"
    return con, construcao.construir(con, "pessoas.colaborador", origem, REFERENCIA)


def test_a_silver_guarda_a_chave_o_ano_e_nao_o_nome(
    colaborador: tuple[duckdb.DuckDBPyConnection, str],
) -> None:
    con, nome = colaborador
    colunas = [r[0] for r in con.execute(f"DESCRIBE {nome}").fetchall()]
    assert {"nome", "cpf", "pis", "dt_nascimento"}.isdisjoint(colunas)
    assert (
        colunas.index("cpf_chave") == 3 and "ano_nascimento" in colunas and "pis_chave" in colunas
    )
    linha = con.execute(
        f"SELECT cpf_chave, ano_nascimento, matricula FROM {nome} WHERE id = 1"
    ).fetchall()[0]  # noqa: S608
    assert linha == (pseudonimizacao.chave(SEGREDO, "cpf", CPF), 1990, "M1")
    origem = "(SELECT *, 2024 AS _ano FROM pessoas.colaborador)"
    assert construcao.conferir(con, "pessoas.colaborador", origem, nome).aprovada


def test_a_conferencia_acusa_documento_em_claro(
    colaborador: tuple[duckdb.DuckDBPyConnection, str],
) -> None:
    con, nome = colaborador
    con.execute(f"UPDATE {nome} SET cpf_chave = '52998224725' WHERE id = 1")  # noqa: S608
    origem = "(SELECT *, 2024 AS _ano FROM pessoas.colaborador)"
    problemas = construcao.conferir(con, "pessoas.colaborador", origem, nome).problemas
    assert any("dado em claro" in p for p in problemas)
    assert any("valores originais" in p for p in problemas)


def test_a_linha_descartada_nao_vira_defeito_de_origem() -> None:
    """O CPF que o descarte apagou não é "candidato sem CPF": a linha não é avaliada."""
    con = duckdb.connect()
    _ddl(con)
    pseudonimizacao.registrar(con, SEGREDO)
    base = {"dt_cadastro": date(2020, 1, 1), "fonte_id": 1}
    _inserir(
        con,
        "ats.candidato",
        [
            {**base, "id": 1, "nome": "Ana Lima", "cpf": None},  # sem CPF de verdade
            {**base, "id": 2, "nome": None, "cpf": None},  # descartada por retenção
        ],
    )
    origem = f"(SELECT *, 2020 AS {construcao.ANO} FROM ats.candidato)"
    nome = construcao.construir(con, "ats.candidato", origem, REFERENCIA)
    linhas = con.execute(
        f"SELECT id, {construcao.DESCARTADO}, q_ats_06, q_ats_01 FROM {nome} ORDER BY id"
    ).fetchall()  # noqa: S608
    assert linhas == [(1, False, True, False), (2, True, None, None)]
    assert construcao.conferir(con, "ats.candidato", origem, nome).aprovada
    assert contas.contar(con, regras.ATS_06, REFERENCIA) == 1


# ------------------------------------------------------------------ a bronze aceita o nulo do descarte


class _Cursor:
    def __init__(self, linhas: list[tuple[Any, ...]]) -> None:
        self.linhas = linhas

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, *_: object) -> None:
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.linhas


class _Replica:
    def __init__(self, linhas: list[tuple[Any, ...]]) -> None:
        self.linhas = linhas

    def cursor(self) -> _Cursor:
        return _Cursor(self.linhas)


def test_na_bronze_a_coluna_pessoal_aceita_nulo_e_a_outra_nao() -> None:
    information_schema = [
        ("id", "bigint", 20, 0, "NO", "bigint unsigned"),
        ("nome", "varchar", None, None, "NO", "varchar(120)"),
        ("dt_cadastro", "date", None, None, "NO", "date"),
    ]
    campos = backfill.esquema(cast("Any", _Replica(information_schema)), "ats", "candidato")
    assert campos.field("nome").nullable
    assert not campos.field("dt_cadastro").nullable and not campos.field("id").nullable


# ------------------------------------------------------------------ o descarte, numa pasta local


class _LakeLocal:
    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz

    def caminho(self, camada: str, *partes: str) -> str:
        return "/".join((str(self.raiz), camada, *partes))

    def sistema(self) -> AbstractFileSystem:
        return fsspec.filesystem("file")


CANDIDATO = pa.schema(
    [
        pa.field("id", pa.int64(), nullable=False),
        pa.field("nome", pa.string(), nullable=False),  # como a ingestão gravava antes do 6.5
        pa.field("cpf", pa.string()),
        pa.field("dt_nascimento", pa.date32()),
        pa.field("sexo", pa.string()),
        pa.field("municipio_id", pa.int64()),
        pa.field("telefone", pa.string()),
        pa.field("email", pa.string()),
        pa.field("escolaridade", pa.string()),
        pa.field("fonte_id", pa.int64(), nullable=False),
        pa.field("dt_cadastro", pa.date32(), nullable=False),
        pa.field("criado_em", pa.timestamp("us"), nullable=False),
        pa.field("atualizado_em", pa.timestamp("us"), nullable=False),
        pa.field(CONTROLE, pa.timestamp("us")),
    ]
)


def _candidato(
    i: int, cadastro: date, cpf: str | None = CPF, excluido: bool = False
) -> dict[str, object]:
    return {
        "id": i, "nome": f"Pessoa {i}", "cpf": cpf, "dt_nascimento": date(1990, 1, i), "sexo": "F",
        "municipio_id": 1, "telefone": f"1199999000{i}", "email": f"p{i}@exemplo.com", "escolaridade": "MEDIO",
        "fonte_id": 1, "dt_cadastro": cadastro, "criado_em": datetime(cadastro.year, 1, 1),
        "atualizado_em": datetime(cadastro.year, 1, 1), CONTROLE: datetime(2025, 1, 1) if excluido else None,
    }  # fmt: skip


@pytest.fixture
def lake_local(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Lake]:
    """Candidatos na bronze (parquet numa pasta), o resto da DDL como tabelas.

    1 contratado e antigo; 2 antigo, nunca contratado, sem candidatura (vencido); 3 recente;
    4 antigo, com candidatura recente; 5 excluído na origem, ainda com dado pessoal.
    """
    pasta = tmp_path / "bronze" / "ats" / "candidato"
    pasta.mkdir(parents=True)
    por_ano = {
        2020: [
            _candidato(1, date(2020, 3, 1)),
            _candidato(2, date(2020, 4, 1)),
            _candidato(4, date(2020, 5, 1)),
        ],
        2026: [_candidato(3, date(2026, 3, 1)), _candidato(5, date(2026, 4, 1), excluido=True)],
    }
    for ano, linhas in por_ano.items():
        pq.write_table(pa.Table.from_pylist(linhas, schema=CANDIDATO), pasta / f"ano={ano}.parquet")
    con = duckdb.connect()
    _ddl(con, exceto=("ats.candidato",))
    con.execute(
        f"CREATE VIEW ats.candidato AS SELECT * FROM read_parquet('{pasta}/ano=*.parquet', union_by_name = true)"
    )
    _inserir(con, "pessoas.colaborador", [{"id": 10, "candidato_id": 1, "nome": "Pessoa 1"}])
    _inserir(
        con,
        "ats.candidatura",
        [{"id": 20, "candidato_id": 4, "vaga_id": 1, "dt_inscricao": date(2026, 6, 1)}],
    )
    return con, cast("Lake", _LakeLocal(tmp_path))


def _parametro(con: duckdb.DuckDBPyConnection) -> None:
    _inserir(
        con,
        "cadastro.parametro",
        [
            {
                "id": 1,
                "chave": descarte.PARAMETRO,
                "valor": "730",
                "vigencia_inicio": date(2026, 10, 1),
            }
        ],
    )


def test_sem_prazo_declarado_so_a_eliminacao(
    lake_local: tuple[duckdb.DuckDBPyConnection, Lake],
) -> None:
    con, _ = lake_local
    assert descarte.prazo(con, REFERENCIA) is None
    assert descarte.alvos(con, REFERENCIA, None) == {"ats.candidato": {descarte.ELIMINACAO: {5}}}


def test_o_vencido_e_o_antigo_nunca_contratado_sem_atividade(
    lake_local: tuple[duckdb.DuckDBPyConnection, Lake],
) -> None:
    con, _ = lake_local
    _parametro(con)
    vigente = descarte.prazo(con, REFERENCIA)
    assert vigente == descarte.Prazo(730, date(2026, 10, 1))
    assert descarte.prazo(con, date(2026, 9, 30)) is None  # antes da vigência, não há prazo
    assert descarte.alvos(con, REFERENCIA, vigente) == {
        "ats.candidato": {descarte.ELIMINACAO: {5}, descarte.RETENCAO: {2}}
    }


def test_o_descarte_apaga_so_o_dado_pessoal_dos_alvos_e_e_idempotente(
    lake_local: tuple[duckdb.DuckDBPyConnection, Lake],
) -> None:
    con, lake = lake_local
    _parametro(con)
    vigente, resultados = descarte.aplicar(con, lake, REFERENCIA)
    (r,) = resultados
    assert (r.tabela, r.eliminadas, r.vencidas, r.arquivos, r.problemas) == (
        "ats.candidato",
        1,
        1,
        2,
        [],
    )
    assert r.colunas == sorted(lgpd.colunas()["ats.candidato"])
    # os vivos 1 a 4 tinham o mesmo CPF; o vencido perdeu o dele e saiu do grupo repetido
    assert r.contas["ATS-01"] == (4, 3)
    # e o CPF apagado não virou "candidato sem CPF": a linha descartada não é avaliada
    assert r.contas["ATS-06"] == (0, 0)
    preenchidas = " OR ".join(f"{c} IS NOT NULL" for c in r.colunas)
    sobra = f"SELECT count(*) FROM ats.candidato WHERE id IN (2, 5) AND ({preenchidas})"  # noqa: S608
    assert con.execute(sobra).fetchall()[0][0] == 0
    restos = "SELECT id, dt_cadastro IS NOT NULL, fonte_id FROM ats.candidato WHERE id IN (2, 5) ORDER BY id"
    assert con.execute(restos).fetchall() == [(2, True, 1), (5, True, 1)]  # a linha fica
    intactos = "SELECT id, cpf, nome, email FROM ats.candidato WHERE id IN (1, 3, 4) ORDER BY id"
    assert con.execute(intactos).fetchall() == [
        (1, CPF, "Pessoa 1", "p1@exemplo.com"),
        (3, CPF, "Pessoa 3", "p3@exemplo.com"),
        (4, CPF, "Pessoa 4", "p4@exemplo.com"),
    ]
    assert not lake.sistema().glob(descarte.caminho(lake, "ats.candidato", em_descarte=True))
    assert descarte.aplicar(con, lake, REFERENCIA)[1] == []  # nada mais a apagar


def test_o_descarte_recusado_nao_toca_a_bronze(
    lake_local: tuple[duckdb.DuckDBPyConnection, Lake], monkeypatch: pytest.MonkeyPatch
) -> None:
    con, lake = lake_local
    original = Path(descarte.caminho(lake, "ats.candidato", "2026")).read_bytes()
    estragado = descarte._apagado

    def _estraga(tabela: pa.Table, alvo: pa.Array, colunas: list[str]) -> pa.Table:
        nova = estragado(tabela, alvo, colunas)
        posicao = nova.schema.get_field_index("escolaridade")
        return nova.set_column(posicao, "escolaridade", pa.array(["X"] * nova.num_rows))

    monkeypatch.setattr(descarte, "_apagado", _estraga)
    (r,) = descarte.aplicar(con, lake, REFERENCIA)[1]
    assert r.problemas and any("não era alvo" in p for p in r.problemas)
    assert Path(descarte.caminho(lake, "ats.candidato", "2026")).read_bytes() == original
    assert Path(descarte.caminho(lake, "ats.candidato", "2026", em_descarte=True)).exists()


# ------------------------------------------------------------------ a cadeia de custódia


def test_sem_descarte_o_esperado_e_a_auditoria() -> None:
    assert contas._esperado(457, []) == (457, contas.AUDITORIA, "")


def test_o_descarte_registrado_passa_a_ser_o_esperado() -> None:
    elos = [
        contas.Elo("b", "ATS-03", 450, 440, ordem=2),
        contas.Elo("a", "ATS-03", 457, 450, ordem=1),
    ]
    assert contas._esperado(457, elos) == (440, "descarte de b", "")


def test_a_cadeia_quebrada_reprova() -> None:
    esperado, origem, quebra = contas._esperado(457, [contas.Elo("a", "ATS-03", 400, 390, ordem=1)])
    assert (esperado, origem) == (457, contas.AUDITORIA) and "400" in quebra
    conta = contas.Conta(
        "ATS-03", "ats", "t", "2026-09-24", 457, 457, "aprovada", 457, origem, quebra
    )
    assert not conta.confere


class _WarehouseFalso:
    """O bastante de um Warehouse para `descarte.elos`: o DDL passa, a consulta devolve linhas."""

    def __init__(self, linhas: list[tuple[Any, ...]]) -> None:
        self.linhas = linhas

    def conectar(self) -> _WarehouseFalso:
        return self

    def __enter__(self) -> _WarehouseFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def cursor(self) -> _Cursor:
        return _Cursor([])

    def commit(self) -> None:
        return None

    def consultar(self, *_: object) -> list[tuple[Any, ...]]:
        return self.linhas


def test_os_registros_viram_elos_na_ordem_do_registro() -> None:
    quando = datetime(2026, 10, 1, 9, 30)
    linhas = [
        (7, quando, {"ATS-03": [457, 450], "ATS-06": [295, 300]}),
        (9, quando, json.dumps({"ATS-03": [450, 449]})),
    ]
    elos = descarte.elos(cast("Warehouse", _WarehouseFalso(linhas)))
    assert [(e.codigo, e.antes, e.depois, e.ordem) for e in elos] == [
        ("ATS-03", 457, 450, 7),
        ("ATS-06", 295, 300, 7),
        ("ATS-03", 450, 449, 9),
    ]
    assert contas._esperado(457, [e for e in elos if e.codigo == "ATS-03"])[0] == 449


# ------------------------------------------------------------------ o Dagster


def test_a_silver_de_tabela_pessoal_vem_depois_do_descarte() -> None:
    por_chave = {a.key.to_user_string(): a for a in orquestracao_silver.ASSETS}
    assert orquestracao_silver.DESCARTE in por_chave["silver/ats/candidato"].dependency_keys
    assert (
        orquestracao_silver.DESCARTE not in por_chave["silver/comercial/contrato"].dependency_keys
    )
    dependencias = {
        k.to_user_string() for k in orquestracao_lgpd.descarte_de_dado_pessoal.dependency_keys
    }
    assert {
        "bronze/ats/candidato",
        "bronze/cadastro/parametro",
        "bronze/pessoas/colaborador",
    } <= dependencias


def test_o_job_do_descarte_refaz_a_silver_afetada_e_presta_contas() -> None:
    todos = [
        orquestracao_lgpd.descarte_de_dado_pessoal,
        *orquestracao_silver.ASSETS,
        orquestracao_silver.prestacao_de_contas,
    ]
    selecao = orquestracao_lgpd.aplicar_descarte.selection
    selecionadas = {k.to_user_string() for k in selecao.resolve(todos)}
    assert {"lgpd/descarte", "silver/ats/candidato", "silver/prestacao_de_contas"} <= selecionadas
    assert "silver/comercial/contrato" not in selecionadas
    assert set(orquestracao_lgpd.CARGAS) == {"carga_incremental", "backfill_bronze"}
