# ruff: noqa: E501
"""A pseudonimização da silver: a pessoa vira chave, e o que identifica e não serve sai.

A LGPD chama de pseudonimização o tratamento depois do qual o dado "perde a possibilidade de
associação, direta ou indireta, a um indivíduo, senão pelo uso de informação adicional mantida
separadamente" (art. 13, § 4º). Aqui a informação adicional é um segredo: a chave de uma
pessoa é o HMAC-SHA256 do documento dela com o segredo `PSEUDONIMIZACAO_SEGREDO`, que mora no
`.env` e em nenhum outro lugar. Com o segredo, o mesmo CPF dá sempre a mesma chave (a gold
conta pessoas e junta candidato com colaborador); sem ele, a chave não volta ao CPF, nem por
força bruta sobre os 10^11 CPFs possíveis, porque o atacante não sabe o que concatenar.

Cada coluna etiquetada na DDL (`staging.lgpd`) tem aqui uma decisão, com o motivo:

- **chave**: o valor vira o HMAC do valor normalizado (só letras e dígitos, sem caixa nem
  acento) e a coluna passa a se chamar `<coluna>_chave`. O domínio entra no HMAC: o CPF do
  candidato e o do colaborador estão no mesmo domínio (`cpf`) e dão a mesma chave; um PIS
  igual a um CPF não daria.
- **ano**: a data vira o ano (`dt_nascimento` vira `ano_nascimento`). Decisão do Tiago em
  01/10/2026: o ano basta para faixa etária, e a data inteira é o identificador indireto mais
  forte que sobra.
- **remover**: a coluna não entra na silver. Nome, telefone, e-mail e endereço não servem a
  nenhum indicador, e minimizar é o princípio (art. 6º, III).
- **manter**: a coluna entra como veio, com o motivo escrito: a remuneração individual é o
  custo da folha; as quatro colunas de saúde servem a indicadores agregados de absenteísmo e
  segurança, e a regra de que nunca chegam à gold com chave de pessoa é da gold.

As marcas de qualidade (`q_`) são calculadas sobre a bronze em claro **antes** da
pseudonimização: o CPF inválido do ATS-03 continua marcado, só que a silver não guarda mais
o CPF. Uma coluna derivada que carrega dado pessoal (o `grupo_pessoa` do ATS-01, que era o
CPF) também passa pela chave.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

import duckdb
import pyarrow as pa
from duckdb.func import FunctionNullHandling, PythonUDFType

VARIAVEL = "PSEUDONIMIZACAO_SEGREDO"
MINIMO = 32  # caracteres do segredo; `openssl rand -hex 32` dá 64
FUNCAO = "pseudonimo"
CHAVE_VALIDA = "^[0-9a-f]{64}$"  # o que toda coluna de chave tem de ser na silver


class Tratamento(StrEnum):
    CHAVE = "chave"
    ANO = "ano"
    REMOVER = "remover"
    MANTER = "manter"


@dataclass(frozen=True)
class Decisao:
    tratamento: Tratamento
    motivo: str
    dominio: str = ""  # só para chave: o espaço em que valores iguais dão a mesma chave


_DOC = "identificador de pessoa: vira chave para a gold contar e juntar sem ver o documento"
_NOME = "identifica a pessoa e não serve a indicador nenhum"
_CONTATO = "contato da pessoa; nenhum indicador usa"
_NASCIMENTO = "o ano basta para faixa etária; decisão do Tiago em 01/10/2026"
_SAUDE = "dado de saúde para indicador agregado de absenteísmo e segurança; a gold não o leva com chave de pessoa"

DECISOES: dict[str, dict[str, Decisao]] = {
    "cadastro.endereco": {
        "logradouro": Decisao(
            Tratamento.REMOVER, "com o número, localiza a casa de quem mora; o município basta"
        ),
        "cep": Decisao(Tratamento.REMOVER, "localiza a rua; o município basta"),
    },
    "comercial.cliente_contato": {
        "nome": Decisao(Tratamento.REMOVER, _NOME),
        "email": Decisao(Tratamento.REMOVER, _CONTATO),
        "telefone": Decisao(Tratamento.REMOVER, _CONTATO),
    },
    "ats.candidato": {
        "nome": Decisao(
            Tratamento.REMOVER,
            "identifica a pessoa; a conformação do ATS-05 virou recomendação ao cliente na origem (decisão do Tiago em 01/10/2026)",
        ),
        "cpf": Decisao(Tratamento.CHAVE, _DOC, "cpf"),
        "dt_nascimento": Decisao(Tratamento.ANO, _NASCIMENTO),
        "sexo": Decisao(
            Tratamento.MANTER, "indicador de diversidade do funil; sozinho não identifica"
        ),
        "telefone": Decisao(Tratamento.REMOVER, _CONTATO),
        "email": Decisao(Tratamento.REMOVER, _CONTATO),
    },
    "pessoas.colaborador": {
        "nome": Decisao(Tratamento.REMOVER, _NOME),
        "cpf": Decisao(Tratamento.CHAVE, _DOC, "cpf"),
        "dt_nascimento": Decisao(Tratamento.ANO, _NASCIMENTO),
        "endereco_id": Decisao(
            Tratamento.MANTER,
            "chave interna; o endereço que ela aponta já sai sem logradouro e sem CEP",
        ),
        "pis": Decisao(Tratamento.CHAVE, _DOC, "pis"),
    },
    "pessoas.colaborador_documento": {
        "numero": Decisao(Tratamento.CHAVE, _DOC, "documento"),
    },
    "pessoas.dependente": {
        "nome": Decisao(Tratamento.REMOVER, _NOME),
        "dt_nascimento": Decisao(Tratamento.ANO, _NASCIMENTO),
    },
    "pessoas.afastamento": {
        "cid_grupo": Decisao(Tratamento.MANTER, _SAUDE),
    },
    "folha.folha_item": {
        "valor": Decisao(
            Tratamento.MANTER,
            "remuneração individual é o custo da folha, base da margem; a pessoa já é só um id",
        ),
    },
    "sst.aso": {
        "resultado": Decisao(Tratamento.MANTER, _SAUDE),
        # sem etiqueta na DDL: o CRM é o registro público do médico, uma pessoa (achado do 6.5)
        "medico_crm": Decisao(
            Tratamento.REMOVER, "identifica o médico examinador; nenhum indicador usa"
        ),
    },
    "sst.acidente": {
        "tipo": Decisao(Tratamento.MANTER, _SAUDE),
        "gravidade": Decisao(Tratamento.MANTER, _SAUDE),
    },
    "seguranca.usuario": {
        "nome": Decisao(Tratamento.REMOVER, _NOME),
        "email": Decisao(Tratamento.REMOVER, _CONTATO),
        # sem etiqueta na DDL: o login costuma ser o nome da pessoa (achado do 6.5); vira chave
        # porque a auditoria de acesso agrupa por usuário (SEG-02)
        "login": Decisao(
            Tratamento.CHAVE,
            "o login costuma ser o nome; vira chave para a auditoria de acesso agrupar",
            "login",
        ),
    },
    "seguranca.log_auditoria": {
        "valor_anterior": Decisao(Tratamento.REMOVER, "pode carregar o dado pessoal alterado"),
        "valor_novo": Decisao(Tratamento.REMOVER, "pode carregar o dado pessoal alterado"),
    },
}

# colunas tratadas que a DDL não etiqueta: o teste exige que estejam aqui, com o porquê acima
FORA_DA_ETIQUETA = {("sst.aso", "medico_crm"), ("seguranca.usuario", "login")}

# colunas que as regras da silver criam e que carregam dado pessoal
DERIVADAS: dict[str, dict[str, Decisao]] = {
    "ats.candidato": {
        "grupo_pessoa": Decisao(
            Tratamento.CHAVE, "o grupo da duplicidade era o CPF; vira a chave do CPF", "cpf"
        ),
    },
}


def nome_na_silver(coluna: str, decisao: Decisao | None, derivada: bool = False) -> str | None:
    """O nome que a coluna tem na silver; `None` se ela não entra."""
    if decisao is None or decisao.tratamento is Tratamento.MANTER:
        return coluna
    if decisao.tratamento is Tratamento.REMOVER:
        return None
    if decisao.tratamento is Tratamento.ANO:
        return "ano_" + coluna.removeprefix("dt_")
    return coluna if derivada else f"{coluna}_chave"


def expressao(referencia: str, decisao: Decisao | None) -> str:
    """O SQL que leva o valor da bronze (`referencia`, ex. `b.cpf`) ao valor da silver."""
    if decisao is None or decisao.tratamento is Tratamento.MANTER:
        return referencia
    if decisao.tratamento is Tratamento.ANO:
        return f"CAST(year({referencia}) AS INTEGER)"
    if decisao.tratamento is Tratamento.CHAVE:
        return f"{FUNCAO}('{decisao.dominio}', CAST({referencia} AS VARCHAR))"
    raise ValueError(f"coluna removida não tem expressão: {referencia}")


def colunas_de_chave(tabela: str) -> list[str]:
    """Os nomes, na silver, das colunas que têm de conter só chaves."""
    nomes = [
        f"{c}_chave"
        for c, d in DECISOES.get(tabela, {}).items()
        if d.tratamento is Tratamento.CHAVE
    ]
    nomes += [c for c, d in DERIVADAS.get(tabela, {}).items() if d.tratamento is Tratamento.CHAVE]
    return nomes


def _normalizado(valor: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode()
    return re.sub(r"[^0-9a-z]", "", sem_acento.lower())


def chave(segredo: bytes, dominio: str, valor: str | None) -> str | None:
    """A chave de um valor: HMAC-SHA256 de `dominio:valor normalizado`, em hexadecimal."""
    if valor is None:
        return None
    normalizado = _normalizado(valor)
    if not normalizado:
        return None  # sem letra nem dígito não há o que identificar
    mensagem = f"{dominio}:{normalizado}".encode()
    return hmac.new(segredo, mensagem, hashlib.sha256).hexdigest()


def segredo_do_ambiente() -> bytes:
    """O segredo, do ambiente; sem ele a silver não é construída (falha fechada)."""
    valor = os.environ.get(VARIAVEL, "")
    if len(valor) < MINIMO:
        raise RuntimeError(
            f"defina {VARIAVEL} no .env com pelo menos {MINIMO} caracteres "
            "(o manual, docs/08, tem o comando que gera e grava sem mostrar o valor)"
        )
    return valor.encode()


def registrar(con: duckdb.DuckDBPyConnection, segredo: bytes) -> None:
    """Cria na conexão a função SQL `pseudonimo(dominio, valor)` com o segredo dado."""

    def _pseudonimo(dominios: pa.Array, valores: pa.Array) -> pa.Array:
        return pa.array(
            [
                chave(segredo, d, v)
                for d, v in zip(dominios.to_pylist(), valores.to_pylist(), strict=True)
            ],
            type=pa.string(),
        )

    # recriar com outro segredo: a função anterior, se houver, sai antes
    with contextlib.suppress(duckdb.InvalidInputException, duckdb.CatalogException):
        con.remove_function(FUNCAO)
    con.create_function(
        FUNCAO,
        _pseudonimo,
        [duckdb.sqltype("VARCHAR"), duckdb.sqltype("VARCHAR")],
        duckdb.sqltype("VARCHAR"),
        type=PythonUDFType.ARROW,
        null_handling=FunctionNullHandling.SPECIAL,  # o nulo chega à função, que devolve nulo
        side_effects=False,
    )
