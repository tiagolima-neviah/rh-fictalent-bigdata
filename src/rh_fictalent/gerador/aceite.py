"""O aceite da base sintética: as seis etapas de ponta a ponta contra a régua inteira.

Cada etapa já confere a própria parte quando é gerada. Aqui a base é gerada inteira, as medidas
de todas as etapas viram um arquivo só (`dados/regua/medidas.json`, o contrato de
`validacao.bandas.MEDIDAS`) e a régua dá o veredito sobre todos os checks
(`dados/regua/laudo.txt`). Com `--replica`, o número de linhas de cada tabela é contado na
réplica e tem de ser o que o gerador produz: o laudo mede a base que está gravada, não outra.

Reprovou, regenera: o que se ajusta é o gerador (ou, com data e motivo, a banda), nunca o dado.
"""

from __future__ import annotations

import json
from pathlib import Path

from rh_fictalent.gerador import (
    etapa1_cadastro,
    etapa2_carteira,
    etapa3_pessoas,
    etapa4_ponto_folha,
    etapa5_financeiro,
    etapa6_conformidade,
)
from rh_fictalent.gerador.nucleo import SEMENTE, Replica, Tabelas
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.regua import Laudo, Medidas, Veredito, avaliar

PASTA = Path("dados/regua")
SAIDA = {Veredito.APROVADA: 0, Veredito.REPROVADA: 1, Veredito.INCOMPLETA: 2}
Juntas = dict[str, dict[str, float]]


def juntar(partes: list[Medidas]) -> Juntas:
    """As medidas das etapas num dicionário só. A mesma medida pode vir de duas etapas (a etapa 3
    repete as da carteira); se vier, tem de ser o mesmo número."""
    juntas: Juntas = {}
    for parte in partes:
        for medida, valores in parte.items():
            for chave, valor in valores.items():
                anterior = juntas.setdefault(medida, {}).setdefault(chave, float(valor))
                if abs(anterior - float(valor)) > 1e-9:
                    raise ValueError(f"{medida}/{chave}: {anterior} numa etapa, {valor} em outra")
    return juntas


def gerar_e_medir(publicos: Path = etapa1_cadastro.PUBLICOS) -> tuple[Juntas, dict[str, int]]:
    """Gera as seis etapas, confere cada uma e devolve as medidas e as linhas por tabela."""
    t5, base = etapa5_financeiro.gerar_com_base(publicos)
    t3: Tabelas = base["etapa3"]
    t4: Tabelas = base["etapa4"]
    t6, base6 = etapa6_conformidade.montar(t3, base)
    etapa3_pessoas.conferir(t3, base)
    etapa4_ponto_folha.conferir(t4, base)
    etapa5_financeiro.conferir(t5, base)
    etapa6_conformidade.conferir(t6, base6)
    medidas = juntar(
        [
            etapa2_carteira.medir(base["carteira"]),
            etapa3_pessoas.medir(t3, base),
            etapa4_ponto_folha.medir(t4, base),
            etapa5_financeiro.medir(t5, base),
            etapa6_conformidade.medir(t6, base6),
        ]
    )
    linhas: dict[str, int] = {}
    for etapa in (base["mundo"], base["carteira"], t3, t4, t5, t6):
        for nome, quadro in etapa.items():  # a etapa 3 continua o cadastro.endereco da etapa 1
            linhas[nome] = linhas.get(nome, 0) + len(quadro)
    return medidas, linhas


def fechar(
    medidas: Juntas, linhas: dict[str, int], replica: Replica | None = None
) -> tuple[Juntas, list[str]]:
    """Fecha a medida de linhas: contadas na réplica, quando há, e iguais às do gerador."""
    contadas = replica.contar(sorted(linhas)) if replica else linhas
    problemas = [
        f"{nome}: {contadas[nome]} linhas na réplica, {linhas[nome]} geradas"
        for nome in sorted(linhas)
        if contadas[nome] != linhas[nome]
    ]
    completas = {medida: dict(valores) for medida, valores in medidas.items()}
    completas["linhas_tabela"] = {nome: float(contadas[nome]) for nome in bandas.LINHAS}
    completas["linhas_tabela"]["total"] = float(sum(contadas.values()))
    return completas, problemas


def escrever(medidas: Juntas, laudo: Laudo, na_replica: bool, pasta: Path = PASTA) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(medidas, ensure_ascii=False, indent=2, sort_keys=True)
    (pasta / "medidas.json").write_text(texto + "\n", encoding="utf-8")
    origem = "contadas na réplica" if na_replica else "contadas no que o gerador produz"
    cabecalho = [
        f"Aceite da base sintética · semente {SEMENTE}",
        f"{int(medidas['linhas_tabela']['total'])} linhas ({origem}).",
        "Para refazer: python -m rh_fictalent.gerador --aceite --replica",
        "",
    ]
    (pasta / "laudo.txt").write_text(
        "\n".join(cabecalho) + "\n" + laudo.texto() + "\n", encoding="utf-8"
    )


def executar(replica: Replica | None = None, pasta: Path = PASTA) -> int:
    medidas, linhas = gerar_e_medir()
    completas, problemas = fechar(medidas, linhas, replica)
    laudo = avaliar(bandas.checks(), completas)
    print(laudo.texto(so_problemas=True))
    for problema in problemas:
        print(f"réplica diferente do gerador: {problema}")
    if problemas:
        return 1
    escrever(completas, laudo, replica is not None, pasta)
    print(f"medidas e laudo em {pasta}")
    return SAIDA[laudo.veredito]
