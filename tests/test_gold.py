# ruff: noqa: E501
"""A gold provada sem o lake de verdade: um cenário pequeno plantado na bronze, levado à silver
pela construção real, lido pelas views que a gold usa e conferido número a número, à mão.

O cenário: um contrato, um posto de 2 posições que começa em 10/01/2024, duas alocações (uma
termina em 15/02, a outra segue aberta), uma fatura de três itens com imposto que não divide
exato, uma fatura de recrutamento sem item, e o último apontamento em 10/03/2024, que é o
horizonte. A prova com o dado inteiro é `python -m rh_fictalent.gold --publicar`.
"""

from __future__ import annotations

import os
import socket
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import duckdb
import fsspec
import pandas as pd
import pytest
from dotenv import dotenv_values

from rh_fictalent.auditoria import cadernos, esquema
from rh_fictalent.gold import (
    analitico,
    barramento,
    construcao,
    dcl,
    indices,
    modelo,
    regua,
    rls,
    warehouse,
)
from rh_fictalent.ingestao.backfill import CONTROLE
from rh_fictalent.lake import consulta
from rh_fictalent.orquestracao import definicoes
from rh_fictalent.orquestracao import gold as orquestracao
from rh_fictalent.orquestracao import warehouse as orquestracao_dw
from rh_fictalent.orquestracao.recursos import Warehouse
from rh_fictalent.silver import construcao as silver
from rh_fictalent.silver import pseudonimizacao
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.regua import FAMILIAS, Situacao, Veredito

if TYPE_CHECKING:
    from fsspec.spec import AbstractFileSystem

    from rh_fictalent.orquestracao.recursos import Lake

RAIZ = Path(__file__).resolve().parents[1]
REFERENCIA = date(2024, 3, 11)
SEGREDO = b"segredo-de-teste-com-mais-de-trinta-e-dois"  # nunca o do .env
TIPOS = {
    "BIGINT": "BIGINT", "INT": "BIGINT", "INTEGER": "BIGINT", "SMALLINT": "BIGINT",
    "TINYINT": "BIGINT", "MEDIUMINT": "BIGINT", "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",
    "DATE": "DATE", "DATETIME": "TIMESTAMP", "TIMESTAMP": "TIMESTAMP", "TIME": "TIME",
    "DECIMAL": "DECIMAL(18, 4)", "FLOAT": "DOUBLE", "DOUBLE": "DOUBLE",
}  # fmt: skip
LIDAS = sorted(set().union(*(t.fontes for t in modelo.TABELAS)))
FONTES = [t for t in LIDAS if not t.startswith("fontes.")]  # as da silver
PUBLICAS = [t for t in LIDAS if t.startswith("fontes.")]
# o CAGED do cenário: Extrema (312510) e o estado de MG no grupo 78, e o comércio de Extrema
CAGED = pd.DataFrame(
    {
        "competencia": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-01-01", "2024-01-01"]),
        "escopo": ["312510", "312510", "31", "312510"],
        "nome_escopo": ["Extrema", "Extrema", "MG", "Extrema"],
        "nivel": ["município", "município", "UF", "município"],
        "grupo": ["78", "78", "78", "G"],
        "admissoes": [10, 12, 500, 30],
        "desligamentos": [8, 15, 450, 20],
        "saldo": [2, -3, 50, 10],
    }
)


def _etapas(candidatura: int, etapas: tuple[int, ...]) -> list[dict[str, object]]:
    """As etapas do funil que a candidatura venceu, uma linha por etapa."""
    return [
        {
            "id": candidatura * 10 + e,
            "candidatura_id": candidatura,
            "etapa_id": e,
            "resultado": "APROVADO",
        }
        for e in etapas
    ]


