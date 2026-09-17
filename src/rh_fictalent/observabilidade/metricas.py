"""Métricas de execução: o que cada execução e cada passo fizeram, gravado no warehouse.

Duas tabelas no schema `observabilidade` do Postgres: `execucao` (uma linha por execução) e
`execucao_passo` (uma por passo: asset, partição, duração, status, linhas, metadados, erro).
São alimentadas pelos sensores de fim de execução (rh_fictalent.orquestracao.sensores), que
leem o event log do Dagster e gravam com upsert: reprocessar não duplica.

O Grafana lê daqui (papel grafana_leitor): execuções por dia, duração por passo, falhas,
frescor do dado. Log (rh_fictalent.observabilidade.logs) é o detalhe; isto é o resumo.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import dagster as dg

from rh_fictalent.orquestracao.recursos import Warehouse

DDL = """
CREATE SCHEMA IF NOT EXISTS observabilidade;

CREATE TABLE IF NOT EXISTS observabilidade.execucao (
  run_id         text PRIMARY KEY,
  job            text NOT NULL,
  status         text NOT NULL,
  inicio         timestamptz,
  fim            timestamptz,
  duracao_s      numeric(12,3),
  passos         integer NOT NULL DEFAULT 0,
  passos_falhos  integer NOT NULL DEFAULT 0,
  tags           jsonb,
  registrado_em  timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE observabilidade.execucao IS
  'Uma linha por execução do Dagster, gravada pelo sensor de fim de execução';

CREATE TABLE IF NOT EXISTS observabilidade.execucao_passo (
  run_id         text NOT NULL REFERENCES observabilidade.execucao (run_id) ON DELETE CASCADE,
  passo          text NOT NULL,
  asset          text,
  particao       text,
  inicio         timestamptz,
  fim            timestamptz,
  duracao_s      numeric(12,3),
  status         text NOT NULL,
  linhas         bigint,
  metadados      jsonb,
  erro           text,
  registrado_em  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, passo)
);
COMMENT ON TABLE observabilidade.execucao_passo IS
  'Uma linha por passo (asset) de cada execução: duração, status, linhas e metadados';
CREATE INDEX IF NOT EXISTS ix_execucao_passo_asset_fim
  ON observabilidade.execucao_passo (asset, fim DESC);
CREATE INDEX IF NOT EXISTS ix_execucao_job_inicio ON observabilidade.execucao (job, inicio DESC);

