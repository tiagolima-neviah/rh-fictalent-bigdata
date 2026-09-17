"""Assets de verificação da plataforma: provam, de dentro do Dagster, que cada recurso alcança
o seu serviço. É o primeiro job de verdade do projeto e o que a Fase 3 usa para medir.

Cada asset devolve metadados que ficam no histórico do Dagster (e que o Grafana vai ler):
quantas tabelas a réplica tem, o que o lake respondeu, que versão o warehouse roda.
"""

# sem `from __future__ import annotations`: o Dagster lê a anotação de `context` em tempo de
# execução e precisa do tipo, não da string
from datetime import UTC, datetime

import dagster as dg

from rh_fictalent.orquestracao.convencoes import MODULOS
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON
from rh_fictalent.orquestracao.recursos import Lake, Replica, Warehouse

GRUPO = "plataforma"
TABELAS_ESPERADAS = 76  # 75 de negócio + meta.exclusao_auditoria


@dg.asset(
    group_name=GRUPO, description="A réplica responde ao usuário pipeline e tem as 76 tabelas."
)
def replica_pronta(context: dg.AssetExecutionContext, replica: Replica) -> None:
    linhas = replica.consultar(
        "SELECT table_schema, COUNT(*) FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' AND table_schema IN %s GROUP BY table_schema",
        (*MODULOS, "meta"),
    )
    por_modulo = {str(m): int(n) for m, n in linhas}
    total = sum(por_modulo.values())
    if total != TABELAS_ESPERADAS:
        raise dg.Failure(f"réplica com {total} tabelas; esperadas {TABELAS_ESPERADAS}")
    context.log.info("réplica alcançada: %s tabelas em %s databases", total, len(por_modulo))
    context.add_output_metadata({"tabelas": total, "por_modulo": dg.MetadataValue.json(por_modulo)})


@dg.asset(group_name=GRUPO, description="O lake aceita escrita e leitura no bucket, por s3://.")
def lake_pronto(context: dg.AssetExecutionContext, lake: Lake) -> None:
    fs = lake.sistema()
    marca = datetime.now(UTC).isoformat(timespec="seconds")
    caminho = lake.caminho("controle", "verificacao.txt")
    with fs.open(caminho, "w") as arquivo:
        arquivo.write(marca)
    with fs.open(caminho, "r") as arquivo:
        lido = arquivo.read()
    if lido != marca:
        raise dg.Failure(f"o lake devolveu {lido!r}, esperado {marca!r}")
    context.log.info("lake alcançado: escreveu e leu %s", caminho)
    context.add_output_metadata({"bucket": lake.bucket, "caminho": caminho, "marca": marca})


@dg.asset(group_name=GRUPO, description="O warehouse responde e tem o papel de leitura do Grafana.")
def warehouse_pronto(context: dg.AssetExecutionContext, warehouse: Warehouse) -> None:
    (versao,) = warehouse.consultar("SELECT version()")[0]
    (leitores,) = warehouse.consultar(
        "SELECT COUNT(*) FROM pg_roles WHERE rolname = 'grafana_leitor'"
    )[0]
    if int(leitores) != 1:
        raise dg.Failure("papel grafana_leitor ausente no warehouse")
    context.log.info("warehouse alcançado: %s", str(versao).split(",")[0])
    context.add_output_metadata({"versao": str(versao).split(",")[0]})


verificar_plataforma = dg.define_asset_job(
    name="verificar_plataforma",
    selection=dg.AssetSelection.groups(GRUPO),
    description="Prova que réplica, lake e warehouse estão alcançáveis pelos recursos do Dagster.",
    config=CONFIG_LOGS_JSON,
)
