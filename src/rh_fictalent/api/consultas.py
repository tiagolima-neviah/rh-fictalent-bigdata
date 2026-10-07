"""O SQL de cada ponto do contrato, no Postgres do warehouse.

Composto com `psycopg.sql`: os schemas entram como identificadores citados pelo driver e os
valores do pedido entram como parâmetros (`%(nome)s`), nunca por formatação de texto.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import sql


@dataclass(frozen=True)
class Esquemas:
    dim: str = "dim"
    fato: str = "fato"

    def tabela(self, esquema: str, nome: str) -> sql.Identifier:
        return sql.Identifier(getattr(self, esquema), nome)


def filiais(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "SELECT id, codigo, nome, tipo, municipio, uf, ativo FROM {filial} WHERE id > 0 ORDER BY id"
    ).format(filial=e.tabela("dim", "filial"))


def resultado_da_filial(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "SELECT mes_id, mes_parcial, faturamento, faturamento_liquido, custo_pessoal, impostos, "
        "despesas, resultado, margem_liquida, pessoas_alocadas, clientes_ativos, vagas_abertas "
        "FROM {resultado} WHERE filial_id = %(filial)s AND mes_id BETWEEN %(de)s AND %(ate)s "
        "ORDER BY mes_id"
    ).format(resultado=e.tabela("fato", "resultado_mes"))


def clientes_do_ano(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "WITH por_cliente AS ("
        "  SELECT p.cliente_id, c.nome_fantasia AS cliente, c.porte, "
        "         sum(p.receita) AS receita, sum(p.margem) AS margem"
        "  FROM {posto_mes} p JOIN {cliente} c ON c.id = p.cliente_id"
        "  WHERE p.ano = %(ano)s GROUP BY 1, 2, 3 HAVING sum(p.receita) > 0) "
        "SELECT cliente_id, cliente, porte, receita, margem, "
        "       rank() OVER (ORDER BY receita DESC) AS posicao, "
        "       (receita / sum(receita) OVER ())::float AS participacao, "
        "       (sum(receita) OVER (ORDER BY receita DESC ROWS UNBOUNDED PRECEDING) "
        "        / sum(receita) OVER ())::float AS participacao_acumulada "
        "FROM por_cliente ORDER BY posicao, cliente_id"
    ).format(posto_mes=e.tabela("fato", "posto_mes"), cliente=e.tabela("dim", "cliente"))


def ponto_do_posto(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "SELECT status, count(*) AS dias, count(DISTINCT colaborador_id) AS pessoas, "
        "       coalesce(sum(horas_trabalhadas), 0) AS horas_trabalhadas "
        "FROM {ponto} WHERE posto_id = %(posto)s "
        "  AND data_id BETWEEN %(mes)s * 100 + 1 AND %(mes)s * 100 + 31 "
        "GROUP BY status ORDER BY status"
    ).format(ponto=e.tabela("fato", "ponto_dia"))


def funil_do_ano(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "SELECT ((data_inscricao_id / 100) %% 100 + 2) / 3 AS trimestre, count(*) AS candidaturas, "
        "       count(*) FILTER (WHERE chegou_a_triagem) AS triadas, "
        "       count(*) FILTER (WHERE chegou_a_entrevista_interna) AS entrevistadas, "
        "       count(*) FILTER (WHERE chegou_ao_encaminhamento) AS encaminhadas, "
        "       count(*) FILTER (WHERE aprovada) AS aprovadas, "
        "       count(*) FILTER (WHERE admitida) AS admitidas, "
        "       count(*) FILTER (WHERE reprovada) AS reprovadas, "
        "       count(*) FILTER (WHERE desistiu) AS desistencias, "
        "       avg(dias_no_funil) FILTER (WHERE data_conclusao_id > 0)::float "
        "         AS dias_medios_no_funil "
        "FROM {candidatura} WHERE ano = %(ano)s GROUP BY 1 ORDER BY 1"
    ).format(candidatura=e.tabela("fato", "candidatura"))


def escopos(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "SELECT id, territorio, nivel, grupo, segmento_da_fictalent FROM {escopo} "
        "WHERE id > 0 ORDER BY id"
    ).format(escopo=e.tabela("dim", "escopo_mercado"))


def mercado_do_escopo(e: Esquemas) -> sql.Composed:
    return sql.SQL(
        "SELECT mes_id, admissoes, desligamentos, saldo FROM {mercado} "
        "WHERE escopo_mercado_id = %(escopo)s ORDER BY mes_id"
    ).format(mercado=e.tabela("fato", "mercado_mes"))
