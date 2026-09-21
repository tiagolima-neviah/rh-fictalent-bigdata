"""Etapa 3, o motor: quem ocupa cada posição de cada posto, do primeiro pedido ao desligamento.

A carteira (etapa 2) diz quantas posições cada cliente contrata e quando. Aqui cada posição
vira uma fila de acontecimentos: o cliente pede (a necessidade fica conhecida), a vaga abre,
demora para fechar (o time to fill do ano), às vezes não fecha (o fill rate), a pessoa admitida
às vezes não aparece no primeiro dia, e quem aparece um dia sai (pedido, dispensa, fim do
posto, fim do prazo legal do temporário, efetivação pelo cliente). Cada saída antes do fim do
posto abre uma vaga de reposição, e o tempo entre a necessidade e o preenchimento é o posto
descoberto. Os contratos de recrutamento geram vagas sem posto: a pessoa vai para o cliente.

Cada posição tem o seu próprio sorteio (semente, posto, posição): mexer num parâmetro muda
o que ele governa, não embaralha a base inteira. O resultado são duas listas (vagas e
vínculos) que as partes seguintes transformam em linhas de `ats` e `pessoas`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from rh_fictalent.gerador import historia
from rh_fictalent.gerador.nucleo import FIM, SEMENTE
from rh_fictalent.validacao.bandas import VAGAS_ABERTAS

HOJE = FIM.date()
POSICOES_POR_VAGA = 4  # um pedido grande vira várias vagas (turmas) deste tamanho, no máximo
DISPERSAO_DO_TTF = 0.5  # desvio do logaritmo do time to fill
CHANCE_DE_REABRIR = 0.95  # vaga cancelada sem preencher: o cliente quase sempre pede de novo
# o temporário é contratado por demanda, com duração combinada (dias, peso); ao fim, se o posto
# continua, entra outra pessoa: é a rotação que faz uma empresa deste porte abrir milhares de vagas
DURACAO_DO_TEMPORARIO = ((30, 0.12), (45, 0.16), (60, 0.21), (90, 0.16), (120, 0.10), (180, 0.25))
# dias de antecedência com que se pede a reposição de um fim previsto (calibra a ocupação do ano)
AVISO_DO_FIM_PLANEJADO = {
    2018: 3,
    2019: 5,
    2020: 4,
    2021: 12,
    2022: 13,
    2023: 25,
    2024: 23,
    2025: 17,
    2026: 69,
}
# quanto a duração combinada estica ou encolhe em cada ano: no começo os contratos eram mais
# longos; com logística e varejo (2022 a 2024) a rotação acelera; na crise a demanda esfria
ROTACAO = {
    2018: 1.69,
    2019: 1.04,
    2020: 1.0,
    2021: 0.87,
    2022: 0.7,
    2023: 0.76,
    2024: 0.85,
    2025: 1.12,
    2026: 1.13,
}
PRAZO_TEMPORARIO, PRAZO_PRORROGADO = 180, 270
CHANCE_DE_PRORROGAR = 0.85
CHANCE_DE_EFETIVACAO = 0.04  # o cliente contrata o temporário para o quadro dele
RISCO_MENSAL_APOS_90_DIAS = {"TEMPORARIO": 0.030, "TERCEIRIZACAO": 0.022}
# calibração por ano (scripts do card 4.6: o calibrador roda o motor em laço até cada medida
# cair no centro da banda): a saída precoce (turnover de 90 dias menos o no-show) e o no-show
FATOR_DA_SAIDA_PRECOCE = {
    2018: 0.46,
    2019: 1.14,
    2020: 1.04,
    2021: 1.01,
    2022: 1.03,
    2023: 1.16,
    2024: 1.24,
    2025: 1.11,
    2026: 1.24,
}
FATOR_DO_NO_SHOW = {
    2018: 0.89,
    2019: 1.07,
    2020: 1.22,
    2021: 1.12,
    2022: 0.93,
    2023: 1.03,
    2024: 1.04,
    2025: 0.96,
    2026: 1.03,
}
# entre os temporários que chegam a 180 dias com o posto aberto: quantos seguem sem aditivo (PES-02)
CHANCE_DE_IRREGULARIDADE = {"ate_2022": 0.18, "desde_2023": 0.72}
# parcela das vagas do ano que são de recrutamento e seleção (a empresa nasce colocando efetivos)
PARCELA_DE_VAGAS_DE_RS = {
    2018: 0.38,
    2019: 0.25,
    2020: 0.22,
    2021: 0.15,
    2022: 0.12,
    2023: 0.10,
    2024: 0.10,
    2025: 0.09,
    2026: 0.22,
}
PESO_DO_MES_PARA_RS = (0.9, 0.9, 1.2, 1.2, 1.2, 1.1, 1.0, 1.0, 0.9, 0.9, 0.9, 0.8)


@dataclass
class Vaga:
    posto_id: int | None  # None = recrutamento e seleção para o quadro do cliente
    contrato_id: int
    tipo_servico: str
    funcao_id: int
    posicoes: int
    conhecida: date  # quando o cliente pediu
    necessidade: date  # quando a posição precisa estar coberta
    abertura: date
    fechamento: date | None = None
    situacao: str = "ABERTA"  # ABERTA, PREENCHIDA ou CANCELADA
    motivo_cancelamento: str | None = None
    reposicao: bool = False


@dataclass
class Vinculo:
    vaga: int  # índice na lista de vagas
    posto_id: int
    posicao: int
    tipo_servico: str
    funcao_id: int
    inicio: date
    fim: date | None = None  # None = alocado hoje
    prevista: date | None = None  # término previsto do temporário
    prorrogado_em: date | None = None
    novo_termino: date | None = None
    tipo_desligamento: str | None = None
    motivo: str | None = None
    no_show: bool = False
    irregular: bool = False  # passou do prazo legal sem aditivo (PES-02)


class Calendario:
    """Dias úteis com os feriados nacionais da etapa 1 (numpy busday)."""

    def __init__(self, feriados: list[date]) -> None:
        self.feriados = np.array(sorted(set(feriados)), dtype="datetime64[D]")

    def somar(self, dia: date, uteis: int) -> date:
        alvo = np.busday_offset(np.datetime64(dia), uteis, roll="forward", holidays=self.feriados)
        return alvo.astype(date)  # type: ignore[no-any-return]

    def contar(self, de: date, ate: date) -> int:
        return int(np.busday_count(np.datetime64(de), np.datetime64(ate), holidays=self.feriados))


def _ttf(rng: np.random.Generator, tipo: str, ano: int) -> int:
    medida = "ttf_rs_mediana" if tipo == "RECRUTAMENTO" else "ttf_temporario_mediana"
    mediana = historia.referencia_do_ano(medida, ano)
    if tipo == "TERCEIRIZACAO":
        mediana *= 1.3  # posto fixo pede mais critério que reforço de temporada
    return max(1, round(mediana * math.exp(DISPERSAO_DO_TTF * float(rng.standard_normal()))))


def _saida(
    rng: np.random.Generator, tipo: str, inicio: date, fim_do_posto: date | None
) -> dict[str, Any]:
    """Quando e por que a pessoa deixa a posição (sem olhar ainda para o fim da história)."""
    ano = inicio.year
    precoce = historia.referencia_do_ano("turnover_90d", ano)
    precoce -= historia.referencia_do_ano("no_show_primeiro_dia", ano)
    candidatos: list[tuple[date, str, str, int]] = []  # (dia, tipo, motivo, aviso em dias)
    combinado = PRAZO_TEMPORARIO
    if tipo == "TEMPORARIO":
        duracoes = [d for d, _ in DURACAO_DO_TEMPORARIO]
        pesos = [p for _, p in DURACAO_DO_TEMPORARIO]
        combinado = min(PRAZO_TEMPORARIO, round(int(rng.choice(duracoes, p=pesos)) * ROTACAO[ano]))
    horizonte = min(90, combinado) if tipo == "TEMPORARIO" else 90
    if rng.random() < precoce * FATOR_DA_SAIDA_PRECOCE[ano]:
        dia = inicio + timedelta(days=int(rng.integers(2, max(3, horizonte))))
        if rng.random() < 0.6:
            motivo = "PEDIDO_DEMISSAO" if rng.random() < 0.7 else "ABANDONO"
            candidatos.append((dia, "VOLUNTARIO", motivo, 0))
        else:
            motivo = str(
                rng.choice(
                    ["PEDIDO_CLIENTE", "SEM_JUSTA_CAUSA", "JUSTA_CAUSA"], p=[0.6, 0.35, 0.05]
                )
            )
            candidatos.append((dia, "INVOLUNTARIO", motivo, 2))
    else:
        espera = float(rng.exponential(30 / RISCO_MENSAL_APOS_90_DIAS[tipo]))
        dia = inicio + timedelta(days=90 + int(espera))
        if rng.random() < 0.65:
            candidatos.append((dia, "VOLUNTARIO", "PEDIDO_DEMISSAO", 0))
        else:
            candidatos.append((dia, "INVOLUNTARIO", "SEM_JUSTA_CAUSA", 5))

    resultado: dict[str, Any] = {
        "prevista": None,
        "prorrogado_em": None,
        "novo_termino": None,
        "irregular": False,
    }
    if tipo == "TEMPORARIO":
        limite = inicio + timedelta(days=combinado - 1)
        resultado["prevista"] = min(limite, fim_do_posto) if fim_do_posto else limite
        if rng.random() < CHANCE_DE_EFETIVACAO:
            dia = inicio + timedelta(days=int(rng.integers(60, 171)))
            candidatos.append((dia, "EFETIVACAO_CLIENTE", "EFETIVADO_CLIENTE", 10))
        posto_continua = fim_do_posto is None or fim_do_posto > limite
        chega_ao_prazo = min(c[0] for c in candidatos) > limite  # ninguém o tira antes dos 180 dias
        if posto_continua and chega_ao_prazo and combinado == PRAZO_TEMPORARIO:
            chave = "desde_2023" if limite.year >= 2023 else "ate_2022"
            if rng.random() < CHANCE_DE_IRREGULARIDADE[chave]:
                resultado["irregular"] = True
                limite = inicio + timedelta(days=PRAZO_TEMPORARIO + int(rng.integers(10, 150)))
            elif rng.random() < CHANCE_DE_PRORROGAR:
                resultado["prorrogado_em"] = limite - timedelta(days=int(rng.integers(5, 20)))
                limite = inicio + timedelta(days=PRAZO_PRORROGADO - 1)
                resultado["novo_termino"] = limite
        candidatos.append((limite, "FIM_CONTRATO", "TERMINO_CONTRATO", AVISO_DO_FIM_PLANEJADO[ano]))
    if fim_do_posto is not None:
        if tipo == "TEMPORARIO":
            candidatos.append((fim_do_posto, "FIM_CONTRATO", "TERMINO_CONTRATO", 0))
        else:
            candidatos.append((fim_do_posto, "INVOLUNTARIO", "REDUCAO_QUADRO", 0))
    dia, tipo_desligamento, motivo, aviso = min(candidatos, key=lambda c: c[0])
    resultado.update(fim=dia, tipo_desligamento=tipo_desligamento, motivo=motivo, aviso=aviso)
    if resultado["prorrogado_em"] is not None and dia < resultado["prorrogado_em"]:
        resultado["prorrogado_em"] = resultado["novo_termino"] = None  # saiu antes de prorrogar
    return resultado


def simular(
    postos: list[dict[str, Any]], contratos: dict[int, dict[str, Any]], feriados: list[date]
) -> tuple[list[Vaga], list[Vinculo]]:
    calendario = Calendario(feriados)
    vagas: list[Vaga] = []
    vinculos: list[Vinculo] = []
    for posto in postos:
        contrato = contratos[posto["contrato_id"]]
        tipo = str(contrato["tipo_servico"])
        fim_do_posto: date | None = posto["vigencia_fim"]
        conhecida = posto["criado_em"].date()
        # o pedido inicial vira turmas de até POSICOES_POR_VAGA; cada turma é uma vaga
        posicao = 0
        while posicao < posto["quantidade"]:
            turma = min(POSICOES_POR_VAGA, posto["quantidade"] - posicao)
            rng = np.random.default_rng([SEMENTE, 3, int(posto["id"]), posicao])
            primeira = _abrir(
                vagas,
                calendario,
                rng,
                posto,
                tipo,
                turma,
                conhecida,
                posto["vigencia_inicio"],
                False,
            )
            for i in range(turma):
                sorteio = np.random.default_rng([SEMENTE, 3, int(posto["id"]), posicao + i, 1])
                _ocupar(
                    vagas,
                    vinculos,
                    calendario,
                    sorteio,
                    posto,
                    tipo,
                    posicao + i,
                    primeira,
                    fim_do_posto,
                )
            posicao += turma
    return vagas, vinculos


def _abrir(
    vagas: list[Vaga],
    calendario: Calendario,
    rng: np.random.Generator,
    posto: dict[str, Any],
    tipo: str,
    posicoes: int,
    conhecida: date,
    necessidade: date,
    reposicao: bool,
) -> int:
    """Abre a vaga e decide o destino dela (preenche em tantos dias úteis, ou cancela)."""
    abertura = calendario.somar(conhecida, 0)
    vaga = Vaga(
        posto_id=int(posto["id"]),
        contrato_id=int(posto["contrato_id"]),
        tipo_servico=tipo,
        funcao_id=int(posto["funcao_id"]),
        posicoes=posicoes,
        conhecida=conhecida,
        necessidade=necessidade,
        abertura=abertura,
        reposicao=reposicao,
    )
    if rng.random() < historia.fill_rate(abertura.year):
        fechamento = calendario.somar(abertura, _ttf(rng, tipo, abertura.year))
        if fechamento <= HOJE:
            vaga.fechamento, vaga.situacao = fechamento, "PREENCHIDA"
    else:
        desistencia = calendario.somar(abertura, int(rng.integers(5, 13)))
        if desistencia <= HOJE:
            motivo = str(
                rng.choice(
                    ["PRAZO_EXPIRADO", "CLIENTE_CANCELOU", "PREENCHIDA_CLIENTE"], p=[0.5, 0.3, 0.2]
                )
            )
            vaga.fechamento, vaga.situacao, vaga.motivo_cancelamento = (
                desistencia,
                "CANCELADA",
                motivo,
            )
    vagas.append(vaga)
    return len(vagas) - 1


def _ocupar(
    vagas: list[Vaga],
    vinculos: list[Vinculo],
    calendario: Calendario,
    rng: np.random.Generator,
    posto: dict[str, Any],
    tipo: str,
    posicao: int,
    indice_da_vaga: int,
    fim_do_posto: date | None,
) -> None:
    """A vida de uma posição: preenche, alguém sai, abre reposição, até o posto acabar."""
    while True:
        vaga = vagas[indice_da_vaga]
        if vaga.situacao == "ABERTA":
            return
        if vaga.situacao == "CANCELADA":
            fechou = vaga.fechamento or HOJE
            acabou = fim_do_posto is not None and fechou >= fim_do_posto
            if acabou or rng.random() >= CHANCE_DE_REABRIR:
                return  # a posição fica vazia: é assim que o fill rate vira headcount menor
            indice_da_vaga = _abrir(
                vagas, calendario, rng, posto, tipo, 1, fechou, vaga.necessidade, True
            )
            continue
        inicio = max(vaga.fechamento or HOJE, vaga.necessidade)
        if fim_do_posto is not None and inicio >= fim_do_posto:
            return  # preencheu tarde demais: o posto já tinha acabado
        if inicio > HOJE:
            return  # aprovado, mas começa depois do fim da história
        falta = historia.referencia_do_ano("no_show_primeiro_dia", inicio.year)
        if rng.random() < falta * FATOR_DO_NO_SHOW.get(inicio.year, 1.0):
            vinculos.append(
                Vinculo(
                    indice_da_vaga,
                    int(posto["id"]),
                    posicao,
                    tipo,
                    int(posto["funcao_id"]),
                    inicio,
                    fim=inicio,
                    tipo_desligamento="VOLUNTARIO",
                    motivo="ABANDONO",
                    no_show=True,
                )
            )
            indice_da_vaga = _abrir(vagas, calendario, rng, posto, tipo, 1, inicio, inicio, True)
            continue
        saida = _saida(rng, tipo, inicio, fim_do_posto)
        vinculo = Vinculo(
            indice_da_vaga,
            int(posto["id"]),
            posicao,
            tipo,
            int(posto["funcao_id"]),
            inicio,
            prevista=saida["prevista"],
            irregular=saida["irregular"],
        )
        vinculos.append(vinculo)
        if saida["prorrogado_em"] is not None and saida["prorrogado_em"] <= HOJE:
            vinculo.prorrogado_em, vinculo.novo_termino = (
                saida["prorrogado_em"],
                saida["novo_termino"],
            )
        if saida["fim"] > HOJE:
            return  # segue alocado no fim da história
        vinculo.fim, vinculo.tipo_desligamento, vinculo.motivo = (
            saida["fim"],
            saida["tipo_desligamento"],
            saida["motivo"],
        )
        if fim_do_posto is not None and saida["fim"] >= fim_do_posto:
            return
        conhecida = saida["fim"] - timedelta(days=int(saida["aviso"]))
        if max(conhecida, inicio) > HOJE:
            return
        necessidade = saida["fim"] + timedelta(days=1)
        indice_da_vaga = _abrir(
            vagas, calendario, rng, posto, tipo, 1, max(conhecida, inicio), necessidade, True
        )


def vagas_de_recrutamento(
    contratos: dict[int, dict[str, Any]],
    funcoes_por_setor: dict[int, list[int]],
    feriados: list[date],
) -> list[Vaga]:
    """As vagas sem posto: colocação de efetivos no quadro do cliente, mês a mês."""
    calendario = Calendario(feriados)
    rng = np.random.default_rng([SEMENTE, 3, 0])
    de_recrutamento = [k for k in contratos.values() if k["tipo_servico"] == "RECRUTAMENTO"]
    vagas: list[Vaga] = []
    resto = 0.0
    for mes in historia.meses():
        primeiro, ultimo = historia.limites_do_mes(mes)
        vivos = [
            k
            for k in de_recrutamento
            if k["vigencia_inicio"] <= ultimo
            and (k["dt_encerramento"] is None or k["dt_encerramento"] >= primeiro)
        ]
        ano = primeiro.year
        meses_do_ano = FIM.month if ano == FIM.year else 12
        resto += (
            VAGAS_ABERTAS[ano]
            * PARCELA_DE_VAGAS_DE_RS[ano]
            / meses_do_ano
            * PESO_DO_MES_PARA_RS[primeiro.month - 1]
        )
        while resto >= 1 and vivos:
            resto -= 1
            contrato = vivos[int(rng.integers(len(vivos)))]
            inicio = max(primeiro, contrato["vigencia_inicio"])
            conhecida = inicio + timedelta(
                days=int(rng.integers(0, max(1, (ultimo - inicio).days + 1)))
            )
            abertura = calendario.somar(conhecida, 0)
            funcoes = funcoes_por_setor[int(contrato["cliente_id"])]
            vaga = Vaga(
                posto_id=None,
                contrato_id=int(contrato["id"]),
                tipo_servico="RECRUTAMENTO",
                funcao_id=funcoes[int(rng.integers(len(funcoes)))],
                posicoes=1 if rng.random() < 0.8 else 2,
                conhecida=conhecida,
                necessidade=conhecida + timedelta(days=30),
                abertura=abertura,
            )
            if rng.random() < historia.fill_rate(ano):
                fechamento = calendario.somar(abertura, _ttf(rng, "RECRUTAMENTO", ano))
                if fechamento <= HOJE:
                    vaga.fechamento, vaga.situacao = fechamento, "PREENCHIDA"
            else:
                desistencia = calendario.somar(abertura, int(rng.integers(20, 46)))
                if desistencia <= HOJE:
                    vaga.fechamento, vaga.situacao = desistencia, "CANCELADA"
                    vaga.motivo_cancelamento = (
                        "SEM_ORCAMENTO" if rng.random() < 0.5 else "CLIENTE_CANCELOU"
                    )
            vagas.append(vaga)
        if not vivos:
            resto = min(resto, 3.0)
    return vagas
