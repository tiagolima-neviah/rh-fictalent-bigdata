"""Calibra os parâmetros por ano do motor de ocupação (etapa 3) contra o centro das bandas.

    python -m rh_fictalent.gerador.calibrar_ocupacao

Não faz parte da geração: é a ferramenta que achou os números que estão em etapa3_ocupacao.
Roda só o motor (cerca de um segundo por volta), mede por ano e empurra cada botão na direção
do alvo, até estabilizar:

- ROTACAO                 <- vagas abertas no ano (duração combinada maior = menos vagas)
- AVISO_DO_FIM_PLANEJADO  <- dias descobertos por posição e mês (mais antecedência = menos)
- FATOR_DA_SAIDA_PRECOCE  <- turnover nos primeiros 90 dias
- FATOR_DO_NO_SHOW        <- no-show de primeiro dia

Como cada posição tem o próprio sorteio, mexer num botão de um ano quase não mexe nos outros,
e a calibração converge em poucas voltas. Ao fim imprime os dicionários para colar no módulo.
Se a etapa 2 mudar (postos, antecedência dos pedidos), rode de novo.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np

from rh_fictalent.gerador import etapa1_cadastro, etapa2_carteira, historia
from rh_fictalent.gerador import etapa3_ocupacao as motor
from rh_fictalent.validacao import bandas

VOLTAS = 10
ANOS = list(bandas.ANOS)


def _medir(
    postos: list[dict[str, Any]],
    contratos: dict[int, dict[str, Any]],
    feriados: list[date],
    posicoes: np.ndarray[Any, Any],
    ano_de: np.ndarray[Any, Any],
) -> dict[int, dict[str, float]]:
    dia0 = date(bandas.ANOS[0], 1, 1)
    n = len(posicoes)
    vagas, vinculos = motor.simular(postos, contratos, feriados)
    funcoes = {int(k["cliente_id"]): [1] for k in contratos.values()}
    vagas = vagas + motor.vagas_de_recrutamento(contratos, funcoes, feriados)
    delta = np.zeros(n + 1)
    for v in vinculos:
        if v.no_show or (v.fim is not None and v.fim <= v.inicio):
            continue
        delta[(v.inicio - dia0).days] += 1
        delta[((v.fim or motor.HOJE) - dia0).days + 1] -= 1
    headcount = np.cumsum(delta)[:n]
    medidas: dict[int, dict[str, float]] = {}
    for ano in ANOS:
        do_ano = ano_de == ano
        admitidos = [v for v in vinculos if v.inicio.year == ano]
        cedo = sum(
            1
            for v in admitidos
            if v.fim is not None
            and v.tipo_desligamento in ("VOLUNTARIO", "INVOLUNTARIO")
            and (v.fim - v.inicio).days <= 90
        )
        medidas[ano] = {
            "vagas": float(sum(1 for v in vagas if v.abertura.year == ano)),
            "descoberto": 30.4 * (1 - float(headcount[do_ano].sum() / posicoes[do_ano].sum())),
            "turnover": cedo / len(admitidos),
            "no_show": sum(v.no_show for v in admitidos) / len(admitidos),
        }
    return medidas


def main() -> None:
    r = etapa2_carteira._registros
    mundo, carteira = etapa1_cadastro.gerar(), etapa2_carteira.gerar()
    postos = r(carteira["comercial.posto"])
    contratos = {int(k["id"]): k for k in r(carteira["comercial.contrato"])}
    feriados = [f["data"] for f in r(mundo["cadastro.feriado"]) if f["abrangencia"] == "NACIONAL"]
    dia0 = date(bandas.ANOS[0], 1, 1)
    n = (motor.HOJE - dia0).days + 1
    ano_de = np.array([(dia0 + timedelta(days=i)).year for i in range(n)])
    delta = np.zeros(n + 1)
    for p in postos:
        inicio = (p["vigencia_inicio"] - dia0).days
        fim = (min(p["vigencia_fim"] or motor.HOJE, motor.HOJE) - dia0).days + 1
        if inicio < n:
            delta[inicio] += p["quantidade"]
            delta[min(n, max(inicio, fim))] -= p["quantidade"]
    posicoes = np.cumsum(delta)[:n]

    def alvo(medida: str, ano: int) -> float:
        return historia.referencia_do_ano(medida, ano)

    for volta in range(VOLTAS):
        medidas = _medir(postos, contratos, feriados, posicoes, ano_de)
        pior = 0.0
        for ano in ANOS:
            m = medidas[ano]
            razao_de_vagas = m["vagas"] / bandas.VAGAS_ABERTAS[ano]
            erro_descoberto = m["descoberto"] - alvo("posto_descoberto_dias", ano)
            motor.ROTACAO[ano] = round(
                float(np.clip(motor.ROTACAO[ano] * razao_de_vagas**0.9, 0.5, 3)), 2
            )
            aviso = motor.AVISO_DO_FIM_PLANEJADO[ano] + 9 * erro_descoberto
            motor.AVISO_DO_FIM_PLANEJADO[ano] = int(np.clip(round(aviso), 0, 120))
            for fator, medida, chave in (
                (motor.FATOR_DA_SAIDA_PRECOCE, "turnover_90d", "turnover"),
                (motor.FATOR_DO_NO_SHOW, "no_show_primeiro_dia", "no_show"),
            ):
                fator[ano] = round(
                    float(np.clip(fator[ano] * (alvo(medida, ano) / m[chave]) ** 0.8, 0.3, 2)), 2
                )
            pior = max(
                pior,
                abs(razao_de_vagas - 1) / 0.10,
                abs(erro_descoberto) / 0.4,
                abs(m["turnover"] - alvo("turnover_90d", ano)) / 0.03,
                abs(m["no_show"] - alvo("no_show_primeiro_dia", ano)) / 0.015,
            )
        print(f"volta {volta + 1}: o pior desvio usa {pior:.0%} da folga da banda")

    medidas = _medir(postos, contratos, feriados, posicoes, ano_de)
    print("ano   vagas (alvo)  descoberto (alvo)  turnover (alvo)  no-show (alvo)")
    for ano in ANOS:
        m = medidas[ano]
        print(
            f"{ano}  {m['vagas']:5.0f} ({bandas.VAGAS_ABERTAS[ano]:4d})"
            f"   {m['descoberto']:5.2f} ({alvo('posto_descoberto_dias', ano):3.1f})"
            f"      {m['turnover']:.3f} ({alvo('turnover_90d', ano):.3f})"
            f"    {m['no_show']:.3f} ({alvo('no_show_primeiro_dia', ano):.3f})"
        )
    for nome in ("ROTACAO", "AVISO_DO_FIM_PLANEJADO", "FATOR_DA_SAIDA_PRECOCE", "FATOR_DO_NO_SHOW"):
        print(f"{nome} = {getattr(motor, nome)}")


if __name__ == "__main__":
    main()
