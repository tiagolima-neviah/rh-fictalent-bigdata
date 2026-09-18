"""A régua: o motor que confere medidas contra bandas e emite o laudo.

A régua é o contrato de aceite do dado sintético. Antes de o gerador rodar, as bandas já
existem (rh_fictalent.validacao.bandas); depois que ele roda, cada medida da base é
conferida contra a sua banda e o laudo diz aprovado ou reprovado. Reprovou, regenera: o
gerador é recalibrado, o dado nunca é remendado.

O motor é deliberadamente simples. Todo check é "um número dentro de uma faixa":

- uma Medida é um número com nome e chave (headcount_medio["2024"] = 903);
- uma Banda é a faixa aceita (mínimo, máximo ou os dois);
- um Check liga uma medida a uma banda, com código, família e descrição;
- o Laudo junta os resultados e dá o veredito.

Checks que parecem mais complexos (variação contra a média móvel, desvio contra o índice
do CAGED) viram um número antes de chegar aqui, em rh_fictalent.validacao.derivadas.
Medida ausente não aprova nem reprova: fica PENDENTE e o laudo sai INCOMPLETO, o que permite
rodar a régua família a família enquanto o gerador é construído por etapas.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

FAMILIAS = {
    "escala": "1 · Escala e forma",
    "naturalidade": "2 · Naturalidade das transições",
    "historia": "3 · A história",
    "sazonalidade": "4 · Sazonalidade",
    "coerencia": "5 · Coerência interna",
    "sujeira": "6 · A sujeira na medida certa",
}

# nome da medida -> chave -> valor; chaves são texto ("2024", "2024-11", "CAD-01") para o
# contrato caber num JSON
Medidas = Mapping[str, Mapping[str, float]]


class Situacao(StrEnum):
    APROVADO = "APROVADO"
    REPROVADO = "REPROVADO"
    PENDENTE = "PENDENTE"


class Veredito(StrEnum):
    APROVADA = "APROVADA"
    REPROVADA = "REPROVADA"
    INCOMPLETA = "INCOMPLETA"


@dataclass(frozen=True)
class Banda:
    """A faixa aceita para uma medida, com os dois limites incluídos."""

    minimo: float | None = None
    maximo: float | None = None

    def __post_init__(self) -> None:
        if self.minimo is None and self.maximo is None:
            raise ValueError("banda sem limite não confere nada")
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError(f"banda invertida: {self.minimo} > {self.maximo}")

    @classmethod
    def em_torno(cls, centro: float, absoluta: float = 0.0, relativa: float = 0.0) -> Banda:
        """Centro mais ou menos a maior das duas tolerâncias (absoluta, ou relativa ao centro)."""
        tolerancia = max(absoluta, abs(centro) * relativa)
        return cls(centro - tolerancia, centro + tolerancia)

    @classmethod
    def exatamente(cls, valor: float) -> Banda:
        return cls(valor, valor)

    def contem(self, valor: float) -> bool:
        if math.isnan(valor):
            return False
        if self.minimo is not None and valor < self.minimo:
            return False
        return not (self.maximo is not None and valor > self.maximo)

    def centro(self) -> float:
        """O valor mais confortável dentro da banda (o meio, ou o único limite)."""
        if self.minimo is not None and self.maximo is not None:
            return (self.minimo + self.maximo) / 2
        return self.minimo if self.minimo is not None else float(self.maximo or 0.0)

    def __str__(self) -> str:
        if self.minimo is not None and self.maximo is not None:
            if self.minimo == self.maximo:
                return f"= {_numero(self.minimo)}"
            return f"[{_numero(self.minimo)}, {_numero(self.maximo)}]"
        if self.minimo is not None:
            return f">= {_numero(self.minimo)}"
        return f"<= {_numero(float(self.maximo or 0.0))}"


@dataclass(frozen=True)
class Check:
    codigo: str  # único, ex.: "E-02/2024"
    familia: str  # chave de FAMILIAS
    descricao: str
    medida: str  # nome no contrato de medidas
    chave: str  # chave dentro da medida
    banda: Banda

    def __post_init__(self) -> None:
        if self.familia not in FAMILIAS:
            raise ValueError(f"família desconhecida: {self.familia!r}")


@dataclass(frozen=True)
class Resultado:
    check: Check
    valor: float | None
    situacao: Situacao


@dataclass(frozen=True)
class Laudo:
    resultados: tuple[Resultado, ...]

    @property
    def veredito(self) -> Veredito:
        situacoes = {r.situacao for r in self.resultados}
        if Situacao.REPROVADO in situacoes:
            return Veredito.REPROVADA
        if Situacao.PENDENTE in situacoes or not self.resultados:
            return Veredito.INCOMPLETA
        return Veredito.APROVADA

    def com_situacao(self, situacao: Situacao) -> tuple[Resultado, ...]:
        return tuple(r for r in self.resultados if r.situacao == situacao)

    def resumo(self) -> dict[str, dict[str, int]]:
        """Por família: quantos checks aprovados, reprovados e pendentes."""
        contagem: dict[str, dict[str, int]] = {}
        for r in self.resultados:
            linha = contagem.setdefault(r.check.familia, {s.value: 0 for s in Situacao})
            linha[r.situacao.value] += 1
        return contagem

    def texto(self, so_problemas: bool = False) -> str:
        """O laudo para ler no terminal: família a família, um check por linha."""
        marca = {Situacao.APROVADO: "✓", Situacao.REPROVADO: "✗", Situacao.PENDENTE: "…"}
        linhas: list[str] = []
        for familia, titulo in FAMILIAS.items():
            da_familia = [r for r in self.resultados if r.check.familia == familia]
            if not da_familia:
                continue
            n = {s: sum(1 for r in da_familia if r.situacao == s) for s in Situacao}
            linhas.append(
                f"\n{titulo}: {n[Situacao.APROVADO]} ✓  {n[Situacao.REPROVADO]} ✗  "
                f"{n[Situacao.PENDENTE]} …"
            )
            for r in da_familia:
                if so_problemas and r.situacao == Situacao.APROVADO:
                    continue
                valor = "sem medida" if r.valor is None else _numero(r.valor)
                linhas.append(
                    f"  {marca[r.situacao]} {r.check.codigo:<28} {valor:>14}  "
                    f"banda {r.check.banda!s:<22} {r.check.descricao}"
                )
        total = len(self.resultados)
        reprovados = len(self.com_situacao(Situacao.REPROVADO))
        pendentes = len(self.com_situacao(Situacao.PENDENTE))
        linhas.append(
            f"\nRÉGUA {self.veredito.value}: {total - reprovados - pendentes} de {total} checks "
            f"aprovados, {reprovados} reprovados, {pendentes} pendentes."
        )
        if self.veredito == Veredito.REPROVADA:
            linhas.append("Reprovou, regenera: recalibre o gerador; o dado não se remenda.")
        return "\n".join(linhas).lstrip("\n")

    def para_json(self) -> str:
        corpo: dict[str, Any] = {
            "veredito": self.veredito.value,
            "resumo": self.resumo(),
            "resultados": [
                {
                    "codigo": r.check.codigo,
                    "familia": r.check.familia,
                    "descricao": r.check.descricao,
                    "medida": r.check.medida,
                    "chave": r.check.chave,
                    "banda": {"minimo": r.check.banda.minimo, "maximo": r.check.banda.maximo},
                    "valor": r.valor,
                    "situacao": r.situacao.value,
                }
                for r in self.resultados
            ],
        }
        return json.dumps(corpo, ensure_ascii=False, indent=2)


def avaliar(
    checks: Iterable[Check], medidas: Medidas, familias: Iterable[str] | None = None
) -> Laudo:
    """Confere cada check contra as medidas. `familias` restringe a régua a parte do contrato."""
    escolhidas = set(familias) if familias is not None else set(FAMILIAS)
    desconhecidas = escolhidas - set(FAMILIAS)
    if desconhecidas:
        raise ValueError(f"famílias desconhecidas: {sorted(desconhecidas)}")
    resultados: list[Resultado] = []
    for check in checks:
        if check.familia not in escolhidas:
            continue
        bruto = medidas.get(check.medida, {}).get(check.chave)
        if bruto is None:
            resultados.append(Resultado(check, None, Situacao.PENDENTE))
            continue
        valor = float(bruto)
        situacao = Situacao.APROVADO if check.banda.contem(valor) else Situacao.REPROVADO
        resultados.append(Resultado(check, valor, situacao))
    return Laudo(tuple(resultados))


def _numero(valor: float) -> str:
    """Número legível: inteiro sem casas, fração com até 4 casas significativas."""
    if math.isnan(valor):
        return "nan"
    if float(valor).is_integer() and abs(valor) < 1e15:
        return f"{int(valor):,}".replace(",", ".")
    return f"{valor:.4g}".replace(".", ",")
