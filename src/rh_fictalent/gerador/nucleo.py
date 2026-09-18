"""O núcleo do gerador: semente, relógio, o conjunto de tabelas e a escrita na réplica.

O gerador faz o papel do sistema do cliente (e da replicação) escrevendo na réplica MySQL como
o usuário `replicador`. Três regras valem para todas as etapas:

- determinismo: a semente é fixa (SEMENTE) e cada etapa tira o seu gerador aleatório dela
  pelo nome, então rodar duas vezes produz a mesma base e mexer numa etapa não embaralha outra;
- os ids são atribuídos pelo gerador (1, 2, 3...), não pelo AUTO_INCREMENT, para que as chaves
  estrangeiras sejam conhecidas antes de gravar e iguais em toda execução;
- criado_em e atualizado_em são escritos com o instante histórico do fato (uma filial aberta
  em 2019 nasce em 2019), porque é por eles que a carga incremental vai andar.

Cada etapa é uma função pura gerar() -> Tabelas, testável sem banco; gravar é um passo à parte.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd
import pymysql

SEMENTE = 20260910
INICIO = date(2018, 1, 2)  # o primeiro dia útil da história
FIM = datetime(2026, 9, 10, 8, 0)  # o instante da primeira reunião com a Neviah
LOTE = 5000

# "schema.tabela" -> linhas, na ordem em que podem ser inseridas (pais antes de filhos)
Tabelas = dict[str, pd.DataFrame]


class BaseNaoVazia(RuntimeError):
    """A réplica já tem dado nas tabelas da etapa: gravar por cima quebraria o determinismo."""


def aleatorio(etapa: str) -> np.random.Generator:
    """O gerador aleatório de uma etapa: derivado da semente e do nome, independente das outras."""
    resumo = hashlib.sha256(f"{SEMENTE}:{etapa}".encode()).digest()
    return np.random.default_rng(int.from_bytes(resumo[:8], "big"))


def instante(dia: date, hora: int = 8, minuto: int = 0) -> datetime:
    return datetime.combine(dia, time(hora, minuto))


def primeiro_dia_util(ano: int, mes: int = 1, dia: int = 1) -> date:
    """O primeiro dia de semana a partir da data (feriado fica por conta de quem chama)."""
    candidato = date(ano, mes, dia)
    while candidato.weekday() >= 5:
        candidato += timedelta(days=1)
    return candidato


def tabela(linhas: list[dict[str, Any]]) -> pd.DataFrame:
    """Um DataFrame com id sequencial a partir de 1, na ordem das linhas."""
    quadro = pd.DataFrame(linhas, dtype=object)  # tipos nativos: None, int, date, datetime
    quadro.insert(0, "id", range(1, len(quadro) + 1))
    return quadro


def valores(quadro: pd.DataFrame) -> list[list[Any]]:
    """As linhas como tipos nativos do Python (nulo vira None), prontas para o driver."""
    return quadro.astype(object).where(quadro.notna(), None).to_numpy().tolist()


def assinatura(tabelas: Tabelas) -> str:
    """A impressão digital da base gerada: igual em toda execução, ou o determinismo quebrou."""
    resumo = hashlib.sha256()
    for nome, quadro in tabelas.items():
        resumo.update(nome.encode())
        resumo.update(quadro.to_csv(index=False, lineterminator="\n").encode())
    return resumo.hexdigest()


@dataclass(frozen=True)
class Replica:
    """A réplica MySQL vista por quem escreve nela (replicador) ou a administra (root)."""

    host: str
    porta: int
    usuario: str
    senha: str

    def conectar(self) -> pymysql.connections.Connection[Any]:
        return pymysql.connect(
            host=self.host,
            port=self.porta,
            user=self.usuario,
            password=self.senha,
            charset="utf8mb4",
            autocommit=False,
        )

    def contar(self, nomes: list[str]) -> dict[str, int]:
        alvos = {nome: _identificador(nome) for nome in nomes}  # confere antes de conectar
        con = self.conectar()
        try:
            with con.cursor() as cur:
                contagem = {}
                for nome, alvo in alvos.items():
                    cur.execute(f"SELECT COUNT(*) FROM {alvo}")  # noqa: S608 # nosec B608
                    contagem[nome] = int(cur.fetchone()[0])
                return contagem
        finally:
            con.close()

    def gravar(self, tabelas: Tabelas) -> dict[str, int]:
        """Insere tudo numa transação só; recusa se alguma tabela da etapa já tiver linhas."""
        ocupadas = {n: q for n, q in self.contar(list(tabelas)).items() if q}
        if ocupadas:
            raise BaseNaoVazia(f"tabelas com dado: {ocupadas}; use --zerar para recomeçar")
        con = self.conectar()
        try:
            with con.cursor() as cur:
                for nome, quadro in tabelas.items():
                    colunas = ", ".join(f"`{c}`" for c in quadro.columns)
                    marcas = ", ".join(["%s"] * len(quadro.columns))
                    sql = f"INSERT INTO {_identificador(nome)} ({colunas}) VALUES ({marcas})"  # noqa: S608 # nosec B608
                    linhas = valores(quadro)
                    for i in range(0, len(linhas), LOTE):
                        cur.executemany(sql, linhas[i : i + LOTE])
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()
        return {nome: len(quadro) for nome, quadro in tabelas.items()}

    def ler(self, nome: str, colunas: list[str]) -> list[tuple[Any, ...]]:
        con = self.conectar()
        try:
            with con.cursor() as cur:
                lista = ", ".join(f"`{c}`" for c in colunas)
                cur.execute(f"SELECT {lista} FROM {_identificador(nome)} ORDER BY id")  # noqa: S608 # nosec B608
                return list(cur.fetchall())
        finally:
            con.close()

    def zerar(self) -> int:
        """Esvazia a réplica inteira (negócio e trilha de exclusões). Só o root consegue: é
        ato de administração, o `replicador` não tem TRUNCATE. Devolve quantas tabelas zerou."""
        con = self.conectar()
        try:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_type = 'BASE TABLE' AND table_schema NOT IN "
                    "('mysql', 'sys', 'information_schema', 'performance_schema')"
                )
                alvos = [f"{schema}.{nome}" for schema, nome in cur.fetchall()]
                cur.execute("SET FOREIGN_KEY_CHECKS = 0")
                for alvo in alvos:
                    cur.execute(f"TRUNCATE TABLE {_identificador(alvo)}")
                cur.execute("SET FOREIGN_KEY_CHECKS = 1")
            con.commit()
            return len(alvos)
        finally:
            con.close()


def replica_do_ambiente(usuario: str = "replicador") -> Replica:
    """A conexão a partir do ambiente (.env): replicador para escrever, root para zerar."""
    variavel = "STAGING_ROOT_PASSWORD" if usuario == "root" else f"{usuario.upper()}_PASSWORD"
    senha = os.environ.get(variavel)
    if not senha:
        raise RuntimeError(f"defina {variavel} no .env")
    return Replica(
        host=os.environ.get("STAGING_HOST") or "127.0.0.1",
        porta=int(os.environ.get("STAGING_PORT") or "3316"),
        usuario=usuario,
        senha=senha,
    )


def _identificador(nome: str) -> str:
    """`schema`.`tabela`, só com letras, dígitos e sublinhado: nome nunca vem de fora."""
    partes = nome.split(".")
    if len(partes) != 2 or not all(p.replace("_", "").isalnum() for p in partes):
        raise ValueError(f"nome de tabela inválido: {nome!r}")
    return ".".join(f"`{p}`" for p in partes)
