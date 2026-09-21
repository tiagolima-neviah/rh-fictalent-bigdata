"""Etapa 1 do gerador: o mundo cadastral (as 12 tabelas do database `cadastro`).

É o que existe antes de qualquer cliente, vaga ou pessoa: regiões e municípios (da tabela do
IBGE versionada em dados/publicos), as três filiais com endereço e centro de custo, funções,
convenções coletivas com piso por função e ano, feriados (nacionais da BrasilAPI, mais o
estadual de SP e os três municipais), escalas, motivos e parâmetros.

Centro de custo de contrato e endereços de cliente, local de trabalho e colaborador nascem
nas etapas que criam esses contratos e pessoas; aqui entram só os da estrutura da empresa.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from rh_fictalent.gerador import catalogos as cat
from rh_fictalent.gerador.nucleo import (
    FIM,
    INICIO,
    Tabelas,
    aleatorio,
    instante,
    primeiro_dia_util,
    tabela,
)

PUBLICOS = Path("dados/publicos")
ENTRADA_NO_AR = instante(INICIO)  # o dia em que o sistema da Fictalent entrou no ar
ANOS = range(INICIO.year, FIM.year + 1)


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open(encoding="utf-8", newline="") as arquivo:
        return list(csv.DictReader(arquivo))


def _carimbo(criado: datetime, atualizado: datetime | None = None) -> dict[str, datetime]:
    return {"criado_em": criado, "atualizado_em": atualizado or criado}


def _regioes_e_municipios(publicos: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Os municípios das cinco regiões imediatas do IBGE em torno do eixo, com a região."""
    regioes = [{"nome": nome, **_carimbo(ENTRADA_NO_AR)} for nome in cat.REGIOES.values()]
    id_da_regiao = {imediata: i for i, imediata in enumerate(cat.REGIOES, start=1)}
    municipios = [
        {
            "nome": m["nome"],
            "uf": m["uf"],
            "regiao_id": id_da_regiao[m["regiao_imediata"]],
            "codigo_ibge": m["codigo_ibge"],
            **_carimbo(ENTRADA_NO_AR),
        }
        for m in _ler_csv(publicos / "ibge" / "municipios.csv")
        if m["regiao_imediata"] in id_da_regiao
    ]
    return regioes, municipios


def _vigencias(mes_data_base: int) -> list[tuple[int, date, date | None]]:
    """(ano da data-base, início, fim) de cada vigência anual; a de 2017 cobre o começo de 2018."""
    inicios = [date(ano, mes_data_base, 1) for ano in range(INICIO.year - 1, FIM.year + 1)]
    inicios = [d for d in inicios if d <= FIM.date() and d + timedelta(days=366) > INICIO]
    fins: list[date | None] = [proximo - timedelta(days=1) for proximo in inicios[1:]]
    return [(d.year, d, fim) for d, fim in zip(inicios, [*fins, None], strict=True)]


