# ruff: noqa: E501
"""A gold provada sem o lake de verdade: um cenário pequeno plantado na bronze, levado à silver
pela construção real, lido pelas views que a gold usa e conferido número a número, à mão.

O cenário: um contrato, um posto de 2 posições que começa em 10/01/2024, duas alocações (uma
termina em 15/02, a outra segue aberta), uma fatura de três itens com imposto que não divide
exato, uma fatura de recrutamento sem item, e o último apontamento em 10/03/2024, que é o
horizonte. A prova com o dado inteiro é `python -m rh_fictalent.gold --publicar`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import duckdb
import fsspec
import pytest

from rh_fictalent.auditoria import esquema
from rh_fictalent.gold import barramento, construcao, modelo
from rh_fictalent.ingestao.backfill import CONTROLE
from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao import definicoes
from rh_fictalent.orquestracao import gold as orquestracao
from rh_fictalent.silver import construcao as silver
from rh_fictalent.silver import pseudonimizacao

if TYPE_CHECKING:
    from fsspec.spec import AbstractFileSystem

    from rh_fictalent.orquestracao.recursos import Lake

REFERENCIA = date(2024, 3, 11)
SEGREDO = b"segredo-de-teste-com-mais-de-trinta-e-dois"  # nunca o do .env
TIPOS = {
    "BIGINT": "BIGINT", "INT": "BIGINT", "INTEGER": "BIGINT", "SMALLINT": "BIGINT",
    "TINYINT": "BIGINT", "MEDIUMINT": "BIGINT", "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",
    "DATE": "DATE", "DATETIME": "TIMESTAMP", "TIMESTAMP": "TIMESTAMP", "TIME": "TIME",
    "DECIMAL": "DECIMAL(18, 4)", "FLOAT": "DOUBLE", "DOUBLE": "DOUBLE",
}  # fmt: skip
FONTES = sorted(set().union(*(t.fontes for t in modelo.TABELAS)))


def _etapas(candidatura: int, etapas: tuple[int, ...]) -> list[dict[str, object]]:
    """As etapas do funil que a candidatura venceu, uma linha por etapa."""
    return [
        {
            "id": candidatura * 10 + e,
            "candidatura_id": candidatura,
            "etapa_id": e,
            "resultado": "APROVADO",
        }
        for e in etapas
    ]


CENARIO: dict[str, list[dict[str, object]]] = {
    "cadastro.regiao": [{"id": 1, "nome": "Bragantina"}],
    "cadastro.municipio": [{"id": 1, "nome": "Extrema", "uf": "MG", "regiao_id": 1}],
    "cadastro.endereco": [{"id": 1, "municipio_id": 1, "tipo": "FILIAL"}],
    "cadastro.filial": [
        {
            "id": 1,
            "codigo": "F1",
            "nome": "Matriz",
            "tipo": "MATRIZ",
            "endereco_id": 1,
            "ativo": True,
        }
    ],
    "cadastro.funcao": [
        {"id": 1, "codigo": "OP", "nome": "Operador", "cbo": "784205", "familia": "OPERACAO"}
    ],
    "cadastro.escala": [{"id": 1, "codigo": "5X2", "horas_semanais": 44}],
    "cadastro.motivo": [
        {"id": 1, "tipo": "FIM_ALOCACAO", "codigo": "X", "descricao": "Fim do posto"}
    ],
    "cadastro.feriado": [
        {"id": 1, "data": date(2024, 1, 1), "nome": "Confraternização", "abrangencia": "NACIONAL"},
        {
            "id": 2,
            "data": date(2024, 1, 2),
            "nome": "Feriado da cidade",
            "abrangencia": "MUNICIPAL",
            "municipio_id": 1,
        },
    ],
    "comercial.cliente": [
        {"id": 1, "razao_social": "Cliente Um", "municipio_id": 1, "ativo": True}
    ],
    "comercial.contrato": [
        {
            "id": 1,
            "numero": "CT-1",
            "cliente_id": 1,
            "filial_id": 1,
            "tipo_servico": "TERCEIRIZACAO",
            "status": "ATIVO",
            "dt_assinatura": date(2024, 1, 5),
            "vigencia_inicio": date(2024, 1, 10),
            "vigencia_fim": date(2024, 12, 31),
        },
    ],
    "comercial.contrato_aditivo": [
        {
            "id": 1,
            "contrato_id": 1,
            "numero": 1,
            "tipo": "PRORROGACAO",
            "dt_assinatura": date(2024, 2, 1),
        },
        {
            "id": 2,
            "contrato_id": 1,
            "numero": 2,
            "tipo": "REAJUSTE",
            "dt_assinatura": date(2024, 2, 1),
        },
    ],
    "comercial.posto": [
        {
            "id": 1,
            "contrato_id": 1,
            "funcao_id": 1,
            "quantidade": 2,
            "turno": "MANHA",
            "escala_id": 1,
            "endereco_id": 1,
            "vigencia_inicio": date(2024, 1, 10),
        },
    ],
    "comercial.posto_preco": [
        {
            "id": 1,
            "posto_id": 1,
            "valor_mensal": 1000,
            "vigencia_inicio": date(2024, 1, 10),
            "vigencia_fim": date(2024, 1, 31),
        },
        {"id": 2, "posto_id": 1, "valor_mensal": 1100, "vigencia_inicio": date(2024, 2, 1)},
    ],
    "ats.fonte_candidato": [{"id": 1, "nome": "INDICACAO"}],
    "ats.candidato": [
        {
            "id": 1,
            "nome": "Pessoa Um",
            "cpf": "11111111111",
            "sexo": "F",
            "fonte_id": 1,
            "municipio_id": 1,
            "dt_cadastro": date(2023, 12, 1),
        },
        {
            "id": 2,
            "nome": "Pessoa Dois",
            "cpf": "22222222222",
            "sexo": "M",
            "fonte_id": 1,
            "municipio_id": 1,
            "dt_cadastro": date(2023, 12, 2),
        },
        # excluída no sistema do cliente: não existe para a gold
        {
            "id": 3,
            "nome": "Pessoa Três",
            "cpf": "33333333333",
            "fonte_id": 1,
            "dt_cadastro": date(2023, 12, 3),
            CONTROLE: "2024-01-01 00:00:00",
        },
        {
            "id": 4,
            "nome": "Pessoa Quatro",
            "cpf": "44444444444",
            "sexo": "M",
            "fonte_id": 1,
            "dt_cadastro": date(2023, 12, 4),
        },
        {
            "id": 5,
            "nome": "Pessoa Cinco",
            "cpf": "55555555555",
            "sexo": "F",
            "fonte_id": 1,
            "dt_cadastro": date(2023, 12, 5),
        },
    ],
    "pessoas.colaborador": [
        {
            "id": 1,
            "candidato_id": 1,
            "matricula": "M1",
            "cpf": "11111111111",
            "municipio_id": 1,
            "ativo": True,
        },
        {
            "id": 2,
            "candidato_id": 2,
            "matricula": "M2",
            "cpf": "22222222222",
            "municipio_id": 1,
            "ativo": True,
        },
    ],
    "pessoas.alocacao": [
        {
            "id": 1,
            "colaborador_id": 1,
            "contrato_trabalho_id": 1,
            "posto_id": 1,
            "dt_inicio": date(2024, 1, 10),
            "dt_fim": date(2024, 2, 15),
            "motivo_fim_id": 1,
        },
        # a segunda substitui a primeira e segue aberta
        {
            "id": 2,
            "colaborador_id": 2,
            "contrato_trabalho_id": 2,
            "posto_id": 1,
            "dt_inicio": date(2024, 1, 20),
            "substituindo_alocacao_id": 1,
        },
    ],
    "pessoas.contrato_trabalho": [
        {
            "id": 1,
            "colaborador_id": 1,
            "tipo": "TEMPORARIO",
            "funcao_id": 1,
            "filial_id": 1,
            "dt_admissao": date(2024, 1, 10),
            "dt_prevista_termino": date(2024, 4, 9),
            "dt_rescisao": date(2024, 2, 15),
            "salario_base": Decimal("1500.00"),
            "escala_id": 1,
            "prazo_legal_dias": 90,
            "status": "ENCERRADO",
        },
        {
            "id": 2,
            "colaborador_id": 2,
            "tipo": "TEMPORARIO",
            "funcao_id": 1,
            "filial_id": 1,
            "dt_admissao": date(2024, 1, 20),
            "dt_prevista_termino": date(2024, 4, 19),
            "salario_base": Decimal("1600.00"),
            "escala_id": 1,
            "prazo_legal_dias": 90,
            "status": "ATIVO",
        },
    ],
    "pessoas.contrato_trabalho_prorrogacao": [
        {
            "id": 1,
            "contrato_trabalho_id": 2,
            "dt_assinatura": date(2024, 3, 1),
            "dt_novo_termino": date(2024, 7, 18),
            "dias_adicionais": 90,
        },
    ],
    "pessoas.desligamento": [
        {
            "id": 1,
            "contrato_trabalho_id": 1,
            "dt_desligamento": date(2024, 2, 15),
            "tipo": "VOLUNTARIO",
            "motivo_id": 1,
            "dias_aviso_previo": 0,
            "valor_rescisao": Decimal("800.00"),
        },
    ],
    "comercial.contrato_ocorrencia": [
        {
            "id": 1,
            "contrato_id": 1,
            "posto_id": 1,
            "dt_ocorrencia": date(2024, 2, 1),
            "tipo": "RECLAMACAO",
            "descricao": "Posto ficou descoberto no turno",
        },
        {
            "id": 2,
            "contrato_id": 1,
            "dt_ocorrencia": date(2024, 2, 20),
            "tipo": "ELOGIO",
            "descricao": "Cliente elogiou o atendimento da equipe",
        },
    ],
    "ats.etapa_funil": [
        {"id": 1, "codigo": "TRIAGEM", "nome": "Triagem de currículo", "ordem": 1},
        {"id": 2, "codigo": "ENTREVISTA_INTERNA", "nome": "Entrevista interna", "ordem": 2},
        {"id": 3, "codigo": "ENCAMINHAMENTO", "nome": "Encaminhamento ao cliente", "ordem": 3},
        {"id": 4, "codigo": "ENTREVISTA_CLIENTE", "nome": "Entrevista no cliente", "ordem": 4},
        {"id": 5, "codigo": "APROVACAO", "nome": "Aprovação e admissão", "ordem": 5},
    ],
    "ats.requisicao": [
        {
            "id": 1,
            "numero": "RQ-1",
            "cliente_id": 1,
            "contrato_id": 1,
            "posto_id": 1,
            "quantidade": 2,
            "dt_abertura": date(2023, 12, 15),
            "dt_necessidade": date(2024, 1, 10),
            "prioridade": "NORMAL",
            "status": "ATENDIDA",
        },
        # recrutamento: sem posto
        {
            "id": 2,
            "numero": "RQ-2",
            "cliente_id": 1,
            "contrato_id": 1,
            "quantidade": 1,
            "dt_abertura": date(2024, 2, 1),
            "dt_necessidade": date(2024, 3, 1),
            "prioridade": "ALTA",
            "status": "EM_ATENDIMENTO",
        },
    ],
    "ats.vaga": [
        {
            "id": 1,
            "requisicao_id": 1,
            "codigo": "VG-1",
            "titulo": "Operador",
            "funcao_id": 1,
            "filial_id": 1,
            "quantidade_posicoes": 2,
            "dt_abertura": date(2023, 12, 18),
            "dt_fechamento": date(2024, 1, 8),
            "status": "PREENCHIDA",
            "salario_previsto": Decimal("1500.00"),
        },
        {
            "id": 2,
            "requisicao_id": 2,
            "codigo": "VG-2",
            "titulo": "Operador",
            "funcao_id": 1,
            "filial_id": 1,
            "quantidade_posicoes": 1,
            "dt_abertura": date(2024, 2, 5),
            "status": "ABERTA",
        },
    ],
    "ats.candidatura": [
        {
            "id": 1,
            "vaga_id": 1,
            "candidato_id": 1,
            "dt_inscricao": date(2023, 12, 20),
            "status": "APROVADA",
            "dt_conclusao": date(2024, 1, 5),
        },
        {
            "id": 2,
            "vaga_id": 1,
            "candidato_id": 2,
            "dt_inscricao": date(2023, 12, 22),
            "status": "APROVADA",
            "dt_conclusao": date(2024, 1, 8),
        },
        {
            "id": 3,
            "vaga_id": 1,
            "candidato_id": 4,
            "dt_inscricao": date(2023, 12, 21),
            "status": "REPROVADA",
            "dt_conclusao": date(2023, 12, 28),
            "motivo_reprovacao_id": 1,
        },
        {
            "id": 4,
            "vaga_id": 2,
            "candidato_id": 4,
            "dt_inscricao": date(2024, 2, 6),
            "status": "EM_ANDAMENTO",
        },
        # aprovada que nunca virou vínculo
        {
            "id": 5,
            "vaga_id": 1,
            "candidato_id": 5,
            "dt_inscricao": date(2023, 12, 23),
            "status": "APROVADA",
            "dt_conclusao": date(2024, 1, 9),
        },
    ],
    "ats.candidatura_etapa": [
        *_etapas(1, (1, 2, 3, 5)),
        *_etapas(2, (1, 2, 3, 4, 5)),
        {"id": 31, "candidatura_id": 3, "etapa_id": 1, "resultado": "REPROVADO", "motivo_id": 1},
        {"id": 41, "candidatura_id": 4, "etapa_id": 1, "resultado": "APROVADO"},
        {"id": 42, "candidatura_id": 4, "etapa_id": 2, "resultado": "PENDENTE"},
        *_etapas(5, (1, 2, 3, 5)),
    ],
    "ats.entrevista": [
        {
            "id": 1,
            "candidatura_id": 1,
            "tipo": "INTERNA",
            "fl_compareceu": True,
            "resultado": "APROVADO",
        },
        {
            "id": 2,
            "candidatura_id": 2,
            "tipo": "INTERNA",
            "fl_compareceu": True,
            "resultado": "APROVADO",
        },
        {
            "id": 3,
            "candidatura_id": 2,
            "tipo": "CLIENTE",
            "fl_compareceu": True,
            "resultado": "APROVADO",
        },
        {
            "id": 4,
            "candidatura_id": 5,
            "tipo": "INTERNA",
            "fl_compareceu": False,
            "resultado": "NAO_COMPARECEU",
        },
    ],
    "ponto.apontamento": [
        {
            "id": 1,
            "colaborador_id": 2,
            "alocacao_id": 2,
            "data": date(2024, 3, 10),
            "status": "PRESENTE",
        }
    ],
    "financeiro.fatura": [
        {
            "id": 1,
            "numero": "NF-1",
            "cliente_id": 1,
            "contrato_id": 1,
            "competencia": date(2024, 1, 1),
            "dt_emissao": date(2024, 2, 1),
            "valor_bruto": Decimal("100.00"),
            "valor_impostos": Decimal("10.01"),
            "valor_liquido": Decimal("89.99"),
            "status": "EMITIDA",
        },
        {
            "id": 2,
            "numero": "NF-2",
            "cliente_id": 1,
            "contrato_id": 1,
            "competencia": date(2024, 2, 1),
            "dt_emissao": date(2024, 3, 1),
            "valor_bruto": Decimal("50.00"),
            "valor_impostos": Decimal("5.00"),
            "valor_liquido": Decimal("45.00"),
            "status": "EMITIDA",
        },
    ],
    "financeiro.fatura_item": [
        {
            "id": 1,
            "fatura_id": 1,
            "posto_id": 1,
            "valor_postos": Decimal("33.33"),
            "valor_total": Decimal("33.33"),
        },
        {
            "id": 2,
            "fatura_id": 1,
            "posto_id": 1,
            "valor_postos": Decimal("33.33"),
            "valor_total": Decimal("33.33"),
        },
        {
            "id": 3,
            "fatura_id": 1,
            "posto_id": 1,
            "valor_postos": Decimal("33.34"),
            "valor_total": Decimal("33.34"),
        },
    ],
    "folha.rateio_custo": [
        {
            "id": 1,
            "competencia": date(2024, 1, 1),
            "colaborador_id": 1,
            "alocacao_id": 1,
            "contrato_id": 1,
            "posto_id": 1,
            "valor_salario": Decimal("40.00"),
            "custo_total": Decimal("60.00"),
        },
        # custo lançado num mês depois do horizonte: não pode sumir da gold
        {
            "id": 2,
            "competencia": date(2024, 4, 1),
            "colaborador_id": 2,
            "alocacao_id": 2,
            "contrato_id": 1,
            "posto_id": 1,
            "valor_salario": Decimal("20.00"),
            "custo_total": Decimal("25.00"),
        },
    ],
}


class _LakeLocal:
    """O recurso `Lake` sobre uma pasta: o mesmo contrato (`caminho`, `sistema`), sem S3."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz

    def caminho(self, camada: str, *partes: str) -> str:
        return "/".join((str(self.raiz), camada, *partes))

    def sistema(self) -> AbstractFileSystem:
        return fsspec.filesystem("file")


