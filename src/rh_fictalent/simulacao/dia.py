"""Dias correntes: a réplica continua se mexendo depois do fim da história gerada.

A base sintética termina em 10/09/2026, o dia da primeira reunião. Um pipeline que só lê uma
base parada nunca exercita o que foi construído na fase 5: a marca d'água nunca avança, a
sobreposição nunca serve para nada e a trilha de exclusões nunca tem o que contar. Este módulo
existe para dar movimento à réplica, como o sistema do cliente daria.

**O que ele é, e o que não é.** Ele é a operação continuando: gente batendo ponto, vaga
fechando, alocação terminando, e de vez em quando um registro apagado por engano. Ele **não é**
uma continuação do gerador: a fidelidade aqui é menor e está declarada abaixo, e a régua de
validação continua valendo para a base gerada até 10/09/2026, não para o que a operação
acrescentou depois. Confundir as duas coisas seria dizer que o dado corrente foi validado, e
ele não foi.

As simplificações, todas de propósito:

- a escala vira uma regra simples de dia da semana (5X2 de segunda a sexta, 6X1 e 5X1 até
  sábado, 12X36 em dias alternados), em vez do motor de ocupação da etapa 3;
- ninguém é admitido nem alocado: a simulação mexe em quem já está em campo. Abrir vaga, rodar
  o funil e admitir é o gerador, e refazer isso aqui seria escrever um segundo gerador pior;
- folha e faturamento não fecham no dia: isso é mensal, e a fase 6 vai tratar.

Cada dia é escrito uma vez só. O que a simulação fez fica registrado no warehouse
(`ingestao.dia_simulado`), para que a conferência da base gerada continue possível: basta
descontar o que a operação acrescentou depois do marco.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

import numpy as np

from rh_fictalent.gerador.nucleo import FIM, SEMENTE

if TYPE_CHECKING:  # pragma: no cover
    import pymysql

    from rh_fictalent.orquestracao.recursos import Replica

FIM_DA_HISTORIA = FIM.date()
# escala -> dias da semana em que se trabalha (0 = segunda). 12X36 é tratado à parte
DIAS_DA_ESCALA = {"5X2": (0, 1, 2, 3, 4), "6X1": (0, 1, 2, 3, 4, 5), "5X1": (0, 1, 2, 3, 4, 5)}
FOLGA_EM_FERIADO = ("5X2", "6X1")  # revezamento e 12X36 trabalham em feriado, como no gerador
CHANCE_DE_FALTA = 0.034
CHANCE_DE_ATESTADO = 0.010
CHANCE_DE_HORA_EXTRA = 0.12
CHANCE_DE_MARCACAO_FALTANTE = 0.025  # PON-01, o mesmo defeito do catálogo
CHANCE_DE_MARCACAO_DUPLICADA = 0.006  # PON-02
VAGAS_FECHADAS_POR_DIA = (0, 3)  # quantas vagas abertas passam a PREENCHIDA no dia
ALOCACOES_ENCERRADAS_POR_DIA = (0, 2)
CHANCE_DE_EXCLUSAO = 0.15  # por dia: alguém apaga uma batida errada, e a trilha registra


@dataclass
class Movimento:
    """O que a operação fez num dia."""

    dia: date
    inseridas: dict[str, int] = field(default_factory=dict)
    alteradas: dict[str, int] = field(default_factory=dict)
    excluidas: dict[str, int] = field(default_factory=dict)
    ja_simulado: bool = False

    @property
    def total_inserido(self) -> int:
        return sum(self.inseridas.values())

    def resumo(self) -> str:
        if self.ja_simulado:
            return f"{self.dia}: já simulado, nada a fazer"
        return (
            f"{self.dia}: {self.total_inserido} linhas novas, "
            f"{sum(self.alteradas.values())} alteradas, {sum(self.excluidas.values())} apagadas"
        )


def aleatorio(dia: date) -> np.random.Generator:
    """Um gerador por dia, derivado da semente do projeto: o mesmo dia dá o mesmo movimento."""
    resumo = hashlib.sha256(f"{SEMENTE}:dia:{dia.isoformat()}".encode()).digest()
    return np.random.default_rng(int.from_bytes(resumo[:8], "big"))


def _trabalha(escala: str, dia: date, feriado: bool, colaborador: int) -> bool:
    if escala == "12X36":  # plantão: trabalha dia sim, dia não, ancorado no id da pessoa
        return (dia.toordinal() + colaborador) % 2 == 0
    if feriado and escala in FOLGA_EM_FERIADO:
        return False
    return dia.weekday() in DIAS_DA_ESCALA.get(escala, (0, 1, 2, 3, 4))


def _hora(rng: np.random.Generator, base: int, folga_min: int = 40) -> time:
    minutos = int(base * 60 + rng.integers(-folga_min, folga_min))
    return time(minutos // 60 % 24, minutos % 60, int(rng.integers(0, 60)))


def ja_simulado(con: pymysql.connections.Connection[Any], dia: date) -> bool:
    with con.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM ponto.apontamento WHERE data = %s", (dia,))
        (quantos,) = cur.fetchone()
    return int(quantos) > 0


def _em_campo(con: pymysql.connections.Connection[Any], dia: date) -> list[tuple[int, int, str]]:
    """Quem estava alocado no dia: (colaborador, alocação, escala vigente)."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT a.colaborador_id, a.id, e.codigo "
            "FROM pessoas.alocacao a "
            "JOIN ponto.escala_colaborador ec ON ec.colaborador_id = a.colaborador_id "
            "  AND ec.vigencia_inicio <= %s AND (ec.vigencia_fim IS NULL OR ec.vigencia_fim >= %s) "
            "JOIN cadastro.escala e ON e.id = ec.escala_id "
            "WHERE a.dt_inicio <= %s AND (a.dt_fim IS NULL OR a.dt_fim >= %s) "
            "GROUP BY a.colaborador_id, a.id, e.codigo",
            (dia, dia, dia, dia),
        )
        return [(int(c), int(a), str(e)) for c, a, e in cur.fetchall()]


