"""Fontes públicas por API REST: municípios (IBGE) e feriados nacionais (BrasilAPI).

Toda ingestão de API precisa dos mesmos três cuidados, e eles moram num cliente só:

- timeout: nenhum pedido espera para sempre;
- retry com recuo exponencial: falha de rede, 429 e 5xx são passageiros; a espera dobra a
  cada tentativa e respeita o Retry-After quando a API o manda;
- limite de taxa: um intervalo mínimo entre pedidos, para não derrubar (nem ser bloqueado
  por) uma API pública, que é de todos.

Estas duas APIs não paginam: a lista de municípios de uma UF e os feriados de um ano vêm
inteiros num pedido. A paginação entra no cliente quando uma fonte precisar dela.

O que sai daqui alimenta duas coisas: as tabelas versionadas em dados/publicos, que o
gerador usa para ser reprodutível sem rede, e os assets do Dagster que gravam o mesmo dado
no lake (rh_fictalent.orquestracao.fontes), a primeira ingestão de verdade do pipeline.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from rh_fictalent.observabilidade.logs import FormatadorJSON, obter_logger

log = obter_logger("fontes.apis")

IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades"
BRASILAPI = "https://brasilapi.com.br/api"
UF_CODIGO = {"SP": "35", "MG": "31"}  # as UFs do caso; a API do IBGE recebe o código
ANOS = tuple(range(2018, 2027))  # a história da Fictalent
COLUNAS_MUNICIPIO = (
    "codigo_ibge",
    "nome",
    "uf",
    "microrregiao",
    "mesorregiao",
    "regiao_imediata",
    "regiao_intermediaria",
)
COLUNAS_FERIADO = ("data", "nome", "abrangencia", "ano")
ABRANGENCIA = {"national": "NACIONAL", "state": "ESTADUAL", "municipal": "MUNICIPAL"}
RETENTAVEIS = frozenset({429, 500, 502, 503, 504})
SAIDA_PADRAO = Path("dados/publicos")
AGENTE = "rh-fictalent-bigdata (projeto de estudo)"

# Os testes trocam por um httpx.MockTransport; None é a rede de verdade.
transporte_de_teste: httpx.BaseTransport | None = None


@dataclass
class ClienteHTTP:
    """GET em JSON com timeout, limite de taxa e retry com recuo exponencial."""

    timeout: float = 30.0
    tentativas: int = 5
    intervalo_minimo: float = 0.5  # segundos entre dois pedidos (limite de taxa)
    recuo_inicial: float = 0.5  # segundos; dobra a cada tentativa
    dormir: Callable[[float], None] = time.sleep
    relogio: Callable[[], float] = time.monotonic
    _ultimo_pedido: float | None = field(default=None, init=False, repr=False)

    def obter_json(self, url: str) -> Any:
        cabecalhos = {"User-Agent": AGENTE, "Accept": "application/json"}
        with httpx.Client(
            timeout=self.timeout, transport=transporte_de_teste, headers=cabecalhos
        ) as cliente:
            for tentativa in range(1, self.tentativas + 1):
                self._esperar_a_vez()
                try:
                    resposta = cliente.get(url)
                except httpx.TransportError as erro:
                    if tentativa == self.tentativas:
                        raise
                    self._recuar(tentativa, f"{type(erro).__name__} em {url}", None)
                    continue
                if resposta.status_code in RETENTAVEIS and tentativa < self.tentativas:
                    motivo = f"HTTP {resposta.status_code} em {url}"
                    self._recuar(tentativa, motivo, resposta.headers.get("Retry-After"))
                    continue
                resposta.raise_for_status()
                return resposta.json()
        raise RuntimeError("tentativas esgotadas")  # pragma: no cover

    def _esperar_a_vez(self) -> None:
        """Limite de taxa: garante o intervalo mínimo desde o último pedido."""
        if self._ultimo_pedido is not None:
            falta = self.intervalo_minimo - (self.relogio() - self._ultimo_pedido)
            if falta > 0:
                self.dormir(falta)
        self._ultimo_pedido = self.relogio()

    def _recuar(self, tentativa: int, motivo: str, retry_after: str | None) -> None:
        """Recuo exponencial (0,5 s, 1 s, 2 s...), nunca menor que o Retry-After da API."""
        espera = self.recuo_inicial * 2 ** (tentativa - 1)
        if retry_after and retry_after.isdigit():
            espera = max(espera, float(retry_after))
        log.warning(
            "%s; tentativa %s de %s, a próxima em %.1f s",
            motivo,
            tentativa,
            self.tentativas,
            espera,
        )
        self.dormir(espera)


def municipios(cliente: ClienteHTTP, ufs: Iterable[str] = tuple(UF_CODIGO)) -> pd.DataFrame:
    """Os municípios das UFs, com o código IBGE de 7 dígitos e as quatro regiões do IBGE."""
    linhas: list[dict[str, str]] = []
    for uf in ufs:
        dados = cliente.obter_json(f"{IBGE}/estados/{UF_CODIGO[uf]}/municipios")
        log.info("IBGE: %s municípios em %s", len(dados), uf)
        for m in dados:
            micro = m.get("microrregiao") or {}
            meso = micro.get("mesorregiao") or {}
            imediata = m.get("regiao-imediata") or {}
            intermediaria = imediata.get("regiao-intermediaria") or {}
            linhas.append(
                {
                    "codigo_ibge": str(m["id"]),
                    "nome": str(m["nome"]),
                    "uf": uf,
                    "microrregiao": str(micro.get("nome", "")),
                    "mesorregiao": str(meso.get("nome", "")),
                    "regiao_imediata": str(imediata.get("nome", "")),
                    "regiao_intermediaria": str(intermediaria.get("nome", "")),
                }
            )
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS_MUNICIPIO))
    return tabela.sort_values(["uf", "codigo_ibge"]).reset_index(drop=True)


def feriados(cliente: ClienteHTTP, anos: Iterable[int] = ANOS) -> pd.DataFrame:
    """Os feriados nacionais de cada ano, com a abrangência no vocabulário da réplica."""
    linhas: list[dict[str, Any]] = []
    for ano in anos:
        dados = cliente.obter_json(f"{BRASILAPI}/feriados/v1/{ano}")
        log.info("BrasilAPI: %s feriados em %s", len(dados), ano)
        for f in dados:
            linhas.append(
                {
                    "data": str(f["date"]),
                    "nome": str(f["name"]),
                    "abrangencia": ABRANGENCIA.get(str(f.get("type", "")), "NACIONAL"),
                    "ano": int(ano),
                }
            )
    tabela = pd.DataFrame(linhas, columns=list(COLUNAS_FERIADO))
    return tabela.sort_values(["data", "nome"]).reset_index(drop=True)


def _gravar(pasta: Path, nome: str, tabela: pd.DataFrame, fonte: dict[str, Any]) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    tabela.to_csv(pasta / nome, index=False)
    fonte["baixado_em"] = datetime.now(UTC).isoformat(timespec="seconds")
    fonte["linhas"] = int(len(tabela))
    texto = json.dumps(fonte, ensure_ascii=False, indent=2) + "\n"
    (pasta / "fonte.json").write_text(texto, encoding="utf-8")


def derivar(cliente: ClienteHTTP, saida: Path = SAIDA_PADRAO) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Baixa as duas fontes e reescreve as tabelas versionadas, cada uma com o seu fonte.json."""
    tabela_municipios = municipios(cliente)
    _gravar(
        saida / "ibge",
        "municipios.csv",
        tabela_municipios,
        {
            "fonte": "IBGE, API de localidades v1",
            "url": f"{IBGE}/estados/{{codigo_uf}}/municipios",
            "ufs": list(UF_CODIGO),
            "colunas": list(COLUNAS_MUNICIPIO),
        },
    )
    tabela_feriados = feriados(cliente)
    _gravar(
        saida / "brasilapi",
        "feriados_nacionais.csv",
        tabela_feriados,
        {
            "fonte": "BrasilAPI, feriados nacionais v1",
            "url": f"{BRASILAPI}/feriados/v1/{{ano}}",
            "anos": [ANOS[0], ANOS[-1]],
            "colunas": list(COLUNAS_FERIADO),
        },
    )
    return tabela_municipios, tabela_feriados


def main() -> None:
    parser = argparse.ArgumentParser(description="Municípios (IBGE) e feriados (BrasilAPI).")
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args()
    saida_json = logging.StreamHandler(sys.stdout)
    saida_json.setFormatter(FormatadorJSON())
    logging.basicConfig(level=logging.INFO, handlers=[saida_json])  # progresso em JSON
    tabela_municipios, tabela_feriados = derivar(ClienteHTTP(), args.saida)
    print(f"{args.saida}: {len(tabela_municipios)} municípios, {len(tabela_feriados)} feriados")


if __name__ == "__main__":
    main()
