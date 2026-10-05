"""A matriz de barramento contra o que existe: a silver, as marcas de qualidade, os indicadores
do entendimento do negócio e as sete afirmações dos donos."""

from __future__ import annotations

import re
from pathlib import Path

from rh_fictalent.gold import barramento
from rh_fictalent.gold.barramento import AFIRMACOES, DIMENSOES, FATOS, INDICADORES
from rh_fictalent.silver import construcao

RAIZ = Path(__file__).resolve().parents[1]
SILVER = set(construcao.TABELAS)
NOMES_DE_DIMENSAO = {d.nome for d in DIMENSOES}
NOMES_DE_FATO = {f.nome for f in FATOS}


def test_nomes_unicos_e_no_padrao() -> None:
    assert len(NOMES_DE_FATO) == len(FATOS) and len(NOMES_DE_DIMENSAO) == len(DIMENSOES)
    assert all(f.nome.startswith("fato_") for f in FATOS)
    assert all(d.nome.startswith("dim_") for d in DIMENSOES)
    assert {f.familia for f in FATOS} <= set(barramento.FAMILIAS)
    assert {f.prioridade for f in FATOS} | {d.prioridade for d in DIMENSOES} == {1, 2}


def test_toda_fonte_existe_na_silver_ou_esta_declarada_como_externa() -> None:
    itens: list[barramento.Fato | barramento.Dimensao] = [*FATOS, *DIMENSOES]
    for item in itens:
        desconhecidas = set(item.fontes) - SILVER - set(barramento.EXTERNAS)
        assert not desconhecidas, (item.nome, desconhecidas)
    assert all(f.fontes for f in FATOS)


def test_todo_fato_tem_grao_tempo_e_medida() -> None:
    for f in FATOS:
        assert f.grao and f.medidas, f.nome
        assert {"dim_data", "dim_mes"} & set(f.dimensoes), f"{f.nome} sem dimensão de tempo"
        assert set(f.dimensoes) <= NOMES_DE_DIMENSAO, f.nome


def test_toda_dimensao_e_usada_e_as_conformadas_sao_divididas() -> None:
    uso = {d: [f.nome for f in FATOS if d in f.dimensoes] for d in NOMES_DE_DIMENSAO}
    assert all(uso.values()), [d for d, fatos in uso.items() if not fatos]
    # o que faz a matriz ser de barramento: as dimensões centrais servem a vários fatos
    for central in ("dim_filial", "dim_cliente", "dim_contrato", "dim_posto", "dim_mes"):
        assert len(uso[central]) >= 4, (central, uso[central])


def test_fato_de_prioridade_1_nao_depende_de_dimensao_de_prioridade_2() -> None:
    p2 = {d.nome for d in DIMENSOES if d.prioridade == 2}
    for f in FATOS:
        if f.prioridade == 1:
            assert not set(f.dimensoes) & p2, f.nome


def test_toda_marca_citada_existe_numa_tabela_que_o_fato_le() -> None:
    for f in FATOS:
        das_fontes = {n.nome for t in f.fontes for n in construcao.novas(t) if n.marca}
        assert set(f.marcas) <= das_fontes, (f.nome, set(f.marcas) - das_fontes)


def test_fato_de_saude_nao_leva_pessoa() -> None:
    """O `docs/05` promete: dado de saúde só em agregado, sem chave de pessoa."""
    saude = {"pessoas.afastamento", "sst.aso", "sst.acidente", "sst.cat"}
    detalhe = [
        f for f in FATOS if saude & set(f.fontes) and f.tipo is not barramento.Tipo.PERIODICO
    ]
    assert {f.nome for f in detalhe} == {"fato_afastamento", "fato_saude_ocupacional"}
    for f in detalhe:
        assert not {"dim_colaborador", "dim_candidato"} & set(f.dimensoes), f.nome
    # a foto mensal de conformidade conta pessoas por posto, sem a dimensão de pessoa
    assert "dim_colaborador" not in barramento.fato("fato_conformidade_mes").dimensoes


def test_dimensao_de_pessoa_nao_tem_identidade() -> None:
    proibido = ("nome", "cpf", "documento", "matrícula", "telefone", "e-mail", "login")
    for nome in ("dim_colaborador", "dim_candidato"):
        atributos = " ".join(barramento.dimensao(nome).atributos).lower()
        assert not [p for p in proibido if p in atributos], nome


def test_todo_indicador_do_docs_01_tem_fato() -> None:
    """Os indicadores da seção 3 do entendimento do negócio, um a um, pelo nome em destaque ou
    pela palavra que o identifica."""
    for i in INDICADORES:
        assert set(i.fatos) <= NOMES_DE_FATO and i.fatos and i.como, i.nome
    assert {i.familia for i in INDICADORES} == set(barramento.FAMILIAS) - {"acesso"}
    texto = (RAIZ / "docs" / "01_entendimento_negocio.md").read_text(encoding="utf-8")
    secao = texto.split("## 3. O que a empresa mede")[1].split("## 4.")[0]
    declarados = " ".join(i.nome for i in INDICADORES).lower()
    sem_titulos = re.sub(r"\*\*[^*]+:\*\*", "", secao)  # o título de cada família também é negrito
    destaques = re.findall(r"\*\*([^*]+)\*\*", sem_titulos)
    assert len(destaques) >= 6
    for destaque in destaques:
        chave = destaque.lower().split(" por ")[0].split(" dos ")[0].strip()
        assert chave in declarados, f"indicador em destaque sem linha na matriz: {destaque}"


def test_as_sete_afirmacoes_tem_resposta_em_fato_de_prioridade_1() -> None:
    texto = (RAIZ / "docs" / "01_entendimento_negocio.md").read_text(encoding="utf-8")
    codigos = set(re.findall(r"^\| ([DA]\d) \|", texto, re.M))
    assert {a.codigo for a in AFIRMACOES} == codigos and len(codigos) == 7
    p1 = {f.nome for f in FATOS if f.prioridade == 1}
    for a in AFIRMACOES:
        assert a.fatos and set(a.fatos) <= p1, a.codigo
        assert f'"{a.texto}"' in texto.replace("“", '"').replace("”", '"'), a.codigo
        for d in a.dimensoes:
            assert any(d in barramento.fato(f).dimensoes for f in a.fatos), (a.codigo, d)


def test_o_documento_versionado_e_o_gerado(tmp_path: Path) -> None:
    gerado = barramento.gerar(tmp_path / "15.md").read_text(encoding="utf-8")
    assert gerado == barramento.DESTINO.read_text(encoding="utf-8")
    for f in FATOS:
        assert f'<a id="{f.nome}"></a>' in gerado
    assert "—" not in gerado
