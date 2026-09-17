"""Novo CAGED: dos microdados públicos ao índice sazonal que calibra o gerador.

O que sai daqui é só o ritmo do ano, nunca o enredo: para cada escopo (os três municípios do
caso e os estados de SP e MG como reserva) e grupo de atividade (as subclasses 78.10, 78.20 e
78.30 do segmento, e cada seção CNAE nos municípios), quantas admissões e desligamentos houve
por mês, e o índice sazonal (mês dividido pela média do ano, com a média dos anos).

Fonte: microdados do Novo CAGED, PDET/Ministério do Trabalho e Emprego, FTP público
ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/. Três arquivos por competência de
declaração: MOV (no prazo), FOR (fora do prazo) e EXC (exclusões, que invertem o saldo).
Tudo é agregado pela competência da movimentação (competênciamov), não da declaração.

O bruto (7z de ~50 MB e txt de ~400 MB por mês) fica num cache fora do repositório; só as
tabelas derivadas entram no git (dados/publicos/caged/).

Uso:  python -m rh_fictalent.fontes.caged --de 2023-01 --ate 2025-12
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import pandas as pd
import py7zr

from rh_fictalent.observabilidade.logs import FormatadorJSON, obter_logger

log = obter_logger("fontes.caged")  # nome estável mesmo rodando como módulo (__main__)

FTP = "ftp://ftp.mtps.gov.br/pdet/microdados/NOVO%20CAGED"
TIPOS = {"MOV": 1, "FOR": 1, "EXC": -1}  # sinal de cada arquivo sobre o saldo
MUNICIPIOS = {"350410": "Atibaia", "350760": "Bragança Paulista", "312510": "Extrema"}
UFS = {"35": "SP", "31": "MG"}
SUBCLASSES_78 = {"7810800", "7820500", "7830200"}
GRUPO_78 = "78"
COLUNAS = ("competenciamov", "uf", "municipio", "secao", "subclasse", "saldomovimentacao")
SAIDA_PADRAO = Path("dados/publicos/caged")
CACHE_PADRAO = Path.home() / "refs_privadas" / "fictalent" / "caged"

Chave = tuple[str, str, str]  # (competencia AAAA-MM, escopo, grupo)


def _ascii(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def competencias(de: str, ate: str) -> list[str]:
    """Lista AAAAMM de `de` até `ate` (formato AAAA-MM), inclusive."""
    inicio, fim = pd.Period(de, "M"), pd.Period(ate, "M")
    return [p.strftime("%Y%m") for p in pd.period_range(inicio, fim, freq="M")]


def baixar(competencia: str, cache: Path) -> dict[str, Path]:
    """Baixa MOV, FOR e EXC da competência de declaração para o cache, se ainda não estiverem lá."""
    cache.mkdir(parents=True, exist_ok=True)
    caminhos: dict[str, Path] = {}
    for tipo in TIPOS:
        nome = f"CAGED{tipo}{competencia}.7z"
        destino = cache / nome
        if not destino.exists() or destino.stat().st_size == 0:
            url = f"{FTP}/{competencia[:4]}/{competencia}/{nome}"
            if not url.startswith(
                FTP + "/"
            ):  # só o FTP público do MTE; nunca file:// ou outro esquema
                raise ValueError(f"URL fora da fonte: {url}")
            log.info("baixando %s", url)
            urllib.request.urlretrieve(url, destino)  # noqa: S310 # nosec B310
        caminhos[tipo] = destino
    return caminhos


def extrair(arquivo_7z: Path, destino: Path) -> Path:
    with py7zr.SevenZipFile(arquivo_7z, mode="r") as z:
        (nome,) = z.getnames()
        z.extractall(path=destino)
    return destino / str(nome)


def agregar(
    texto: TextIO, sinal: int, acumulado: dict[Chave, list[int]] | None = None
) -> dict[Chave, list[int]]:
    """Lê um arquivo do CAGED em fluxo e acumula [admissões, desligamentos] por chave.

    Municípios do caso: uma chave por seção CNAE e uma para o grupo 78 (quando a subclasse é
    78.10, 78.20 ou 78.30). Estados de SP e MG: só o grupo 78, como reserva de amostra.
    """
    acumulado = {} if acumulado is None else acumulado
    for pedaco in pd.read_csv(texto, sep=";", dtype=str, chunksize=500_000, encoding="utf-8"):
        pedaco.columns = [_ascii(c) for c in pedaco.columns]
        p = pedaco[list(COLUNAS)]
        p = p[
            p["municipio"].isin(MUNICIPIOS)
            | (p["uf"].isin(UFS) & p["subclasse"].isin(SUBCLASSES_78))
        ]
        for competencia, uf, municipio, secao, subclasse, saldo in p.itertuples(index=False):
            comp = f"{competencia[:4]}-{competencia[4:6]}"
            posicao = 0 if saldo == "1" else 1
            chaves: list[Chave] = []
            if municipio in MUNICIPIOS:
                chaves.append((comp, municipio, secao))
                if subclasse in SUBCLASSES_78:
                    chaves.append((comp, municipio, GRUPO_78))
            if uf in UFS and subclasse in SUBCLASSES_78:
                chaves.append((comp, uf, GRUPO_78))
            for chave in chaves:
                acumulado.setdefault(chave, [0, 0])[posicao] += sinal
    return acumulado


def tabela_mensal(acumulado: dict[Chave, list[int]], de: str, ate: str) -> pd.DataFrame:
    linhas = [
        {"competencia": c, "escopo": e, "grupo": g, "admissoes": a, "desligamentos": d}
        for (c, e, g), (a, d) in acumulado.items()
        if de <= c <= ate
    ]
    tabela = (
        pd.DataFrame(linhas).sort_values(["escopo", "grupo", "competencia"]).reset_index(drop=True)
    )
    tabela["saldo"] = tabela["admissoes"] - tabela["desligamentos"]
    tabela["nome_escopo"] = tabela["escopo"].map({**MUNICIPIOS, **UFS})
    return tabela


def indice_sazonal(mensal: pd.DataFrame) -> pd.DataFrame:
    """Por escopo e grupo: o índice de cada mês do ano (mês ÷ média do ano), na média dos anos.

    Um índice 1,3 em novembro quer dizer 30% acima da média do ano; a média dos 12 índices de
    cada ano é 1 por construção. amostra_media é a média mensal de admissões, para julgar se a
    amostra sustenta o índice (abaixo de ~30 por mês, use a reserva estadual).
    """
    m = mensal.copy()
    m["ano"] = m["competencia"].str[:4]
    m["mes"] = m["competencia"].str[5:7].astype(int)
    saida = []
    for (escopo, grupo), bloco in m.groupby(["escopo", "grupo"]):
        indices = defaultdict(list)
        for _, ano in bloco.groupby("ano"):
            if len(ano) < 12:
                continue  # ano incompleto não entra no índice
            for medida in ("admissoes", "desligamentos"):
                media = ano[medida].mean()
                for mes, valor in zip(ano["mes"], ano[medida], strict=True):
                    indices[(medida, mes)].append(valor / media if media else 0.0)
        for mes in range(1, 13):
            adm = indices.get(("admissoes", mes), [])
            des = indices.get(("desligamentos", mes), [])
            if not adm:
                continue
            saida.append(
                {
                    "escopo": escopo,
                    "nome_escopo": {**MUNICIPIOS, **UFS}.get(str(escopo), ""),
                    "grupo": grupo,
                    "mes": mes,
                    "indice_admissoes": round(sum(adm) / len(adm), 4),
                    "indice_desligamentos": round(sum(des) / len(des), 4),
                    "anos": len(adm),
                    "amostra_media": round(bloco["admissoes"].mean(), 1),
                }
            )
    return pd.DataFrame(saida)


def derivar(de: str, ate: str, cache: Path, saida: Path, manter_txt: bool = False) -> pd.DataFrame:
    """Baixa, agrega e escreve as duas tabelas e o registro da fonte. Devolve o índice."""
    acumulado: dict[Chave, list[int]] = {}
    extracao = cache / "tmp"
    meses = competencias(de, ate)
    for i, competencia in enumerate(meses, 1):
        caminhos = baixar(competencia, cache)
        for tipo, sinal in TIPOS.items():
            txt = extrair(caminhos[tipo], extracao)
            with txt.open(encoding="utf-8") as arquivo:
                agregar(arquivo, sinal, acumulado)
            if not manter_txt:
                txt.unlink()
        log.info("competência %s agregada (%s de %s)", competencia, i, len(meses))
    mensal = tabela_mensal(acumulado, de, ate)
    indice = indice_sazonal(mensal)
    saida.mkdir(parents=True, exist_ok=True)
    mensal.to_csv(saida / "movimentacao_mensal.csv", index=False, lineterminator="\n")
    indice.to_csv(saida / "indice_sazonal.csv", index=False, lineterminator="\n")
    (saida / "fonte.json").write_text(
        json.dumps(
            {
                "fonte": "Novo CAGED, microdados não identificados, PDET/MTE",
                "url": FTP.replace("%20", " "),
                "arquivos": "CAGEDMOV, CAGEDFOR e CAGEDEXC de cada competência de declaração",
                "agregacao": "por competência da movimentação; MOV + FOR - EXC",
                "competencias_declaracao": [f"{m[:4]}-{m[4:]}" for m in meses],
                "escopos": {**MUNICIPIOS, **UFS},
                "grupo_78": sorted(SUBCLASSES_78),
                "baixado_em": datetime.now(UTC).isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return indice


def main() -> None:
    parser = argparse.ArgumentParser(description="Deriva o índice sazonal do Novo CAGED.")
    parser.add_argument("--de", default="2023-01")
    parser.add_argument("--ate", default="2025-12")
    parser.add_argument("--cache", type=Path, default=CACHE_PADRAO)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument("--manter-txt", action="store_true")
    args = parser.parse_args()
    saida_json = logging.StreamHandler(sys.stdout)
    saida_json.setFormatter(FormatadorJSON())
    logging.basicConfig(level=logging.INFO, handlers=[saida_json])  # progresso em JSON
    indice = derivar(args.de, args.ate, args.cache, args.saida, args.manter_txt)
    escopos = indice["escopo"].nunique() if len(indice) else 0
    print(f"{args.saida}: {len(indice)} linhas de índice, {escopos} escopos")


if __name__ == "__main__":
    main()
