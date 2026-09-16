"""Gera docs/dicionario/README.md a partir da information_schema da réplica.

O dicionário não é escrito à mão: é o banco descrevendo a si mesmo. Tipo, nulidade, chave,
referência de chave estrangeira, padrão e comentário vêm da information_schema; a
classificação LGPD vem das etiquetas nos comentários ([LGPD:pessoal], [LGPD:sensivel] na
coluna; [LGPD:publica] na tabela de referência). O que não tem etiqueta é "interna".

Uso:  python -m rh_fictalent.staging.dicionario      (réplica de pé e .env presente)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import pymysql
from dotenv import dotenv_values

from rh_fictalent.staging.gatilhos import MODULOS_DE_NEGOCIO, RAIZ

DESTINO = RAIZ / "docs" / "dicionario" / "README.md"
MODULOS = (*MODULOS_DE_NEGOCIO, "meta")
ETIQUETA = re.compile(r"\[LGPD:(pessoal|sensivel|publica)\]\s*")
NOME_DA_CLASSE = {
    "sensivel": "pessoal sensível",
    "pessoal": "pessoal",
    "publica": "pública",
    "interna": "interna",
}
ROTULO_DA_CHAVE = {"PRIMARY KEY": "PK", "UNIQUE": "único", "FOREIGN KEY": "FK"}
ABERTURA = (
    '<a id="topo"></a>\n\n'
    "# Dicionário de dados · a réplica descrevendo a si mesma\n\n"
    "[Home](../../README.md) | [Modelo de Dados](../04_modelo_dados_staging.md)\n\n"
    "> **Arquivo gerado** por `src/rh_fictalent/staging/dicionario.py` a partir da "
    "`information_schema` da réplica MySQL. Não edite à mão: rode "
    "`python -m rh_fictalent.staging.dicionario` com a réplica de pé e versione o resultado. "
    "Um teste de integração confere que este arquivo é igual ao que o banco produz.\n\n"
    "## Classificação de sensibilidade\n\n"
    "Toda coluna carrega uma classe, derivada das etiquetas nos comentários da DDL: "
    "**pessoal sensível** (saúde: CID, resultado de exame, acidente), **pessoal** (identifica "
    "ou contata uma pessoa, ou é remuneração individual), **pública** (referência de domínio "
    "público: município, feriado, CBO, tributo) e **interna** (todo o resto). A classe "
    "alimenta o controle de acesso da réplica (o `GRANT` de coluna dos relatórios do cliente "
    "exclui pessoal e pessoal sensível) e a pseudonimização na silver.\n\n"
    "| classe | colunas |\n|---|---|\n"
)
INVENTARIO = (
    "## Inventário de dado pessoal\n\n"
    "As colunas que a LGPD alcança, por módulo. É a lista que o encarregado de dados pede "
    "primeiro.\n\n"
    "| módulo | tabela | coluna | classe | descrição |\n|---|---|---|---|---|\n"
)
CABECALHO_COLUNAS = (
    "| coluna | tipo | nulo | chave | padrão | classe | descrição |\n"
    "|---|---|---|---|---|---|---|\n"
)


def _conectar() -> pymysql.connections.Connection[Any]:
    env = dotenv_values(RAIZ / ".env")
    return pymysql.connect(
        host="127.0.0.1",
        port=int(env.get("STAGING_PORT") or 3316),
        user="root",
        password=env.get("STAGING_ROOT_PASSWORD") or "",
        database="information_schema",
        charset="utf8mb4",
    )


def _linhas(
    con: pymysql.connections.Connection[Any], sql: str, *args: Any
) -> list[tuple[Any, ...]]:
    with con.cursor() as cur:
        cur.execute(sql, args or None)
        return list(cur.fetchall())


def _classe(comentario: str, classe_da_tabela: str) -> tuple[str, str]:
    """Devolve (classe, comentário sem a etiqueta)."""
    m = ETIQUETA.search(comentario)
    if m:
        return m.group(1), ETIQUETA.sub("", comentario).strip()
    classe = "publica" if classe_da_tabela == "publica" else "interna"
    return classe, comentario.strip()


def _chaves(con: pymysql.connections.Connection[Any]) -> dict[tuple[str, str, str], list[str]]:
    chaves: dict[tuple[str, str, str], list[str]] = {}
    for esquema, tabela, coluna, tipo, ref_esquema, ref_tabela in _linhas(
        con,
        "SELECT k.table_schema, k.table_name, k.column_name, t.constraint_type, "
        "k.referenced_table_schema, k.referenced_table_name "
        "FROM key_column_usage k JOIN table_constraints t "
        "ON t.constraint_schema = k.constraint_schema AND t.constraint_name = k.constraint_name "
        "AND t.table_name = k.table_name WHERE k.table_schema IN %s",
        MODULOS,
    ):
        rotulo = ROTULO_DA_CHAVE[tipo]
        if tipo == "FOREIGN KEY":
            rotulo = f"FK → {ref_esquema}.{ref_tabela}"
        chaves.setdefault((esquema, tabela, coluna), []).append(rotulo)
    return chaves


def ler_replica(con: pymysql.connections.Connection[Any]) -> dict[str, list[dict[str, Any]]]:
    """Para cada módulo, a lista de tabelas com as suas colunas, já classificadas."""
    chaves = _chaves(con)
    saida: dict[str, list[dict[str, Any]]] = {m: [] for m in MODULOS}
    for esquema, tabela, comentario_tabela in _linhas(
        con,
        "SELECT table_schema, table_name, table_comment FROM tables "
        "WHERE table_type = 'BASE TABLE' AND table_schema IN %s "
        "ORDER BY table_schema, table_name",
        MODULOS,
    ):
        classe_tabela, comentario_tabela = _classe(comentario_tabela, "")
        colunas = []
        for coluna, tipo, nulo, padrao, comentario in _linhas(
            con,
            "SELECT column_name, column_type, is_nullable, column_default, column_comment "
            "FROM columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
            esquema,
            tabela,
        ):
            classe, descricao = _classe(comentario, classe_tabela)
            colunas.append(
                {
                    "coluna": coluna,
                    "tipo": tipo,
                    "nulo": "sim" if nulo == "YES" else "não",
                    "chave": ", ".join(sorted(chaves.get((esquema, tabela, coluna), []))),
                    "padrao": "" if padrao is None else str(padrao),
                    "classe": classe,
                    "descricao": descricao,
                }
            )
        saida[esquema].append(
            {
                "tabela": tabela,
                "comentario": comentario_tabela,
                "classe": classe_tabela,
                "colunas": colunas,
            }
        )
    return saida


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def gerar_markdown(dados: dict[str, list[dict[str, Any]]]) -> str:
    contagem: Counter[str] = Counter()
    inventario: list[tuple[str, str, str, str, str]] = []
    total_tabelas = 0
    for modulo, tabelas in dados.items():
        for t in tabelas:
            total_tabelas += 1
            for c in t["colunas"]:
                contagem[c["classe"]] += 1
                if c["classe"] in ("pessoal", "sensivel"):
                    inventario.append(
                        (modulo, t["tabela"], c["coluna"], c["classe"], c["descricao"])
                    )

    partes = [ABERTURA]
    for chave in ("sensivel", "pessoal", "publica", "interna"):
        partes.append(f"| {NOME_DA_CLASSE[chave]} | {contagem.get(chave, 0)} |\n")
    partes.append(f"\n{total_tabelas} tabelas, {sum(contagem.values())} colunas.\n\n")

    partes.append(INVENTARIO)
    for modulo, tabela, coluna, classe, descricao in inventario:
        partes.append(
            f"| `{modulo}` | `{tabela}` | `{coluna}` | {NOME_DA_CLASSE[classe]} | "
            f"{_celula(descricao)} |\n"
        )

    partes.append("\n## Módulos\n\n")
    for modulo, tabelas in dados.items():
        partes.append(f"- [`{modulo}`](#{modulo}) · {len(tabelas)} tabelas\n")
    for modulo, tabelas in dados.items():
        partes.append(f'\n<a id="{modulo}"></a>\n\n## `{modulo}`\n\n')
        for t in tabelas:
            marca = " · referência pública" if t["classe"] == "publica" else ""
            partes.append(f"### `{modulo}.{t['tabela']}`{marca}\n\n{_celula(t['comentario'])}\n\n")
            partes.append(CABECALHO_COLUNAS)
            for c in t["colunas"]:
                partes.append(
                    f"| `{c['coluna']}` | `{c['tipo']}` | {c['nulo']} | {_celula(c['chave'])} | "
                    f"{_celula(c['padrao'])} | {NOME_DA_CLASSE[c['classe']]} | "
                    f"{_celula(c['descricao'])} |\n"
                )
            partes.append("\n")
    partes.append("---\n\n[Início](#topo)\n")
    return "".join(partes)


def gerar() -> str:
    con = _conectar()
    try:
        return gerar_markdown(ler_replica(con))
    finally:
        con.close()


def main() -> None:
    texto = gerar()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"{DESTINO.relative_to(RAIZ)}: {texto.count(chr(10) + '### ')} tabelas")


if __name__ == "__main__":
    main()
