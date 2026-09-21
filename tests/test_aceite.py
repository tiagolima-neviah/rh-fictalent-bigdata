"""O aceite: a base inteira contra a régua inteira, e o laudo versionado é o da base gerada."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from dotenv import dotenv_values

from rh_fictalent.gerador import aceite, nucleo
from rh_fictalent.gerador.__main__ import main
from rh_fictalent.validacao import bandas
from rh_fictalent.validacao.__main__ import main as regua
from rh_fictalent.validacao.regua import Veredito, avaliar

RAIZ = Path(__file__).resolve().parents[1]
ENV = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
PASTA = RAIZ / "dados" / "regua"


class _ReplicaDeMentira(nucleo.Replica):
    def __init__(self, contagem: dict[str, int]) -> None:
        super().__init__("127.0.0.1", 0, "ninguem", "nada")
        self.contagem = contagem

    def contar(self, nomes: list[str]) -> dict[str, int]:
        return {nome: self.contagem[nome] for nome in nomes}


def test_juntar_aceita_a_mesma_medida_de_duas_etapas_so_se_for_o_mesmo_numero() -> None:
    carteira = {"clientes_ativos_fim_ano": {"2018": 12.0}, "sujeira": {"COM-01": 0.02}}
    pessoas = {"clientes_ativos_fim_ano": {"2018": 12.0}, "sujeira": {"CAD-01": 0.036}}
    juntas = aceite.juntar([carteira, pessoas])
    assert juntas["sujeira"] == {"COM-01": 0.02, "CAD-01": 0.036}
    with pytest.raises(ValueError, match="clientes_ativos_fim_ano/2018"):
        aceite.juntar([carteira, {"clientes_ativos_fim_ano": {"2018": 13.0}}])


def test_fechar_conta_as_linhas_e_acusa_replica_diferente_do_gerador() -> None:
    linhas = dict.fromkeys(bandas.LINHAS, 10) | {"cadastro.filial": 3}
    completas, problemas = aceite.fechar({"sujeira": {"CAD-01": 0.036}}, linhas)
    assert not problemas and completas["sujeira"] == {"CAD-01": 0.036}
    assert set(completas["linhas_tabela"]) == {*bandas.LINHAS, "total"}
    assert completas["linhas_tabela"]["total"] == 10 * len(bandas.LINHAS) + 3
    na_replica = _ReplicaDeMentira(linhas | {"cadastro.filial": 2})
    completas, problemas = aceite.fechar({}, linhas, na_replica)
    assert problemas == ["cadastro.filial: 2 linhas na réplica, 3 geradas"]
    assert completas["linhas_tabela"]["total"] == 10 * len(bandas.LINHAS) + 2


def test_o_laudo_versionado_aprova_a_regua_inteira_sem_pendencia(
    capsys: pytest.CaptureFixture[str],
) -> None:
    medidas = json.loads((PASTA / "medidas.json").read_text(encoding="utf-8"))
    assert set(medidas) == set(bandas.MEDIDAS)
    laudo = avaliar(bandas.checks(), medidas)
    assert laudo.veredito is Veredito.APROVADA and len(laudo.resultados) == len(bandas.checks())
    assert regua(["--medidas", str(PASTA / "medidas.json"), "--so-problemas"]) == 0
    final = f"RÉGUA APROVADA: {len(laudo.resultados)} de {len(laudo.resultados)} checks"
    assert final in capsys.readouterr().out
    versionado = (PASTA / "laudo.txt").read_text(encoding="utf-8")
    assert final in versionado and "contadas na réplica" in versionado
    assert versionado.endswith(laudo.texto() + "\n")


def test_o_laudo_versionado_e_o_da_base_que_o_gerador_produz() -> None:
    """Mexeu no gerador e as medidas mudaram? O aceite tem de ser refeito e versionado de novo."""
    versionadas = json.loads((PASTA / "medidas.json").read_text(encoding="utf-8"))
    medidas, linhas = aceite.gerar_e_medir(RAIZ / "dados" / "publicos")
    completas, _ = aceite.fechar(medidas, linhas)
    assert set(completas) == set(versionadas)
    for medida, valores in completas.items():
        assert valores == pytest.approx(versionadas[medida], rel=1e-9, abs=1e-12), medida


def test_cli_pede_etapa_ou_aceite(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as saida:
        main([])
    assert saida.value.code == 2 and "--etapa ou --aceite" in capsys.readouterr().err


def test_replica_tem_as_linhas_do_laudo() -> None:
    senha, porta = ENV.get("REPLICADOR_PASSWORD"), int(ENV.get("STAGING_PORT") or 0)
    if not senha or not porta:
        pytest.skip(".env ausente")
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
    except OSError:
        pytest.skip("réplica fora do ar")
    replica = nucleo.Replica("127.0.0.1", porta, "replicador", senha)
    if replica.contar(["sst.aso"])["sst.aso"] == 0:
        pytest.skip("réplica ainda sem a base completa (rode o gerador com --gravar)")
    versionadas = json.loads((PASTA / "medidas.json").read_text(encoding="utf-8"))["linhas_tabela"]
    contadas = replica.contar(list(bandas.LINHAS))
    assert {nome: float(n) for nome, n in contadas.items()} == {
        nome: versionadas[nome] for nome in bandas.LINHAS
    }
