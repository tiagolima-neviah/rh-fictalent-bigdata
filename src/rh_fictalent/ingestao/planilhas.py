"""A terceira natureza de fonte: o arquivo. As planilhas do consolidado gerencial.

A gerente-geral da Fictalent fecha o mês numa pasta de trabalho por ano. O arquivo não tem
contrato nenhum: tem título na primeira linha, uma linha em branco, o cabeçalho na terceira, os
dados, e um **TOTAL** no fim que não é dado, é soma. Ler isso com `read_excel` e seguir em
frente é como o erro começa: a coluna de competência chega como texto (porque a palavra "TOTAL"
está nela), o headcount chega como decimal (porque a célula do total está vazia), e ninguém
percebe até um número aparecer errado num painel três camadas adiante.

Por isso a ingestão de arquivo tem duas etapas separadas e nessa ordem:

1. **Preparar**, que é trabalho declarado e revisável: descartar o título e o total, renomear as
   colunas para nomes de coluna (sem acento, sem unidade entre parênteses) e converter os tipos
   que a planilha misturou.
2. **Validar** contra um esquema **pandera** declarado neste módulo. Esquema reprovado, asset
   reprovado, carga interrompida ([ADR-0006](../../docs/adr/0006-pandera-e-regua.md)). A régua
   de validação é outra coisa: ela confere a história do caso; o esquema confere a forma do
   arquivo.

O que a bronze guarda é o que o arquivo disse, com o nome do arquivo junto: quando a planilha e
a operação discordarem (e elas discordam a partir de 2022, de propósito), é preciso poder
apontar de qual arquivo veio cada número.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pandera.pandas as pa

if TYPE_CHECKING:  # pragma: no cover
    from rh_fictalent.orquestracao.recursos import Lake

PASTA = Path("dados/gerencial")
ABA = "Consolidado"
LINHA_DO_CABECALHO = 2  # base zero: título na 1, branco na 2, cabeçalho na 3
MARCA_DO_TOTAL = "TOTAL"
CAMADA, MODULO, TABELA = "bronze", "arquivo", "consolidado_gerencial"
ARQUIVO = re.compile(r"consolidado_gerencial_(\d{4})\.xlsx$")
# o rótulo da planilha e o nome que a coluna passa a ter na bronze
COLUNAS = {
    "Competência": "competencia",
    "Filial": "filial",
    "Headcount": "headcount",
    "Vagas abertas": "vagas_abertas",
    "Faturamento (R$)": "faturamento",
    "Custo (R$)": "custo",
    "Lançado em": "lancado_em",
}
FILIAIS = ("Atibaia (matriz)", "Bragança Paulista", "Extrema")

ESQUEMA = pa.DataFrameSchema(
    {
        "competencia": pa.Column(
            "datetime64[ns]",
            checks=[
                pa.Check(lambda s: (s.dt.day == 1).all(), error="competência não é o 1º do mês"),
                pa.Check.in_range(pd.Timestamp("2018-01-01"), pd.Timestamp("2026-12-01")),
            ],
        ),
        "filial": pa.Column(str, checks=pa.Check.isin(FILIAIS)),
        "headcount": pa.Column(int, checks=pa.Check.ge(0)),
        "vagas_abertas": pa.Column(int, checks=pa.Check.ge(0)),
        "faturamento": pa.Column(float, checks=pa.Check.ge(0)),
        "custo": pa.Column(float, checks=pa.Check.ge(0)),
        "lancado_em": pa.Column("datetime64[ns]"),
        "arquivo": pa.Column(str),
    },
    checks=[
        pa.Check(
            lambda q: (q["lancado_em"] >= q["competencia"]).all(),
            error="fechamento lançado antes da competência",
        ),
        pa.Check(
            lambda q: q["competencia"].dt.year.nunique() == 1,
            error="a pasta de trabalho do ano tem competência de outro ano",
        ),
    ],
    unique=["competencia", "filial"],  # uma linha por mês e filial, e só uma
    strict=True,  # coluna a mais na planilha é erro, não curiosidade
    coerce=False,  # converter é trabalho de `preparar`, declarado; aqui só se confere
    name="consolidado gerencial (planilha da gerência)",
)


def ano_do_arquivo(caminho: Path) -> int:
    achado = ARQUIVO.search(caminho.name)
    if not achado:
        raise ValueError(
            f"nome de arquivo fora do padrão consolidado_gerencial_AAAA.xlsx: {caminho.name}"
        )
    return int(achado.group(1))


def preparar(caminho: Path) -> pd.DataFrame:
    """Da pasta de trabalho para um quadro com nome e tipo de coluna, sem o enfeite da planilha.

    Cada linha desta função existe por causa de uma coisa que a planilha tem e o dado não pode
    ter: o título, a linha de total, o nome com acento e unidade, e o tipo que a mistura das
    duas coisas estragou.
    """
    quadro = pd.read_excel(caminho, sheet_name=ABA, header=LINHA_DO_CABECALHO)
    faltando = set(COLUNAS) - set(quadro.columns)
    if faltando:
        raise ValueError(f"{caminho.name}: a planilha não tem {sorted(faltando)}")
    quadro = quadro.rename(columns=COLUNAS)[list(COLUNAS.values())]
    total = quadro["competencia"].astype(str).str.strip().str.upper() == MARCA_DO_TOTAL
    quadro = quadro.loc[~total].copy()  # o total é soma, não observação
    quadro["competencia"] = pd.to_datetime(quadro["competencia"])
    quadro["lancado_em"] = pd.to_datetime(quadro["lancado_em"])
    quadro["filial"] = quadro["filial"].astype(str)
    for inteira in ("headcount", "vagas_abertas"):  # vieram decimais por causa do total vazio
        quadro[inteira] = quadro[inteira].astype("int64")
    for decimal in ("faturamento", "custo"):
        quadro[decimal] = quadro[decimal].astype(float)
    quadro["arquivo"] = caminho.name  # de onde veio cada número, quando alguém perguntar
    return quadro.reset_index(drop=True)


def validar(quadro: pd.DataFrame) -> pd.DataFrame:
    """Aplica o esquema. Reprovou, a carga para: dado de forma errada não entra na bronze."""
    return ESQUEMA.validate(quadro, lazy=True)  # lazy: relata todos os erros, não só o primeiro


def ingerir(lake: Lake, caminho: Path) -> tuple[int, str]:
    """Lê, valida e grava a planilha do ano na bronze. Devolve (linhas, caminho no lake)."""
    ano = ano_do_arquivo(caminho)
    quadro = validar(preparar(caminho))
    if set(quadro["competencia"].dt.year) != {ano}:
        raise ValueError(f"{caminho.name}: competências de {set(quadro['competencia'].dt.year)}")
    destino = lake.caminho(CAMADA, MODULO, TABELA, f"ano={ano}.parquet")
    lake.escrever_parquet(quadro, destino)
    return len(quadro), destino


def planilhas(pasta: Path = PASTA) -> list[Path]:
    return sorted(p for p in pasta.glob("consolidado_gerencial_*.xlsx") if ARQUIVO.search(p.name))


def caminho_do_ano(pasta: Path, ano: int) -> Path:
    caminho = pasta / f"consolidado_gerencial_{ano}.xlsx"
    if not caminho.exists():
        raise FileNotFoundError(f"não há planilha do consolidado para {ano} em {pasta}")
    return caminho


def total_declarado(caminho: Path) -> dict[str, float]:
    """A linha de TOTAL da planilha, que a ingestão descarta.

    Descartar não é ignorar: o total é o que a gerente conferiu, e comparar a soma das linhas
    com ele é uma forma barata de perceber que a planilha foi editada à mão depois de fechada.
    """
    bruto = pd.read_excel(caminho, sheet_name=ABA, header=LINHA_DO_CABECALHO)
    bruto = bruto.rename(columns=COLUNAS)
    linha = bruto.loc[bruto["competencia"].astype(str).str.strip().str.upper() == MARCA_DO_TOTAL]
    if len(linha) != 1:
        raise ValueError(f"{caminho.name}: esperava uma linha de TOTAL, achei {len(linha)}")
    return {
        coluna: float(linha[coluna].iloc[0]) for coluna in ("vagas_abertas", "faturamento", "custo")
    }