GRANT USAGE ON SCHEMA observabilidade TO grafana_leitor;
GRANT SELECT ON ALL TABLES IN SCHEMA observabilidade TO grafana_leitor;
ALTER DEFAULT PRIVILEGES IN SCHEMA observabilidade GRANT SELECT ON TABLES TO grafana_leitor;
"""

TIPOS_DE_PASSO = {
    dg.DagsterEventType.STEP_START,
    dg.DagsterEventType.STEP_SUCCESS,
    dg.DagsterEventType.STEP_FAILURE,
    dg.DagsterEventType.STEP_SKIPPED,
    dg.DagsterEventType.ASSET_MATERIALIZATION,
}


@dataclass
class Evento:
    """O que o resumo precisa de cada entrada do event log, já desembrulhado."""

    instante: float
    tipo: str
    passo: str
    asset: str | None = None
    particao: str | None = None
    metadados: dict[str, Any] = field(default_factory=dict)
    erro: str | None = None


@dataclass
class Passo:
    passo: str
    status: str = "EM_ANDAMENTO"
    asset: str | None = None
    particao: str | None = None
    inicio: float | None = None
    fim: float | None = None
    linhas: int | None = None
    metadados: dict[str, Any] = field(default_factory=dict)
    erro: str | None = None

    @property
    def duracao_s(self) -> float | None:
        if self.inicio is None or self.fim is None:
            return None
        return round(self.fim - self.inicio, 3)


def desembrulhar(entradas: Sequence[dg.EventLogEntry]) -> list[Evento]:
    """Reduz as entradas do event log ao que interessa (só eventos de passo)."""
    eventos: list[Evento] = []
    for entrada in entradas:
        ev = entrada.dagster_event
        if ev is None or ev.event_type not in TIPOS_DE_PASSO or not ev.step_key:
            continue
        evento = Evento(instante=entrada.timestamp, tipo=ev.event_type_value, passo=ev.step_key)
        if ev.event_type == dg.DagsterEventType.ASSET_MATERIALIZATION:
            mat = ev.step_materialization_data.materialization
            evento.asset = mat.asset_key.to_user_string()
            evento.particao = mat.partition
            evento.metadados = {k: _valor(v) for k, v in mat.metadata.items()}
        elif ev.event_type == dg.DagsterEventType.STEP_FAILURE:
            erro = ev.step_failure_data.error
            evento.erro = erro.message.strip() if erro and erro.message else "falha sem mensagem"
        eventos.append(evento)
    return eventos


def _valor(valor: Any) -> Any:
    bruto = getattr(valor, "value", valor)
    try:
        json.dumps(bruto)
    except TypeError:
        return str(bruto)
    return bruto


def resumir_passos(eventos: list[Evento]) -> list[Passo]:
    """Junta os eventos de cada passo num resumo: início, fim, status, asset, linhas, metadados."""
    passos: dict[str, Passo] = {}
    for e in sorted(eventos, key=lambda x: x.instante):
        p = passos.setdefault(e.passo, Passo(passo=e.passo))
        if e.tipo == "STEP_START":
            p.inicio = e.instante
        elif e.tipo == "STEP_SUCCESS":
            p.fim, p.status = e.instante, "SUCESSO"
        elif e.tipo == "STEP_FAILURE":
            p.fim, p.status, p.erro = e.instante, "FALHA", e.erro
        elif e.tipo == "STEP_SKIPPED":
            p.fim, p.status = e.instante, "PULADO"
        elif e.tipo == "ASSET_MATERIALIZATION":
            p.asset, p.particao = e.asset, e.particao
            p.metadados.update(e.metadados)
            linhas = e.metadados.get("linhas")
            if isinstance(linhas, int | float):
                p.linhas = int(linhas)
    return list(passos.values())


def _ts(instante: float | None) -> datetime | None:
    return None if instante is None else datetime.fromtimestamp(instante, UTC)


def registrar_execucao(
    instance: dg.DagsterInstance, run: dg.DagsterRun, status: str, warehouse: Warehouse
) -> list[Passo]:
    """Grava a execução e os passos dela no warehouse (upsert). Devolve o resumo dos passos."""
    entradas = instance.all_logs(run.run_id, of_type=TIPOS_DE_PASSO)
    passos = resumir_passos(desembrulhar(entradas))
    stats = instance.get_run_stats(run.run_id)
    inicio, fim = stats.start_time, stats.end_time
    duracao = round(fim - inicio, 3) if inicio and fim else None
    falhos = sum(1 for p in passos if p.status == "FALHA")

    with warehouse.conectar() as con, con.cursor() as cur:
        cur.execute(DDL)
        cur.execute(
            "INSERT INTO observabilidade.execucao "
            "(run_id, job, status, inicio, fim, duracao_s, passos, passos_falhos, tags) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
            "ON CONFLICT (run_id) DO UPDATE SET status = EXCLUDED.status, fim = EXCLUDED.fim, "
            "duracao_s = EXCLUDED.duracao_s, passos = EXCLUDED.passos, "
            "passos_falhos = EXCLUDED.passos_falhos, registrado_em = now()",
            (
                run.run_id,
                run.job_name,
                status,
                _ts(inicio),
                _ts(fim),
                duracao,
                len(passos),
                falhos,
                json.dumps(dict(run.tags)),
            ),
        )
        for p in passos:
            cur.execute(
                "INSERT INTO observabilidade.execucao_passo "
                "(run_id, passo, asset, particao, inicio, fim, duracao_s, status, linhas, "
                "metadados, erro) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s) "
                "ON CONFLICT (run_id, passo) DO UPDATE SET status = EXCLUDED.status, "
                "fim = EXCLUDED.fim, duracao_s = EXCLUDED.duracao_s, linhas = EXCLUDED.linhas, "
                "metadados = EXCLUDED.metadados, erro = EXCLUDED.erro, registrado_em = now()",
                (
                    run.run_id,
                    p.passo,
                    p.asset,
                    p.particao,
                    _ts(p.inicio),
                    _ts(p.fim),
                    p.duracao_s,
                    p.status,
                    p.linhas,
                    json.dumps(p.metadados, default=str),
                    p.erro,
                ),
            )
        con.commit()
    return passos
