"""As etiquetas LGPD da DDL como dado: que coluna é pessoal, que coluna é sensível.

A DDL etiqueta no comentário de cada coluna o que a LGPD alcança: `[LGPD:pessoal]` (identifica
ou contata uma pessoa, ou é remuneração individual) e `[LGPD:sensivel]` (saúde). O dicionário
de dados (`staging.dicionario`) lê essas etiquetas da `information_schema` da réplica para
documentar; este módulo lê as mesmas etiquetas direto dos arquivos da DDL, sem banco, para o
pipeline **agir**: a bronze aceita nulo nessas colunas (o descarte as apaga), a silver as
pseudonimiza, e o job de descarte sabe o que apagar.

Uma fonte só para as três coisas: coluna pessoal nova na DDL, com a etiqueta, entra nas três
sozinha, e o teste da pseudonimização reprova até alguém decidir o que fazer com ela.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from rh_fictalent.staging.gatilhos import DDL

PESSOAL = "pessoal"
SENSIVEL = "sensivel"

_TABELA = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) ENCRYPTION", re.S)
_COLUNA = re.compile(r"^\s+(\w+)\s+[A-Z]+[^\n]*?COMMENT '([^']*)'", re.M)
_ETIQUETA = re.compile(r"\[LGPD:(pessoal|sensivel)\]")


@cache
def colunas(pasta: Path = DDL) -> dict[str, dict[str, str]]:
    """Por tabela (`modulo.tabela`), as colunas etiquetadas e a classe de cada uma."""
    etiquetadas: dict[str, dict[str, str]] = {}
    for arquivo in sorted(pasta.glob("*.sql")):
        texto = arquivo.read_text(encoding="utf-8")
        modulo = re.search(r"^USE (\w+);", texto, re.M)
        if modulo is None:
            continue
        for tabela, corpo in _TABELA.findall(texto):
            for coluna, comentario in _COLUNA.findall(corpo):
                classe = _ETIQUETA.search(comentario)
                if classe:
                    nome = f"{modulo.group(1)}.{tabela}"
                    etiquetadas.setdefault(nome, {})[coluna] = classe.group(1)
    return etiquetadas


# Como reconhecer, na bronze, a linha cujo dado pessoal foi descartado por retenção, sem coluna
# nova: o nome do candidato é obrigatório na réplica (NOT NULL), então nome nulo na bronze só
# acontece por descarte. As regras de qualidade não avaliam essa linha (o CPF que nós apagamos
# não é "candidato sem CPF"), e a silver a identifica em `pessoal_descartado`.
DESCARTADA = {"ats.candidato": "{a}.nome IS NULL"}


def descartada(tabela: str, apelido: str) -> str | None:
    """A condição SQL de linha descartada na tabela, sobre o apelido dado; `None` se não há."""
    condicao = DESCARTADA.get(tabela)
    return condicao.format(a=apelido) if condicao else None


def da_tabela(modulo: str, tabela: str) -> dict[str, str]:
    """As colunas etiquetadas de uma tabela (vazio se ela não tem dado pessoal)."""
    return colunas().get(f"{modulo}.{tabela}", {})