def _bronze() -> duckdb.DuckDBPyConnection:
    """As tabelas da DDL na memória, com os nomes da réplica, e o cenário plantado nelas."""
    con = duckdb.connect()
    for tabela in esquema.ler().values():
        colunas = ", ".join(f'"{c.nome}" {TIPOS.get(c.tipo, "VARCHAR")}' for c in tabela.colunas)
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{tabela.esquema}"')
        con.execute(f"CREATE TABLE {tabela.qualificado} ({colunas}, {CONTROLE} TIMESTAMP)")
    for tabela_, linhas in CENARIO.items():
        for linha in linhas:
            marcadores = ", ".join("?" for _ in linha)
            con.execute(
                f"INSERT INTO {tabela_} ({', '.join(linha)}) VALUES ({marcadores})",
                list(linha.values()),
            )  # noqa: S608
    return con


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory) -> Lake:
    """A silver do cenário, gravada em parquet pela construção de verdade."""
    assert set(CENARIO) == set(FONTES), "o cenário tem de alimentar toda tabela que a gold lê"
    local = cast("Lake", _LakeLocal(tmp_path_factory.mktemp("lake")))
    con = _bronze()
    pseudonimizacao.registrar(con, SEGREDO)
    for tabela in FONTES:
        origem = f"(SELECT *, 2024 AS {silver.ANO} FROM {tabela})"  # noqa: S608
        silver.construir(con, tabela, origem, REFERENCIA)
        assert silver.gravar(con, local, tabela, em_conferencia=False)
    con.close()
    return local


