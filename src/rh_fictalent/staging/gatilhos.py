"""Gera staging/ddl/12_gatilhos_exclusao.sql: um gatilho BEFORE DELETE por tabela de negócio.

A marca d agua (atualizado_em) encontra o que foi criado ou alterado, mas não o que foi
apagado: a linha apagada não tem mais atualizado_em para ser lida. O gatilho grava em
meta.exclusao_auditoria (database, tabela, id, usuário de banco) antes de a linha sumir,
e a carga incremental aplica a exclusão na bronze como marcação lógica.

O arquivo gerado é versionado. Um teste (tests/test_ddl.py) garante que ele é idêntico ao
que este módulo produz a partir da DDL: tabela nova sem gatilho não passa na esteira.

Uso:  python -m rh_fictalent.staging.gatilhos
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
DDL = RAIZ / "staging" / "ddl"
DESTINO = DDL / "12_gatilhos_exclusao.sql"
MODULOS_DE_NEGOCIO = (
    "cadastro",
    "comercial",
    "ats",
    "pessoas",
    "ponto",
    "folha",
    "financeiro",
    "treinamento",
    "sst",
    "seguranca",
)
CRIA_TABELA = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \(")
CABECALHO = """\
-- Trilha de exclusões · um gatilho BEFORE DELETE por tabela de negócio.
--
-- ARQUIVO GERADO por src/rh_fictalent/staging/gatilhos.py a partir da DDL dos módulos.
-- Não edite à mão: rode  python -m rh_fictalent.staging.gatilhos  e versione o resultado.
--
-- Cada gatilho grava em meta.exclusao_auditoria o database, a tabela, o id e o usuário de
-- banco, antes de a linha sumir. Corre na mesma transação do DELETE: uma exclusão barrada
-- por chave estrangeira é desfeita junto com o rastro. meta não tem gatilho (só insere).
"""


def tabelas_por_modulo(ddl: Path = DDL) -> dict[str, list[str]]:
    """Lê os nomes das tabelas de cada módulo direto dos arquivos da DDL, na ordem deles."""
    saida: dict[str, list[str]] = {}
    for modulo in MODULOS_DE_NEGOCIO:
        (arquivo,) = sorted(ddl.glob(f"*_{modulo}.sql"))
        saida[modulo] = CRIA_TABELA.findall(arquivo.read_text(encoding="utf-8"))
    return saida


def gatilho(modulo: str, tabela: str) -> str:
    return (
        f"CREATE TRIGGER IF NOT EXISTS {modulo}.trg_{tabela}_exclusao\n"
        f"  BEFORE DELETE ON {modulo}.{tabela} FOR EACH ROW\n"
        f"  INSERT INTO meta.exclusao_auditoria (banco, tabela, registro_id, usuario_banco)\n"
        f"  VALUES ('{modulo}', '{tabela}', OLD.id, CURRENT_USER());\n"
    )


def gerar_sql(ddl: Path = DDL) -> str:
    partes = [CABECALHO]
    for modulo, tabelas in tabelas_por_modulo(ddl).items():
        partes.append(f"\n-- {modulo} ({len(tabelas)} tabelas)\n")
        partes.extend(gatilho(modulo, tabela) for tabela in tabelas)
    return "".join(partes)


def main() -> None:
    DESTINO.write_text(gerar_sql(), encoding="utf-8", newline="\n")
    total = sum(len(tabelas) for tabelas in tabelas_por_modulo().values())
    print(f"{DESTINO.relative_to(RAIZ)}: {total} gatilhos")


if __name__ == "__main__":
    main()
