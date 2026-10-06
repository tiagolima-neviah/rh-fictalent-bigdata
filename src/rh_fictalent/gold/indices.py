# ruff: noqa: E501
"""Os índices do warehouse, medidos: cada um existe porque um plano de execução o usa.

A DDL do warehouse (`gold.warehouse`) só cria o que o modelo exige: a chave primária e as
chaves estrangeiras. A chave primária vira um índice; a chave estrangeira, no Postgres, não.
Então toda consulta do painel que filtra um fato por uma dimensão (o ponto de um posto, as
candidaturas de uma pessoa, a receita de um cliente) varre a tabela inteira, e no fato de ponto
isso é 1,2 milhão de linhas por pergunta.

A regra deste módulo é não criar índice por palpite. Há **candidatos**, cada um com a consulta
do painel que o pede, e há a **medida**: a consulta roda com `EXPLAIN (ANALYZE)` sem o índice e
com ele, e o laudo guarda o tempo, o plano e se o índice entrou. Só o candidato que o planejador
usa e que faz diferença é **adotado**; o que foi medido e descartado fica declarado com o motivo,
para ninguém o propor de novo. O asset do warehouse cria os adotados (idempotente, `IF NOT
EXISTS`) e atualiza as estatísticas (`ANALYZE`), porque o planejador decide pelas estatísticas.

Num fato particionado, o índice é criado na tabela-mãe e o Postgres o desce a cada partição,
inclusive às que a carga criar depois. O plano cita o índice da partição; o laudo o traduz para
o da mãe.

O valor usado em cada consulta é o mais frequente da coluna (o posto com mais ponto, o cliente
com mais faturas): é o pior caso para o índice, porque é o que mais linhas devolve.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from rh_fictalent.gold import modelo, warehouse

if TYPE_CHECKING:
    from rh_fictalent.orquestracao.recursos import Warehouse

LAUDO = "_indices.json"  # no lake, ao lado das tabelas da gold
REPETICOES = 3  # cada consulta roda três vezes; fica a mediana


@dataclass(frozen=True)
class Indice:
    tabela: str  # o nome na gold (fato_ponto_dia)
    colunas: tuple[str, ...]
    para: str  # a consulta do painel que o pede
    adotado: bool = True
    motivo: str = ""  # quando descartado, a medida que o descartou

    @property
    def nome(self) -> str:
        return f"ix_{self.tabela.split('_', 1)[1]}_{'_'.join(self.colunas)}"


@dataclass(frozen=True)
class Consulta:
    """Uma pergunta do painel no SQL do Postgres; `{fato}` e `{dim}` são os schemas."""

    nome: str
    pergunta: str
    tabela: str
    sql: str
    parametros: str  # o SQL que escolhe o valor da consulta: o mais frequente da coluna


INDICES: tuple[Indice, ...] = (
    Indice("fato_ponto_dia", ("posto_id", "data_id"), "ponto_do_posto_no_mes"),
    Indice("fato_ponto_dia", ("colaborador_id",), "ponto_da_pessoa"),
    Indice("fato_candidatura", ("candidato_id",), "candidaturas_da_pessoa"),
    Indice("fato_custo_pessoal", ("colaborador_id",), "custo_da_pessoa"),
    # medidos em 06/10/2026 e descartados: o planejador os usa, mas a tabela é pequena (9 a 17 mil
    # linhas) e a consulta fica abaixo de 1 ms com ou sem índice; voltam quando o volume pedir
    Indice(
        "fato_alocacao",
        ("posto_id",),
        "alocacoes_do_posto",
        adotado=False,
        motivo="17 mil linhas: 0,67 ms sem índice, 0,58 ms com (medido em 06/10/2026)",
    ),
    Indice(
        "fato_posto_mes",
        ("cliente_id",),
        "receita_do_cliente",
        adotado=False,
        motivo="9 mil linhas: 0,60 ms sem índice, 0,47 ms com (medido em 06/10/2026)",
    ),
    Indice(
        "fato_faturamento",
        ("cliente_id",),
        "faturas_do_cliente",
        adotado=False,
        motivo="10 mil linhas: 0,62 ms sem índice, 0,36 ms com (medido em 06/10/2026)",
    ),
    # o controle: coluna de três valores
    Indice(
        "fato_ponto_dia",
        ("filial_id",),
        "ponto_da_filial",
        adotado=False,
        motivo=(
            "coluna de três valores: o planejador não o usa nem quando existe; a consulta da filial "
            "no mês preferiu o índice composto de posto e data, 24,8 ms para 10,8 ms (medido em 06/10/2026)"
        ),
    ),
)

CONSULTAS: tuple[Consulta, ...] = (
    Consulta(
        "ponto_do_posto_no_mes",
        "O ponto de um posto no último mês dele, por situação (a tela da coordenação)",
        "fato_ponto_dia",
        "SELECT status, count(*) FROM {fato}.ponto_dia WHERE posto_id = %(posto)s AND data_id BETWEEN %(inicio)s AND %(fim)s GROUP BY 1 ORDER BY 1",
        "SELECT posto_id AS posto, max(data_id) / 100 * 100 AS inicio, max(data_id) / 100 * 100 + 31 AS fim FROM {fato}.ponto_dia GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "ponto_da_pessoa",
        "O ponto de uma pessoa, mês a mês",
        "fato_ponto_dia",
        "SELECT data_id / 100 AS mes, count(*) FROM {fato}.ponto_dia WHERE colaborador_id = %(pessoa)s GROUP BY 1 ORDER BY 1",
        "SELECT colaborador_id AS pessoa FROM {fato}.ponto_dia GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "candidaturas_da_pessoa",
        "As candidaturas de uma pessoa e em que etapa pararam (a tela da assistente)",
        "fato_candidatura",
        "SELECT status, count(*) FROM {fato}.candidatura WHERE candidato_id = %(pessoa)s GROUP BY 1 ORDER BY 1",
        "SELECT candidato_id AS pessoa FROM {fato}.candidatura GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "custo_da_pessoa",
        "O custo de uma pessoa, competência a competência",
        "fato_custo_pessoal",
        "SELECT mes_id, sum(custo_total) FROM {fato}.custo_pessoal WHERE colaborador_id = %(pessoa)s GROUP BY 1 ORDER BY 1",
        "SELECT colaborador_id AS pessoa FROM {fato}.custo_pessoal GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "alocacoes_do_posto",
        "Quem passou por um posto, e por quanto tempo",
        "fato_alocacao",
        "SELECT colaborador_id, data_inicio_id, data_fim_id FROM {fato}.alocacao WHERE posto_id = %(posto)s ORDER BY data_inicio_id",
        "SELECT posto_id AS posto FROM {fato}.alocacao GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "receita_do_cliente",
        "A receita e a margem de um cliente, mês a mês",
        "fato_posto_mes",
        "SELECT mes_id, sum(receita), sum(margem) FROM {fato}.posto_mes WHERE cliente_id = %(cliente)s GROUP BY 1 ORDER BY 1",
        "SELECT cliente_id AS cliente FROM {fato}.posto_mes GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "faturas_do_cliente",
        "As faturas de um cliente (a tela do financeiro)",
        "fato_faturamento",
        "SELECT fatura_id, sum(valor_bruto) FROM {fato}.faturamento WHERE cliente_id = %(cliente)s GROUP BY 1 ORDER BY 1",
        "SELECT cliente_id AS cliente FROM {fato}.faturamento GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
    Consulta(
        "ponto_da_filial",
        "O ponto de uma filial no mês (o controle: a coluna tem três valores)",
        "fato_ponto_dia",
        "SELECT status, count(*) FROM {fato}.ponto_dia WHERE filial_id = %(filial)s AND data_id BETWEEN %(inicio)s AND %(fim)s GROUP BY 1 ORDER BY 1",
        "SELECT filial_id AS filial, max(data_id) / 100 * 100 AS inicio, max(data_id) / 100 * 100 + 31 AS fim FROM {fato}.ponto_dia GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    ),
)


@dataclass
class Medida:
    """Uma consulta medida: o tempo e o plano, sem e com os índices."""

    consulta: str
    pergunta: str
    parametros: dict[str, Any]
    linhas: int = 0
    antes_ms: float = 0.0
    depois_ms: float = 0.0
    plano_antes: str = ""
    plano_depois: str = ""
    indices_antes: list[str] = field(default_factory=list)
    indices_depois: list[str] = field(default_factory=list)

    @property
    def ganho(self) -> float:
        """Quantas vezes mais rápido ficou (1,0 = igual)."""
        return self.antes_ms / self.depois_ms if self.depois_ms else 0.0


def indice(nome: str) -> Indice:
    return next(i for i in INDICES if i.nome == nome)


def consulta(nome: str) -> Consulta:
    return next(c for c in CONSULTAS if c.nome == nome)


def adotados() -> list[Indice]:
    return [i for i in INDICES if i.adotado]


def ddl(indices: list[Indice] | None = None, esquema_fato: str = warehouse.ESQUEMA_FATO) -> str:
    """CREATE INDEX IF NOT EXISTS de cada índice (por padrão, os adotados); idempotente."""
    linhas = [
        "-- índices do warehouse; GERADO por rh_fictalent.gold.indices, cada um medido por plano de execução."
    ]
    for i in indices if indices is not None else adotados():
        destino = warehouse.alvo(modelo.tabela(i.tabela), esquema_fato=esquema_fato)
        linhas.append(
            f"CREATE INDEX IF NOT EXISTS {i.nome} ON {destino.qualificado} ({', '.join(i.colunas)});"
        )
    return "\n".join(linhas) + "\n"


def ddl_de_remocao(
    indices: list[Indice] | None = None, esquema_fato: str = warehouse.ESQUEMA_FATO
) -> str:
    alvo = indices if indices is not None else list(INDICES)
    return "".join(f"DROP INDEX IF EXISTS {esquema_fato}.{i.nome};\n" for i in alvo)


def analise(esquema_fato: str = warehouse.ESQUEMA_FATO) -> str:
    """ANALYZE de todo fato: o planejador decide pelas estatísticas, e a carga as envelhece."""
    return "".join(
        f"ANALYZE {warehouse.alvo(t, esquema_fato=esquema_fato).qualificado};\n"
        for t in modelo.TABELAS
        if t.fato
    )


def criar(dw: Warehouse, esquema_fato: str = warehouse.ESQUEMA_FATO) -> int:
    """Cria os índices adotados e atualiza as estatísticas; devolve quantos índices há."""
    with dw.conectar() as conexao, conexao.cursor() as cur:
        cur.execute(ddl(esquema_fato=esquema_fato))
        cur.execute(analise(esquema_fato))
        conexao.commit()
    return len(adotados())


def _indices_do_plano(plano: dict[str, Any]) -> list[str]:
    nomes = [plano["Index Name"]] if "Index Name" in plano else []
    for filho in plano.get("Plans", []):
        nomes += _indices_do_plano(filho)
    return nomes


def _indice_mae(cur: Any, nome: str, esquema_fato: str) -> str:
    """O índice da partição vira o da tabela-mãe (`ponto_dia_2024_posto_id_data_id_idx` → `ix_ponto_dia_posto_id_data_id`)."""
    cur.execute(
        "SELECT p.relname FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
        "JOIN pg_class p ON p.oid = i.inhparent JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s",
        (esquema_fato, nome),
    )
    linha = cur.fetchone()
    return str(linha[0]) if linha else nome


def _explicar(
    cur: Any, sql: str, parametros: dict[str, Any], esquema_fato: str
) -> tuple[float, str, list[str], int]:
    """A mediana de REPETICOES execuções: ms, o nó de cima do plano, os índices usados, as linhas."""
    tempos, plano = [], {}
    for _ in range(REPETICOES):
        cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, parametros)
        (laudo,) = cur.fetchone()
        plano = laudo[0]
        tempos.append(float(plano["Execution Time"]))
    nos = _indices_do_plano(plano["Plan"])
    usados = sorted({_indice_mae(cur, n, esquema_fato) for n in nos})
    return (
        statistics.median(tempos),
        str(plano["Plan"]["Node Type"]),
        usados,
        int(plano["Plan"]["Actual Rows"]),
    )


def medir(dw: Warehouse, esquema_fato: str = warehouse.ESQUEMA_FATO) -> list[Medida]:
    """Antes e depois: remove todo candidato, mede; cria todos, mede; no fim deixa só os adotados."""
    medidas: list[Medida] = []
    with dw.conectar() as conexao, conexao.cursor() as cur:
        cur.execute(ddl_de_remocao(esquema_fato=esquema_fato) + analise(esquema_fato))
        conexao.commit()
        for c in CONSULTAS:
            cur.execute(c.parametros.format(fato=esquema_fato))
            linha = cur.fetchone()
            parametros = {
                d.name: v for d, v in zip(cur.description or [], linha or (), strict=True)
            }
            ms, plano, usados, linhas = _explicar(
                cur, c.sql.format(fato=esquema_fato), parametros, esquema_fato
            )
            medidas.append(
                Medida(
                    c.nome,
                    c.pergunta,
                    parametros,
                    linhas,
                    antes_ms=ms,
                    plano_antes=plano,
                    indices_antes=usados,
                )
            )
        cur.execute(ddl(list(INDICES), esquema_fato) + analise(esquema_fato))
        conexao.commit()
        for m in medidas:
            c = consulta(m.consulta)
            m.depois_ms, m.plano_depois, m.indices_depois, _ = _explicar(
                cur, c.sql.format(fato=esquema_fato), m.parametros, esquema_fato
            )
        cur.execute(ddl_de_remocao([i for i in INDICES if not i.adotado], esquema_fato))
        conexao.commit()
    return medidas


def texto(medidas: list[Medida]) -> str:
    cabecalho = f"{'consulta':<24} {'linhas':>7} {'antes ms':>9} {'depois ms':>10} {'ganho':>6}  plano antes → depois (índice)"
    linhas = [cabecalho]
    for m in medidas:
        usados = ", ".join(m.indices_depois) or "nenhum"
        linhas.append(
            f"{m.consulta:<24} {m.linhas:>7} {m.antes_ms:>9.2f} {m.depois_ms:>10.2f} {m.ganho:>5.1f}x  {m.plano_antes} → {m.plano_depois} ({usados})"
        )
    return "\n".join(linhas)


def laudo_json(medidas: list[Medida], medido_em: str) -> str:
    return json.dumps(
        {
            "medido_em": medido_em,
            "repeticoes": REPETICOES,
            "indices": [asdict(i) | {"nome": i.nome} for i in INDICES],
            "medidas": [asdict(m) | {"ganho": round(m.ganho, 2)} for m in medidas],
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
