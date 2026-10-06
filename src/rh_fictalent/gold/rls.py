# ruff: noqa: E501
"""O RLS do warehouse: cada filial enxerga só as próprias linhas, no próprio banco.

O DCL (`gold.dcl`) diz quem lê qual tabela e qual coluna; não diz qual linha. É o *row level
security* do Postgres que faz a coordenadora de Extrema enxergar só as linhas de Extrema sem
depender da aplicação (`docs/03`): a política fica na tabela e vale para qualquer cliente que se
conecte, o painel, o notebook ou o `psql`.

Quem é da empresa inteira (sócio, gerência, financeiro) tem a política que deixa tudo passar;
quem é de filial (coordenação, assistente) tem a política que só deixa passar a linha cuja
`filial_id` está entre as filiais do seu papel. A ligação entre o papel de login de uma pessoa e
as suas filiais fica em `acesso.filial_do_papel`, que só o administrador lê e escreve; a política
a consulta por uma função `SECURITY DEFINER`, que recebe o papel de quem consulta e devolve as
filiais dele. Papel sem filial registrada não vê linha nenhuma: fecha por padrão. A linha 0 (não
se aplica) das dimensões é de todos.

A política vale em toda tabela da gold que carrega `filial_id` (treze fatos e a dimensão de
contrato); o mercado (CAGED) é público e não tem filial. O administrador, dono das tabelas e da
carga, não passa pela política. A partição de um fato não é concedida a ninguém, então não há como
ler o ano por baixo da política.

O rito para dar acesso a uma pessoa: `CREATE ROLE ana LOGIN IN ROLE perfil_coordenacao` (a senha
pelo `\\password`, nunca em texto) e `INSERT INTO acesso.filial_do_papel VALUES ('ana', 3)`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rh_fictalent.gold import dcl, modelo, warehouse

if TYPE_CHECKING:
    from rh_fictalent.orquestracao.recursos import Warehouse

ESQUEMA_ACESSO = "acesso"
TABELA_DE_ACESSO = "filial_do_papel"
FUNCAO = "filiais_do_papel"
COLUNA = "filial_id"
LINHA_DE_TODOS = 0  # a linha 0 (não se aplica) das dimensões


def tabelas_com_filial() -> list[modelo.Tabela]:
    """Toda tabela da gold que carrega a filial: é nela que a política vale."""
    return [t for t in modelo.TABELAS if COLUNA in t.referencias]


def papeis(alcance: str) -> str:
    return ", ".join(p.papel for p in dcl.PERFIS if p.alcance == alcance)


def gerar_sql(
    esquema_dim: str = warehouse.ESQUEMA_DIM,
    esquema_fato: str = warehouse.ESQUEMA_FATO,
    esquema_acesso: str = ESQUEMA_ACESSO,
) -> str:
    """O RLS inteiro, idempotente: a tabela de acesso, a função que a lê e a política por tabela."""
    acesso = f"{esquema_acesso}.{TABELA_DE_ACESSO}"
    funcao = f"{esquema_acesso}.{FUNCAO}"
    filial = warehouse.alvo(modelo.DIM_FILIAL, esquema_dim, esquema_fato).qualificado
    da_empresa, da_filial = papeis(dcl.EMPRESA), papeis(dcl.FILIAL)
    linhas = [
        "-- RLS do warehouse: cada filial enxerga só as próprias linhas.",
        "-- GERADO por rh_fictalent.gold.rls; repetir não muda nada. Pressupõe o DCL aplicado (os perfis existem).",
        f"CREATE SCHEMA IF NOT EXISTS {esquema_acesso};",
        f"REVOKE ALL ON SCHEMA {esquema_acesso} FROM PUBLIC;",
        f"CREATE TABLE IF NOT EXISTS {acesso} (papel text NOT NULL, {COLUNA} bigint NOT NULL REFERENCES {filial} (id), PRIMARY KEY (papel, {COLUNA}));",
        f"COMMENT ON TABLE {acesso} IS 'As filiais que cada papel de login enxerga; só o administrador lê e escreve. Papel sem linha aqui não vê linha nenhuma.';",
        f"REVOKE ALL ON {acesso} FROM PUBLIC;",
        # SECURITY DEFINER: roda como o dono (o administrador) e por isso recebe o papel como argumento,
        # porque dentro dela current_user seria o dono; o search_path fixo é a blindagem padrão
        f"CREATE OR REPLACE FUNCTION {funcao}(papel name) RETURNS SETOF bigint LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp",
        f"  AS $$ SELECT {COLUNA} FROM {acesso} WHERE papel = $1 $$;",  # noqa: S608 # nosec B608
        f"REVOKE ALL ON FUNCTION {funcao}(name) FROM PUBLIC;",
        f"GRANT USAGE ON SCHEMA {esquema_acesso} TO {da_filial};",
        f"GRANT EXECUTE ON FUNCTION {funcao}(name) TO {da_filial};",
    ]
    for t in tabelas_com_filial():
        destino = warehouse.alvo(t, esquema_dim, esquema_fato).qualificado
        linhas += [
            f"ALTER TABLE {destino} ENABLE ROW LEVEL SECURITY;",
            f"DROP POLICY IF EXISTS empresa_inteira ON {destino};",
            f"CREATE POLICY empresa_inteira ON {destino} FOR SELECT TO {da_empresa} USING (true);",
            f"DROP POLICY IF EXISTS por_filial ON {destino};",
            f"CREATE POLICY por_filial ON {destino} FOR SELECT TO {da_filial} USING ({COLUNA} = {LINHA_DE_TODOS} OR {COLUNA} IN (SELECT {funcao}(current_user)));",
        ]
    return "\n".join(linhas) + "\n"


def aplicar(
    dw: Warehouse,
    esquema_dim: str = warehouse.ESQUEMA_DIM,
    esquema_fato: str = warehouse.ESQUEMA_FATO,
    esquema_acesso: str = ESQUEMA_ACESSO,
) -> int:
    """Aplica o RLS no warehouse; devolve quantos comandos rodaram."""
    sql = gerar_sql(esquema_dim, esquema_fato, esquema_acesso)
    with dw.conectar() as conexao, conexao.cursor() as cur:
        cur.execute(sql)
        conexao.commit()
    return sum(1 for linha in sql.splitlines() if linha and not linha.startswith(("--", "  AS")))