CENARIO: dict[str, list[dict[str, object]]] = {
    "cadastro.regiao": [{"id": 1, "nome": "Bragantina"}],
    "cadastro.municipio": [
        {"id": 1, "nome": "Extrema", "uf": "MG", "regiao_id": 1, "codigo_ibge": "3125101"},
        {"id": 2, "nome": "Atibaia", "uf": "SP", "regiao_id": 1},
    ],
    "cadastro.endereco": [
        {"id": 1, "municipio_id": 1, "tipo": "FILIAL"},
        {"id": 2, "municipio_id": 2, "tipo": "FILIAL"},
    ],
    "cadastro.filial": [
        {
            "id": 1,
            "codigo": "F1",
            "nome": "Matriz",
            "tipo": "MATRIZ",
            "endereco_id": 1,
            "ativo": True,
        },
        {
            "id": 2,
            "codigo": "F2",
            "nome": "Filial Dois",
            "tipo": "FILIAL",
            "endereco_id": 2,
            "ativo": True,
        },
    ],
    "cadastro.centro_custo": [
        {"id": 1, "codigo": "CC-F1", "nome": "Operação matriz", "tipo": "FILIAL", "filial_id": 1},
        {"id": 4, "codigo": "CC-RET", "nome": "Retaguarda", "tipo": "RETAGUARDA", "filial_id": 1},
    ],
    "cadastro.funcao": [
        {"id": 1, "codigo": "OP", "nome": "Operador", "cbo": "784205", "familia": "OPERACAO"}
    ],
    "cadastro.escala": [{"id": 1, "codigo": "5X2", "horas_semanais": 44}],
    "cadastro.motivo": [
        {"id": 1, "tipo": "FIM_ALOCACAO", "codigo": "X", "descricao": "Fim do posto"}
    ],
    "cadastro.feriado": [
        {"id": 1, "data": date(2024, 1, 1), "nome": "Confraternização", "abrangencia": "NACIONAL"},
        {
            "id": 2,
            "data": date(2024, 1, 2),
            "nome": "Feriado da cidade",
            "abrangencia": "MUNICIPAL",
            "municipio_id": 1,
        },
    ],
    "comercial.cliente": [
        {"id": 1, "razao_social": "Cliente Um", "municipio_id": 1, "ativo": True}
    ],
    "comercial.contrato": [
        {
            "id": 1,
            "numero": "CT-1",
            "cliente_id": 1,
            "filial_id": 1,
            "tipo_servico": "TERCEIRIZACAO",
            "status": "ATIVO",
            "dt_assinatura": date(2024, 1, 5),
            "vigencia_inicio": date(2024, 1, 10),
            "vigencia_fim": date(2024, 12, 31),
        },
        # recrutamento na segunda filial: uma fatura, sem posto
        {
            "id": 2,
            "numero": "CT-2",
            "cliente_id": 1,
            "filial_id": 2,
            "tipo_servico": "RECRUTAMENTO",
            "status": "ATIVO",
            "dt_assinatura": date(2024, 1, 2),
            "vigencia_inicio": date(2024, 1, 5),
            "vigencia_fim": date(2024, 12, 31),
        },
    ],
    "comercial.contrato_aditivo": [
        {
            "id": 1,
            "contrato_id": 1,
            "numero": 1,
            "tipo": "PRORROGACAO",
            "dt_assinatura": date(2024, 2, 1),
        },
        {
            "id": 2,
            "contrato_id": 1,
            "numero": 2,
            "tipo": "REAJUSTE",
            "dt_assinatura": date(2024, 2, 1),
        },
    ],
    "comercial.posto": [
        {
            "id": 1,
            "contrato_id": 1,
            "funcao_id": 1,
            "quantidade": 2,
            "turno": "MANHA",
            "escala_id": 1,
            "endereco_id": 1,
            "vigencia_inicio": date(2024, 1, 10),
        },
    ],
    "comercial.posto_preco": [
        {
            "id": 1,
            "posto_id": 1,
            "valor_mensal": 1000,
            "vigencia_inicio": date(2024, 1, 10),
            "vigencia_fim": date(2024, 1, 31),
        },
        {"id": 2, "posto_id": 1, "valor_mensal": 1100, "vigencia_inicio": date(2024, 2, 1)},
    ],
    "ats.fonte_candidato": [{"id": 1, "nome": "INDICACAO"}],
    "ats.candidato": [
        {
            "id": 1,
            "nome": "Pessoa Um",
            "cpf": "11111111111",
            "sexo": "F",
            "fonte_id": 1,
            "municipio_id": 1,
            "dt_cadastro": date(2023, 12, 1),
        },
        {
            "id": 2,
            "nome": "Pessoa Dois",
            "cpf": "22222222222",
            "sexo": "M",
            "fonte_id": 1,
            "municipio_id": 1,
            "dt_cadastro": date(2023, 12, 2),
        },
        # excluída no sistema do cliente: não existe para a gold
        {
            "id": 3,
            "nome": "Pessoa Três",
            "cpf": "33333333333",
            "fonte_id": 1,
            "dt_cadastro": date(2023, 12, 3),
            CONTROLE: "2024-01-01 00:00:00",
        },
        {
            "id": 4,
            "nome": "Pessoa Quatro",
            "cpf": "44444444444",
            "sexo": "M",
            "fonte_id": 1,
            "dt_cadastro": date(2023, 12, 4),
        },
        {
            "id": 5,
            "nome": "Pessoa Cinco",
            "cpf": "55555555555",
            "sexo": "F",
            "fonte_id": 1,
            "dt_cadastro": date(2023, 12, 5),
        },
    ],
    "pessoas.colaborador": [
        {
            "id": 1,
            "candidato_id": 1,
            "matricula": "M1",
            "cpf": "11111111111",
            "municipio_id": 1,
            "ativo": True,
        },
        {
            "id": 2,
            "candidato_id": 2,
            "matricula": "M2",
            "cpf": "22222222222",
            "municipio_id": 1,
            "ativo": True,
        },
    ],
    "pessoas.alocacao": [
        {
            "id": 1,
            "colaborador_id": 1,
            "contrato_trabalho_id": 1,
            "posto_id": 1,
            "dt_inicio": date(2024, 1, 10),
            "dt_fim": date(2024, 2, 15),
            "motivo_fim_id": 1,
        },
        # a segunda substitui a primeira e segue aberta
        {
            "id": 2,
            "colaborador_id": 2,
            "contrato_trabalho_id": 2,
            "posto_id": 1,
            "dt_inicio": date(2024, 1, 20),
            "substituindo_alocacao_id": 1,
        },
    ],
    "pessoas.contrato_trabalho": [
        {
            "id": 1,
            "colaborador_id": 1,
            "tipo": "TEMPORARIO",
            "funcao_id": 1,
            "filial_id": 1,
            "dt_admissao": date(2024, 1, 10),
            "dt_prevista_termino": date(2024, 4, 9),
            "dt_rescisao": date(2024, 2, 15),
            "salario_base": Decimal("1500.00"),
            "escala_id": 1,
            "prazo_legal_dias": 90,
            "status": "ENCERRADO",
        },
        {
            "id": 2,
            "colaborador_id": 2,
            "tipo": "TEMPORARIO",
            "funcao_id": 1,
            "filial_id": 1,
            "dt_admissao": date(2024, 1, 20),
            "dt_prevista_termino": date(2024, 4, 19),
            "salario_base": Decimal("1600.00"),
            "escala_id": 1,
            "prazo_legal_dias": 60,
            "status": "ATIVO",
        },
    ],
    "pessoas.contrato_trabalho_prorrogacao": [
        {
            "id": 1,
            "contrato_trabalho_id": 2,
            "dt_assinatura": date(2024, 3, 1),
            "dt_novo_termino": date(2024, 7, 18),
            "dias_adicionais": 90,
        },
    ],
    "pessoas.desligamento": [
        {
            "id": 1,
            "contrato_trabalho_id": 1,
            "dt_desligamento": date(2024, 2, 15),
            "tipo": "VOLUNTARIO",
            "motivo_id": 1,
            "dias_aviso_previo": 0,
            "valor_rescisao": Decimal("800.00"),
        },
    ],
    "comercial.contrato_ocorrencia": [
        {
            "id": 1,
            "contrato_id": 1,
            "posto_id": 1,
            "dt_ocorrencia": date(2024, 2, 1),
            "tipo": "RECLAMACAO",
            "descricao": "Posto ficou descoberto no turno",
        },
        {
            "id": 2,
            "contrato_id": 1,
            "dt_ocorrencia": date(2024, 2, 20),
            "tipo": "ELOGIO",
            "descricao": "Cliente elogiou o atendimento da equipe",
        },
    ],
    "ats.etapa_funil": [
        {"id": 1, "codigo": "TRIAGEM", "nome": "Triagem de currículo", "ordem": 1},
        {"id": 2, "codigo": "ENTREVISTA_INTERNA", "nome": "Entrevista interna", "ordem": 2},
        {"id": 3, "codigo": "ENCAMINHAMENTO", "nome": "Encaminhamento ao cliente", "ordem": 3},
        {"id": 4, "codigo": "ENTREVISTA_CLIENTE", "nome": "Entrevista no cliente", "ordem": 4},
        {"id": 5, "codigo": "APROVACAO", "nome": "Aprovação e admissão", "ordem": 5},
    ],
    "ats.requisicao": [
        {
            "id": 1,
            "numero": "RQ-1",
            "cliente_id": 1,
            "contrato_id": 1,
            "posto_id": 1,
            "quantidade": 2,
            "dt_abertura": date(2023, 12, 15),
            "dt_necessidade": date(2024, 1, 10),
            "prioridade": "NORMAL",
            "status": "ATENDIDA",
        },
        # recrutamento: sem posto
        {
            "id": 2,
            "numero": "RQ-2",
            "cliente_id": 1,
            "contrato_id": 1,
            "quantidade": 1,
            "dt_abertura": date(2024, 2, 1),
            "dt_necessidade": date(2024, 3, 1),
            "prioridade": "ALTA",
            "status": "EM_ATENDIMENTO",
        },
    ],
    "ats.vaga": [
        {
            "id": 1,
            "requisicao_id": 1,
            "codigo": "VG-1",
            "titulo": "Operador",
            "funcao_id": 1,
            "filial_id": 1,
            "quantidade_posicoes": 2,
            "dt_abertura": date(2023, 12, 18),
            "dt_fechamento": date(2024, 1, 8),
            "status": "PREENCHIDA",
            "salario_previsto": Decimal("1500.00"),
        },
        {
            "id": 2,
            "requisicao_id": 2,
            "codigo": "VG-2",
            "titulo": "Operador",
            "funcao_id": 1,
            "filial_id": 1,
            "quantidade_posicoes": 1,
            "dt_abertura": date(2024, 2, 5),
            "status": "ABERTA",
        },
    ],
    "ats.candidatura": [
        {
            "id": 1,
            "vaga_id": 1,
            "candidato_id": 1,
            "dt_inscricao": date(2023, 12, 20),
            "status": "APROVADA",
            "dt_conclusao": date(2024, 1, 5),
        },
        {
            "id": 2,
            "vaga_id": 1,
            "candidato_id": 2,
            "dt_inscricao": date(2023, 12, 22),
            "status": "APROVADA",
            "dt_conclusao": date(2024, 1, 8),
        },
        {
            "id": 3,
            "vaga_id": 1,
            "candidato_id": 4,
            "dt_inscricao": date(2023, 12, 21),
            "status": "REPROVADA",
            "dt_conclusao": date(2023, 12, 28),
            "motivo_reprovacao_id": 1,
        },
        {
            "id": 4,
            "vaga_id": 2,
            "candidato_id": 4,
            "dt_inscricao": date(2024, 2, 6),
            "status": "EM_ANDAMENTO",
        },
        # aprovada que nunca virou vínculo
        {
            "id": 5,
            "vaga_id": 1,
            "candidato_id": 5,
            "dt_inscricao": date(2023, 12, 23),
            "status": "APROVADA",
            "dt_conclusao": date(2024, 1, 9),
        },
    ],
    "ats.candidatura_etapa": [
        *_etapas(1, (1, 2, 3, 5)),
        *_etapas(2, (1, 2, 3, 4, 5)),
        {"id": 31, "candidatura_id": 3, "etapa_id": 1, "resultado": "REPROVADO", "motivo_id": 1},
        {"id": 41, "candidatura_id": 4, "etapa_id": 1, "resultado": "APROVADO"},
        {"id": 42, "candidatura_id": 4, "etapa_id": 2, "resultado": "PENDENTE"},
        *_etapas(5, (1, 2, 3, 5)),
    ],
    "ats.entrevista": [
        {
            "id": 1,
            "candidatura_id": 1,
            "tipo": "INTERNA",
            "fl_compareceu": True,
            "resultado": "APROVADO",
        },
        {
            "id": 2,
            "candidatura_id": 2,
            "tipo": "INTERNA",
            "fl_compareceu": True,
            "resultado": "APROVADO",
        },
        {
            "id": 3,
            "candidatura_id": 2,
            "tipo": "CLIENTE",
            "fl_compareceu": True,
            "resultado": "APROVADO",
        },
        {
            "id": 4,
            "candidatura_id": 5,
            "tipo": "INTERNA",
            "fl_compareceu": False,
            "resultado": "NAO_COMPARECEU",
        },
    ],
    "ponto.apontamento": [
        {
            "id": 1,
            "colaborador_id": 2,
            "alocacao_id": 2,
            "data": date(2024, 3, 10),
            "status": "NORMAL",
            "horas_trabalhadas": 8,
            "horas_extras": 0,
            "horas_noturnas": 0,
        },
        {
            "id": 2,
            "colaborador_id": 1,
            "alocacao_id": 1,
            "data": date(2024, 1, 15),
            "status": "NORMAL",
            "horas_trabalhadas": 8,
            "horas_extras": 1,
            "horas_noturnas": 0,
        },
        {
            "id": 3,
            "colaborador_id": 1,
            "alocacao_id": 1,
            "data": date(2024, 1, 16),
            "status": "FALTA",
            "horas_trabalhadas": 0,
            "horas_extras": 0,
            "horas_noturnas": 0,
        },
        {
            "id": 4,
            "colaborador_id": 2,
            "alocacao_id": 2,
            "data": date(2024, 2, 1),
            "status": "FERIADO",
            "horas_trabalhadas": 0,
            "horas_extras": 0,
            "horas_noturnas": 0,
        },
    ],
    "ponto.ocorrencia_ponto": [
        {"id": 1, "apontamento_id": 2, "tipo": "ATRASO", "minutos": 15},
        {"id": 2, "apontamento_id": 3, "tipo": "FALTA_INJUSTIFICADA", "minutos": 0},
    ],
    # conformidade: o ASO da pessoa 1 vence em janeiro; o da pessoa 2 vence 20 dias depois do fim de fevereiro
    "sst.aso": [
        {
            "id": 1,
            "colaborador_id": 1,
            "tipo_exame_id": 1,
            "dt_exame": date(2024, 1, 8),
            "dt_validade": date(2024, 1, 20),
            "resultado": "APTO",
        },
        {
            "id": 2,
            "colaborador_id": 2,
            "tipo_exame_id": 1,
            "dt_exame": date(2024, 1, 18),
            "dt_validade": date(2024, 3, 20),
            "resultado": "APTO",
        },
    ],
    "sst.programa_sst": [
        {
            "id": 1,
            "tipo": "PCMSO",
            "cliente_id": 1,
            "contrato_id": 1,
            "dt_elaboracao": date(2023, 12, 1),
            "dt_validade": date(2024, 2, 15),
        },
        {
            "id": 2,
            "tipo": "PGR",
            "cliente_id": 1,
            "contrato_id": 1,
            "dt_elaboracao": date(2024, 1, 1),
            "dt_validade": date(2025, 1, 1),
        },
    ],
    # o curso 1 é obrigatório para a função 1; só a pessoa 2 tem certificado
    "treinamento.curso_funcao": [
        {"id": 1, "curso_id": 1, "funcao_id": 1, "fl_obrigatorio": True},
        {"id": 2, "curso_id": 2, "funcao_id": 1, "fl_obrigatorio": False},
    ],
    "treinamento.turma": [
        {
            "id": 1,
            "curso_id": 1,
            "filial_id": 1,
            "dt_inicio": date(2024, 1, 5),
            "dt_fim": date(2024, 1, 6),
        }
    ],
    "treinamento.turma_participante": [
        {"id": 1, "turma_id": 1, "colaborador_id": 2, "fl_aprovado": True}
    ],
    "treinamento.certificado": [
        {
            "id": 1,
            "turma_participante_id": 1,
            "numero": "C-1",
            "dt_emissao": date(2024, 1, 6),
            "dt_validade": date(2025, 1, 5),
        }
    ],
    "financeiro.fatura": [
        {
            "id": 1,
            "numero": "NF-1",
            "cliente_id": 1,
            "contrato_id": 1,
            "competencia": date(2024, 1, 1),
            "dt_emissao": date(2024, 2, 1),
            "valor_bruto": Decimal("100.00"),
            "valor_impostos": Decimal("10.01"),
            "valor_liquido": Decimal("89.99"),
            "status": "EMITIDA",
        },
        {
            "id": 2,
            "numero": "NF-2",
            "cliente_id": 1,
            "contrato_id": 1,
            "competencia": date(2024, 2, 1),
            "dt_emissao": date(2024, 3, 1),
            "valor_bruto": Decimal("50.00"),
            "valor_impostos": Decimal("5.00"),
            "valor_liquido": Decimal("45.00"),
            "status": "EMITIDA",
        },
        {
            "id": 3,
            "numero": "NF-3",
            "cliente_id": 1,
            "contrato_id": 2,
            "competencia": date(2024, 1, 1),
            "dt_emissao": date(2024, 1, 20),
            "valor_bruto": Decimal("50.00"),
            "valor_impostos": Decimal("5.00"),
            "valor_liquido": Decimal("45.00"),
            "status": "QUITADA",
        },
    ],
    "financeiro.titulo_receber": [
        {
            "id": 1,
            "fatura_id": 1,
            "cliente_id": 1,
            "numero_parcela": 1,
            "dt_vencimento": date(2024, 3, 2),
            "valor": Decimal("89.99"),
            "status": "PAGO",
            "dt_pagamento": date(2024, 3, 5),
            "valor_pago": Decimal("89.99"),
        },
        # vencida antes do horizonte e ainda sem pagamento
        {
            "id": 2,
            "fatura_id": 2,
            "cliente_id": 1,
            "numero_parcela": 1,
            "dt_vencimento": date(2024, 3, 1),
            "valor": Decimal("45.00"),
            "status": "ABERTO",
        },
        {
            "id": 3,
            "fatura_id": 3,
            "cliente_id": 1,
            "numero_parcela": 1,
            "dt_vencimento": date(2024, 2, 1),
            "valor": Decimal("45.00"),
            "status": "PAGO",
            "dt_pagamento": date(2024, 1, 30),
            "valor_pago": Decimal("45.00"),
        },
    ],
    # o ISS tem município (um por filial); o tributo 2 é federal e se rateia pelo faturamento
    "financeiro.imposto_apurado": [
        {
            "id": 1,
            "competencia": date(2024, 1, 1),
            "tributo_id": 1,
            "municipio_id": 1,
            "base_calculo": Decimal("100.00"),
            "valor_devido": Decimal("5.00"),
            "titulo_pagar_id": 1,
        },
        {
            "id": 2,
            "competencia": date(2024, 1, 1),
            "tributo_id": 1,
            "municipio_id": 2,
            "base_calculo": Decimal("50.00"),
            "valor_devido": Decimal("2.50"),
            "titulo_pagar_id": 1,
        },
        {
            "id": 3,
            "competencia": date(2024, 1, 1),
            "tributo_id": 2,
            "base_calculo": Decimal("150.00"),
            "valor_devido": Decimal("3.00"),
            "titulo_pagar_id": 1,
        },
    ],
    "financeiro.titulo_pagar": [
        {
            "id": 1,
            "tipo": "IMPOSTOS",
            "centro_custo_id": 4,
            "competencia": date(2024, 1, 1),
            "dt_vencimento": date(2024, 2, 20),
            "valor": Decimal("10.50"),
            "status": "PAGO",
        },
        {
            "id": 2,
            "tipo": "FORNECEDOR",
            "centro_custo_id": 4,
            "competencia": date(2024, 1, 1),
            "dt_vencimento": date(2024, 2, 10),
            "valor": Decimal("30.00"),
            "status": "PAGO",
        },
        # a folha da filial não é despesa da retaguarda: já está no rateio de custo
        {
            "id": 3,
            "tipo": "FOLHA",
            "centro_custo_id": 1,
            "competencia": date(2024, 1, 1),
            "dt_vencimento": date(2024, 2, 5),
            "valor": Decimal("40.00"),
            "status": "PAGO",
        },
    ],
    "financeiro.consolidado_gerencial": [
        {
            "id": 1,
            "competencia": date(2024, 1, 1),
            "filial_id": 1,
            "headcount_informado": 3,
            "vagas_abertas_informado": 1,
            "faturamento_informado": Decimal("110.00"),
            "custo_informado": Decimal("55.00"),
            "dt_lancamento": date(2024, 2, 3),
            "origem": "PLANILHA",
        },
    ],
    "financeiro.fatura_item": [
        {
            "id": 1,
            "fatura_id": 1,
            "posto_id": 1,
            "valor_postos": Decimal("33.33"),
            "valor_total": Decimal("33.33"),
        },
        {
            "id": 2,
            "fatura_id": 1,
            "posto_id": 1,
            "valor_postos": Decimal("33.33"),
            "valor_total": Decimal("33.33"),
        },
        {
            "id": 3,
            "fatura_id": 1,
            "posto_id": 1,
            "valor_postos": Decimal("33.34"),
            "valor_total": Decimal("33.34"),
        },
    ],
    "folha.rateio_custo": [
        {
            "id": 1,
            "competencia": date(2024, 1, 1),
            "colaborador_id": 1,
            "alocacao_id": 1,
            "contrato_id": 1,
            "posto_id": 1,
            "valor_salario": Decimal("40.00"),
            "custo_total": Decimal("60.00"),
        },
        # custo lançado num mês depois do horizonte: não pode sumir da gold
        {
            "id": 2,
            "competencia": date(2024, 4, 1),
            "colaborador_id": 2,
            "alocacao_id": 2,
            "contrato_id": 1,
            "posto_id": 1,
            "valor_salario": Decimal("20.00"),
            "custo_total": Decimal("25.00"),
        },
    ],
}


