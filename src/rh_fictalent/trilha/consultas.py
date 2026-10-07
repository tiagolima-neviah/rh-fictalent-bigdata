# ruff: noqa: E501
"""As consultas de auditoria, declaradas: a pergunta, onde a resposta mora e o SQL.

Duas fontes. As do **lake** rodam no DuckDB sobre a silver (`silver.seguranca.*`, só linhas
vivas, com o login já como chave e sem o valor alterado) e sobre a bronze (a trilha
`meta.exclusao_auditoria`, que não passa pela silver); os parâmetros são `$desde` e `$ate`
(datas). As do **warehouse** rodam no Postgres como o administrador, sobre `observabilidade`,
`lgpd`, `acesso` e o catálogo de papéis; os parâmetros são `%(desde)s` e `%(ate)s`. Nenhuma
devolve dado pessoal: o usuário aparece pela chave do login, o token nunca aparece.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

import pandas as pd

if TYPE_CHECKING:
    import duckdb

    from rh_fictalent.orquestracao.recursos import Warehouse

Fonte = Literal["lake", "warehouse"]
INICIO = date(2018, 1, 1)
FIM = date(2099, 12, 31)

# o usuário sem identidade: a chave do login, o perfil vigente e a filial; uma view temporária
# criada ao abrir, para as consultas do lake lerem o mesmo recorte
VIEW_DO_USUARIO = """
CREATE OR REPLACE TEMP VIEW usuario_sem_identidade AS
SELECT u.id, u.login_chave, u.filial_id, u.ativo, coalesce(p.codigo, 'SEM PERFIL') AS perfil
FROM silver.seguranca.usuario u
LEFT JOIN silver.seguranca.usuario_perfil up ON up.usuario_id = u.id AND up.vigencia_fim IS NULL
LEFT JOIN silver.seguranca.perfil p ON p.id = up.perfil_id
"""


@dataclass(frozen=True)
class Consulta:
    nome: str
    pergunta: str
    fonte: Fonte
    sql: str
    grao: str  # o que é uma linha da resposta


CONSULTAS: tuple[Consulta, ...] = (
    Consulta(
        "acessos_por_perfil_e_mes",
        "Quem entrou no sistema, por perfil e filial, mês a mês?",
        "lake",
        """SELECT date_trunc('month', l.dt_evento)::DATE AS mes, u.perfil, u.filial_id,
                  count(*) AS logins, count(DISTINCT l.usuario_id) AS usuarios
           FROM silver.seguranca.log_auditoria l JOIN usuario_sem_identidade u ON u.id = l.usuario_id
           WHERE l.acao = 'LOGIN' AND l.dt_evento >= CAST($desde AS DATE) AND l.dt_evento < CAST($ate AS DATE) + INTERVAL 1 DAY
           GROUP BY ALL ORDER BY mes, perfil, filial_id""",
        "um perfil numa filial num mês",
    ),
    Consulta(
        "usuarios_ativos_sem_acesso",
        "Que contas ativas não entram há mais de 90 dias, ou nunca entraram?",
        "lake",
        """WITH ultimo AS (
             SELECT usuario_id, max(dt_evento) AS ultimo_login
             FROM silver.seguranca.log_auditoria
             WHERE acao = 'LOGIN' AND dt_evento < CAST($ate AS DATE) + INTERVAL 1 DAY GROUP BY 1)
           SELECT u.login_chave, u.perfil, u.filial_id, ul.ultimo_login,
                  CAST(date_diff('day', ul.ultimo_login::DATE, CAST($ate AS DATE)) AS INTEGER) AS dias_sem_entrar
           FROM usuario_sem_identidade u LEFT JOIN ultimo ul ON ul.usuario_id = u.id
           WHERE u.ativo AND (ul.ultimo_login IS NULL OR ul.ultimo_login < CAST($ate AS DATE) - INTERVAL 90 DAY)
           ORDER BY ul.ultimo_login NULLS FIRST, u.login_chave""",
        "uma conta ativa sem acesso recente",
    ),
    Consulta(
        "alteracoes_por_modulo_e_mes",
        "O que foi criado, editado e excluído, por módulo e tabela, mês a mês?",
        "lake",
        """SELECT date_trunc('month', dt_evento)::DATE AS mes, modulo, tabela, acao, count(*) AS eventos,
                  count(DISTINCT usuario_id) AS usuarios
           FROM silver.seguranca.log_auditoria
           WHERE acao IN ('CRIAR', 'EDITAR', 'EXCLUIR') AND dt_evento >= CAST($desde AS DATE) AND dt_evento < CAST($ate AS DATE) + INTERVAL 1 DAY
           GROUP BY ALL ORDER BY mes, modulo, tabela, acao""",
        "uma ação numa tabela num mês",
    ),
    Consulta(
        "acoes_sem_permissao",
        "Que ações foram feitas sem permissão vigente para elas (o achado SEG-01), por quem e onde?",
        "lake",
        """SELECT u.login_chave, u.perfil, u.filial_id, l.modulo, l.acao,
                  count(*) AS eventos, min(l.dt_evento) AS primeiro, max(l.dt_evento) AS ultimo
           FROM silver.seguranca.log_auditoria l JOIN usuario_sem_identidade u ON u.id = l.usuario_id
           WHERE l.q_seg_01 AND l.dt_evento >= CAST($desde AS DATE) AND l.dt_evento < CAST($ate AS DATE) + INTERVAL 1 DAY
           GROUP BY ALL ORDER BY eventos DESC, u.login_chave""",
        "um usuário numa ação sem permissão",
    ),
    Consulta(
        "exportacoes_por_usuario_e_mes",
        "Quem exportou planilhas, quanto e de que módulo, mês a mês?",
        "lake",
        """SELECT date_trunc('month', l.dt_evento)::DATE AS mes, u.login_chave, u.perfil, u.filial_id, l.modulo,
                  count(*) AS exportacoes
           FROM silver.seguranca.log_auditoria l JOIN usuario_sem_identidade u ON u.id = l.usuario_id
           WHERE l.acao = 'EXPORTAR' AND l.dt_evento >= CAST($desde AS DATE) AND l.dt_evento < CAST($ate AS DATE) + INTERVAL 1 DAY
           GROUP BY ALL ORDER BY mes, exportacoes DESC""",
        "um usuário exportando de um módulo num mês",
    ),
    Consulta(
        "acoes_fora_do_horario",
        "Que alterações e exportações aconteceram fora do horário comercial (antes das 7h, depois das 20h, fim de semana)?",
        "lake",
        """SELECT u.login_chave, u.perfil, u.filial_id, l.acao,
                  count(*) AS eventos,
                  count(*) FILTER (WHERE dayofweek(l.dt_evento) IN (0, 6)) AS no_fim_de_semana,
                  min(l.dt_evento) AS primeiro, max(l.dt_evento) AS ultimo
           FROM silver.seguranca.log_auditoria l JOIN usuario_sem_identidade u ON u.id = l.usuario_id
           WHERE l.acao <> 'LOGIN' AND l.dt_evento >= CAST($desde AS DATE) AND l.dt_evento < CAST($ate AS DATE) + INTERVAL 1 DAY
             AND (hour(l.dt_evento) < 7 OR hour(l.dt_evento) >= 20 OR dayofweek(l.dt_evento) IN (0, 6))
           GROUP BY ALL ORDER BY eventos DESC, u.login_chave""",
        "um usuário numa ação fora do horário",
    ),
    Consulta(
        "exclusoes_na_replica",
        "O que foi apagado na réplica, por banco, tabela e usuário de banco, mês a mês (a trilha dos gatilhos)?",
        "lake",
        """SELECT date_trunc('month', dt_exclusao)::DATE AS mes, banco, tabela, usuario_banco, count(*) AS linhas_apagadas
           FROM meta.exclusao_auditoria
           WHERE dt_exclusao >= CAST($desde AS DATE) AND dt_exclusao < CAST($ate AS DATE) + INTERVAL 1 DAY
           GROUP BY ALL ORDER BY mes, banco, tabela""",
        "uma tabela apagada por um usuário de banco num mês",
    ),
    Consulta(
        "execucoes_por_job",
        "O que rodou no pipeline, com que resultado e em quanto tempo, por job?",
        "warehouse",
        """SELECT job, status, count(*) AS execucoes, round(avg(duracao_s), 1) AS duracao_media_s,
                  round(max(duracao_s), 1) AS duracao_maxima_s, sum(passos_falhos) AS passos_falhos,
                  max(inicio) AS ultima
           FROM observabilidade.execucao
           WHERE inicio >= %(desde)s AND inicio < %(ate)s + INTERVAL '1 day'
           GROUP BY job, status ORDER BY job, status""",
        "um job num status",
    ),
    Consulta(
        "passos_que_falharam",
        "Que passos falharam, em que execução, com que erro?",
        "warehouse",
        """SELECT e.job, p.passo, p.particao, p.fim, left(p.erro, 160) AS erro, p.run_id
           FROM observabilidade.execucao_passo p JOIN observabilidade.execucao e ON e.run_id = p.run_id
           WHERE p.status <> 'SUCESSO' AND p.fim >= %(desde)s AND p.fim < %(ate)s + INTERVAL '1 day'
           ORDER BY p.fim DESC""",
        "um passo que falhou",
    ),
    Consulta(
        "descartes_lgpd",
        "Que descartes de dado pessoal foram feitos, quando, de que tabela e por que regra?",
        "warehouse",
        """SELECT executado_em, referencia, tabela, eliminadas, vencidas, regra_retencao, run_id
           FROM lgpd.descarte
           WHERE executado_em >= %(desde)s AND executado_em < %(ate)s + INTERVAL '1 day'
           ORDER BY executado_em DESC""",
        "um descarte",
    ),
    Consulta(
        "papeis_do_warehouse",
        "Quem pode entrar no warehouse e com que perfil de negócio e filiais?",
        "warehouse",
        """SELECT r.rolname AS papel, r.rolcanlogin AS entra_com_senha,
                  string_agg(DISTINCT p.rolname, ', ') AS perfis,
                  string_agg(DISTINCT f.filial_id::text, ', ') AS filiais,
                  bool_or(a.member IS NOT NULL) AS a_api_assume
           FROM pg_roles r
           LEFT JOIN pg_auth_members m ON m.member = r.oid
           LEFT JOIN pg_roles p ON p.oid = m.roleid AND p.rolname LIKE 'perfil\\_%%'
           LEFT JOIN acesso.filial_do_papel f ON f.papel = r.rolname
           LEFT JOIN pg_auth_members a ON a.member = (SELECT oid FROM pg_roles WHERE rolname = 'api') AND a.roleid = r.oid
           WHERE r.rolname NOT LIKE 'pg\\_%%' AND r.rolname NOT LIKE 'perfil\\_%%' AND NOT r.rolsuper
           GROUP BY r.rolname, r.rolcanlogin ORDER BY r.rolname""",
        "um papel do banco",
    ),
    Consulta(
        "tokens_da_api",
        "Que tokens da API existem, de quem, com que validade, e quando foram usados pela última vez (nunca o token)?",
        "warehouse",
        """SELECT t.papel, t.descricao, t.criado_em, t.valido_ate,
                  (t.valido_ate IS NOT NULL AND t.valido_ate < current_date) AS vencido,
                  (SELECT max(instante) FROM acesso.pedido q WHERE q.papel = t.papel) AS ultimo_pedido
           FROM acesso.token t ORDER BY t.papel, t.criado_em""",
        "um token, sem o token",
    ),
    Consulta(
        "pedidos_da_api_por_dia",
        "Quem pediu o quê à API, dia a dia, e quantas vezes foi recusado (401 sem token, 403 pelo banco)?",
        "warehouse",
        """SELECT instante::date AS dia, coalesce(papel, '(sem token)') AS papel, caminho,
                  count(*) AS pedidos,
                  count(*) FILTER (WHERE codigo = 200) AS ok,
                  count(*) FILTER (WHERE codigo = 401) AS sem_token,
                  count(*) FILTER (WHERE codigo = 403) AS recusados_pelo_banco,
                  count(*) FILTER (WHERE codigo NOT IN (200, 401, 403)) AS outros
           FROM acesso.pedido
           WHERE instante >= %(desde)s AND instante < %(ate)s + INTERVAL '1 day'
           GROUP BY 1, 2, 3 ORDER BY dia DESC, pedidos DESC""",
        "um papel num caminho num dia",
    ),
)


def consulta(nome: str) -> Consulta:
    return next(c for c in CONSULTAS if c.nome == nome)


def no_lake(
    con: duckdb.DuckDBPyConnection, nome: str, desde: date = INICIO, ate: date = FIM
) -> pd.DataFrame:
    c = consulta(nome)
    if c.fonte != "lake":
        raise ValueError(f"{nome} roda no warehouse, não no lake")
    con.execute(VIEW_DO_USUARIO)
    janela = {"desde": desde, "ate": ate}
    return con.execute(c.sql, {k: v for k, v in janela.items() if f"${k}" in c.sql}).df()


def no_warehouse(dw: Warehouse, nome: str, desde: date = INICIO, ate: date = FIM) -> pd.DataFrame:
    c = consulta(nome)
    if c.fonte != "warehouse":
        raise ValueError(f"{nome} roda no lake, não no warehouse")
    with dw.conectar() as con, con.cursor() as cur:
        cur.execute(c.sql, {"desde": desde, "ate": ate})
        colunas = [d.name for d in cur.description or []]
        linhas: list[tuple[Any, ...]] = list(cur.fetchall())
    return pd.DataFrame(linhas, columns=colunas)
