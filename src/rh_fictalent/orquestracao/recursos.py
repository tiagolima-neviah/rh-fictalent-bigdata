"""Recursos do Dagster: as três portas do pipeline, configuradas pelo ambiente.

Um recurso é um objeto que os assets recebem pronto (conexão, sistema de arquivos), em vez
de cada asset ler variáveis e abrir conexão por conta própria. Os segredos entram por
EnvVar, resolvidos na hora da execução, nunca gravados no metadado do Dagster.

Dentro do Compose os hosts são os nomes dos serviços (mysql-staging, s3, pg-dw) e as portas
internas; fora dele, 127.0.0.1 com as portas publicadas do .env. Só o ambiente muda.
"""

from __future__ import annotations

import os
from typing import Any

import dagster as dg
import psycopg
import pymysql
import s3fs


def _ambiente(nome: str, padrao: str) -> str:
    return os.environ.get(nome) or padrao


class Replica(dg.ConfigurableResource):  # type: ignore[type-arg]
    """A réplica MySQL do sistema do cliente, lida como o usuário pipeline (só leitura)."""

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
        )

    def consultar(self, sql: str, *args: Any) -> list[tuple[Any, ...]]:
        con = self.conectar()
        try:
            with con.cursor() as cur:
                cur.execute(sql, args or None)
                return list(cur.fetchall())
        finally:
            con.close()


class Lake(dg.ConfigurableResource):  # type: ignore[type-arg]
    """O lake em S3 (SeaweedFS no Compose), endereçado por s3://bucket/camada/..."""

    endpoint: str
    chave: str
    segredo: str
    bucket: str

    def sistema(self) -> s3fs.S3FileSystem:
        return s3fs.S3FileSystem(
            key=self.chave,
            secret=self.segredo,
            endpoint_url=self.endpoint,
            config_kwargs={"s3": {"addressing_style": "path"}},
        )

    def caminho(self, camada: str, *partes: str) -> str:
        return "/".join((f"s3://{self.bucket}", camada, *partes))


class Warehouse(dg.ConfigurableResource):  # type: ignore[type-arg]
    """O warehouse Postgres, destino da gold."""

    host: str
    porta: int
    banco: str
    usuario: str
    senha: str

    def conectar(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            host=self.host,
            port=self.porta,
            dbname=self.banco,
            user=self.usuario,
            password=self.senha,
        )

    def consultar(self, sql: str, *args: Any) -> list[tuple[Any, ...]]:
        with self.conectar() as con, con.cursor() as cur:
            cur.execute(sql, args or None)
            linhas = list(cur.fetchall())
            con.commit()
            return linhas


def recursos_do_ambiente() -> dict[str, Any]:
    """Os três recursos, lendo o ambiente: hosts e portas com padrão local, segredos por EnvVar."""
    return {
        "replica": Replica(
            host=_ambiente("STAGING_HOST", "127.0.0.1"),
            porta=int(_ambiente("STAGING_PORT", "3316")),
            usuario="pipeline",
            senha=dg.EnvVar("PIPELINE_PASSWORD"),
        ),
        "lake": Lake(
            endpoint=_ambiente("S3_ENDPOINT", "http://127.0.0.1:8333"),
            chave=dg.EnvVar("S3_ACCESS_KEY"),
            segredo=dg.EnvVar("S3_SECRET_KEY"),
            bucket=_ambiente("S3_BUCKET", "fictalent-lake"),
        ),
        "warehouse": Warehouse(
            host=_ambiente("DW_HOST", "127.0.0.1"),
            porta=int(_ambiente("DW_PORT", "5441")),
            banco=_ambiente("DW_DB", "dw_fictalent"),
            usuario=_ambiente("DW_ADMIN_USER", "fictalent_admin"),
            senha=dg.EnvVar("DW_ADMIN_PASSWORD"),
        ),
    }
