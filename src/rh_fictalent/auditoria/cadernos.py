"""Os notebooks da auditoria: executar do início ao fim e verificar o padrão.

Notebook que só funciona na ordem em que foi executado à mão não é reprodutível. Aqui cada
um é executado num kernel novo, de cima a baixo, e gravado com as saídas; é essa versão que
vai para o repositório. O verificador confere o que o padrão de entrega exige e o que a
regra da auditoria às cegas proíbe:

- toda célula tem `id` (nbformat 4.5), para o editor não inventar um e criar conflito;
- o cabeçalho diz autor, objetivo e base analisada;
- cada seção numerada fecha com uma Nota Técnica de três campos (Observado, Por que importa,
  Ação), e há uma Nota Técnica de fechamento;
- toda célula de código foi executada (tem número de execução);
- nenhum caminho absoluto de máquina aparece no código nem nas saídas;
- **nenhuma célula importa o gerador nem a régua**: a auditoria procura os defeitos no dado,
  sem consultar o que foi plantado. É o que faz do catálogo uma prova, não uma cópia.
"""

from __future__ import annotations

import re
from pathlib import Path

import nbformat
from nbclient import NotebookClient

PASTA = Path(__file__).resolve().parents[3] / "notebooks" / "auditoria"
VERSAO_MINIMA = (4, 5)
CAMPOS_DA_NOTA = ("**Observado:**", "**Por que importa:**", "**Ação:**")
PROIBIDOS = ("rh_fictalent.gerador", "rh_fictalent.validacao", ".contexto")
CAMINHOS_DE_MAQUINA = re.compile(r"(/home/\w+|/Users/\w+|[A-Z]:\\Users)")


def listar(pasta: Path = PASTA) -> list[Path]:
    return sorted(p for p in pasta.glob("*.ipynb") if ".ipynb_checkpoints" not in p.parts)


def executar(caminho: Path, tempo_limite: int = 3600) -> Path:
    """Roda o notebook de cima a baixo num kernel novo e o regrava com as saídas."""
    nb = nbformat.read(caminho, as_version=4)  # type: ignore[no-untyped-call]
    cliente = NotebookClient(
        nb,
        timeout=tempo_limite,
        kernel_name="python3",
        resources={"metadata": {"path": str(caminho.parent)}},
    )
    cliente.execute()
    nbformat.write(nb, caminho)  # type: ignore[no-untyped-call]
    return caminho


def verificar(caminho: Path) -> list[str]:
    """Os problemas do notebook contra o padrão; lista vazia é aprovado."""
    nb = nbformat.read(caminho, as_version=4)  # type: ignore[no-untyped-call]
    problemas: list[str] = []
    if (nb.nbformat, nb.nbformat_minor) < VERSAO_MINIMA:
        problemas.append(f"nbformat {nb.nbformat}.{nb.nbformat_minor} < 4.5: células sem id")
    celulas = list(nb.cells)
    if not celulas or celulas[0].cell_type != "markdown" or not celulas[0].source.startswith("# "):
        problemas.append("a primeira célula não é o cabeçalho (markdown começando por '# ')")
    else:
        for campo in ("**Autor:**", "**Objetivo:**", "**Base analisada:**"):
            if campo not in celulas[0].source:
                problemas.append(f"cabeçalho sem {campo}")

    secao_aberta: str | None = None
    tem_nota = False
    fechamento = False
    for i, celula in enumerate(celulas):
        if not celula.get("id"):
            problemas.append(f"célula {i} sem id")
        fonte = celula.source
        if celula.cell_type == "markdown":
            titulo = re.match(r"^#\s+(\d+)\.", fonte)
            if titulo:
                if secao_aberta is not None and not tem_nota:
                    problemas.append(f"seção {secao_aberta} sem Nota Técnica")
                secao_aberta, tem_nota = titulo.group(1), False
            if fonte.startswith("## Nota Técnica"):
                tem_nota = True
                faltando = [c for c in CAMPOS_DA_NOTA if c not in fonte]
                if "fechamento" in fonte.splitlines()[0].lower():
                    fechamento = True
                elif faltando:
                    problemas.append(f"Nota Técnica da célula {i} sem {', '.join(faltando)}")
        else:
            if celula.get("execution_count") is None:
                problemas.append(f"célula de código {i} não executada")
            for proibido in PROIBIDOS:
                if proibido in fonte:
                    problemas.append(f"célula {i} consulta {proibido}: a auditoria é às cegas")
            textos = [fonte] + [
                "".join(s.get("text", "")) + "".join(s.get("data", {}).get("text/plain", ""))
                for s in celula.get("outputs", [])
            ]
            for texto in textos:
                if CAMINHOS_DE_MAQUINA.search(texto):
                    problemas.append(f"célula {i} expõe caminho de máquina")
                    break
    if secao_aberta is not None and not tem_nota:
        problemas.append(f"seção {secao_aberta} sem Nota Técnica")
    if not fechamento:
        problemas.append("sem Nota Técnica de fechamento")
    return problemas
