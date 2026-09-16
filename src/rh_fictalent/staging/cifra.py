"""Gera staging/ddl/15_cifra.sql: liga a cifra em repouso em todo database e tabela da réplica.

A DDL já nasce com ENCRYPTION='Y' em cada CREATE TABLE e DEFAULT ENCRYPTION='Y' em cada
CREATE DATABASE, então um volume novo já vem cifrado. Este arquivo existe para o volume que
já existia antes da cifra: ALTER DATABASE e ALTER TABLE reescrevem cada tablespace cifrado
com a chave mestra do keyring. Reaplicar numa réplica já cifrada é inofensivo.

Uso:  python -m rh_fictalent.staging.cifra
"""

from __future__ import annotations

from pathlib import Path

from rh_fictalent.staging.gatilhos import DDL, MODULOS_DE_NEGOCIO, RAIZ, tabelas_por_modulo

DESTINO = DDL / "15_cifra.sql"
CABECALHO = """\
-- Cifra em repouso · todo database e toda tabela da réplica com ENCRYPTION='Y'.
--
-- ARQUIVO GERADO por src/rh_fictalent/staging/cifra.py a partir da DDL dos módulos.
-- Não edite à mão: rode  python -m rh_fictalent.staging.cifra  e versione o resultado.
--
-- Serve ao volume que já existia antes da cifra (a DDL nova já nasce cifrada). Exige o
-- componente de keyring carregado (infra/mysql/mysqld.my) e reescreve cada tablespace;
-- numa réplica já cifrada é inofensivo. Detalhe: docs/04_modelo_dados_staging.md, seção 8.
"""


def gerar_sql(ddl: Path = DDL) -> str:
    partes = [CABECALHO, "\n-- databases: tabela nova nasce cifrada por padrão\n"]
    for modulo in (*MODULOS_DE_NEGOCIO, "meta"):
        partes.append(f"ALTER DATABASE {modulo} DEFAULT ENCRYPTION='Y';\n")
    for modulo, tabelas in tabelas_por_modulo(ddl).items():
        partes.append(f"\n-- {modulo}\n")
        partes.extend(f"ALTER TABLE {modulo}.{tabela} ENCRYPTION='Y';\n" for tabela in tabelas)
    partes.append("\n-- meta\nALTER TABLE meta.exclusao_auditoria ENCRYPTION='Y';\n")
    return "".join(partes)


def main() -> None:
    DESTINO.write_text(gerar_sql(), encoding="utf-8", newline="\n")
    print(f"{DESTINO.relative_to(RAIZ)}: {gerar_sql().count('ALTER TABLE')} tabelas")


if __name__ == "__main__":
    main()
