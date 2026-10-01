"""O que o cliente faz no sistema dele depois do histórico gerado.

O gerador escreve a história até `nucleo.FIM` (10/09/2026) e recusa qualquer data depois
dela. Mas o cliente continua vivo: decide coisas e as cadastra no sistema. Este módulo faz o
papel dessas decisões, gravando na réplica como o `replicador` (o próprio sistema do
cliente), nunca como o pipeline, que só lê.

A primeira decisão foi a do prazo de retenção do candidato não contratado, tomada pelo Tiago,
no papel de cliente, em 01/10/2026 (card 6.5):

    python -m rh_fictalent.gerador --parametro RETENCAO_CANDIDATO_DIAS 730 2026-10-01
"""

from __future__ import annotations

from datetime import date, timedelta

from rh_fictalent.gerador.nucleo import Replica


def declarar_parametro(replica: Replica, chave: str, valor: str, desde: date) -> str:
    """Grava um parâmetro com vigência a partir de `desde`, encerrando o vigente na véspera.

    Idempotente: declarar de novo o mesmo valor na mesma data não faz nada. Mudar o valor de
    uma vigência já declarada é recusado: a decisão nova ganha data nova, e a antiga fica na
    história, como no resto da tabela.
    """
    con = replica.conectar()
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT valor FROM cadastro.parametro WHERE chave = %s AND vigencia_inicio = %s",
                (chave, desde),
            )
            existente = cur.fetchone()
            if existente is not None:
                if str(existente[0]) == valor:
                    return f"{chave}={valor} já declarado desde {desde:%d/%m/%Y}"
                raise ValueError(
                    f"{chave} já tem o valor {existente[0]} desde {desde:%d/%m/%Y}; "
                    "a decisão nova precisa de data nova"
                )
            cur.execute(
                "UPDATE cadastro.parametro SET vigencia_fim = %s "
                "WHERE chave = %s AND vigencia_fim IS NULL AND vigencia_inicio < %s",
                (desde - timedelta(days=1), chave, desde),
            )
            encerrados = cur.rowcount
            cur.execute(
                "INSERT INTO cadastro.parametro (chave, valor, vigencia_inicio) "
                "VALUES (%s, %s, %s)",
                (chave, valor, desde),
            )
        con.commit()
    finally:
        con.close()
    anterior = f"; {encerrados} vigência anterior encerrada" if encerrados else ""
    return f"{chave}={valor} declarado desde {desde:%d/%m/%Y}{anterior}"