def _abrir(lake: Lake) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    caminhos = {t: lake.caminho("silver", *t.split("."), "ano=*.parquet") for t in FONTES}
    consulta.criar_views_da_silver(con, caminhos)
    return con


@pytest.fixture
def gold(lake: Lake) -> duckdb.DuckDBPyConnection:
    """A gold inteira montada na memória sobre a silver do cenário."""
    con = _abrir(lake)
    resultados = construcao.construir(con)
    assert {n: r.problemas for n, r in resultados.items() if not r.aprovada} == {}
    return con


def _linhas(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    cursor = con.execute(sql)
    nomes = [d[0] for d in cursor.description]
    return [dict(zip(nomes, linha, strict=True)) for linha in cursor.fetchall()]


# ------------------------------------------------------------------ o modelo contra a matriz


def test_o_modelo_implementa_a_matriz_aprovada() -> None:
    nomes = [t.nome for t in modelo.TABELAS]
    assert len(nomes) == len(set(nomes))
    for t in modelo.TABELAS:
        if t.fato:
            previsto = barramento.fato(t.nome)
            assert set(t.referencias.values()) == set(previsto.dimensoes), t.nome
            assert t.particao and t.conservacoes, f"{t.nome}: fato sem partição ou sem conservação"
            for marca in previsto.marcas:
                assert marca in t.sql, (t.nome, marca)
        else:
            assert barramento.dimensao(t.nome).prioridade == 1 and t.chave == ("id",)
        na_matriz = set(
            barramento.fato(t.nome).fontes if t.fato else barramento.dimensao(t.nome).fontes
        )
        assert na_matriz <= t.fontes, (t.nome, na_matriz - t.fontes)
        implicitas = set(modelo.FONTES_DO_HORIZONTE) | set(modelo.FONTES_DO_CALENDARIO)
        assert t.fontes - na_matriz <= implicitas, (t.nome, t.fontes - na_matriz - implicitas)


def test_a_dimensao_vem_antes_de_quem_a_referencia() -> None:
    ordem = [t.nome for t in modelo.TABELAS]
    for t in modelo.TABELAS:
        for dimensao in t.referencias.values():
            assert ordem.index(dimensao) < ordem.index(t.nome), (t.nome, dimensao)


# ------------------------------------------------------------------ a leitura da silver


def test_a_gold_so_enxerga_as_linhas_vivas_da_silver(lake: Lake) -> None:
    con = _abrir(lake)
    vivos = con.execute("SELECT list(id ORDER BY id) FROM silver.ats.candidato").fetchall()[0][0]
    assert vivos == [1, 2, 4, 5]
    colunas = {c[0] for c in con.execute("DESCRIBE silver.ats.candidato").fetchall()}
    assert CONTROLE not in colunas and "cpf" not in colunas and "nome" not in colunas
    arquivo = lake.caminho("silver", "ats", "candidato", "ano=2024.parquet")
    assert con.execute(f"SELECT count(*) FROM '{arquivo}'").fetchall()[0][0] == 5  # noqa: S608


# ------------------------------------------------------------------ as dimensões


def test_o_horizonte_e_o_ultimo_dia_com_movimento(lake: Lake) -> None:
    assert modelo.preparar(_abrir(lake)) == "2024-03-10"


def test_sem_movimento_nao_ha_horizonte() -> None:
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS silver")
    con.execute("CREATE SCHEMA silver.ponto; CREATE SCHEMA silver.pessoas")
    con.execute("CREATE TABLE silver.ponto.apontamento (data DATE)")
    con.execute("CREATE TABLE silver.pessoas.alocacao (dt_inicio DATE, dt_fim DATE)")
    with pytest.raises(RuntimeError, match="sem horizonte"):
        modelo.preparar(con)


def test_o_calendario_conhece_dia_util_e_feriado_nacional(gold: duckdb.DuckDBPyConnection) -> None:
    dias = {
        d["id"]: d
        for d in _linhas(gold, "SELECT * FROM gold.dim_data WHERE id BETWEEN 20240101 AND 20240107")
    }
    assert dias[20240101]["feriado_nacional"] and not dias[20240101]["dia_util"]
    # o feriado municipal não fecha o calendário da empresa inteira
    assert dias[20240102]["dia_util"] and not dias[20240102]["feriado_nacional"]
    assert not dias[20240106]["dia_util"] and dias[20240106]["dia_da_semana"] == 6
    janeiro = _linhas(gold, "SELECT * FROM gold.dim_mes WHERE id = 202401")[0]
    assert (janeiro["dias"], janeiro["dias_uteis"]) == (31, 22)
    fevereiro = _linhas(gold, "SELECT * FROM gold.dim_mes WHERE id = 202402")[0]
    assert (fevereiro["dias"], fevereiro["ultimo_dia"]) == (29, date(2024, 2, 29))
    n, primeiro, ultimo = gold.execute(
        "SELECT count(*), min(data), max(data) FROM gold.dim_data"
    ).fetchall()[0]
    # 2922 dias (até o ano seguinte ao horizonte) e a linha 0
    assert (n, primeiro, ultimo) == (2923, date(2018, 1, 1), date(2025, 12, 31))


def test_toda_dimensao_tem_a_linha_nao_se_aplica(gold: duckdb.DuckDBPyConnection) -> None:
    for t in modelo.TABELAS:
        if not t.fato:
            assert (
                gold.execute(f"SELECT count(*) FROM gold.{t.nome} WHERE id = 0").fetchall()[0][0]
                == 1
            ), t.nome  # noqa: S608


def test_a_dimensao_de_pessoa_nao_identifica_ninguem(gold: duckdb.DuckDBPyConnection) -> None:
    for nome in modelo.DIMENSOES_DE_PESSOA:
        colunas = {c[0] for c in gold.execute(f"DESCRIBE gold.{nome}").fetchall()}
        assert not colunas & set(modelo.IDENTIDADE), nome
        assert not [c for c in colunas if c.endswith("_chave")], nome
    colaborador = _linhas(gold, "SELECT * FROM gold.dim_colaborador WHERE id = 1")[0]
    assert (
        colaborador["sexo"],
        colaborador["fonte_de_recrutamento"],
        colaborador["municipio"],
    ) == ("F", "INDICACAO", "Extrema")
    candidatos = gold.execute("SELECT list(id ORDER BY id) FROM gold.dim_candidato").fetchall()[0][
        0
    ]
    assert candidatos == [0, 1, 2, 4, 5]  # a 3 foi excluída no sistema do cliente


def test_o_contrato_e_o_posto_carregam_a_hierarquia(gold: duckdb.DuckDBPyConnection) -> None:
    contrato = _linhas(gold, "SELECT * FROM gold.dim_contrato WHERE id = 1")[0]
    assert (contrato["prorrogacoes"], contrato["cliente_id"], contrato["filial_id"]) == (1, 1, 1)
    assert contrato["status_informado"] == "ATIVO" and contrato["situacao_derivada"] is not None
    posto = _linhas(gold, "SELECT * FROM gold.dim_posto WHERE id = 1")[0]
    assert (posto["posicoes"], posto["escala"], posto["municipio"], posto["cliente_id"]) == (
        2,
        "5X2",
        "Extrema",
        1,
    )


# ------------------------------------------------------------------ os fatos


def test_o_imposto_da_fatura_e_repartido_e_fecha_ao_centavo(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    itens = _linhas(
        gold, "SELECT * FROM gold.fato_faturamento WHERE fatura_id = 1 ORDER BY fatura_item_id"
    )
    assert [i["valor_impostos"] for i in itens] == [
        Decimal("3.34"),
        Decimal("3.34"),
        Decimal("3.33"),
    ]
    assert sum(cast("Decimal", i["valor_liquido"]) for i in itens) == Decimal("89.99")
    assert {
        (i["mes_id"], i["data_emissao_id"], i["posto_id"], i["funcao_id"], i["filial_id"])
        for i in itens
    } == {(202401, 20240201, 1, 1, 1)}


def test_a_fatura_sem_item_entra_numa_linha_sem_posto(gold: duckdb.DuckDBPyConnection) -> None:
    (linha,) = _linhas(gold, "SELECT * FROM gold.fato_faturamento WHERE fatura_id = 2")
    assert (linha["fatura_item_id"], linha["posto_id"], linha["funcao_id"]) == (0, 0, 0)
    assert (linha["valor_bruto"], linha["valor_impostos"], linha["valor_liquido"]) == (
        Decimal("50.00"),
        Decimal("5.00"),
        Decimal("45.00"),
    )
    assert linha["valor_postos"] is None and linha["ano"] == 2024


def test_o_custo_de_pessoal_fica_no_grao_do_rateio(gold: duckdb.DuckDBPyConnection) -> None:
    linhas = _linhas(gold, "SELECT * FROM gold.fato_custo_pessoal ORDER BY id")
    assert [
        (
            c["mes_id"],
            c["colaborador_id"],
            c["posto_id"],
            c["cliente_id"],
            c["filial_id"],
            c["funcao_id"],
            c["custo_total"],
        )
        for c in linhas
    ] == [
        (202401, 1, 1, 1, 1, 1, Decimal("60.00")),
        (202404, 2, 1, 1, 1, 1, Decimal("25.00")),
    ]


def test_o_posto_por_mes_conta_dias_pessoas_e_margem(gold: duckdb.DuckDBPyConnection) -> None:
    meses = {
        m["mes_id"]: m for m in _linhas(gold, "SELECT * FROM gold.fato_posto_mes ORDER BY mes_id")
    }
    assert list(meses) == [202401, 202402, 202403, 202404]

    janeiro = meses[202401]  # o posto começa no dia 10: 22 dias, 2 posições
    assert (janeiro["dias_vigentes"], janeiro["posicao_dias_contratados"]) == (22, 44)
    assert (janeiro["pessoa_dias_alocados"], janeiro["posicao_dias_descobertos"]) == (22 + 12, 10)
    assert janeiro["taxa_de_ocupacao"] == pytest.approx(34 / 44)
    assert (janeiro["pessoas_no_fim_do_mes"], janeiro["entradas"], janeiro["saidas"]) == (2, 2, 0)
    assert (
        janeiro["preco_mensal_vigente"],
        janeiro["receita"],
        janeiro["custo_pessoal"],
        janeiro["margem"],
    ) == (1000, Decimal("100.00"), Decimal("60.00"), Decimal("40.00"))
    assert janeiro["margem_pct"] == pytest.approx(0.4) and janeiro["faturado"]

    fevereiro = meses[202402]  # 29 dias; a primeira alocação sai no dia 15
    assert (fevereiro["posicao_dias_contratados"], fevereiro["pessoa_dias_alocados"]) == (
        58,
        15 + 29,
    )
    assert (fevereiro["pessoas_no_fim_do_mes"], fevereiro["entradas"], fevereiro["saidas"]) == (
        1,
        0,
        1,
    )
    assert fevereiro["preco_mensal_vigente"] == 1100  # o preço reajustado em fevereiro
    assert (
        not fevereiro["faturado"] and fevereiro["receita"] == 0 and fevereiro["margem_pct"] is None
    )

    marco = meses[202403]  # o mês do horizonte: medido até o dia 10 e marcado
    assert marco["mes_parcial"] and not janeiro["mes_parcial"]
    assert (
        marco["dias_vigentes"],
        marco["posicao_dias_contratados"],
        marco["pessoa_dias_alocados"],
    ) == (10, 20, 10)
    assert marco["pessoas_no_fim_do_mes"] == 1

    abril = meses[202404]  # só custo, depois do horizonte: a linha existe e diz que está fora
    assert abril["fora_da_vigencia"] and abril["custo_pessoal"] == Decimal("25.00")
    assert abril["taxa_de_ocupacao"] is None and abril["margem"] == Decimal("-25.00")


def test_o_contrato_acumula_a_vida_dele(gold: duckdb.DuckDBPyConnection) -> None:
    (k,) = _linhas(gold, "SELECT * FROM gold.fato_contrato")
    assert (
        k["data_inicio_id"],
        k["data_fim_id"],
        k["data_encerramento_id"],
        k["motivo_encerramento_id"],
    ) == (20240110, 20241231, 0, 0)
    assert not k["encerrado"] and k["meses_de_vida"] == 2  # de 10/01 ao horizonte, 10/03
    assert (k["prorrogacoes"], k["reajustes"], k["postos"], k["posicoes"]) == (1, 1, 1, 2)
    assert (k["reclamacoes"], k["elogios"], k["avisos_de_rescisao"], k["faturas"]) == (1, 1, 0, 2)
    assert (k["receita_bruta"], k["receita_liquida"]) == (Decimal("150.00"), Decimal("134.99"))


def test_a_vaga_conta_candidaturas_e_dias(gold: duckdb.DuckDBPyConnection) -> None:
    vagas = {v["vaga_id"]: v for v in _linhas(gold, "SELECT * FROM gold.fato_vaga")}
    preenchida, aberta = vagas[1], vagas[2]
    assert (preenchida["candidaturas"], preenchida["aprovados"], preenchida["posicoes"]) == (
        4,
        3,
        2,
    )
    assert (
        preenchida["preenchida"]
        and not preenchida["aberta"]
        and preenchida["dias_ate_preencher"] == 21
    )
    assert preenchida["dias_em_aberto"] is None and preenchida["dias_alem_da_necessidade"] == -2
    assert (preenchida["contrato_id"], preenchida["posto_id"], preenchida["cliente_id"]) == (
        1,
        1,
        1,
    )
    assert (
        aberta["aberta"] and aberta["dias_em_aberto"] == 34 and aberta["dias_ate_preencher"] is None
    )
    assert (
        aberta["posto_id"],
        aberta["em_andamento"],
        aberta["data_fechamento_id"],
        aberta["dias_alem_da_necessidade"],
    ) == (0, 1, 0, 9)


def test_a_candidatura_tem_as_etapas_em_colunas_e_a_admissao_casada(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    c = {x["candidatura_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_candidatura")}
    assert c[1]["admitida"] and (
        c[1]["contrato_trabalho_id"],
        c[1]["data_admissao_id"],
        c[1]["dias_ate_a_admissao"],
    ) == (1, 20240110, 5)
    assert c[2]["admitida"] and (c[2]["contrato_trabalho_id"], c[2]["dias_ate_a_admissao"]) == (
        2,
        12,
    )
    assert (
        c[1]["dias_no_funil"],
        c[1]["entrevistas"],
        c[1]["chegou_a_entrevista_no_cliente"],
        c[1]["chegou_a_aprovacao"],
    ) == (16, 1, False, True)
    assert (
        c[2]["entrevistas"],
        c[2]["entrevistas_no_cliente"],
        c[2]["chegou_a_entrevista_no_cliente"],
    ) == (2, 1, True)
    assert c[3]["reprovada"] and c[3]["motivo_id"] == 1 and not c[3]["chegou_a_entrevista_interna"]
    assert c[4]["em_andamento"] and (c[4]["data_conclusao_id"], c[4]["dias_no_funil"]) == (0, 33)
    assert (
        c[5]["aprovada"]
        and not c[5]["admitida"]
        and c[5]["aprovada_sem_admissao"]
        and not c[5]["aguardando_admissao"]
    )
    assert (c[5]["faltas_a_entrevista"], c[5]["contrato_trabalho_id"], c[5]["fonte"]) == (
        1,
        0,
        "INDICACAO",
    )
    assert {x["filial_id"] for x in c.values()} == {1} and {
        x["cliente_id"] for x in c.values()
    } == {1}


def test_a_alocacao_e_o_vinculo_contam_os_mesmos_dias(gold: duckdb.DuckDBPyConnection) -> None:
    a = {x["alocacao_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_alocacao")}
    assert a[1]["encerrada"] and (
        a[1]["dias_alocada"],
        a[1]["motivo_fim_id"],
        a[1]["data_fim_id"],
    ) == (37, 1, 20240215)
    assert (
        not a[1]["em_substituicao"]
        and a[2]["em_substituicao"]
        and a[2]["substituindo_alocacao_id"] == 1
    )
    assert not a[2]["encerrada"] and (
        a[2]["dias_alocada"],
        a[2]["data_fim_id"],
        a[2]["motivo_fim_id"],
    ) == (51, 0, 0)
    assert {x["efetivada_pelo_cliente"] for x in a.values()} == {False}
    assert {
        (x["contrato_id"], x["cliente_id"], x["filial_id"], x["funcao_id"], x["tipo_de_vinculo"])
        for x in a.values()
    } == {(1, 1, 1, 1, "TEMPORARIO")}

    v = {x["contrato_trabalho_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_vinculo")}
    assert (
        v[1]["desligado"]
        and v[1]["saiu_em_ate_90_dias"]
        and (v[1]["dias_de_vinculo"], v[1]["tipo_de_desligamento"]) == (36, "VOLUNTARIO")
    )
    assert (v[1]["motivo_desligamento_id"], v[1]["valor_rescisao"], v[1]["prorrogacoes"]) == (
        1,
        Decimal("800.00"),
        0,
    )
    assert (
        not v[2]["desligado"] and not v[2]["saiu_em_ate_90_dias"] and v[2]["dias_de_vinculo"] == 50
    )
    assert (
        v[2]["prorrogacoes"],
        v[2]["dias_prorrogados"],
        v[2]["data_termino_previsto_id"],
        v[2]["data_rescisao_id"],
    ) == (1, 90, 20240419, 0)
    assert v[2]["tipo_de_desligamento"] is None and v[2]["valor_rescisao"] is None


# ------------------------------------------------------------------ a conferência


def test_a_conferencia_reprova_o_grao_quebrado(gold: duckdb.DuckDBPyConnection) -> None:
    gold.execute(
        "INSERT INTO gold.fato_posto_mes SELECT * FROM gold.fato_posto_mes WHERE mes_id = 202401"
    )
    resultado = construcao.conferir(gold, modelo.FATO_POSTO_MES, "gold.fato_posto_mes")
    assert any("grão quebrado: 1 chaves" in p for p in resultado.problemas)


def test_a_conferencia_reprova_a_chave_que_nao_existe_na_dimensao(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    gold.execute("UPDATE gold.fato_custo_pessoal SET colaborador_id = 99 WHERE id = 1")
    resultado = construcao.conferir(gold, modelo.FATO_CUSTO_PESSOAL, "gold.fato_custo_pessoal")
    assert resultado.problemas == ["1 linhas com colaborador_id fora de dim_colaborador"]


def test_a_conferencia_reprova_o_total_que_nao_se_conserva(gold: duckdb.DuckDBPyConnection) -> None:
    gold.execute(
        "UPDATE gold.fato_faturamento SET valor_impostos = valor_impostos + 0.01 WHERE fatura_item_id = 1"
    )
    resultado = construcao.conferir(gold, modelo.FATO_FATURAMENTO, "gold.fato_faturamento")
    assert resultado.problemas == ["impostos não se conserva: gold 15.0200, silver 15.0100"]
    assert resultado.conservado["faturas"] == "2"


def test_a_conferencia_reprova_identidade_na_dimensao_de_pessoa(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    gold.execute("ALTER TABLE gold.dim_colaborador ADD COLUMN matricula VARCHAR")
    gold.execute("DELETE FROM gold.dim_colaborador WHERE id = 0")
    resultado = construcao.conferir(gold, modelo.DIM_COLABORADOR, "gold.dim_colaborador")
    assert len(resultado.problemas) == 2 and "['matricula']" in resultado.problemas[1]


# ------------------------------------------------------------------ o lake


def test_publicar_grava_confere_e_so_entao_publica(lake: Lake) -> None:
    con = _abrir(lake)
    for t in modelo.TABELAS:
        resultado = construcao.publicar(con, lake, t)
        assert resultado.aprovada, (t.nome, resultado.problemas)
    assert Path(construcao.pasta(lake, "dim_posto"), "dim_posto.parquet").exists()
    assert sorted(p.name for p in Path(construcao.pasta(lake, "fato_posto_mes")).iterdir()) == [
        "ano=2024.parquet"
    ]
    sobras = [p for p in Path(lake.caminho("gold", construcao.EM_CONFERENCIA)).rglob("*.parquet")]
    assert sobras == []
    lido = con.execute(
        f"SELECT sum(margem) FROM {construcao.leitura(lake, 'fato_posto_mes')}"
    ).fetchall()[0][0]  # noqa: S608
    assert lido == Decimal("15.00")  # 100 de receita menos 85 de custo


def test_a_reprovada_fica_na_conferencia_e_a_publicada_continua(
    lake: Lake, monkeypatch: pytest.MonkeyPatch
) -> None:
    con = _abrir(lake)
    for t in modelo.TABELAS:
        construcao.publicar(con, lake, t)
    publicada = Path(construcao.pasta(lake, "fato_custo_pessoal"), "ano=2024.parquet")
    antes = publicada.read_bytes()
    quebrada = modelo.Tabela(
        "fato_custo_pessoal",
        modelo.FATO_CUSTO_PESSOAL.sql.replace(
            "c.custo_total,", "c.custo_total + 1 AS custo_total,"
        ),
        referencias=modelo.FATO_CUSTO_PESSOAL.referencias,
        particao="ano",
        conservacoes=modelo.FATO_CUSTO_PESSOAL.conservacoes,
    )
    resultado = construcao.publicar(con, lake, quebrada)
    assert [p.split(":")[0] for p in resultado.problemas] == ["custo total não se conserva"]
    assert publicada.read_bytes() == antes
    assert Path(
        construcao.pasta(lake, "fato_custo_pessoal", em_conferencia=True), "ano=2024.parquet"
    ).exists()


def test_o_ano_que_deixou_de_existir_sai_do_publicado(lake: Lake) -> None:
    con = _abrir(lake)
    for t in modelo.TABELAS:
        construcao.publicar(con, lake, t)
    velho = Path(construcao.pasta(lake, "fato_custo_pessoal"), "ano=2019.parquet")
    velho.write_bytes(
        Path(construcao.pasta(lake, "fato_custo_pessoal"), "ano=2024.parquet").read_bytes()
    )
    assert construcao.publicar(con, lake, modelo.FATO_CUSTO_PESSOAL).aprovada
    assert not velho.exists()


# ------------------------------------------------------------------ o Dagster


def test_um_asset_por_tabela_com_a_linhagem_do_modelo() -> None:
    chaves = {a.key.to_user_string() for a in orquestracao.ASSETS}
    assert chaves == {f"gold/{t.nome}" for t in modelo.TABELAS}
    (posto_mes,) = [a for a in orquestracao.ASSETS if a.key.path == ["gold", "fato_posto_mes"]]
    dependencias = {k.to_user_string() for k in posto_mes.dependency_keys}
    assert {
        "gold/dim_posto",
        "gold/dim_mes",
        "silver/pessoas/alocacao",
        "silver/folha/rateio_custo",
        "silver/ponto/apontamento",
    } <= dependencias
    conhecidas = {
        k.to_user_string() for k in definicoes.defs.resolve_asset_graph().get_all_asset_keys()
    }
    for a in orquestracao.ASSETS:
        assert {k.to_user_string() for k in a.dependency_keys} <= conhecidas, a.key


def test_o_job_da_gold_esta_nas_definicoes() -> None:
    job = definicoes.defs.resolve_job_def("construir_gold")
    assert {k.to_user_string() for k in job.asset_layer.executable_asset_keys} == {
        f"gold/{t.nome}" for t in modelo.TABELAS
    }
