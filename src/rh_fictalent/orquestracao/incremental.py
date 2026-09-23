"""O job da carga incremental e a primeira agenda do projeto.

Aqui a forma muda de propósito. O backfill é um asset por tabela e partição, porque o que
interessa lá é **o arquivo de cada ano**, materializado um a um, com backfill pela interface.
A carga diária é outra coisa: ela não sabe de antemão quais partições vai tocar (depende do que
mudou na réplica naquele dia), e tocar 675 partições para descobrir que 3 mudaram seria caro e
ilegível no histórico.

Então a carga é um **op**, e as partições que ele reescreve viram `AssetMaterialization` dos
mesmos assets `bronze/modulo/tabela`. A linhagem continua sendo a do card 5.1, o histórico do
asset mostra as duas origens (backfill e carga diária), e o Dagster não precisa de um passo por
alvo possível. É o padrão para carga que descobre o alvo enquanto roda.

A agenda roda às 5h da manhã, fuso de São Paulo: depois do fechamento do dia anterior e antes
de qualquer gente olhar o painel.
"""

# sem `from __future__ import annotations`: o Dagster lê as anotações em tempo de execução
from datetime import datetime

import dagster as dg

from rh_fictalent.ingestao import marca_dagua
from rh_fictalent.ingestao.exclusoes import NOME_DA_TRILHA, TRILHA, ler_trilha, marcar
from rh_fictalent.ingestao.incremental import (
    SOBREPOSICAO,
    Sincronizacao,
    agora_na_replica,
    conferir,
    marca_da_bronze,
    refazer,
    sincronizar,
)
from rh_fictalent.orquestracao.convencoes import chave
from rh_fictalent.orquestracao.logger_json import CONFIG_LOGS_JSON, logger_json
from rh_fictalent.orquestracao.recursos import Lake, Replica, Warehouse
from rh_fictalent.staging.gatilhos import tabelas_por_modulo

HORA_DA_CARGA = "0 5 * * *"
FUSO = "America/Sao_Paulo"


class Carga(dg.Config):
    """O que a carga vai fazer nesta execução."""

    tabelas: list[str] = []  # vazio: todas as tabelas de negócio; senão "modulo.tabela"
    refazer_tudo: bool = False  # ignora a marca e recopia da réplica (saída de emergência)


def _publicar(context: dg.OpExecutionContext, s: Sincronizacao) -> None:
    """Cada partição reescrita vira materialização do asset bronze correspondente."""
    for ano, linhas in s.particoes.items():
        context.log_event(
            dg.AssetMaterialization(
                asset_key=chave("bronze", s.modulo, s.tabela),
                partition=str(ano),
                description="carga incremental",
                metadata={
                    "linhas": linhas,
                    "alteradas_na_janela": s.alteradas,
                    "desde": s.desde.isoformat(sep=" ", timespec="microseconds"),
                    "ate": s.ate.isoformat(sep=" ", timespec="microseconds"),
                },
            )
        )