def _feriado(con: pymysql.connections.Connection[Any], dia: date) -> bool:
    with con.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM cadastro.feriado WHERE data = %s AND abrangencia = 'NACIONAL'",
            (dia,),
        )
        (quantos,) = cur.fetchone()
    return int(quantos) > 0


def _ponto_do_dia(
    con: pymysql.connections.Connection[Any], dia: date, rng: np.random.Generator
) -> dict[str, int]:
    """O dia de quem está em campo: apontamento, as quatro batidas e a ocorrência da falta."""
    feriado = _feriado(con, dia)
    apontamentos: list[tuple[Any, ...]] = []
    marcacoes: list[tuple[Any, ...]] = []
    faltas: list[tuple[int, str, int]] = []  # posição do apontamento, tipo, minutos
    for colaborador, alocacao, escala in _em_campo(con, dia):
        if not _trabalha(escala, dia, feriado, colaborador):
            continue
        sorteio = float(rng.random())
        if sorteio < CHANCE_DE_FALTA:
            status, horas, extras = "FALTA", 0.0, 0.0
        elif sorteio < CHANCE_DE_FALTA + CHANCE_DE_ATESTADO:
            status, horas, extras = "ATESTADO", 0.0, 0.0
        else:
            jornada = 11.0 if escala == "12X36" else 7.33
            extras = (
                round(float(rng.uniform(0.5, 2.0)), 2)
                if rng.random() < CHANCE_DE_HORA_EXTRA
                else 0.0
            )
            status, horas = "NORMAL", jornada
        apontamentos.append((colaborador, alocacao, dia, horas, extras, 0.0, status))
        if status != "NORMAL":
            if status == "FALTA":
                faltas.append((len(apontamentos), "FALTA_INJUSTIFICADA", 0))
            continue
        entrada = 6 if escala != "12X36" else 7
        batidas = [
            ("ENTRADA", _hora(rng, entrada)),
            ("SAIDA_INTERVALO", _hora(rng, entrada + 4)),
            ("RETORNO_INTERVALO", _hora(rng, entrada + 5)),
            ("SAIDA", _hora(rng, entrada + 8 + int(extras))),
        ]
        if rng.random() < CHANCE_DE_MARCACAO_FALTANTE:  # PON-01: o relógio comeu uma batida
            batidas.pop(int(rng.integers(0, len(batidas))))
        elif rng.random() < CHANCE_DE_MARCACAO_DUPLICADA:  # PON-02: bateu duas vezes
            batidas.append(batidas[0])
        for tipo, hora in batidas:
            marcacoes.append((colaborador, dia, hora, tipo, "RELOGIO"))

    feito: dict[str, int] = {}
    with con.cursor() as cur:
        inseridos: list[int] = []
        if apontamentos:
            cur.executemany(
                "INSERT INTO ponto.apontamento (colaborador_id, alocacao_id, data, "
                "horas_trabalhadas, horas_extras, horas_noturnas, status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                apontamentos,
            )
            # os ids são lidos de volta, não calculados: com `executemany` o `lastrowid` do
            # MySQL é o **primeiro** id do lote, e supor que é o último aponta a ocorrência
            # para o apontamento errado (a chave estrangeira barra, mas o bug é de raciocínio)
            cur.execute("SELECT id FROM ponto.apontamento WHERE data = %s ORDER BY id", (dia,))
            inseridos = [int(i) for (i,) in cur.fetchall()]
            feito["ponto.apontamento"] = len(apontamentos)
        if marcacoes:
            cur.executemany(
                "INSERT INTO ponto.marcacao (colaborador_id, data, hora, tipo, origem) "
                "VALUES (%s, %s, %s, %s, %s)",
                marcacoes,
            )
            feito["ponto.marcacao"] = len(marcacoes)
        if faltas and inseridos:
            cur.executemany(
                "INSERT INTO ponto.ocorrencia_ponto (apontamento_id, tipo, minutos) "
                "VALUES (%s, %s, %s)",
                [(inseridos[posicao - 1], tipo, minutos) for posicao, tipo, minutos in faltas],
            )
            feito["ponto.ocorrencia_ponto"] = len(faltas)
    return feito


