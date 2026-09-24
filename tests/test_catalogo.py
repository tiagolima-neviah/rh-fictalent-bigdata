"""O catálogo de achados anda junto com os registros da auditoria, e o documento é gerado deles."""

from __future__ import annotations

from pathlib import Path

import pytest

from rh_fictalent.auditoria import achados, catalogo


def test_toda_entrada_casa_com_um_achado_e_todo_achado_com_severidade_tem_entrada() -> None:
    pares = catalogo.casar()
    com_severidade = [a for a in achados.carregar() if a.severidade != "nenhuma"]
    assert len(pares) == len(com_severidade) == len(catalogo.ENTRADAS)


def test_codigos_unicos_e_no_formato() -> None:
    codigos = [e.codigo for e in catalogo.ENTRADAS]
    assert len(codigos) == len(set(codigos))
    for codigo in codigos:
        prefixo, numero = codigo.split("-")
        assert prefixo in {"CAD", "COM", "ATS", "PES", "PON", "FOL", "FIN", "TSS", "SEG"}
        assert numero.isdigit() and len(numero) == 2


def test_o_numero_nao_e_digitado_na_entrada() -> None:
    """A redação técnica pode citar linhas, total e fração só por marcador: quem digita número
    numa entrada congela um valor que o registro vai contradizer na próxima auditoria."""
    for entrada in catalogo.ENTRADAS:
        assert "{linhas}" in entrada.detalhe or "{total}" in entrada.detalhe, entrada.codigo


def test_toda_entrada_nasce_proposta_ou_com_decisao_registrada() -> None:
    for entrada in catalogo.ENTRADAS:
        assert entrada.situacao in {"proposta", "aprovada", "ajustada", "recusada"}, entrada.codigo
        if entrada.tratamento is catalogo.Tratamento.PEDIR:
            assert entrada.acao_cliente, f"{entrada.codigo}: pedir exige dizer o que se pede"
        if entrada.origem:
            assert entrada.acao_cliente, f"{entrada.codigo}: correção na origem exige a ação"


def test_o_documento_gerado_tem_todos_os_codigos_e_as_seis_declaracoes() -> None:
    texto = catalogo.gerar_markdown()
    for entrada in catalogo.ENTRADAS:
        assert f"#### {entrada.codigo} · {entrada.titulo}" in texto
    assert texto.count("**confirmada**") == 6
    assert "## 5. O que não se trata" in texto
    assert "{linhas}" not in texto and "{pct}" not in texto


def test_o_documento_versionado_e_o_gerado(tmp_path: Path) -> None:
    """`docs/13` é gerado: se divergir do que o código produz, alguém editou à mão ou esqueceu
    de gerar depois de mudar uma entrada ou refazer a auditoria."""
    versionado = catalogo.DESTINO
    if not versionado.exists():
        pytest.skip("docs/13 ainda não gerado")
    gerado = catalogo.gerar(tmp_path / "13.md")
    assert gerado.read_text(encoding="utf-8") == versionado.read_text(encoding="utf-8")
