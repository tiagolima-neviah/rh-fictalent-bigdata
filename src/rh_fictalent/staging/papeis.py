"""Gera staging/ddl/13_papeis.sql: os papéis de banco da réplica e o que cada um pode.

Três funções conectam na réplica, e o direito de cada uma nasce da própria DDL:

- papel_pipeline    só leitura em tudo, inclusive meta (a trilha de exclusões);
- papel_relatorios  leitura SEM dado pessoal: nas tabelas com coluna etiquetada
                    [LGPD:...] o GRANT é coluna a coluna, deixando as etiquetadas de fora;
- papel_replicador  escreve o negócio (INSERT, UPDATE, DELETE, SELECT), nunca meta,
                    nunca DDL, nunca GRANT.

Os usuários (com senha do .env) são criados por 14_usuarios.sh e recebem estes papéis.
O arquivo gerado é versionado; um teste garante que ele bate com o gerador.

Uso:  python -m rh_fictalent.staging.papeis
"""

from __future__ import annotations

import re
from pathlib import Path

from rh_fictalent.staging.gatilhos import DDL, MODULOS_DE_NEGOCIO, RAIZ

DESTINO = DDL / "13_papeis.sql"
PAPEIS = ("papel_pipeline", "papel_relatorios", "papel_replicador")
CRIA_TABELA = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) COMMENT=", re.S)
COLUNA = re.compile(r"^  (\w+)\s+\S")
NAO_E_COLUNA = {"PRIMARY", "UNIQUE", "KEY", "CONSTRAINT"}
CABECALHO = """\
-- Papéis da réplica · o que cada função pode fazer, derivado da DDL.
--
-- ARQUIVO GERADO por src/rh_fictalent/staging/papeis.py.
-- Não edite à mão: rode  python -m rh_fictalent.staging.papeis  e versione o resultado.
--
--   papel_pipeline    só leitura em tudo, inclusive meta
--   papel_relatorios  leitura sem dado pessoal (coluna a coluna onde há etiqueta LGPD)
--   papel_replicador  escreve o negócio; nunca meta, nunca DDL, nunca GRANT
--
-- Os usuários que recebem estes papéis (com senha do .env) vêm de 14_usuarios.sh.
-- GRANT é idempotente: repetir não muda nada.

CREATE ROLE IF NOT EXISTS papel_pipeline, papel_relatorios, papel_replicador;
"""


def colunas_por_tabela(ddl: Path = DDL) -> dict[str, list[tuple[str, list[str], list[str]]]]:
    """Para cada módulo: (tabela, colunas sem etiqueta, colunas com etiqueta LGPD)."""
    saida: dict[str, list[tuple[str, list[str], list[str]]]] = {}
    for modulo in MODULOS_DE_NEGOCIO:
        (arquivo,) = sorted(ddl.glob(f"*_{modulo}.sql"))
        tabelas: list[tuple[str, list[str], list[str]]] = []
        for nome, corpo in CRIA_TABELA.findall(arquivo.read_text(encoding="utf-8")):
            livres: list[str] = []
            pessoais: list[str] = []
            for linha in corpo.splitlines():
                m = COLUNA.match(linha)
                if not m or m.group(1) in NAO_E_COLUNA:
                    continue
                (pessoais if "[LGPD:" in linha else livres).append(m.group(1))
            tabelas.append((nome, livres, pessoais))
        saida[modulo] = tabelas
    return saida


def gerar_sql(ddl: Path = DDL) -> str:
    partes = [CABECALHO]
    partes.append("\n-- pipeline: só leitura, inclusive a trilha de exclusões\n")
    for modulo in (*MODULOS_DE_NEGOCIO, "meta"):
        partes.append(f"GRANT SELECT ON {modulo}.* TO papel_pipeline;\n")
    partes.append(
        "\n-- replicador: escreve o negócio; meta fica de fora "
        "(o gatilho grava lá por conta própria)\n"
    )
    for modulo in MODULOS_DE_NEGOCIO:
        partes.append(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {modulo}.* TO papel_replicador;\n")
    partes.append("\n-- relatórios do cliente: leitura sem dado pessoal\n")
    for modulo, tabelas in colunas_por_tabela(ddl).items():
        partes.append(f"\n-- {modulo}\n")
        for nome, livres, pessoais in tabelas:
            if pessoais:
                partes.append(
                    f"GRANT SELECT ({', '.join(livres)}) ON {modulo}.{nome} TO papel_relatorios;"
                    f"  -- fora: {', '.join(pessoais)}\n"
                )
            else:
                partes.append(f"GRANT SELECT ON {modulo}.{nome} TO papel_relatorios;\n")
    return "".join(partes)


def main() -> None:
    DESTINO.write_text(gerar_sql(), encoding="utf-8", newline="\n")
    tabelas = colunas_por_tabela()
    com_etiqueta = sum(1 for t in tabelas.values() for _, _, pessoais in t if pessoais)
    print(
        f"{DESTINO.relative_to(RAIZ)}: {len(PAPEIS)} papéis, "
        f"{com_etiqueta} tabelas com GRANT coluna a coluna"
    )


if __name__ == "__main__":
    main()