def _fechar_vagas(
    con: pymysql.connections.Connection[Any], dia: date, rng: np.random.Generator
) -> dict[str, int]:
    quantas = int(rng.integers(*VAGAS_FECHADAS_POR_DIA, endpoint=True))
    if not quantas:
        return {}
    with con.cursor() as cur:
        cur.execute(
            "SELECT id FROM ats.vaga WHERE status IN ('ABERTA', 'EM_TRIAGEM') "
            "ORDER BY dt_abertura LIMIT %s",
            (quantas,),
        )
        ids = [int(i) for (i,) in cur.fetchall()]
        if not ids:
            return {}
        marcas = ", ".join(["%s"] * len(ids))
        cur.execute(
            f"UPDATE ats.vaga SET status = 'PREENCHIDA', dt_fechamento = %s WHERE id IN ({marcas})",  # noqa: S608 # nosec B608
            (dia, *ids),
        )
        return {"ats.vaga": cur.rowcount}


def _encerrar_alocacoes(
    con: pymysql.connections.Connection[Any], dia: date, rng: np.random.Generator
) -> dict[str, int]:
    quantas = int(rng.integers(*ALOCACOES_ENCERRADAS_POR_DIA, endpoint=True))
    if not quantas:
        return {}
    with con.cursor() as cur:
        cur.execute(
            "SELECT id FROM pessoas.alocacao WHERE dt_fim IS NULL ORDER BY dt_inicio LIMIT %s",
            (quantas,),
        )
        ids = [int(i) for (i,) in cur.fetchall()]
        if not ids:
            return {}
        marcas = ", ".join(["%s"] * len(ids))
        cur.execute(
            f"UPDATE pessoas.alocacao SET dt_fim = %s WHERE id IN ({marcas})",  # noqa: S608 # nosec B608
            (dia, *ids),
        )
        return {"pessoas.alocacao": cur.rowcount}


def _apagar_batida_errada(
    con: pymysql.connections.Connection[Any], dia: date, rng: np.random.Generator
) -> dict[str, int]:
    """Alguém do DP apaga uma batida lançada errada. O gatilho registra na trilha, e é assim
    que a carga incremental fica sabendo: `DELETE` não deixa `atualizado_em` para ser lido."""
    if rng.random() >= CHANCE_DE_EXCLUSAO:
        return {}
    with con.cursor() as cur:
        cur.execute(
            "SELECT id FROM ponto.marcacao WHERE data = %s ORDER BY id DESC LIMIT 1", (dia,)
        )
        achado = cur.fetchone()
        if not achado:
            return {}
        cur.execute("DELETE FROM ponto.marcacao WHERE id = %s", (int(achado[0]),))
        return {"ponto.marcacao": cur.rowcount}


def simular(replica: Replica, dia: date) -> Movimento:
    """Escreve um dia de operação na réplica, como o sistema do cliente faria.

    Tudo numa transação: ou o dia inteiro entra, ou nada entra. Um dia pela metade seria pior
    que nenhum dia, porque a carga incremental o leria como se estivesse completo.
    """
    movimento = Movimento(dia)
    rng = aleatorio(dia)
    con = replica.conectar()
    try:
        if ja_simulado(con, dia):
            movimento.ja_simulado = True
            return movimento
        con.begin()
        try:
            movimento.inseridas = _ponto_do_dia(con, dia, rng)
            movimento.alteradas = _fechar_vagas(con, dia, rng) | _encerrar_alocacoes(con, dia, rng)
            movimento.excluidas = _apagar_batida_errada(con, dia, rng)
            con.commit()
        except Exception:
            con.rollback()
            raise
    finally:
        con.close()
    return movimento


def dias_a_simular(ate: date, desde: date | None = None) -> list[date]:
    """Os dias entre o fim da história (exclusive) e a data pedida."""
    comeco = desde or FIM_DA_HISTORIA + timedelta(days=1)
    if ate < comeco:
        return []
    return [comeco + timedelta(days=i) for i in range((ate - comeco).days + 1)]


def agora() -> datetime:
    return datetime.now()
