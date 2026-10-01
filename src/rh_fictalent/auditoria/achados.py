"""O registro de achados: o que cada notebook encontrou, num formato que o próximo passo lê.

Um achado é um defeito medido: em que tabela e coluna, quantas linhas de quantas, com que
severidade, o que ele custa ao negócio e o que fazer. O notebook anota os achados ao longo
das seções e, no fechamento, grava o registro em `dados/auditoria/<dominio>.json`. É desse
arquivo que o catálogo de achados (o passo seguinte, aprovado antes de qualquer
transformação) parte: o notebook descobre, o catálogo decide, a silver executa.

Uma hipótese testada e refutada também é anotada, com zero linhas e severidade `nenhuma`:
saber que um defeito esperado **não** existe é informação para quem aprova o catálogo, e
some se ficar só num parágrafo.

O critério de severidade é o mesmo dos outros projetos da casa:

| severidade | critério |
|---|---|
| alta | impede uma análise, distorce indicador ou compromete uma decisão |
| media | exige tratamento na silver, sem impedir a análise |
| baixa | incomoda, mas não muda conclusão |
| nenhuma | hipótese testada e refutada, ou ponto forte que vale registrar |
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

SEVERIDADES = ("alta", "media", "baixa", "nenhuma")
PASTA = Path(__file__).resolve().parents[3] / "dados" / "auditoria"


@dataclass(frozen=True)
class Achado:
    dominio: str
    secao: str  # a seção do notebook em que foi encontrado, para quem quiser conferir
    tabela: str
    coluna: str
    achado: str  # uma frase: o que está errado
    linhas: int
    total: int
    severidade: str
    impacto: str  # o que isso custa ao negócio ou à análise
    acao: str  # o que se propõe fazer (a decisão é do catálogo, não do notebook)
    declaracao: str = ""  # a declaração do cliente que este achado testa, se houver

    @property
    def pct(self) -> float:
        return round(self.linhas / self.total * 100, 2) if self.total else 0.0


class Registro:
    """Os achados de um domínio, anotados ao longo do notebook."""

    def __init__(self, dominio: str) -> None:
        self.dominio = dominio
        self._itens: list[Achado] = []

    def anotar(
        self,
        *,
        secao: str,
        tabela: str,
        coluna: str,
        achado: str,
        linhas: int,
        total: int,
        severidade: str,
        impacto: str,
        acao: str,
        declaracao: str = "",
    ) -> Achado:
        if severidade not in SEVERIDADES:
            raise ValueError(f"severidade {severidade!r}; use uma de {SEVERIDADES}")
        if not 0 <= linhas <= max(total, 0):
            raise ValueError(f"linhas={linhas} fora de [0, total={total}]")
        if linhas == 0 and severidade != "nenhuma":
            raise ValueError("achado com zero linhas só entra como severidade 'nenhuma'")
        item = Achado(
            self.dominio,
            secao,
            tabela,
            coluna,
            achado,
            int(linhas),
            int(total),
            severidade,
            impacto,
            acao,
            declaracao,
        )
        self._itens.append(item)
        return item

    def __len__(self) -> int:
        return len(self._itens)

    @property
    def itens(self) -> list[Achado]:
        return list(self._itens)

    def tabela(self) -> pd.DataFrame:
        return consolidar(self._itens)

    def resumo(self) -> pd.DataFrame:
        return resumir(self._itens)

    def salvar(self, referencia: str, pasta: Path = PASTA) -> Path:
        """Grava `<pasta>/<dominio>.json`; `referencia` é o instante dos dados auditados."""
        pasta.mkdir(parents=True, exist_ok=True)
        caminho = pasta / f"{self.dominio}.json"
        conteudo = {
            "dominio": self.dominio,
            "referencia": referencia,
            "achados": [asdict(a) for a in self._itens],
        }
        caminho.write_text(
            json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return caminho


def carregar(pasta: Path = PASTA) -> list[Achado]:
    """Todos os achados gravados, de todos os domínios, na ordem dos arquivos."""
    achados: list[Achado] = []
    for caminho in sorted(pasta.glob("*.json")):
        conteudo = json.loads(caminho.read_text(encoding="utf-8"))
        achados += [Achado(**a) for a in conteudo["achados"]]
    return achados


def consolidar(achados: list[Achado]) -> pd.DataFrame:
    """Uma linha por achado, da severidade mais alta para a mais baixa e, dentro dela, pela
    fração de linhas atingidas."""
    colunas = [
        "dominio",
        "secao",
        "tabela",
        "coluna",
        "achado",
        "linhas",
        "total",
        "pct",
        "severidade",
        "impacto",
        "acao",
        "declaracao",
    ]
    if not achados:
        return pd.DataFrame(columns=colunas)
    quadro = pd.DataFrame([{**asdict(a), "pct": a.pct} for a in achados])[colunas]
    ordem = {s: i for i, s in enumerate(SEVERIDADES)}
    quadro["_ordem"] = quadro["severidade"].map(ordem)
    return (
        quadro.sort_values(["_ordem", "pct"], ascending=[True, False])
        .drop(columns="_ordem")
        .reset_index(drop=True)
    )


def resumir(achados: list[Achado]) -> pd.DataFrame:
    """Quantos achados por severidade, na ordem da tabela de critérios."""
    contagem = {s: sum(1 for a in achados if a.severidade == s) for s in SEVERIDADES}
    return pd.DataFrame({"severidade": list(contagem), "achados": list(contagem.values())})
