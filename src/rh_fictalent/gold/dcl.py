# ruff: noqa: E501
"""O DCL do warehouse: quem lê o quê, por perfil de negócio, sem dado pessoal.

Na réplica os papéis são por função técnica (pipeline, relatórios, replicador). No warehouse
são **por perfil de negócio**, os de quem lê o painel: o sócio, a gerência, a coordenação da
operação, a assistente do funil e o financeiro. Cada perfil é um papel do Postgres sem login
(`perfil_<nome>`); a pessoa que entra recebe o perfil (`CREATE ROLE ana LOGIN IN ROLE
perfil_coordenacao`) e herda só o que o perfil pode. O que cada perfil pode é declarado aqui,
em código, e o SQL é gerado: um teste prova, no banco, que o acesso indevido falha.

Dado pessoal: a gold não identifica ninguém por construção (decisão 3 da matriz: sem nome,
documento, chave nem matrícula). O que sobra nas dimensões de pessoa são **atributos de
pessoa** (ano de nascimento, sexo, escolaridade, município, fonte de recrutamento), que não
identificam sozinhos mas, cruzados, aproximam. Por isso o acesso a eles é coluna a coluna, pelo
princípio da necessidade: a assistente do funil lê os atributos do candidato (é o trabalho
dela); a coordenação, os do colaborador; o financeiro, nenhum (só o `id`, para somar o custo);
o sócio e a gerência, nenhum (decidem no agregado, e o agregado não precisa da pessoa).
Nenhum perfil escreve, cria ou concede nada; a carga é do administrador.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rh_fictalent.gold import modelo, warehouse

if TYPE_CHECKING:
    import duckdb

    from rh_fictalent.orquestracao.recursos import Warehouse

# as colunas das dimensões de pessoa que são atributo de pessoa: o acesso é por necessidade
ATRIBUTOS_DE_PESSOA: dict[str, tuple[str, ...]] = {
    "dim_colaborador": (
        "ano_nascimento",
        "sexo",
        "escolaridade",
        "fonte_de_recrutamento",
        "municipio",
        "uf",
    ),
    "dim_candidato": ("ano_nascimento", "sexo", "escolaridade", "fonte", "municipio", "uf"),
}


@dataclass(frozen=True)
class Perfil:
    nome: str  # vira o papel perfil_<nome>
    quem: str
    fatos: tuple[str, ...]  # os fatos que o perfil lê; as dimensões vêm das referências deles
    atributos_de_pessoa: tuple[str, ...] = ()  # dimensões de pessoa lidas com os atributos

    @property
    def papel(self) -> str:
        return f"perfil_{self.nome}"

    def dimensoes(self) -> list[str]:
        """Toda dimensão que algum fato do perfil referencia, mais data e mês."""
        nomes = {"dim_data", "dim_mes"}
        for fato in self.fatos:
            nomes |= set(modelo.tabela(fato).referencias.values())
        return sorted(nomes)


PERFIS: tuple[Perfil, ...] = (
    Perfil(
        "socio",
        "os sócios: a empresa inteira, no agregado",
        tuple(t.nome for t in modelo.TABELAS if t.fato),
    ),
    Perfil(
        "gerencia",
        "a gerência geral: a operação e o financeiro, no agregado",
        tuple(t.nome for t in modelo.TABELAS if t.fato),
    ),
    Perfil(
        "coordenacao",
        "a coordenação da operação: postos, pessoas alocadas, ponto, conformidade, ocorrências",
        (
            "fato_posto_mes",
            "fato_alocacao",
            "fato_vinculo",
            "fato_ponto_dia",
            "fato_conformidade_mes",
            "fato_ocorrencia",
            "fato_contrato",
            "fato_vaga",
        ),
        atributos_de_pessoa=("dim_colaborador",),
    ),
    Perfil(
        "assistente",
        "a assistente do funil: vagas, candidaturas e o que virou vínculo",
        ("fato_vaga", "fato_candidatura", "fato_vinculo", "fato_alocacao", "fato_mercado_mes"),
        atributos_de_pessoa=("dim_candidato",),
    ),
    Perfil(
        "financeiro",
        "o financeiro: faturar, receber, custear e fechar o mês",
        (
            "fato_faturamento",
            "fato_recebimento",
            "fato_custo_pessoal",
            "fato_resultado_mes",
            "fato_posto_mes",
            "fato_contrato",
        ),
    ),
)


def perfil(nome: str) -> Perfil:
    return next(p for p in PERFIS if p.nome == nome)


def colunas_livres(con: duckdb.DuckDBPyConnection, dimensao: str) -> list[str]:
    """As colunas da dimensão de pessoa que não são atributo de pessoa (o `id` e o operacional)."""
    return [
        n
        for n, _ in warehouse.colunas(con, modelo.tabela(dimensao))
        if n not in ATRIBUTOS_DE_PESSOA[dimensao]
    ]


def gerar_sql(
    con: duckdb.DuckDBPyConnection,
    esquema_dim: str = warehouse.ESQUEMA_DIM,
    esquema_fato: str = warehouse.ESQUEMA_FATO,
) -> str:
    """O DCL inteiro, idempotente: papéis, uso dos schemas, SELECT por tabela e por coluna."""
    linhas = [
        "-- DCL do warehouse: perfis de negócio, só leitura, sem atributo de pessoa fora da necessidade.",
        "-- GERADO por rh_fictalent.gold.dcl; repetir não muda nada.",
        f"REVOKE ALL ON SCHEMA {esquema_dim}, {esquema_fato} FROM PUBLIC;",
    ]
    for p in PERFIS:
        linhas += [
            f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{p.papel}') THEN",  # noqa: S608 # nosec B608
            f"  CREATE ROLE {p.papel} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; END IF; END $$;",
            f"COMMENT ON ROLE {p.papel} IS '{p.quem}';",
            f"GRANT USAGE ON SCHEMA {esquema_dim}, {esquema_fato} TO {p.papel};",
            # o que o perfil tinha e deixou de ter sai: o SQL reflete a declaração, não a história
            f"REVOKE ALL ON ALL TABLES IN SCHEMA {esquema_dim}, {esquema_fato} FROM {p.papel};",
        ]
        for fato in p.fatos:
            linhas.append(
                f"GRANT SELECT ON {warehouse.alvo(modelo.tabela(fato), esquema_dim, esquema_fato).qualificado} TO {p.papel};"
            )
        for dimensao in p.dimensoes():
            destino = warehouse.alvo(modelo.tabela(dimensao), esquema_dim, esquema_fato).qualificado
            if dimensao in ATRIBUTOS_DE_PESSOA and dimensao not in p.atributos_de_pessoa:
                linhas.append(
                    f"GRANT SELECT ({', '.join(colunas_livres(con, dimensao))}) ON {destino} TO {p.papel};"
                )
            else:
                linhas.append(f"GRANT SELECT ON {destino} TO {p.papel};")
    return "\n".join(linhas) + "\n"


def aplicar(
    con: duckdb.DuckDBPyConnection,
    dw: Warehouse,
    esquema_dim: str = warehouse.ESQUEMA_DIM,
    esquema_fato: str = warehouse.ESQUEMA_FATO,
) -> int:
    """Aplica o DCL no warehouse; devolve quantos comandos rodaram."""
    sql = gerar_sql(con, esquema_dim, esquema_fato)
    with dw.conectar() as conexao, conexao.cursor() as cur:
        cur.execute(sql)
        conexao.commit()
    return sum(1 for linha in sql.splitlines() if linha and not linha.startswith("--"))
