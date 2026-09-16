"""Regras da DDL da réplica, conferidas sem banco: contagem por módulo e convenções.

Quem adicionar uma tabela sem id, sem carimbos, sem índice na marca d agua, sem
comentário, com ENUM ou com coluna _id sem chave estrangeira quebra a esteira.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from rh_fictalent.staging.gatilhos import gerar_sql

RAIZ = Path(__file__).resolve().parents[1]
DDL = RAIZ / "staging" / "ddl"
ESPERADO = {
    "cadastro": 12,
    "comercial": 8,
    "ats": 9,
    "pessoas": 8,
    "ponto": 5,
    "folha": 7,
    "financeiro": 10,
    "treinamento": 5,
    "sst": 6,
    "seguranca": 5,
    "meta": 1,
}
SO_INSERE = {"meta"}  # trilha de exclusões: sem atualizado_em de propósito
CRIA_TABELA = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) COMMENT='([^']*)';", re.S)


def _arquivo(modulo: str) -> Path:
    candidatos = sorted(DDL.glob(f"*_{modulo}.sql"))
    assert len(candidatos) == 1, f"arquivo de {modulo}: {candidatos}"
    return candidatos[0]


def _tabelas(modulo: str) -> list[tuple[str, str, str]]:
    return CRIA_TABELA.findall(_arquivo(modulo).read_text(encoding="utf-8"))


def _casos() -> list[tuple[str, str, str, str]]:
    return [
        (m, nome, corpo, comentario) for m in ESPERADO for nome, corpo, comentario in _tabelas(m)
    ]


def test_todo_modulo_nasce_em_00_databases() -> None:
    texto = (DDL / "00_databases.sql").read_text(encoding="utf-8")
    faltando = [m for m in ESPERADO if f"CREATE DATABASE IF NOT EXISTS {m} " not in texto]
    assert not faltando, faltando


@pytest.mark.parametrize("modulo", list(ESPERADO))
def test_contagem_de_tabelas_por_modulo(modulo: str) -> None:
    assert f"USE {modulo};" in _arquivo(modulo).read_text(encoding="utf-8")
    assert len(_tabelas(modulo)) == ESPERADO[modulo], modulo


def test_total_de_tabelas() -> None:
    assert sum(len(_tabelas(m)) for m in ESPERADO) == 76


@pytest.mark.parametrize(
    ("modulo", "nome", "corpo", "comentario"),
    _casos(),
    ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "",
)
def test_convencoes_de_toda_tabela(modulo: str, nome: str, corpo: str, comentario: str) -> None:
    assert "id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT" in corpo or re.search(
        r"^\s+id\s+BIGINT UNSIGNED\s+NOT NULL AUTO_INCREMENT", corpo, re.M
    ), f"{modulo}.{nome} sem id padrão"
    assert "PRIMARY KEY (id)" in corpo, f"{modulo}.{nome}"
    assert re.search(r"^\s+criado_em\s+DATETIME\(6\)", corpo, re.M), (
        f"{modulo}.{nome} sem criado_em"
    )
    assert "ENUM(" not in corpo.upper(), f"{modulo}.{nome} usa ENUM; a regra é CHECK"
    assert comentario.strip(), f"{modulo}.{nome} sem comentário de tabela"
    if modulo not in SO_INSERE:
        assert "ON UPDATE CURRENT_TIMESTAMP(6)" in corpo, (
            f"{modulo}.{nome} sem atualizado_em automático"
        )
        assert f"KEY ix_{nome}_atualizado_em (atualizado_em)" in corpo, (
            f"{modulo}.{nome} sem índice na marca d agua"
        )


@pytest.mark.parametrize(
    ("modulo", "nome", "corpo", "comentario"),
    _casos(),
    ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "",
)
def test_toda_coluna_id_tem_chave_estrangeira(
    modulo: str, nome: str, corpo: str, comentario: str
) -> None:
    declaradas = set(re.findall(r"FOREIGN KEY \((\w+)\)", corpo))
    for linha in corpo.splitlines():
        m = re.match(r"^\s+(\w+_id)\s", linha)
        if not m:
            continue
        coluna = m.group(1)
        adiada = "FK declarada em" in linha or "[sem FK]" in linha
        assert coluna in declaradas or adiada, (
            f"{modulo}.{nome}.{coluna} sem FOREIGN KEY nem justificativa"
        )


def test_ciclos_fechados_por_alter_idempotente() -> None:
    comercial = _arquivo("comercial").read_text(encoding="utf-8")
    seguranca = _arquivo("seguranca").read_text(encoding="utf-8")
    assert (
        "fk_centro_custo_contrato" in comercial
        and "information_schema.TABLE_CONSTRAINTS" in comercial
    )
    assert (
        "fk_entrevista_usuario" in seguranca and "information_schema.TABLE_CONSTRAINTS" in seguranca
    )


def test_gatilhos_de_exclusao_gerados_e_atualizados() -> None:
    texto = (DDL / "12_gatilhos_exclusao.sql").read_text(encoding="utf-8")
    assert texto == gerar_sql(), (
        "arquivo diverge do gerador: python -m rh_fictalent.staging.gatilhos"
    )
    assert texto.count("CREATE TRIGGER IF NOT EXISTS") == 75
    assert texto.count("BEFORE DELETE ON") == 75
    assert "ON meta." not in texto, "a trilha não vigia a si mesma"


def test_dado_pessoal_etiquetado() -> None:
    texto = "\n".join(_arquivo(m).read_text(encoding="utf-8") for m in ESPERADO)
    assert texto.count("[LGPD:pessoal]") >= 20
    assert texto.count("[LGPD:sensivel]") >= 4
    pessoas = _arquivo("pessoas").read_text(encoding="utf-8")
    assert re.search(r"cpf\s+CHAR\(11\)\s+NOT NULL COMMENT '\[LGPD:pessoal\]", pessoas)