def gerar(publicos: Path = PUBLICOS) -> Tabelas:
    sorteio = aleatorio("etapa1_cadastro")
    regioes, municipios = _regioes_e_municipios(publicos)
    id_do_municipio = {m["codigo_ibge"]: i for i, m in enumerate(municipios, start=1)}

    # filiais: cada uma nasce com o seu endereço e o seu centro de custo, no dia da abertura
    enderecos: list[dict[str, Any]] = []
    filiais: list[dict[str, Any]] = []
    centros: list[dict[str, Any]] = []
    for i, f in enumerate(cat.FILIAIS, start=1):
        nascimento = _carimbo(instante(f.dt_abertura))
        enderecos.append(
            {
                "logradouro": f.logradouro,
                "numero": f.numero,
                "complemento": None,
                "bairro": f.bairro,
                "municipio_id": id_do_municipio[f.codigo_ibge],
                "cep": f.cep,
                "tipo": "FILIAL",
                **nascimento,
            }
        )
        filiais.append(
            {
                "codigo": f.codigo,
                "nome": f.nome,
                "tipo": f.tipo,
                "endereco_id": i,
                "dt_abertura": f.dt_abertura,
                "ativo": True,
                **nascimento,
            }
        )
        centros.append(
            {
                "codigo": f"CC-{f.codigo}",
                "nome": f"Operação {f.nome.removeprefix('Fictalent ')}",
                "tipo": "FILIAL",
                "filial_id": i,
                "contrato_id": None,
                **nascimento,
            }
        )
    centros.append(
        {
            "codigo": "CC-RETAGUARDA",
            "nome": "Retaguarda (folha, financeiro, SST)",
            "tipo": "RETAGUARDA",
            "filial_id": 1,
            "contrato_id": None,
            **_carimbo(ENTRADA_NO_AR),
        }
    )

    funcoes = [
        {
            "codigo": f.codigo,
            "nome": f.nome,
            "cbo": f.cbo,
            "familia": f.familia,
            "nivel": f.nivel,
            "fl_insalubre": f.insalubre,
            "fl_periculosidade": f.periculosidade,
            **_carimbo(ENTRADA_NO_AR),
        }
        for f in cat.FUNCOES
    ]

    # convenções: uma linha por município e vigência anual; piso por função em cada uma
    convencoes: list[dict[str, Any]] = []
    pisos: list[dict[str, Any]] = []
    for codigo_ibge, cidade, mes, fator_regional in cat.CONVENCOES:
        # a mesma função custa um pouco diferente em cada cidade: cada sindicato negociou o seu
        jeito_da_cidade = 1 + sorteio.uniform(-0.02, 0.02, size=len(cat.FUNCOES))
        acumulado = 1.0
        for ano, inicio, fim in _vigencias(mes):
            acumulado *= 1 + cat.REAJUSTES.get(ano, 0.0)
            criado = max(instante(inicio), ENTRADA_NO_AR)
            encerrado = instante(fim + timedelta(days=1)) if fim else None
            carimbo = _carimbo(criado, max(encerrado, criado) if encerrado else None)
            convencoes.append(
                {
                    "sindicato": cat.SINDICATO.format(cidade=cidade),
                    "municipio_id": id_do_municipio[codigo_ibge],
                    "mes_data_base": mes,
                    "vigencia_inicio": inicio,
                    "vigencia_fim": fim,
                    **carimbo,
                }
            )
            for funcao, jeito in zip(cat.FUNCOES, jeito_da_cidade, strict=True):
                piso = (
                    cat.PISO_DE_REFERENCIA
                    * funcao.fator
                    * fator_regional
                    * float(jeito)
                    * acumulado
                )
                pisos.append(
                    {
                        "convencao_id": len(convencoes),
                        "funcao_id": cat.FUNCOES.index(funcao) + 1,
                        "valor_piso": round(piso, 2),
                        "adicional_insalubridade_pct": (
                            cat.ADICIONAL_DE_INSALUBRIDADE if funcao.insalubre else 0.0
                        ),
                        "vigencia_inicio": inicio,
                        "vigencia_fim": fim,
                        **carimbo,
                    }
                )

    # feriados: o calendário de cada ano é cadastrado no primeiro dia útil do ano
    feriados: list[dict[str, Any]] = []
    nacionais = _ler_csv(publicos / "brasilapi" / "feriados_nacionais.csv")
    for ano in ANOS:
        cadastro = _carimbo(max(instante(primeiro_dia_util(ano, 1, 2)), ENTRADA_NO_AR))
        do_ano: list[tuple[date, str, str, int | None]] = [
            (date.fromisoformat(f["data"]), f["nome"], f["abrangencia"], None)
            for f in nacionais
            if int(f["ano"]) == ano
        ]
        do_ano += [
            (date(ano, mes, dia), nome, abrangencia, id_do_municipio.get(ibge or ""))
            for mes, dia, nome, abrangencia, ibge in cat.FERIADOS_LOCAIS
        ]
        for dia_do_feriado, nome, abrangencia, municipio_id in sorted(do_ano, key=lambda f: f[0]):
            feriados.append(
                {
                    "data": dia_do_feriado,
                    "nome": nome,
                    "abrangencia": abrangencia,
                    "municipio_id": municipio_id,
                    **cadastro,
                }
            )

    escalas = [
        {
            "codigo": codigo,
            "descricao": descricao,
            "horas_semanais": horas,
            "dias_ciclo": ciclo,
            **_carimbo(ENTRADA_NO_AR),
        }
        for codigo, descricao, horas, ciclo in cat.ESCALAS
    ]
    motivos = [
        {
            "tipo": tipo,
            "codigo": codigo,
            "descricao": descricao,
            "grupo": grupo,
            **_carimbo(ENTRADA_NO_AR),
        }
        for tipo, codigo, descricao, grupo in cat.MOTIVOS
    ]

    # parâmetros: a mesma chave de novo encerra a vigência anterior na véspera
    parametros: list[dict[str, Any]] = []
    for chave, valor, inicio in cat.PARAMETROS:
        for anterior in parametros:
            if anterior["chave"] == chave and anterior["vigencia_fim"] is None:
                anterior["vigencia_fim"] = inicio - timedelta(days=1)
                anterior["atualizado_em"] = instante(inicio)
        parametros.append(
            {
                "chave": chave,
                "valor": valor,
                "vigencia_inicio": inicio,
                "vigencia_fim": None,
                **_carimbo(instante(inicio)),
            }
        )

    tabelas: Tabelas = {
        "cadastro.regiao": tabela(regioes),
        "cadastro.municipio": tabela(municipios),
        "cadastro.endereco": tabela(enderecos),
        "cadastro.filial": tabela(filiais),
        "cadastro.motivo": tabela(motivos),
        "cadastro.funcao": tabela(funcoes),
        "cadastro.convencao_coletiva": tabela(convencoes),
        "cadastro.piso_salarial": tabela(pisos),
        "cadastro.feriado": tabela(feriados),
        "cadastro.escala": tabela(escalas),
        "cadastro.parametro": tabela(parametros),
        "cadastro.centro_custo": tabela(centros),
    }
    conferir(tabelas)
    return tabelas