@dg.op(
    description="Traz da réplica o que mudou desde a marca d'água e reescreve as partições.",
    required_resource_keys=set(),
)
def sincronizar_bronze(
    context: dg.OpExecutionContext,
    config: Carga,
    replica: Replica,
    lake: Lake,
    warehouse: Warehouse,
) -> None:
    marca_dagua.criar(warehouse)
    marcas = marca_dagua.ler(warehouse)
    alvos = [
        (modulo, tabela)
        for modulo, tabelas in tabelas_por_modulo().items()
        for tabela in tabelas
        if not config.tabelas or f"{modulo}.{tabela}" in config.tabelas
    ]
    if not alvos:
        raise dg.Failure(f"nenhuma tabela conhecida em {config.tabelas}")

    con = replica.conectar()
    problemas: list[str] = []
    tocadas = alteradas = excluidas = 0
    try:
        corte = agora_na_replica(con)
        # a trilha primeiro: marcar o que sumiu antes de conferir quantas linhas devem existir
        da_trilha = marcas.get(NOME_DA_TRILHA)
        desde_trilha = (da_trilha.marca - SOBREPOSICAO) if da_trilha else datetime.min
        apagadas = ler_trilha(con, desde_trilha, corte)
        for modulo, tabela in alvos:
            nome = f"{modulo}.{tabela}"
            if (modulo, tabela) in apagadas:
                a = marcar(lake, modulo, tabela, apagadas[(modulo, tabela)])
                excluidas += a.marcadas
                # a partição que só teve exclusão não é tocada pelo merge: confere-se aqui
                problemas += conferir(con, lake, modulo, tabela, a.particoes, corte)
                context.log.info(
                    "%s: %s exclusões (%s marcadas agora, %s já marcadas, %s fora da bronze)",
                    nome,
                    a.pedidas,
                    a.marcadas,
                    a.ja_marcadas,
                    a.ausentes,
                )
            anterior = marcas.get(nome)
            if config.refazer_tudo or anterior is None:
                da_bronze = None if config.refazer_tudo else marca_da_bronze(lake, modulo, tabela)
                if da_bronze is None:
                    motivo = "pedido" if config.refazer_tudo else "sem marca e sem bronze"
                    context.log.warning("%s: recopiando tudo (%s)", nome, motivo)
                    s = refazer(con, lake, modulo, tabela)
                    s.ate = corte
                else:
                    context.log.info("%s: marca derivada da bronze (%s)", nome, da_bronze)
                    s = sincronizar(con, lake, modulo, tabela, da_bronze - SOBREPOSICAO, corte)
            else:
                s = sincronizar(con, lake, modulo, tabela, anterior.marca - SOBREPOSICAO, corte)
            problemas += s.divergencias
            alteradas += s.alteradas
            tocadas += len(s.particoes)
            _publicar(context, s)
            if s.confere:  # marca só avança quando a tabela fechou certa
                marca_dagua.gravar(
                    warehouse,
                    marca_dagua.Marca(nome, corte, s.alteradas, len(s.particoes)),
                    context.run_id,
                )
            if s.alteradas:
                context.log.info(
                    "%s: %s linhas alteradas em %s partição(ões)",
                    nome,
                    s.alteradas,
                    len(s.particoes),
                )
        # a trilha também vai para a bronze: a linha apagada some da réplica, o registro fica
        da_trilha_agora = refazer(con, lake, *TRILHA)
        problemas += da_trilha_agora.divergencias
        if not da_trilha_agora.divergencias:
            marca_dagua.gravar(
                warehouse,
                marca_dagua.Marca(NOME_DA_TRILHA, corte, sum(len(v) for v in apagadas.values()), 0),
                context.run_id,
            )
    finally:
        con.close()

    context.log.info(
        "carga incremental: %s tabelas, %s linhas alteradas, %s partições reescritas, "
        "%s exclusões aplicadas",
        len(alvos),
        alteradas,
        tocadas,
        excluidas,
    )
    if problemas:
        raise dg.Failure(
            "a bronze não bate com a réplica depois da carga:\n- " + "\n- ".join(problemas)
        )


@dg.job(
    name="carga_incremental",
    description="Só o que mudou na réplica desde a última carga, aplicado nas partições tocadas.",
    # um @job nao herda os loggers das Definitions como um asset job herda: declara o dele
    logger_defs={"json": logger_json},
    config=CONFIG_LOGS_JSON,
)
def carga_incremental() -> None:
    sincronizar_bronze()


agenda_incremental = dg.ScheduleDefinition(
    name="carga_incremental_diaria",
    job=carga_incremental,
    cron_schedule=HORA_DA_CARGA,
    execution_timezone=FUSO,
    default_status=dg.DefaultScheduleStatus.RUNNING,
    description="Todo dia às 5h, traz da réplica o que mudou desde a marca d'água.",
)
