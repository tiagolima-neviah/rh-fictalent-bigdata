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


def test_o_docs_20_concentra_os_sintomas_e_o_manual_aponta_para_ele() -> None:
    """A tabela de problemas mudou do manual (§10) para o docs/20; o manual só aponta."""
    docs = RAIZ / "docs"
    vinte = (docs / "20_solucao_de_problemas.md").read_text(encoding="utf-8")
    manual = (docs / "08_manual_de_operacao.md").read_text(encoding="utf-8")
    for sintoma in (
        "required variable ... is missing a value",
        "ChildProcessCrashException",
        "XA crash recovery",
        "sem marca d'água",
        "permission denied to set role",
        "The specified key does not exist",
        "xdg-open",
    ):
        assert sintoma in vinte, sintoma
        assert sintoma not in manual.split("## 10. Quando algo não sobe")[1].split("## ")[0], (
            sintoma
        )
    assert "20_solucao_de_problemas.md" in manual
    assert vinte.count("| ") > 40  # as tabelas por área