def conferir(t: Tabelas) -> None:
    """O aceite da etapa: chaves, unicidade e vigências. Falhou, é defeito do gerador."""
    problemas: list[str] = []

    def exigir(condicao: bool, mensagem: str) -> None:
        if not condicao:
            problemas.append(mensagem)

    def referencia(filha: str, coluna: str, mae: str) -> None:
        ids = set(t[mae]["id"])
        usados = set(t[filha][coluna].dropna().astype(int))
        exigir(usados <= ids, f"{filha}.{coluna} aponta para {mae} inexistente: {usados - ids}")

    referencia("cadastro.municipio", "regiao_id", "cadastro.regiao")
    referencia("cadastro.endereco", "municipio_id", "cadastro.municipio")
    referencia("cadastro.filial", "endereco_id", "cadastro.endereco")
    referencia("cadastro.centro_custo", "filial_id", "cadastro.filial")
    referencia("cadastro.convencao_coletiva", "municipio_id", "cadastro.municipio")
    referencia("cadastro.piso_salarial", "convencao_id", "cadastro.convencao_coletiva")
    referencia("cadastro.piso_salarial", "funcao_id", "cadastro.funcao")
    referencia("cadastro.feriado", "municipio_id", "cadastro.municipio")

    for nome, chave in (
        ("cadastro.regiao", ["nome"]),
        ("cadastro.municipio", ["codigo_ibge"]),
        ("cadastro.filial", ["codigo"]),
        ("cadastro.funcao", ["codigo"]),
        ("cadastro.escala", ["codigo"]),
        ("cadastro.centro_custo", ["codigo"]),
        ("cadastro.motivo", ["tipo", "codigo"]),
        ("cadastro.parametro", ["chave", "vigencia_inicio"]),
        ("cadastro.piso_salarial", ["convencao_id", "funcao_id"]),
    ):
        exigir(not t[nome].duplicated(chave).any(), f"{nome}: chave {chave} repetida")

    for nome in t:
        quadro = t[nome]
        exigir(len(quadro) > 0, f"{nome} vazia")
        exigir(bool((quadro["atualizado_em"] >= quadro["criado_em"]).all()), f"{nome}: carimbo")
        exigir(bool((quadro["criado_em"] >= ENTRADA_NO_AR).all()), f"{nome}: criado antes de 2018")
        exigir(bool((quadro["atualizado_em"] <= FIM).all()), f"{nome}: atualizado depois do fim")

    # em cada dia da história, cada município de filial tem exatamente uma convenção vigente
    convencoes = t["cadastro.convencao_coletiva"]
    for municipio_id, grupo in convencoes.groupby("municipio_id"):
        for dia in (INICIO, date(2020, 6, 15), date(2023, 1, 1), FIM.date()):
            vigentes = grupo[
                (grupo["vigencia_inicio"] <= dia)
                & (grupo["vigencia_fim"].isna() | (grupo["vigencia_fim"] >= dia))
            ]
            achadas = len(vigentes)
            exigir(achadas == 1, f"município {municipio_id}: {achadas} convenções em {dia}")
    if problemas:
        raise ValueError("etapa 1 reprovada:\n- " + "\n- ".join(problemas))
