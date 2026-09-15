"""Navegação da documentação: todo link relativo precisa apontar para algo que existe."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]


def _links_relativos(texto: str) -> list[str]:
    saida = []
    for alvo in re.findall(r"\]\(([^)]+)\)", texto):
        caminho = alvo.split("#")[0].strip()
        if not caminho or caminho.startswith(("http://", "https://", "mailto:")):
            continue
        saida.append(caminho)
    return saida


def test_todo_link_relativo_existe() -> None:
    quebrados = []
    for md in ARQUIVOS:
        for alvo in _links_relativos(md.read_text(encoding="utf-8")):
            if not (md.parent / alvo).resolve().exists():
                quebrados.append(f"{md.relative_to(RAIZ)} -> {alvo}")
    assert not quebrados, "links quebrados: " + "; ".join(quebrados)


def test_cadeia_de_navegacao_dos_docs() -> None:
    docs = sorted((RAIZ / "docs").glob("*.md"))
    for anterior, seguinte in zip(docs, docs[1:], strict=False):
        texto = anterior.read_text(encoding="utf-8")
        assert seguinte.name in texto, f"{anterior.name} não aponta para {seguinte.name}"
        assert "../README.md" in texto, f"{anterior.name} sem link Home"
    assert "../README.md" in docs[-1].read_text(encoding="utf-8")
