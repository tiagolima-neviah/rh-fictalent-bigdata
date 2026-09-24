"""Confere os números escritos à mão nos textos dos notebooks da auditoria.

Num notebook de análise, os números aparecem em dois regimes. Os que saem de célula
executada se atualizam sozinhos a cada execução. Os que estão escritos numa Nota Técnica,
não: congelam no valor que tinham no dia em que foram digitados, e continuam parecendo
corretos para sempre. Essa assimetria é perigosa porque a Nota é justamente a parte que
o leitor lê.

Este roteiro separa os dois regimes e devolve a lista curta: os números do texto que não
aparecem em nenhuma saída do mesmo notebook. A comparação é pelos dígitos, sem separador
de milhar nem vírgula decimal, porque o texto escreve 1.621 e 1,7% e a saída imprime 1621
e 1.70. Ele não decide se estão errados: muitos são proporções calculadas na escrita. Ele
decide **onde olhar**, que é o que transforma uma revisão impossível numa revisão de vinte
minutos.

Rodar: .venv/bin/python scripts/conferir_numeros_dos_notebooks.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

NOTEBOOKS = Path("notebooks") / "auditoria"

# um número com ou sem separador de milhar, com ou sem parte decimal: 1621, 1.621, 91,48, 0.1025
PADRAO = re.compile(r"\d+(?:[.,]\d{3})*(?:[.,]\d+)?")
ANOS = {str(ano) for ano in range(2010, 2041)}


def canonico(bruto: str) -> str:
    """Só os dígitos: 1.621 -> 1621, 1,70 -> 17, 1,364.45 -> 136445, 91,48% -> 9148.

    O último separador é decimal quando não é seguido de exatamente três dígitos; os
    demais são de milhar. Zeros à direita da parte decimal caem (1,70 e 1,7 são o mesmo).
    """
    partes = re.split(r"[.,]", bruto)
    if len(partes) == 1:
        return bruto
    if len(partes[-1]) == 3 and all(len(x) == 3 for x in partes[1:]):
        return "".join(partes)  # só separadores de milhar
    return "".join(partes[:-1]) + partes[-1].rstrip("0")


def relevantes(texto: str) -> set[str]:
    achados = set()
    for bruto in PADRAO.findall(texto):
        if bruto in ANOS:
            continue
        forma = canonico(bruto)
        if len(forma) <= 2:  # 1 a 99, numeração de seção, versões: ruído garantido
            continue
        achados.add(forma)
    return achados


def main() -> int:
    total_orfaos = 0
    for caminho in sorted(NOTEBOOKS.rglob("*.ipynb")):
        if ".ipynb_checkpoints" in str(caminho):
            continue
        nb = json.loads(caminho.read_text(encoding="utf-8"))

        textos, saidas = [], []
        for celula in nb["cells"]:
            if celula["cell_type"] == "markdown":
                textos.append("".join(celula["source"]))
                continue
            for saida in celula.get("outputs", []):
                saidas.append("".join(saida.get("text", [])))
                saidas.append("".join(saida.get("data", {}).get("text/plain", [])))

        escritos = relevantes("\n".join(textos))
        confirmados = escritos & relevantes("\n".join(saidas))
        orfaos = sorted(escritos - confirmados, key=lambda n: (-len(n), n))
        total_orfaos += len(orfaos)

        print(f"\n{caminho.relative_to(NOTEBOOKS)}")
        print(
            f"  {len(escritos):>3} números no texto · {len(confirmados):>3} confirmados "
            f"por saída · {len(orfaos):>3} a conferir"
        )
        for i in range(0, len(orfaos), 8):
            print("      " + "  ".join(f"{n:>12}" for n in orfaos[i : i + 8]))

    print(f"\n{'-' * 70}")
    print(f"{total_orfaos} número(s) sem correspondência em saída executada.")
    print("Não são erros: são o roteiro de conferência depois de mexer nos dados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
