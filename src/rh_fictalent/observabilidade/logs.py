"""Logs estruturados: uma linha JSON por evento, sempre com o id da execução quando há uma.

Por que JSON: log é dado. Uma linha por evento, com campos nomeados, é o que uma ferramenta
de busca (ou um `grep '"run_id": "..."'`) consegue filtrar; texto livre não. O id da execução
(run_id) é o que liga todas as linhas de uma mesma rodada do pipeline, em qualquer passo.

O Dagster anexa a cada registro de log um `dagster_meta` com run_id, job, passo e evento; o
formatador lê dali. Fora de uma execução (script, teste) os campos simplesmente não aparecem.

É o formatador do logger de job (rh_fictalent.orquestracao.logger_json), padrão de todas as
execuções. Para o código do projeto, use obter_logger(__name__): os loggers rh_fictalent.*
são gerenciados pelo Dagster (dagster.yaml), então dentro de uma execução o que eles logam
sai no JSON e aparece na interface.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

RAIZ_DOS_LOGGERS = "rh_fictalent"
CAMPOS_DO_DAGSTER = (("run_id", "run_id"), ("job", "job_name"), ("passo", "step_key"))


class FormatadorJSON(logging.Formatter):
    """Serializa cada registro como uma linha JSON (UTF-8, sem escapar acentos)."""

    def format(self, record: logging.LogRecord) -> str:
        linha: dict[str, Any] = {
            "instante": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "nivel": record.levelname,
            "logger": record.name,
            "mensagem": record.getMessage(),
        }
        meta = getattr(record, "dagster_meta", None) or {}
        if meta.get("orig_message"):
            linha["mensagem"] = str(meta["orig_message"])  # o prefixo do Dagster vira campos
        for campo, chave in CAMPOS_DO_DAGSTER:
            valor = meta.get(chave)
            if valor:
                linha[campo] = valor
        evento = meta.get("dagster_event")
        tipo = getattr(evento, "event_type_value", None)
        if tipo:
            linha["evento"] = tipo
        if record.exc_info and record.exc_info[0] is not None:
            linha["excecao"] = self.formatException(record.exc_info)
        return json.dumps(linha, ensure_ascii=False, default=str)


def obter_logger(nome: str) -> logging.Logger:
    """Logger do projeto; dentro de uma execução do Dagster, gerenciado por ele."""
    if not nome.startswith(RAIZ_DOS_LOGGERS):
        nome = f"{RAIZ_DOS_LOGGERS}.{nome}"
    return logging.getLogger(nome)
