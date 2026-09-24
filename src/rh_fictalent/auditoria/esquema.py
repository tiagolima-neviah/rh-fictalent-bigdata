"""A DDL lida como esquema: colunas, chaves, unicidades e domínios de cada tabela.

A auditoria é às cegas quanto ao gerador, mas não quanto ao esquema: o que a DDL declara
(uma chave estrangeira, um `UNIQUE`, um `CHECK ... IN (...)`) é a regra que o sistema do
cliente promete cumprir, e conferir a bronze contra a promessa é o primeiro passo de qualquer
auditoria. Este módulo lê `staging/ddl/*.sql` e devolve essas promessas como objetos, para que
os notebooks perguntem "quais chaves esta tabela tem?" em vez de digitar a lista.

Ele lê a mesma DDL que gera os gatilhos, os papéis e a fábrica de assets: tabela nova na DDL
entra na auditoria sozinha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rh_fictalent.staging.gatilhos import DDL as PASTA_DDL

TEMPORAIS = ("DATE", "DATETIME")


@dataclass(frozen=True)
class Coluna:
    nome: str
    tipo: str  # o tipo base da DDL, sem tamanho: BIGINT, VARCHAR, DATE, DECIMAL...
    nulo: bool  # aceita NULL?


@dataclass(frozen=True)
class Chave:
    coluna: str
    esquema_alvo: str
    tabela_alvo: str

    @property
    def alvo(self) -> str:
        return f"{self.esquema_alvo}.{self.tabela_alvo}"


@dataclass(frozen=True)
class Tabela:
    esquema: str
    nome: str
    colunas: tuple[Coluna, ...]
    chaves: tuple[Chave, ...] = ()
    unicas: tuple[tuple[str, ...], ...] = ()
    dominios: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def qualificado(self) -> str:
        return f"{self.esquema}.{self.nome}"

    @property
    def nomes(self) -> list[str]:
        return [c.nome for c in self.colunas]

    @property
    def temporais(self) -> list[str]:
        return [c.nome for c in self.colunas if c.tipo in TEMPORAIS]

    def coluna(self, nome: str) -> Coluna:
        return next(c for c in self.colunas if c.nome == nome)


_CRIA = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\) ENCRYPTION", re.S)
_COLUNA = re.compile(r"^\s+(\w+)\s+([A-Z]+)(?:\([^)]*\))?(?: UNSIGNED)?\s+(NOT NULL|NULL)", re.M)
_CHAVE = re.compile(r"FOREIGN KEY \((\w+)\) REFERENCES (?:(\w+)\.)?(\w+) \(")
_UNICA = re.compile(r"UNIQUE KEY \w+ \(([^)]*)\)")
_DOMINIO = re.compile(r"CHECK \((\w+) IN \(([^)]*)\)\)")
_RESERVADAS = {"PRIMARY", "UNIQUE", "KEY", "CONSTRAINT"}


def _tabela(esquema: str, nome: str, corpo: str) -> Tabela:
    colunas = tuple(
        Coluna(n, t, nulo == "NULL")
        for n, t, nulo in _COLUNA.findall(corpo)
        if n not in _RESERVADAS
    )
    chaves = tuple(Chave(c, d or esquema, t) for c, d, t in _CHAVE.findall(corpo))
    unicas = tuple(tuple(u.replace(" ", "").split(",")) for u in _UNICA.findall(corpo))
    dominios = {
        c: tuple(v.strip().strip("'") for v in valores.split(","))
        for c, valores in _DOMINIO.findall(corpo)
    }
    return Tabela(esquema, nome, colunas, chaves, unicas, dominios)


def ler(pasta: Path = PASTA_DDL) -> dict[str, Tabela]:
    """Todas as tabelas de negócio da DDL, por nome qualificado, na ordem dos arquivos."""
    tabelas: dict[str, Tabela] = {}
    for arquivo in sorted(pasta.glob("*.sql")):
        texto = arquivo.read_text(encoding="utf-8")
        esquema = re.search(r"^USE (\w+);", texto, re.M)
        if esquema is None or esquema.group(1) == "meta":
            continue
        for nome, corpo in _CRIA.findall(texto):
            tabela = _tabela(esquema.group(1), nome, corpo)
            tabelas[tabela.qualificado] = tabela
    return tabelas


def do_modulo(esquema: str, tabelas: dict[str, Tabela] | None = None) -> list[Tabela]:
    """As tabelas de um módulo, na ordem da DDL (as de referência vêm antes das de fato)."""
    todas = tabelas if tabelas is not None else ler()
    return [t for t in todas.values() if t.esquema == esquema]