class _LakeLocal:
    """O recurso `Lake` sobre uma pasta: o mesmo contrato (`caminho`, `sistema`), sem S3."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz

    def caminho(self, camada: str, *partes: str) -> str:
        return "/".join((str(self.raiz), camada, *partes))

    def sistema(self) -> AbstractFileSystem:
        return fsspec.filesystem("file")


def _bronze() -> duckdb.DuckDBPyConnection:
    """As tabelas da DDL na memória, com os nomes da réplica, e o cenário plantado nelas."""
    con = duckdb.connect()
    for tabela in esquema.ler().values():
        colunas = ", ".join(f'"{c.nome}" {TIPOS.get(c.tipo, "VARCHAR")}' for c in tabela.colunas)
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{tabela.esquema}"')
        con.execute(f"CREATE TABLE {tabela.qualificado} ({colunas}, {CONTROLE} TIMESTAMP)")
    for tabela_, linhas in CENARIO.items():
        for linha in linhas:
            marcadores = ", ".join("?" for _ in linha)
            con.execute(
                f"INSERT INTO {tabela_} ({', '.join(linha)}) VALUES ({marcadores})",
                list(linha.values()),
            )  # noqa: S608
    return con


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory) -> Lake:
    """A silver do cenário, gravada em parquet pela construção de verdade."""
    assert set(CENARIO) == set(FONTES), "o cenário tem de alimentar toda tabela que a gold lê"
    local = cast("Lake", _LakeLocal(tmp_path_factory.mktemp("lake")))
    con = _bronze()
    pseudonimizacao.registrar(con, SEGREDO)
    for tabela in FONTES:
        origem = f"(SELECT *, 2024 AS {silver.ANO} FROM {tabela})"  # noqa: S608
        silver.construir(con, tabela, origem, REFERENCIA)
        assert silver.gravar(con, local, tabela, em_conferencia=False)
    con.close()
    assert PUBLICAS == ["fontes.caged_movimentacao"]
    pasta = Path(local.caminho("fontes", "caged"))
    pasta.mkdir(parents=True)
    CAGED.to_parquet(pasta / "movimentacao.parquet", index=False)
    return local


def _abrir(lake: Lake) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    caminhos = {t: lake.caminho("silver", *t.split("."), "ano=*.parquet") for t in FONTES}
    consulta.criar_views_da_silver(con, caminhos)
    consulta.criar_views_das_fontes(
        con, {"caged_movimentacao": lake.caminho("fontes", "caged", "movimentacao.parquet")}
    )
    return con


@pytest.fixture
def gold(lake: Lake) -> duckdb.DuckDBPyConnection:
    """A gold inteira montada na memória sobre a silver do cenário."""
    con = _abrir(lake)
    resultados = construcao.construir(con)
    assert {n: r.problemas for n, r in resultados.items() if not r.aprovada} == {}
    return con


def _linhas(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict[str, object]]:
    cursor = con.execute(sql)
    nomes = [d[0] for d in cursor.description]
    return [dict(zip(nomes, linha, strict=True)) for linha in cursor.fetchall()]


# ------------------------------------------------------------------ o modelo contra a matriz


def test_o_modelo_implementa_a_matriz_aprovada() -> None:
    nomes = [t.nome for t in modelo.TABELAS]
    assert len(nomes) == len(set(nomes))
    for t in modelo.TABELAS:
        if t.fato:
            previsto = barramento.fato(t.nome)
            assert set(t.referencias.values()) == set(previsto.dimensoes), t.nome
            assert t.particao and t.conservacoes, f"{t.nome}: fato sem partição ou sem conservação"
            for marca in previsto.marcas:
                assert marca in t.sql, (t.nome, marca)
        else:
            assert barramento.dimensao(t.nome).prioridade == 1 and t.chave == ("id",)
        na_matriz = set(
            barramento.fato(t.nome).fontes if t.fato else barramento.dimensao(t.nome).fontes
        )
        assert na_matriz <= t.fontes, (t.nome, na_matriz - t.fontes)
        implicitas = set(modelo.FONTES_DO_HORIZONTE) | set(modelo.FONTES_DO_CALENDARIO)
        assert t.fontes - na_matriz <= implicitas, (t.nome, t.fontes - na_matriz - implicitas)


def test_a_dimensao_vem_antes_de_quem_a_referencia() -> None:
    ordem = [t.nome for t in modelo.TABELAS]
    for t in modelo.TABELAS:
        for dimensao in t.referencias.values():
            assert ordem.index(dimensao) < ordem.index(t.nome), (t.nome, dimensao)


# ------------------------------------------------------------------ a leitura da silver


def test_a_gold_so_enxerga_as_linhas_vivas_da_silver(lake: Lake) -> None:
    con = _abrir(lake)
    vivos = con.execute("SELECT list(id ORDER BY id) FROM silver.ats.candidato").fetchall()[0][0]
    assert vivos == [1, 2, 4, 5]
    colunas = {c[0] for c in con.execute("DESCRIBE silver.ats.candidato").fetchall()}
    assert CONTROLE not in colunas and "cpf" not in colunas and "nome" not in colunas
    arquivo = lake.caminho("silver", "ats", "candidato", "ano=2024.parquet")
    assert con.execute(f"SELECT count(*) FROM '{arquivo}'").fetchall()[0][0] == 5  # noqa: S608


# ------------------------------------------------------------------ as dimensões


def test_o_horizonte_e_o_ultimo_dia_com_movimento(lake: Lake) -> None:
    assert modelo.preparar(_abrir(lake)) == "2024-03-10"


def test_sem_movimento_nao_ha_horizonte() -> None:
    con = duckdb.connect()
    con.execute("ATTACH ':memory:' AS silver")
    con.execute("CREATE SCHEMA silver.ponto; CREATE SCHEMA silver.pessoas")
    con.execute("CREATE TABLE silver.ponto.apontamento (data DATE)")
    con.execute("CREATE TABLE silver.pessoas.alocacao (dt_inicio DATE, dt_fim DATE)")
    with pytest.raises(RuntimeError, match="sem horizonte"):
        modelo.preparar(con)


def test_o_calendario_conhece_dia_util_e_feriado_nacional(gold: duckdb.DuckDBPyConnection) -> None:
    dias = {
        d["id"]: d
        for d in _linhas(gold, "SELECT * FROM gold.dim_data WHERE id BETWEEN 20240101 AND 20240107")
    }
    assert dias[20240101]["feriado_nacional"] and not dias[20240101]["dia_util"]
    # o feriado municipal não fecha o calendário da empresa inteira
    assert dias[20240102]["dia_util"] and not dias[20240102]["feriado_nacional"]
    assert not dias[20240106]["dia_util"] and dias[20240106]["dia_da_semana"] == 6
    janeiro = _linhas(gold, "SELECT * FROM gold.dim_mes WHERE id = 202401")[0]
    assert (janeiro["dias"], janeiro["dias_uteis"]) == (31, 22)
    fevereiro = _linhas(gold, "SELECT * FROM gold.dim_mes WHERE id = 202402")[0]
    assert (fevereiro["dias"], fevereiro["ultimo_dia"]) == (29, date(2024, 2, 29))
    n, primeiro, ultimo = gold.execute(
        "SELECT count(*), min(data), max(data) FROM gold.dim_data"
    ).fetchall()[0]
    # 2922 dias (até o ano seguinte ao horizonte) e a linha 0
    assert (n, primeiro, ultimo) == (2923, date(2018, 1, 1), date(2025, 12, 31))


def test_toda_dimensao_tem_a_linha_nao_se_aplica(gold: duckdb.DuckDBPyConnection) -> None:
    for t in modelo.TABELAS:
        if not t.fato:
            assert (
                gold.execute(f"SELECT count(*) FROM gold.{t.nome} WHERE id = 0").fetchall()[0][0]
                == 1
            ), t.nome  # noqa: S608


def test_a_dimensao_de_pessoa_nao_identifica_ninguem(gold: duckdb.DuckDBPyConnection) -> None:
    for nome in modelo.DIMENSOES_DE_PESSOA:
        colunas = {c[0] for c in gold.execute(f"DESCRIBE gold.{nome}").fetchall()}
        assert not colunas & set(modelo.IDENTIDADE), nome
        assert not [c for c in colunas if c.endswith("_chave")], nome
    colaborador = _linhas(gold, "SELECT * FROM gold.dim_colaborador WHERE id = 1")[0]
    assert (
        colaborador["sexo"],
        colaborador["fonte_de_recrutamento"],
        colaborador["municipio"],
    ) == ("F", "INDICACAO", "Extrema")
    candidatos = gold.execute("SELECT list(id ORDER BY id) FROM gold.dim_candidato").fetchall()[0][
        0
    ]
    assert candidatos == [0, 1, 2, 4, 5]  # a 3 foi excluída no sistema do cliente


def test_o_contrato_e_o_posto_carregam_a_hierarquia(gold: duckdb.DuckDBPyConnection) -> None:
    contrato = _linhas(gold, "SELECT * FROM gold.dim_contrato WHERE id = 1")[0]
    assert (contrato["prorrogacoes"], contrato["cliente_id"], contrato["filial_id"]) == (1, 1, 1)
    assert contrato["status_informado"] == "ATIVO" and contrato["situacao_derivada"] is not None
    posto = _linhas(gold, "SELECT * FROM gold.dim_posto WHERE id = 1")[0]
    assert (posto["posicoes"], posto["escala"], posto["municipio"], posto["cliente_id"]) == (
        2,
        "5X2",
        "Extrema",
        1,
    )


# ------------------------------------------------------------------ os fatos


def test_o_imposto_da_fatura_e_repartido_e_fecha_ao_centavo(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    itens = _linhas(
        gold, "SELECT * FROM gold.fato_faturamento WHERE fatura_id = 1 ORDER BY fatura_item_id"
    )
    assert [i["valor_impostos"] for i in itens] == [
        Decimal("3.34"),
        Decimal("3.34"),
        Decimal("3.33"),
    ]
    assert sum(cast("Decimal", i["valor_liquido"]) for i in itens) == Decimal("89.99")
    assert {
        (i["mes_id"], i["data_emissao_id"], i["posto_id"], i["funcao_id"], i["filial_id"])
        for i in itens
    } == {(202401, 20240201, 1, 1, 1)}


def test_a_fatura_sem_item_entra_numa_linha_sem_posto(gold: duckdb.DuckDBPyConnection) -> None:
    (linha,) = _linhas(gold, "SELECT * FROM gold.fato_faturamento WHERE fatura_id = 2")
    assert (linha["fatura_item_id"], linha["posto_id"], linha["funcao_id"]) == (0, 0, 0)
    assert (linha["valor_bruto"], linha["valor_impostos"], linha["valor_liquido"]) == (
        Decimal("50.00"),
        Decimal("5.00"),
        Decimal("45.00"),
    )
    assert linha["valor_postos"] is None and linha["ano"] == 2024


def test_o_custo_de_pessoal_fica_no_grao_do_rateio(gold: duckdb.DuckDBPyConnection) -> None:
    linhas = _linhas(gold, "SELECT * FROM gold.fato_custo_pessoal ORDER BY id")
    assert [
        (
            c["mes_id"],
            c["colaborador_id"],
            c["posto_id"],
            c["cliente_id"],
            c["filial_id"],
            c["funcao_id"],
            c["custo_total"],
        )
        for c in linhas
    ] == [
        (202401, 1, 1, 1, 1, 1, Decimal("60.00")),
        (202404, 2, 1, 1, 1, 1, Decimal("25.00")),
    ]


def test_o_posto_por_mes_conta_dias_pessoas_e_margem(gold: duckdb.DuckDBPyConnection) -> None:
    meses = {
        m["mes_id"]: m for m in _linhas(gold, "SELECT * FROM gold.fato_posto_mes ORDER BY mes_id")
    }
    assert list(meses) == [202401, 202402, 202403, 202404]

    janeiro = meses[202401]  # o posto começa no dia 10: 22 dias, 2 posições
    assert (janeiro["dias_vigentes"], janeiro["posicao_dias_contratados"]) == (22, 44)
    assert (janeiro["pessoa_dias_alocados"], janeiro["posicao_dias_descobertos"]) == (22 + 12, 10)
    assert janeiro["taxa_de_ocupacao"] == pytest.approx(34 / 44)
    assert (janeiro["pessoas_no_fim_do_mes"], janeiro["entradas"], janeiro["saidas"]) == (2, 2, 0)
    assert (
        janeiro["preco_mensal_vigente"],
        janeiro["receita"],
        janeiro["custo_pessoal"],
        janeiro["margem"],
    ) == (1000, Decimal("100.00"), Decimal("60.00"), Decimal("40.00"))
    assert janeiro["margem_pct"] == pytest.approx(0.4) and janeiro["faturado"]

    fevereiro = meses[202402]  # 29 dias; a primeira alocação sai no dia 15
    assert (fevereiro["posicao_dias_contratados"], fevereiro["pessoa_dias_alocados"]) == (
        58,
        15 + 29,
    )
    assert (fevereiro["pessoas_no_fim_do_mes"], fevereiro["entradas"], fevereiro["saidas"]) == (
        1,
        0,
        1,
    )
    assert fevereiro["preco_mensal_vigente"] == 1100  # o preço reajustado em fevereiro
    assert (
        not fevereiro["faturado"] and fevereiro["receita"] == 0 and fevereiro["margem_pct"] is None
    )

    marco = meses[202403]  # o mês do horizonte: medido até o dia 10 e marcado
    assert marco["mes_parcial"] and not janeiro["mes_parcial"]
    assert (
        marco["dias_vigentes"],
        marco["posicao_dias_contratados"],
        marco["pessoa_dias_alocados"],
    ) == (10, 20, 10)
    assert marco["pessoas_no_fim_do_mes"] == 1

    abril = meses[202404]  # só custo, depois do horizonte: a linha existe e diz que está fora
    assert abril["fora_da_vigencia"] and abril["custo_pessoal"] == Decimal("25.00")
    assert abril["taxa_de_ocupacao"] is None and abril["margem"] == Decimal("-25.00")


def test_o_contrato_acumula_a_vida_dele(gold: duckdb.DuckDBPyConnection) -> None:
    (k,) = _linhas(gold, "SELECT * FROM gold.fato_contrato WHERE contrato_id = 1")
    assert (
        k["data_inicio_id"],
        k["data_fim_id"],
        k["data_encerramento_id"],
        k["motivo_encerramento_id"],
    ) == (20240110, 20241231, 0, 0)
    assert not k["encerrado"] and k["meses_de_vida"] == 2  # de 10/01 ao horizonte, 10/03
    assert (k["prorrogacoes"], k["reajustes"], k["postos"], k["posicoes"]) == (1, 1, 1, 2)
    assert (k["reclamacoes"], k["elogios"], k["avisos_de_rescisao"], k["faturas"]) == (1, 1, 0, 2)
    assert (k["receita_bruta"], k["receita_liquida"]) == (Decimal("150.00"), Decimal("134.99"))
    (recrutamento,) = _linhas(gold, "SELECT * FROM gold.fato_contrato WHERE contrato_id = 2")
    assert (recrutamento["postos"], recrutamento["faturas"], recrutamento["receita_bruta"]) == (
        0,
        1,
        Decimal("50.00"),
    )


def test_a_vaga_conta_candidaturas_e_dias(gold: duckdb.DuckDBPyConnection) -> None:
    vagas = {v["vaga_id"]: v for v in _linhas(gold, "SELECT * FROM gold.fato_vaga")}
    preenchida, aberta = vagas[1], vagas[2]
    assert (preenchida["candidaturas"], preenchida["aprovados"], preenchida["posicoes"]) == (
        4,
        3,
        2,
    )
    assert (
        preenchida["preenchida"]
        and not preenchida["aberta"]
        and preenchida["dias_ate_preencher"] == 21
    )
    assert preenchida["dias_em_aberto"] is None and preenchida["dias_alem_da_necessidade"] == -2
    assert (preenchida["contrato_id"], preenchida["posto_id"], preenchida["cliente_id"]) == (
        1,
        1,
        1,
    )
    assert (
        aberta["aberta"] and aberta["dias_em_aberto"] == 34 and aberta["dias_ate_preencher"] is None
    )
    assert (
        aberta["posto_id"],
        aberta["em_andamento"],
        aberta["data_fechamento_id"],
        aberta["dias_alem_da_necessidade"],
    ) == (0, 1, 0, 9)


def test_a_candidatura_tem_as_etapas_em_colunas_e_a_admissao_casada(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    c = {x["candidatura_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_candidatura")}
    assert c[1]["admitida"] and (
        c[1]["contrato_trabalho_id"],
        c[1]["data_admissao_id"],
        c[1]["dias_ate_a_admissao"],
    ) == (1, 20240110, 5)
    assert c[2]["admitida"] and (c[2]["contrato_trabalho_id"], c[2]["dias_ate_a_admissao"]) == (
        2,
        12,
    )
    assert (
        c[1]["dias_no_funil"],
        c[1]["entrevistas"],
        c[1]["chegou_a_entrevista_no_cliente"],
        c[1]["chegou_a_aprovacao"],
    ) == (16, 1, False, True)
    assert (
        c[2]["entrevistas"],
        c[2]["entrevistas_no_cliente"],
        c[2]["chegou_a_entrevista_no_cliente"],
    ) == (2, 1, True)
    assert c[3]["reprovada"] and c[3]["motivo_id"] == 1 and not c[3]["chegou_a_entrevista_interna"]
    assert c[4]["em_andamento"] and (c[4]["data_conclusao_id"], c[4]["dias_no_funil"]) == (0, 33)
    assert (
        c[5]["aprovada"]
        and not c[5]["admitida"]
        and c[5]["aprovada_sem_admissao"]
        and not c[5]["aguardando_admissao"]
    )
    assert (c[5]["faltas_a_entrevista"], c[5]["contrato_trabalho_id"], c[5]["fonte"]) == (
        1,
        0,
        "INDICACAO",
    )
    assert {x["filial_id"] for x in c.values()} == {1} and {
        x["cliente_id"] for x in c.values()
    } == {1}


def test_a_alocacao_e_o_vinculo_contam_os_mesmos_dias(gold: duckdb.DuckDBPyConnection) -> None:
    a = {x["alocacao_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_alocacao")}
    assert a[1]["encerrada"] and (
        a[1]["dias_alocada"],
        a[1]["motivo_fim_id"],
        a[1]["data_fim_id"],
    ) == (37, 1, 20240215)
    assert (
        not a[1]["em_substituicao"]
        and a[2]["em_substituicao"]
        and a[2]["substituindo_alocacao_id"] == 1
    )
    assert not a[2]["encerrada"] and (
        a[2]["dias_alocada"],
        a[2]["data_fim_id"],
        a[2]["motivo_fim_id"],
    ) == (51, 0, 0)
    assert {x["efetivada_pelo_cliente"] for x in a.values()} == {False}
    assert {
        (x["contrato_id"], x["cliente_id"], x["filial_id"], x["funcao_id"], x["tipo_de_vinculo"])
        for x in a.values()
    } == {(1, 1, 1, 1, "TEMPORARIO")}

    v = {x["contrato_trabalho_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_vinculo")}
    assert (
        v[1]["desligado"]
        and v[1]["saiu_em_ate_90_dias"]
        and (v[1]["dias_de_vinculo"], v[1]["tipo_de_desligamento"]) == (36, "VOLUNTARIO")
    )
    assert (v[1]["motivo_desligamento_id"], v[1]["valor_rescisao"], v[1]["prorrogacoes"]) == (
        1,
        Decimal("800.00"),
        0,
    )
    assert (
        not v[2]["desligado"] and not v[2]["saiu_em_ate_90_dias"] and v[2]["dias_de_vinculo"] == 50
    )
    assert (
        v[2]["prorrogacoes"],
        v[2]["dias_prorrogados"],
        v[2]["data_termino_previsto_id"],
        v[2]["data_rescisao_id"],
    ) == (1, 90, 20240419, 0)
    assert v[2]["tipo_de_desligamento"] is None and v[2]["valor_rescisao"] is None


def test_o_dia_de_ponto_carrega_as_ocorrencias(gold: duckdb.DuckDBPyConnection) -> None:
    d = {x["apontamento_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_ponto_dia")}
    assert {
        (x["posto_id"], x["contrato_id"], x["cliente_id"], x["filial_id"], x["funcao_id"])
        for x in d.values()
    } == {(1, 1, 1, 1, 1)}
    assert d[2]["trabalhou"] and (
        d[2]["horas_trabalhadas"],
        d[2]["horas_extras"],
        d[2]["minutos_de_atraso"],
    ) == (8, 1, 15)
    assert (
        d[3]["falta"]
        and d[3]["falta_injustificada"]
        and d[3]["dia_previsto"]
        and d[3]["minutos_de_atraso"] == 0
    )
    assert d[4]["feriado"] and not d[4]["dia_previsto"] and not d[4]["falta"]
    assert d[1]["data_id"] == 20240310 and d[1]["colaborador_id"] == 2
    assert d[1]["fim_de_semana"] and not d[2]["fim_de_semana"]  # 10/03/2024 é domingo


def test_o_recebimento_le_a_situacao_das_datas_no_horizonte(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    r = {x["titulo_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_recebimento")}
    assert (r[1]["situacao"], r[1]["dias_de_atraso"], r[1]["pago"], r[1]["vencido_e_nao_pago"]) == (
        "pago com atraso",
        3,
        True,
        False,
    )
    assert (
        r[2]["situacao"],
        r[2]["dias_de_atraso"],
        r[2]["vencido_e_nao_pago"],
        r[2]["data_pagamento_id"],
    ) == ("vencido", 9, True, 0)
    assert (r[3]["situacao"], r[3]["dias_de_atraso"], r[3]["filial_id"], r[3]["contrato_id"]) == (
        "pago em dia",
        0,
        2,
        2,
    )
    assert (r[1]["mes_id"], r[1]["prazo_concedido"], r[1]["valor"]) == (
        202401,
        30,
        Decimal("89.99"),
    )


def test_a_ocorrencia_e_uma_linha_por_evento(gold: duckdb.DuckDBPyConnection) -> None:
    o = {x["ocorrencia_id"]: x for x in _linhas(gold, "SELECT * FROM gold.fato_ocorrencia")}
    assert o[1]["reclamacao"] and (
        o[1]["posto_id"],
        o[1]["data_id"],
        o[1]["motivo_id"],
        o[1]["ocorrencia"],
    ) == (1, 20240201, 0, 1)
    assert (
        o[2]["elogio"]
        and o[2]["posto_id"] == 0
        and (o[2]["cliente_id"], o[2]["filial_id"]) == (1, 1)
    )


def test_a_foto_de_conformidade_e_do_ultimo_dia_do_mes(gold: duckdb.DuckDBPyConnection) -> None:
    f = {
        x["mes_id"]: x
        for x in _linhas(gold, "SELECT * FROM gold.fato_conformidade_mes ORDER BY mes_id")
    }
    assert list(f) == [202401, 202402, 202403]
    jan, fev, mar = f[202401], f[202402], f[202403]
    assert (jan["data_foto_id"], fev["data_foto_id"], mar["data_foto_id"]) == (
        20240131,
        20240229,
        20240310,
    )
    assert (jan["pessoas_alocadas"], fev["pessoas_alocadas"], mar["pessoas_alocadas"]) == (2, 1, 1)
    # a pessoa 1 está com o ASO vencido e sem o curso obrigatório em janeiro; a 2 tem ASO a vencer em março
    assert (
        jan["com_aso_vencido"],
        jan["com_aso_a_vencer_em_30_dias"],
        jan["com_curso_obrigatorio_faltando"],
    ) == (1, 0, 1)
    assert (
        fev["com_aso_vencido"],
        fev["com_aso_a_vencer_em_30_dias"],
        fev["com_curso_obrigatorio_faltando"],
    ) == (0, 1, 0)
    assert (mar["com_aso_vencido"], mar["com_aso_a_vencer_em_30_dias"]) == (0, 1)
    # o prazo legal do vínculo 2 (60 dias a partir de 20/01) vence em 20/03: a 30 dias em fevereiro e março
    assert (
        jan["temporarios_a_30_dias_do_prazo"],
        fev["temporarios_a_30_dias_do_prazo"],
        mar["temporarios_a_30_dias_do_prazo"],
    ) == (0, 1, 1)
    assert {x["temporarios_alem_do_prazo"] for x in f.values()} == {0}
    # o PCMSO do contrato vence em 15/02
    assert (
        jan["programas_legais_vencidos"],
        fev["programas_legais_vencidos"],
        mar["programas_legais_vencidos"],
    ) == (0, 1, 1)
    assert mar["mes_parcial"] and not fev["mes_parcial"]


def test_o_resultado_do_mes_atribui_imposto_e_despesa_a_filial(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    r = {
        (x["filial_id"], x["mes_id"]): x
        for x in _linhas(gold, "SELECT * FROM gold.fato_resultado_mes")
    }
    assert sorted(r) == [
        (1, 202401),
        (1, 202402),
        (1, 202403),
        (1, 202404),
        (2, 202401),
        (2, 202402),
        (2, 202403),
        (2, 202404),
    ]
    m1, f2 = r[(1, 202401)], r[(2, 202401)]
    # o ISS é da filial do município; o federal (3,00) e a despesa (30,00) se rateiam 100:50, com o resto na matriz
    assert (m1["faturamento"], m1["custo_pessoal"], m1["impostos_municipais"]) == (
        Decimal("100.00"),
        Decimal("60.00"),
        Decimal("5.00"),
    )
    assert (m1["impostos_federais"], m1["despesas"]) == (Decimal("2.00"), Decimal("20.00"))
    assert (
        f2["faturamento"],
        f2["custo_pessoal"],
        f2["impostos_municipais"],
        f2["impostos_federais"],
        f2["despesas"],
    ) == (Decimal("50.00"), 0, Decimal("2.50"), Decimal("1.00"), Decimal("10.00"))
    assert (m1["resultado"], f2["resultado"]) == (Decimal("13.00"), Decimal("36.50"))
    assert m1["margem_liquida"] == pytest.approx(0.13)
    # a foto do fim de janeiro: duas pessoas, nenhuma vaga aberta, um cliente
    assert (m1["pessoas_alocadas"], m1["vagas_abertas"], m1["clientes_ativos"]) == (2, 0, 1)
    assert m1["informado"] and (
        m1["faturamento_informado"],
        m1["diferenca_faturamento"],
        m1["diferenca_custo"],
    ) == (Decimal("110.00"), Decimal("10.00"), Decimal("-5.00"))
    assert (m1["diferenca_headcount"], m1["diferenca_vagas"]) == (1, 1)
    assert not f2["informado"] and f2["faturamento_informado"] is None
    # fevereiro: a fatura de recrutamento da matriz; abril: só o custo lançado depois do horizonte
    assert (r[(1, 202402)]["faturamento"], r[(1, 202402)]["vagas_abertas"]) == (Decimal("50.00"), 1)
    assert r[(1, 202403)]["mes_parcial"] and not r[(1, 202404)]["mes_parcial"]
    assert (
        r[(1, 202404)]["custo_pessoal"],
        r[(1, 202404)]["resultado"],
        r[(1, 202404)]["margem_liquida"],
    ) == (Decimal("25.00"), Decimal("-25.00"), None)


def test_o_mercado_entra_como_regua_de_fora(gold: duckdb.DuckDBPyConnection) -> None:
    escopos = {e["id"]: e for e in _linhas(gold, "SELECT * FROM gold.dim_escopo_mercado")}
    assert sorted(cast("int", i) for i in escopos) == [
        0,
        3178,
        31251007,
        31251078,
    ]  # MG·78, Extrema·G (7ª letra), Extrema·78
    extrema = escopos[31251078]
    assert (
        extrema["territorio"],
        extrema["nivel"],
        extrema["grupo_codigo"],
        extrema["municipio_id"],
    ) == ("Extrema", "município", "78", 1)
    assert extrema["segmento_da_fictalent"] and not escopos[31251007]["segmento_da_fictalent"]
    assert (escopos[3178]["nivel"], escopos[3178]["municipio_id"], escopos[3178]["territorio"]) == (
        "UF",
        0,
        "MG",
    )
    mercado = {
        (m["mes_id"], m["escopo_mercado_id"]): m
        for m in _linhas(gold, "SELECT * FROM gold.fato_mercado_mes")
    }
    assert (mercado[(202402, 31251078)]["admissoes"], mercado[(202402, 31251078)]["saldo"]) == (
        12,
        -3,
    )
    assert mercado[(202401, 3178)]["desligamentos"] == 450 and len(mercado) == 4


# ------------------------------------------------------------------ a conferência


def test_a_conferencia_reprova_o_grao_quebrado(gold: duckdb.DuckDBPyConnection) -> None:
    gold.execute(
        "INSERT INTO gold.fato_posto_mes SELECT * FROM gold.fato_posto_mes WHERE mes_id = 202401"
    )
    resultado = construcao.conferir(gold, modelo.FATO_POSTO_MES, "gold.fato_posto_mes")
    assert any("grão quebrado: 1 chaves" in p for p in resultado.problemas)


def test_a_conferencia_reprova_a_chave_que_nao_existe_na_dimensao(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    gold.execute("UPDATE gold.fato_custo_pessoal SET colaborador_id = 99 WHERE id = 1")
    resultado = construcao.conferir(gold, modelo.FATO_CUSTO_PESSOAL, "gold.fato_custo_pessoal")
    assert resultado.problemas == ["1 linhas com colaborador_id fora de dim_colaborador"]


def test_a_conferencia_reprova_o_total_que_nao_se_conserva(gold: duckdb.DuckDBPyConnection) -> None:
    gold.execute(
        "UPDATE gold.fato_faturamento SET valor_impostos = valor_impostos + 0.01 WHERE fatura_item_id = 1"
    )
    resultado = construcao.conferir(gold, modelo.FATO_FATURAMENTO, "gold.fato_faturamento")
    assert resultado.problemas == ["impostos não se conserva: gold 20.0200, silver 20.0100"]
    assert resultado.conservado["faturas"] == "3"


def test_a_conferencia_reprova_identidade_na_dimensao_de_pessoa(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    gold.execute("ALTER TABLE gold.dim_colaborador ADD COLUMN matricula VARCHAR")
    gold.execute("DELETE FROM gold.dim_colaborador WHERE id = 0")
    resultado = construcao.conferir(gold, modelo.DIM_COLABORADOR, "gold.dim_colaborador")
    assert len(resultado.problemas) == 2 and "['matricula']" in resultado.problemas[1]


# ------------------------------------------------------------------ o lake


def test_publicar_grava_confere_e_so_entao_publica(lake: Lake) -> None:
    con = _abrir(lake)
    for t in modelo.TABELAS:
        resultado = construcao.publicar(con, lake, t)
        assert resultado.aprovada, (t.nome, resultado.problemas)
    assert Path(construcao.pasta(lake, "dim_posto"), "dim_posto.parquet").exists()
    assert sorted(p.name for p in Path(construcao.pasta(lake, "fato_posto_mes")).iterdir()) == [
        "ano=2024.parquet"
    ]
    sobras = [p for p in Path(lake.caminho("gold", construcao.EM_CONFERENCIA)).rglob("*.parquet")]
    assert sobras == []
    lido = con.execute(
        f"SELECT sum(margem) FROM {construcao.leitura(lake, 'fato_posto_mes')}"
    ).fetchall()[0][0]  # noqa: S608
    assert lido == Decimal("15.00")  # 100 de receita menos 85 de custo


def test_a_reprovada_fica_na_conferencia_e_a_publicada_continua(
    lake: Lake, monkeypatch: pytest.MonkeyPatch
) -> None:
    con = _abrir(lake)
    for t in modelo.TABELAS:
        construcao.publicar(con, lake, t)
    publicada = Path(construcao.pasta(lake, "fato_custo_pessoal"), "ano=2024.parquet")
    antes = publicada.read_bytes()
    quebrada = modelo.Tabela(
        "fato_custo_pessoal",
        modelo.FATO_CUSTO_PESSOAL.sql.replace(
            "c.custo_total,", "c.custo_total + 1 AS custo_total,"
        ),
        referencias=modelo.FATO_CUSTO_PESSOAL.referencias,
        particao="ano",
        conservacoes=modelo.FATO_CUSTO_PESSOAL.conservacoes,
    )
    resultado = construcao.publicar(con, lake, quebrada)
    assert [p.split(":")[0] for p in resultado.problemas] == ["custo total não se conserva"]
    assert publicada.read_bytes() == antes
    assert Path(
        construcao.pasta(lake, "fato_custo_pessoal", em_conferencia=True), "ano=2024.parquet"
    ).exists()


def test_o_ano_que_deixou_de_existir_sai_do_publicado(lake: Lake) -> None:
    con = _abrir(lake)
    for t in modelo.TABELAS:
        construcao.publicar(con, lake, t)
    velho = Path(construcao.pasta(lake, "fato_custo_pessoal"), "ano=2019.parquet")
    velho.write_bytes(
        Path(construcao.pasta(lake, "fato_custo_pessoal"), "ano=2024.parquet").read_bytes()
    )
    assert construcao.publicar(con, lake, modelo.FATO_CUSTO_PESSOAL).aprovada
    assert not velho.exists()


# ------------------------------------------------------------------ o Dagster


def test_um_asset_por_tabela_com_a_linhagem_do_modelo() -> None:
    chaves = {a.key.to_user_string() for a in orquestracao.ASSETS}
    assert chaves == {f"gold/{t.nome}" for t in modelo.TABELAS}
    (posto_mes,) = [a for a in orquestracao.ASSETS if a.key.path == ["gold", "fato_posto_mes"]]
    dependencias = {k.to_user_string() for k in posto_mes.dependency_keys}
    assert {
        "gold/dim_posto",
        "gold/dim_mes",
        "silver/pessoas/alocacao",
        "silver/folha/rateio_custo",
        "silver/ponto/apontamento",
    } <= dependencias
    (mercado,) = [a for a in orquestracao.ASSETS if a.key.path == ["gold", "fato_mercado_mes"]]
    assert {"fontes/caged/movimentacao", "gold/dim_escopo_mercado", "gold/dim_mes"} <= {
        k.to_user_string() for k in mercado.dependency_keys
    }
    conhecidas = {
        k.to_user_string() for k in definicoes.defs.resolve_asset_graph().get_all_asset_keys()
    }
    for a in orquestracao.ASSETS:
        assert {k.to_user_string() for k in a.dependency_keys} <= conhecidas, a.key


def test_o_job_da_gold_esta_nas_definicoes() -> None:
    job = definicoes.defs.resolve_job_def("construir_gold")
    assert {k.to_user_string() for k in job.asset_layer.executable_asset_keys} == {
        f"gold/{t.nome}" for t in modelo.TABELAS
    } | {"gold/regua"}


# ------------------------------------------------------------------ o SQL analítico


def test_toda_consulta_analitica_declara_as_janelas_que_usa_e_roda_sobre_a_gold(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    nomes = [c.nome for c in analitico.CONSULTAS]
    assert len(nomes) == len(set(nomes))
    for c in analitico.CONSULTAS:
        assert c.pergunta.endswith("?") and c.origem and c.janelas, c.nome
        assert "OVER" in c.sql, f"{c.nome}: SQL analítico sem função de janela"
        for janela in c.janelas:
            funcao = janela.split("(")[0].split(" ")[0]  # LAG, AVG, SUM, RANK, ROW_NUMBER...
            assert funcao.isupper() and funcao in c.sql, (c.nome, funcao)
        resultado = analitico.executar(gold, c.nome)
        assert list(resultado.columns), c.nome
    with pytest.raises(KeyError, match="consulta desconhecida"):
        analitico.consulta("nao_existe")


def test_a_serie_da_filial_anda_no_tempo(gold: duckdb.DuckDBPyConnection) -> None:
    serie = analitico.executar(gold, "serie_da_filial")
    matriz = serie[serie["filial"] == "Matriz"].set_index("mes_id")
    assert list(matriz.index) == [202401, 202402, 202404]  # março é o mês parcial, fora da série
    assert matriz.loc[202402, "variacao_mensal"] == Decimal("-50.00")  # 50 - 100
    assert matriz.loc[202402, "acumulado_no_ano"] == Decimal("150.00")
    assert matriz.loc[202404, "media_movel_3m"] == pytest.approx(50)  # (100 + 50 + 0) / 3
    assert pd.isna(matriz.loc[202401, "variacao_mensal"])


def test_o_pareto_fecha_em_um(gold: duckdb.DuckDBPyConnection) -> None:
    pareto = analitico.executar(gold, "pareto_de_clientes")
    assert len(pareto) == 1 and pareto.loc[0, "posicao"] == 1
    assert pareto.loc[0, "participacao"] == pytest.approx(1) and pareto.loc[
        0, "participacao_acumulada"
    ] == pytest.approx(1)
    assert pareto.loc[0, "margem_pct"] == pytest.approx(15 / 100)  # 100 de receita, 85 de custo


def test_o_informado_contra_o_apurado_conta_a_sequencia(gold: duckdb.DuckDBPyConnection) -> None:
    (linha,) = analitico.executar(gold, "informado_contra_apurado").to_dict("records")
    assert (linha["mes_id"], linha["diverge"], linha["divergencia_pct"]) == (
        202401,
        True,
        pytest.approx(0.10),
    )
    assert (
        linha["meses_divergentes_ate_aqui"],
        linha["meses_seguidos"],
        linha["inicio_da_sequencia"],
    ) == (1, 1, 202401)


def test_a_coorte_conta_a_saida_precoce(gold: duckdb.DuckDBPyConnection) -> None:
    (coorte,) = analitico.executar(gold, "coorte_de_90_dias").to_dict("records")
    # os dois vínculos foram admitidos em janeiro; o primeiro saiu por pedido aos 36 dias
    assert (coorte["admitidos"], coorte["sairam_em_90_dias"], coorte["taxa_90_dias"]) == (2, 1, 0.5)
    assert (
        coorte["taxa_90_dias_12m"] == 0.5 and not coorte["coorte_completa"]
    )  # 90 dias ainda não passaram


def test_as_ilhas_de_posto_descoberto(gold: duckdb.DuckDBPyConnection) -> None:
    """Gaps-and-islands numa série plantada: descoberto nos meses 1-2 e 4-6; o mês 3 separa as duas."""
    gold.execute(
        """CREATE OR REPLACE TABLE gold.fato_posto_mes AS
           SELECT 1 AS posto_id, 1 AS cliente_id, 202400 + m AS mes_id, 31 AS dias_vigentes, FALSE AS mes_parcial,
                  CASE WHEN m = 3 THEN 0.95 ELSE 0.5 END AS taxa_de_ocupacao, 10 AS posicao_dias_descobertos
           FROM range(1, 7) t(m)"""
    )
    ilhas = analitico.executar(gold, "postos_descobertos_em_sequencia").to_dict("records")
    assert [(i["inicio"], i["fim"], i["meses_seguidos"], i["posicao"]) for i in ilhas] == [
        (202404, 202406, 3, 1),
        (202401, 202402, 2, 2),
    ]


def test_os_notebooks_da_gold_seguem_o_padrao_da_auditoria() -> None:
    """O teste que a CI roda sem lake: executados, com Nota Técnica em toda seção e de fechamento."""
    notebooks = cadernos.listar(RAIZ / "notebooks" / "gold")
    assert [n.name for n in notebooks] == ["01_sql_analitico.ipynb"]
    for caminho in notebooks:
        assert cadernos.verificar(caminho) == [], caminho.name


# ------------------------------------------------------------------ a régua da gold


def test_a_regua_da_gold_declara_um_check_por_conservacao_chave_e_linha_zero() -> None:
    checks = regua.checks()
    codigos = [c.codigo for c in checks]
    assert len(codigos) == len(set(codigos))
    assert {c.familia for c in checks} <= set(FAMILIAS)
    conservacao = [c for c in checks if c.familia == regua.CONSERVACAO]
    assert len(conservacao) == sum(len(t.conservacoes) for t in modelo.TABELAS)
    integridade = [c for c in checks if c.familia == regua.INTEGRIDADE]
    esperados = sum(1 + len(t.referencias) + (0 if t.fato else 1) for t in modelo.TABELAS)
    assert len(integridade) == esperados
    # o recorte do contrato de aceite: só as medidas que a gold reproduz com a definição do contrato
    do_contrato = [c for c in checks if c.familia not in regua.FAMILIAS_DA_GOLD]
    assert {c.medida for c in do_contrato} == set(regua.DO_CONTRATO)
    assert {c.codigo for c in do_contrato} <= {c.codigo for c in bandas.checks()}
    assert "C-04" not in {c.codigo for c in do_contrato}  # a folha é prioridade 2


def test_a_regua_da_gold_aprova_o_cenario_e_relata_o_contrato(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    resultado = regua.laudo(gold)
    assert resultado.aprovada, [
        r.check.codigo for r in resultado.laudo.com_situacao(Situacao.REPROVADO)
    ]
    medidas = regua.medir(gold)
    assert set(medidas["conservacao_gold"].values()) == {0.0}
    assert all(
        v == 0.0 for k, v in medidas["integridade_gold"].items() if not k.endswith("linha_0")
    )
    assert all(v == 1.0 for k, v in medidas["integridade_gold"].items() if k.endswith("linha_0"))
    # o contrato é por ano, de 2018 a 2026; o cenário só tem 2024: o resto fica pendente, não reprova a gold
    assert resultado.laudo.veredito in (Veredito.INCOMPLETA, Veredito.REPROVADA)
    assert medidas["clientes_ativos_fim_ano"] == {
        "2024": 1.0
    }  # um cliente com contrato em 31/12/2024... até o horizonte
    assert medidas["vagas_abertas"] == {
        "2023": 1.0,
        "2024": 1.0,
    }  # a vaga 1 abriu em dezembro de 2023
    assert medidas["violacoes"] == {"C-01": 0.0, "C-02": 0.0, "C-03": 0.0, "C-05": 0.0}
    assert "RÉGUA DA GOLD APROVADA" in resultado.veredito


def test_a_regua_da_gold_reprova_a_chave_orfa_e_o_total_que_nao_se_conserva(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    gold.execute("UPDATE gold.fato_custo_pessoal SET colaborador_id = 99 WHERE id = 1")
    gold.execute(
        "UPDATE gold.fato_faturamento SET valor_bruto = valor_bruto + 1 WHERE fatura_item_id = 1"
    )
    resultado = regua.laudo(gold)
    assert not resultado.aprovada
    reprovados = {
        r.check.codigo
        for r in resultado.laudo.com_situacao(Situacao.REPROVADO)
        if r.check.familia in regua.FAMILIAS_DA_GOLD
    }
    assert {
        "G-K/fato_custo_pessoal/colaborador_id",
        "G-C/fato_faturamento/valor bruto",
    } <= reprovados
    assert "RÉGUA DA GOLD REPROVADA" in resultado.veredito


def test_o_asset_da_regua_fecha_o_job_da_gold() -> None:
    assert {k.to_user_string() for k in orquestracao.regua_da_gold.dependency_keys} == {
        f"gold/{t.nome}" for t in modelo.TABELAS
    }
    job = definicoes.defs.resolve_job_def("construir_gold")
    assert "gold/regua" in {k.to_user_string() for k in job.asset_layer.executable_asset_keys}


# ------------------------------------------------------------------ o warehouse Postgres


def test_a_ddl_do_warehouse_sai_do_modelo(gold: duckdb.DuckDBPyConnection) -> None:
    assert warehouse.alvo(modelo.DIM_CLIENTE).qualificado == "dim.cliente"
    assert warehouse.alvo(modelo.FATO_POSTO_MES).qualificado == "fato.posto_mes"
    assert warehouse.alvo(modelo.FATO_POSTO_MES).particao(2024) == "fato.posto_mes_2024"
    assert warehouse.tipo_postgres("DECIMAL(14,2)") == "numeric(14, 2)"
    assert (
        warehouse.tipo_postgres("VARCHAR") == "text"
        and warehouse.tipo_postgres("DOUBLE") == "double precision"
    )
    with pytest.raises(ValueError, match="sem tradução"):
        warehouse.tipo_postgres("STRUCT(a INTEGER)")

    dimensao = warehouse.ddl(gold, modelo.DIM_CLIENTE)
    assert "CREATE SCHEMA IF NOT EXISTS dim;" in dimensao
    assert (
        "CREATE TABLE IF NOT EXISTS dim.cliente (" in dimensao and "  PRIMARY KEY (id)" in dimensao
    )
    assert "PARTITION BY" not in dimensao and "razao_social text" in dimensao
    assert "COMMENT ON TABLE dim.cliente IS 'um cliente; quem contrata a Fictalent';" in dimensao

    fato = warehouse.ddl(gold, modelo.FATO_POSTO_MES)
    assert "CREATE TABLE IF NOT EXISTS fato.posto_mes (" in fato
    assert "  PRIMARY KEY (posto_id, mes_id, ano)" in fato  # o ano entra: é a coluna de partição
    assert fato.rstrip().endswith(
        "PARTITION BY RANGE (ano);\nCOMMENT ON TABLE fato.posto_mes IS 'um posto num mês da vigência dele; o processo: ocupar o posto, faturar e custear';"
    )
    for coluna, dimensao_ in modelo.FATO_POSTO_MES.referencias.items():
        assert (
            f"  FOREIGN KEY ({coluna}) REFERENCES dim.{dimensao_.removeprefix('dim_')} (id)" in fato
        )
    assert "receita numeric(" in fato and "taxa_de_ocupacao double precision" in fato
    assert warehouse.ddl_da_particao(warehouse.alvo(modelo.FATO_POSTO_MES), 2024) == (
        "CREATE TABLE IF NOT EXISTS fato.posto_mes_2024 PARTITION OF fato.posto_mes FOR VALUES FROM (2024) TO (2025);"
    )
    assert warehouse.anos_no_parquet(gold, modelo.FATO_POSTO_MES) == [2024]


def test_os_assets_do_warehouse_seguem_a_gold_e_as_dimensoes_vem_antes() -> None:
    chaves = {a.key.to_user_string() for a in orquestracao_dw.ASSETS}
    assert chaves == {
        f"warehouse/{warehouse.alvo(t).esquema}/{warehouse.alvo(t).nome}" for t in modelo.TABELAS
    }
    (posto_mes,) = [
        a for a in orquestracao_dw.ASSETS if a.key.path == ["warehouse", "fato", "posto_mes"]
    ]
    dependencias = {k.to_user_string() for k in posto_mes.dependency_keys}
    assert "gold/fato_posto_mes" in dependencias
    assert {"warehouse/dim/posto", "warehouse/dim/mes", "warehouse/dim/cliente"} <= dependencias
    (cliente,) = [
        a for a in orquestracao_dw.ASSETS if a.key.path == ["warehouse", "dim", "cliente"]
    ]
    assert {k.to_user_string() for k in cliente.dependency_keys} == {"gold/dim_cliente"}
    job = definicoes.defs.resolve_job_def("carregar_warehouse")
    assert (
        len(set(job.asset_layer.executable_asset_keys)) == len(modelo.TABELAS) + 3
    )  # índices, DCL e RLS


ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}


def _postgres_de_pe() -> bool:
    try:
        socket.create_connection(("127.0.0.1", int(ENV.get("DW_PORT") or 0)), timeout=1).close()
    except (OSError, ValueError):
        return False
    return True


@pytest.mark.skipif(not ENV or not _postgres_de_pe(), reason="warehouse fora do ar ou .env ausente")
def test_a_carga_no_postgres_e_idempotente_e_conferida(gold: duckdb.DuckDBPyConnection) -> None:
    """Com a plataforma de pé: o cenário vai para schemas de teste do warehouse de verdade,
    duas vezes (a segunda não duplica), é conferido, e a adulteração no Postgres reprova."""
    dw = Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or os.environ.get("DW_ADMIN_PASSWORD", ""),
    )
    esquemas = ("teste_gold_dim", "teste_gold_fato")
    try:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            con.commit()
        for _ in range(2):  # idempotente: a dimensão por upsert, o fato por partição
            for t in modelo.TABELAS:
                resultado = warehouse.carregar(gold, dw, t, *esquemas)
                assert resultado.aprovada, (t.nome, resultado.problemas)
        (linhas,) = dw.consultar("SELECT count(*) FROM teste_gold_fato.posto_mes")[0]
        assert (
            linhas == 4 and dw.consultar("SELECT count(*) FROM teste_gold_dim.cliente")[0][0] == 2
        )
        assert dw.consultar("SELECT count(*) FROM teste_gold_fato.posto_mes_2024")[0][0] == 4
        # a chave estrangeira do Postgres vale: posto que não existe na dimensão é recusado
        with (
            pytest.raises(Exception, match="foreign key|chave estrangeira"),
            dw.conectar() as con,
            con.cursor() as cur,
        ):
            cur.execute("UPDATE teste_gold_fato.posto_mes SET posto_id = 99 WHERE mes_id = 202401")
            con.commit()
        # o que foi mexido no Postgres não confere mais com o parquet
        with dw.conectar() as con, con.cursor() as cur:
            cur.execute(
                "UPDATE teste_gold_fato.posto_mes SET receita = receita + 1 WHERE mes_id = 202401"
            )
            con.commit()
        problemas = warehouse.conferir(gold, dw, modelo.FATO_POSTO_MES, *esquemas)
        assert problemas == ["receita dos postos em 2024: parquet 100.0000, postgres 101.0000"]
    finally:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            con.commit()


# ------------------------------------------------------------------ o DCL do warehouse


def test_os_perfis_cobrem_os_fatos_e_so_leem_atributo_de_pessoa_por_necessidade(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    nomes = [p.nome for p in dcl.PERFIS]
    assert nomes == ["socio", "gerencia", "coordenacao", "assistente", "financeiro"]
    fatos = {t.nome for t in modelo.TABELAS if t.fato}
    assert set(dcl.perfil("socio").fatos) == fatos and set(dcl.perfil("gerencia").fatos) == fatos
    for p in dcl.PERFIS:
        assert set(p.fatos) <= fatos and set(p.atributos_de_pessoa) <= set(
            dcl.ATRIBUTOS_DE_PESSOA
        ), p.nome
        assert {"dim_data", "dim_mes"} <= set(p.dimensoes())
    # quem não precisa do atributo de pessoa não o tem: sócio, gerência e financeiro
    for nome in ("socio", "gerencia", "financeiro"):
        assert dcl.perfil(nome).atributos_de_pessoa == ()
    assert (
        "fato_faturamento" not in dcl.perfil("assistente").fatos
        and "fato_candidatura" not in dcl.perfil("financeiro").fatos
    )
    # as colunas livres da dimensão de pessoa: o id e o operacional, nunca o atributo
    livres = dcl.colunas_livres(gold, "dim_colaborador")
    assert (
        "id" in livres
        and "ativo" in livres
        and not set(livres) & set(dcl.ATRIBUTOS_DE_PESSOA["dim_colaborador"])
    )


def test_o_dcl_gerado_e_so_leitura_e_coluna_a_coluna_nas_pessoas(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    sql = dcl.gerar_sql(gold)
    assert "GRANT SELECT" in sql and not any(
        v in sql for v in ("INSERT", "UPDATE", "DELETE", "CREATE TABLE", "WITH GRANT OPTION")
    )
    assert (
        "CREATE ROLE perfil_financeiro NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in sql
    )
    assert "GRANT SELECT ON fato.faturamento TO perfil_financeiro;" in sql
    assert "GRANT SELECT ON fato.faturamento TO perfil_assistente;" not in sql
    assert (
        "GRANT SELECT ON dim.candidato TO perfil_assistente;" in sql
    )  # a assistente lê o candidato inteiro
    assert (
        "GRANT SELECT (id, dt_cadastro, q_ats_01, cadastro_canonico, pessoal_descartado) ON dim.candidato TO perfil_socio;"
        in sql
    )
    assert "GRANT SELECT ON dim.colaborador TO perfil_coordenacao;" in sql
    assert (
        "ON dim.colaborador TO perfil_financeiro;" in sql
        and "GRANT SELECT ON dim.colaborador TO perfil_financeiro;" not in sql
    )
    assert sql.count("REVOKE ALL ON ALL TABLES") == len(dcl.PERFIS)


def test_o_dcl_fecha_o_job_do_warehouse() -> None:
    assert {k.to_user_string() for k in orquestracao_dw.dcl_do_warehouse.dependency_keys} == {
        a.key.to_user_string() for a in orquestracao_dw.ASSETS
    }


@pytest.mark.skipif(not ENV or not _postgres_de_pe(), reason="warehouse fora do ar ou .env ausente")
def test_no_banco_o_acesso_indevido_falha(gold: duckdb.DuckDBPyConnection) -> None:
    """Com a plataforma de pé: o cenário em schemas de teste, o DCL aplicado neles, e cada perfil
    testado por SET ROLE: lê o que pode, e o que não pode falha com erro de privilégio."""
    import psycopg

    dw = Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or os.environ.get("DW_ADMIN_PASSWORD", ""),
    )
    esquemas = ("teste_dcl_dim", "teste_dcl_fato")

    def como(papel: str, sql: str) -> list[tuple[object, ...]]:
        with dw.conectar() as con, con.cursor() as cur:
            cur.execute(f"SET ROLE {papel}")  # noqa: S608
            cur.execute(sql)
            return list(cur.fetchall())

    try:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            con.commit()
        for t in modelo.TABELAS:
            assert warehouse.carregar(gold, dw, t, *esquemas).aprovada, t.nome
        dcl.aplicar(gold, dw, *esquemas)
        dcl.aplicar(gold, dw, *esquemas)  # idempotente

        assert como("perfil_financeiro", "SELECT sum(valor_bruto) FROM teste_dcl_fato.faturamento")[
            0
        ][0] == Decimal("200.00")
        assert (
            como(
                "perfil_financeiro", "SELECT id, ativo FROM teste_dcl_dim.colaborador ORDER BY id"
            )[0][0]
            == 0
        )
        assert (
            len(como("perfil_assistente", "SELECT sexo, escolaridade FROM teste_dcl_dim.candidato"))
            == 5
        )
        assert (
            como("perfil_coordenacao", "SELECT count(*) FROM teste_dcl_fato.ponto_dia")[0][0] == 4
        )
        assert como("perfil_socio", "SELECT count(*) FROM teste_dcl_fato.resultado_mes")[0][0] == 8
        bloqueios = [
            (
                "perfil_financeiro",
                "SELECT ano_nascimento FROM teste_dcl_dim.colaborador",
            ),  # atributo de pessoa
            (
                "perfil_financeiro",
                "SELECT * FROM teste_dcl_dim.colaborador",
            ),  # o asterisco pede as colunas vedadas
            (
                "perfil_financeiro",
                "SELECT count(*) FROM teste_dcl_fato.candidatura",
            ),  # fato de outra área
            ("perfil_assistente", "SELECT count(*) FROM teste_dcl_fato.faturamento"),
            (
                "perfil_socio",
                "SELECT sexo FROM teste_dcl_dim.candidato",
            ),  # o sócio decide no agregado
            (
                "perfil_coordenacao",
                "SELECT escolaridade FROM teste_dcl_dim.candidato",
            ),  # a coordenação lê o colaborador, não o candidato
            ("perfil_socio", "INSERT INTO teste_dcl_dim.filial (id, nome) VALUES (9, 'x')"),
            ("perfil_gerencia", "DELETE FROM teste_dcl_fato.ocorrencia"),
            ("perfil_coordenacao", "CREATE TABLE teste_dcl_fato.x (a int)"),
        ]
        for papel, sql in bloqueios:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                como(papel, sql)
    finally:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            con.commit()


# ------------------------------------------------------------------ o RLS do warehouse


def test_a_politica_vale_em_toda_tabela_com_filial_e_so_os_perfis_de_filial_sao_filtrados() -> None:
    assert {p.nome: p.alcance for p in dcl.PERFIS} == {
        "socio": dcl.EMPRESA,
        "gerencia": dcl.EMPRESA,
        "coordenacao": dcl.FILIAL,
        "assistente": dcl.FILIAL,
        "financeiro": dcl.EMPRESA,
    }
    nomes = {t.nome for t in rls.tabelas_com_filial()}
    assert nomes == {t.nome for t in modelo.TABELAS if t.fato} - {"fato_mercado_mes"} | {
        "dim_contrato"
    }  # o mercado é público e não tem filial; o contrato é a dimensão que tem
    assert len(nomes) == 14


def test_o_rls_gerado_fecha_por_padrao_e_so_o_administrador_mexe_no_acesso() -> None:
    sql = rls.gerar_sql()
    assert sql.count("ENABLE ROW LEVEL SECURITY") == len(rls.tabelas_com_filial())
    assert (
        "CREATE POLICY empresa_inteira ON fato.faturamento FOR SELECT "
        "TO perfil_socio, perfil_gerencia, perfil_financeiro USING (true);" in sql
    )
    assert (
        "CREATE POLICY por_filial ON fato.posto_mes FOR SELECT TO perfil_coordenacao, perfil_assistente "
        "USING (filial_id = 0 OR filial_id IN (SELECT acesso.filiais_do_papel(current_user)));"
        in sql
    )
    assert "ON dim.contrato" in sql and "ON fato.mercado_mes" not in sql
    # a tabela de acesso: ninguém além do administrador a lê ou escreve; a função é SECURITY DEFINER
    assert "GRANT SELECT ON acesso.filial_do_papel" not in sql and "GRANT ALL" not in sql
    assert "REVOKE ALL ON acesso.filial_do_papel FROM PUBLIC;" in sql
    assert "SECURITY DEFINER SET search_path = pg_catalog, pg_temp" in sql
    assert "REFERENCES dim.filial (id)" in sql
    outro = rls.gerar_sql("a", "b", "c")
    assert "REFERENCES a.filial (id)" in outro and "ALTER TABLE b.posto_mes ENABLE" in outro
    assert "c.filiais_do_papel(current_user)" in outro and "acesso." not in outro


def test_o_rls_vem_depois_do_dcl_no_job_do_warehouse() -> None:
    assert {k.to_user_string() for k in orquestracao_dw.rls_do_warehouse.dependency_keys} == {
        "warehouse/dcl"
    }


@pytest.mark.skipif(not ENV or not _postgres_de_pe(), reason="warehouse fora do ar ou .env ausente")
def test_no_banco_a_coordenacao_de_uma_filial_so_ve_a_filial(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    """Com a plataforma de pé: o cenário em schemas de teste, o DCL e o RLS aplicados neles, e um
    papel de login ligado à filial 2 lê só a filial 2; quem é da empresa inteira lê tudo; o perfil
    sem filial registrada não lê nada; e a tabela de acesso e a partição ficam fora do alcance."""
    import psycopg

    dw = Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or os.environ.get("DW_ADMIN_PASSWORD", ""),
    )
    esquemas = ("teste_rls_dim", "teste_rls_fato", "teste_rls_acesso")
    papeis = ("teste_rls_coordenacao_2", "teste_rls_assistente_1_2")

    def como(papel: str, sql: str) -> list[tuple[object, ...]]:
        with dw.conectar() as con, con.cursor() as cur:
            cur.execute(f"SET ROLE {papel}")  # noqa: S608
            cur.execute(sql)
            return list(cur.fetchall())

    def no_parquet(tabela: str, filiais: tuple[int, ...]) -> int:
        lista = ", ".join(map(str, filiais))
        sql = f"SELECT count(*) FROM gold.{tabela} WHERE filial_id IN ({lista})"  # noqa: S608
        (n,) = gold.execute(sql).fetchone() or (0,)
        return int(n)

    def limpar() -> None:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            for papel in papeis:
                cur.execute(f"DROP ROLE IF EXISTS {papel}")  # noqa: S608
            con.commit()

    try:
        limpar()
        for t in modelo.TABELAS:
            assert warehouse.carregar(gold, dw, t, *esquemas[:2]).aprovada, t.nome
        dcl.aplicar(gold, dw, *esquemas[:2])
        rls.aplicar(dw, *esquemas)
        rls.aplicar(dw, *esquemas)  # idempotente
        with dw.conectar() as con, con.cursor() as cur:  # o rito do administrador, sem senha aqui
            cur.execute(f"CREATE ROLE {papeis[0]} NOLOGIN IN ROLE perfil_coordenacao")  # noqa: S608
            cur.execute(f"CREATE ROLE {papeis[1]} NOLOGIN IN ROLE perfil_assistente")  # noqa: S608
            cur.execute(
                "INSERT INTO teste_rls_acesso.filial_do_papel VALUES (%s, 2), (%s, 1), (%s, 2)",
                (papeis[0], papeis[1], papeis[1]),
            )
            con.commit()
        total = no_parquet("fato_contrato", (1, 2))
        da_filial_2 = no_parquet("fato_contrato", (2,))
        assert 0 < da_filial_2 < total  # o cenário tem contrato nas duas filiais
        # a coordenação da filial 2 lê só a filial 2, em todo fato e na dimensão de contrato
        assert como(papeis[0], "SELECT count(*) FROM teste_rls_fato.contrato")[0][0] == da_filial_2
        assert {
            r[0] for r in como(papeis[0], "SELECT DISTINCT filial_id FROM teste_rls_fato.vaga")
        } <= {2}
        assert {
            r[0] for r in como(papeis[0], "SELECT DISTINCT filial_id FROM teste_rls_dim.contrato")
        } == {0, 2}  # a linha 0 (não se aplica) é de todos
        assert como(papeis[0], "SELECT count(*) FROM teste_rls_fato.posto_mes")[0][0] == no_parquet(
            "fato_posto_mes", (2,)
        )
        # a assistente com as duas filiais lê tudo o que a assistente pode
        assert como(papeis[1], "SELECT count(*) FROM teste_rls_fato.vaga")[0][0] == no_parquet(
            "fato_vaga", (1, 2)
        )
        # a empresa inteira: sócio e financeiro leem tudo
        assert como("perfil_socio", "SELECT count(*) FROM teste_rls_fato.contrato")[0][0] == total
        assert como("perfil_financeiro", "SELECT sum(valor_bruto) FROM teste_rls_fato.faturamento")[
            0
        ][0] == Decimal("200.00")
        # o perfil de filial sem filial registrada não vê linha nenhuma: fecha por padrão
        assert como("perfil_coordenacao", "SELECT count(*) FROM teste_rls_fato.contrato")[0][0] == 0
        # o que não pode: ler ou mexer na tabela de acesso, e ler a partição por baixo da política
        bloqueios = [
            (papeis[0], "SELECT * FROM teste_rls_acesso.filial_do_papel"),
            (papeis[0], "INSERT INTO teste_rls_acesso.filial_do_papel VALUES (current_user, 1)"),
            ("perfil_socio", "SELECT count(*) FROM teste_rls_fato.posto_mes_2024"),
            (papeis[0], "SELECT count(*) FROM teste_rls_fato.posto_mes_2024"),
        ]
        for papel, sql in bloqueios:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                como(papel, sql)
    finally:
        limpar()


# ------------------------------------------------------------- os índices do warehouse


def test_todo_indice_tem_a_consulta_que_o_pede_e_colunas_que_o_fato_tem() -> None:
    consultas = {c.nome for c in indices.CONSULTAS}
    for i in indices.INDICES:
        tabela = modelo.tabela(i.tabela)
        assert tabela.fato and i.para in consultas, i.nome
        assert set(i.colunas) <= set(tabela.referencias) | set(tabela.chave), i.nome
        assert indices.consulta(i.para).tabela == i.tabela
        assert i.adotado or i.motivo, i.nome  # descartado só com a medida que o descartou
    assert indices.indice("ix_ponto_dia_posto_id_data_id").colunas == ("posto_id", "data_id")
    assert len({i.nome for i in indices.INDICES}) == len(indices.INDICES)
    assert {c.tabela for c in indices.CONSULTAS} <= {t.nome for t in modelo.TABELAS if t.fato}


def test_a_ddl_dos_indices_cria_so_os_adotados_e_e_idempotente() -> None:
    sql = indices.ddl()
    assert (
        "CREATE INDEX IF NOT EXISTS ix_ponto_dia_posto_id_data_id ON fato.ponto_dia (posto_id, data_id);"
        in sql
    )
    assert (
        "ix_ponto_dia_filial_id" not in sql and "ix_posto_mes" not in sql
    )  # medidos e descartados
    assert [i.nome for i in indices.adotados()] == [
        "ix_ponto_dia_posto_id_data_id",
        "ix_ponto_dia_colaborador_id",
        "ix_candidatura_candidato_id",
        "ix_custo_pessoal_colaborador_id",
    ]  # os quatro em que a medida fez diferença (12 a 66 vezes)
    assert sql.count("CREATE INDEX") == len(indices.adotados())
    assert "ix_ponto_dia_filial_id" in indices.ddl(list(indices.INDICES))
    assert "DROP INDEX IF EXISTS teste.ix_ponto_dia_filial_id;" in indices.ddl_de_remocao(
        esquema_fato="teste"
    )
    assert indices.analise().count("ANALYZE fato.") == len([t for t in modelo.TABELAS if t.fato])


def test_os_indices_vem_depois_das_tabelas_no_job_do_warehouse() -> None:
    assert {k.to_user_string() for k in orquestracao_dw.indices_do_warehouse.dependency_keys} == {
        a.key.to_user_string() for a in orquestracao_dw.ASSETS
    }


@pytest.mark.skipif(not ENV or not _postgres_de_pe(), reason="warehouse fora do ar ou .env ausente")
def test_no_banco_a_medida_roda_antes_e_depois_e_deixa_so_os_adotados(
    gold: duckdb.DuckDBPyConnection,
) -> None:
    """Com a plataforma de pé: o cenário em schemas de teste, a medida remove, mede, cria, mede
    e deixa só os adotados; o laudo tem toda consulta com tempo e plano dos dois lados. Com o
    cenário pequeno o planejador varre a tabela, e o teste prova a mecânica, não o ganho."""
    dw = Warehouse(
        host="127.0.0.1",
        porta=int(ENV.get("DW_PORT") or 5441),
        banco=ENV.get("DW_DB") or "dw_fictalent",
        usuario=ENV.get("DW_ADMIN_USER") or "fictalent_admin",
        senha=ENV.get("DW_ADMIN_PASSWORD") or os.environ.get("DW_ADMIN_PASSWORD", ""),
    )
    esquemas = ("teste_ix_dim", "teste_ix_fato")
    try:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            con.commit()
        for t in modelo.TABELAS:
            assert warehouse.carregar(gold, dw, t, *esquemas).aprovada, t.nome
        medidas = indices.medir(dw, esquemas[1])
        assert [m.consulta for m in medidas] == [c.nome for c in indices.CONSULTAS]
        for m in medidas:
            assert m.antes_ms > 0 and m.depois_ms > 0 and m.plano_antes and m.plano_depois
            assert m.parametros, m.consulta  # o valor mais frequente existe no cenário
        assert "ponto_do_posto_no_mes" in indices.texto(medidas)
        assert '"medido_em": "hoje"' in indices.laudo_json(medidas, "hoje")
        # o que fica no banco: os adotados em cada partição, o descartado em nenhuma
        nomes = {
            n
            for (n,) in dw.consultar(
                "SELECT indexname FROM pg_indexes WHERE schemaname = %s", esquemas[1]
            )
        }
        assert {i.nome for i in indices.adotados()} <= nomes
        assert "ix_ponto_dia_filial_id" not in nomes
        assert "ponto_dia_2024_posto_id_data_id_idx" in nomes  # a partição herda o índice da mãe
        assert indices.criar(dw, esquemas[1]) == len(indices.adotados())  # idempotente
    finally:
        with dw.conectar() as con, con.cursor() as cur:
            for esquema in esquemas:
                cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE")  # noqa: S608
            con.commit()
