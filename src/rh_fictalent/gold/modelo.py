# ruff: noqa: E501
"""As tabelas da gold como SQL sobre a silver: as dimensões e a espinha da margem.

Cada `Tabela` é uma linha ou uma coluna da matriz de barramento (`gold.barramento`, `docs/15`)
tornada consulta. A declaração diz quatro coisas, e as quatro são conferidas antes de a tabela
ser publicada (`gold.construcao`):

- **o grão** (`chave`): as colunas que identificam uma linha; repetição é reprovação;
- **as referências** (`referencias`): que coluna aponta para que dimensão; chave que não
  existe na dimensão é reprovação;
- **a conservação** (`conservacoes`): totais que a gold tem de reproduzir da silver, ao
  centavo. É o que impede um join de multiplicar ou perder dinheiro sem ninguém ver;
- **a partição** (`particao`): a coluna com o ano da data de negócio.

Convenções de todas:

- a gold lê a silver pelas views de `lake.consulta.abrir_silver`, que só têm linhas vivas;
- a chave de uma dimensão é o `id` do sistema do cliente; a linha 0 é "não se aplica";
- a data vira `AAAAMMDD` e o mês vira `AAAAMM`, inteiros, para o join com `dim_data` e `dim_mes`;
- **o horizonte** é o último dia com movimento na operação (a maior data entre apontamento e
  alocação). É o "hoje" da gold: posto e alocação em aberto são medidos até ele, e o mês dele é
  marcado como parcial. É diferente da data de referência da silver, que é o dia da carga;
- dinheiro é decimal do começo ao fim. Onde um valor da fatura é repartido entre os itens, o
  arredondamento fica no último item, para a soma fechar.

Este módulo traz as dez dimensões de prioridade 1 e os três fatos da espinha (faturamento,
custo de pessoal e o posto por mês). Os outros fatos da matriz entram nos cards seguintes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import duckdb

INICIO, FIM = "2018-01-01", "2026-12-31"  # o calendário cobre o arco do caso
HORIZONTE = "CAST(getvariable('horizonte') AS DATE)"
FONTES_DO_HORIZONTE = ("ponto.apontamento", "pessoas.alocacao")
NAO_SE_APLICA = "não se aplica"

# colunas que nenhuma dimensão de pessoa pode ter (a gold conta pessoas, não as identifica)
IDENTIDADE = (
    "nome",
    "cpf",
    "cpf_chave",
    "pis_chave",
    "numero_chave",
    "matricula",
    "grupo_pessoa",
    "telefone",
    "email",
    "login",
    "login_chave",
)
DIMENSOES_DE_PESSOA = ("dim_colaborador", "dim_candidato")


@dataclass(frozen=True)
class Conservacao:
    """Um total que a gold tem de reproduzir da silver."""

    o_que: str
    na_gold: str  # expressão agregada sobre a tabela da gold, ex.: sum(receita)
    na_silver: str  # consulta completa sobre a silver que devolve o mesmo número


@dataclass(frozen=True)
class Tabela:
    nome: str
    sql: str
    chave: tuple[str, ...] = ("id",)
    referencias: dict[str, str] = field(default_factory=dict)  # coluna -> dimensão
    particao: str = ""  # coluna com o ano; vazio = arquivo único (dimensão)
    conservacoes: tuple[Conservacao, ...] = ()

    @property
    def fato(self) -> bool:
        return self.nome.startswith("fato_")

    @property
    def fontes(self) -> set[str]:
        """As tabelas da silver que o SQL lê; quem usa o horizonte lê também as que o definem."""
        lidas = {f"{m}.{t}" for m, t in re.findall(r"\bsilver\.(\w+)\.(\w+)", self.sql)}
        return lidas | (set(FONTES_DO_HORIZONTE) if HORIZONTE in self.sql else set())


_CALENDARIO = f"""
    dias AS (SELECT CAST(unnest(generate_series(DATE '{INICIO}', DATE '{FIM}', INTERVAL 1 DAY)) AS DATE) AS data),
    nacionais AS (SELECT data, min(nome) AS nome FROM silver.cadastro.feriado WHERE abrangencia = 'NACIONAL' GROUP BY 1),
    calendario AS (
      SELECT d.data, n.data IS NOT NULL AS feriado_nacional, n.nome AS nome_do_feriado,
             isodow(d.data) <= 5 AND n.data IS NULL AS dia_util
      FROM dias d LEFT JOIN nacionais n USING (data))
"""  # noqa: S608 # nosec B608 - constantes do módulo

DIM_DATA = Tabela(
    "dim_data",
    f"""
    WITH {_CALENDARIO}
    SELECT CAST(strftime(data, '%Y%m%d') AS INTEGER) AS id, data, CAST(year(data) AS INTEGER) AS ano,
           CAST(quarter(data) AS INTEGER) AS trimestre, CAST(month(data) AS INTEGER) AS mes,
           CAST(year(data) * 100 + month(data) AS INTEGER) AS mes_id,
           CAST(isodow(data) AS INTEGER) AS dia_da_semana, dia_util, feriado_nacional, nome_do_feriado
    FROM calendario
    UNION ALL BY NAME SELECT CAST(0 AS INTEGER) AS id
    """,  # noqa: S608 # nosec B608
)

DIM_MES = Tabela(
    "dim_mes",
    f"""
    WITH {_CALENDARIO}
    SELECT CAST(year(data) * 100 + month(data) AS INTEGER) AS id, min(data) AS primeiro_dia, max(data) AS ultimo_dia,
           CAST(year(min(data)) AS INTEGER) AS ano, CAST(quarter(min(data)) AS INTEGER) AS trimestre,
           CAST(month(min(data)) AS INTEGER) AS mes, CAST(count(*) AS INTEGER) AS dias,
           CAST(count(*) FILTER (WHERE dia_util) AS INTEGER) AS dias_uteis
    FROM calendario GROUP BY 1
    UNION ALL BY NAME SELECT CAST(0 AS INTEGER) AS id
    """,  # noqa: S608 # nosec B608
)

_LUGAR = "LEFT JOIN silver.cadastro.municipio m ON m.id = {de}.municipio_id LEFT JOIN silver.cadastro.regiao r ON r.id = m.regiao_id"

DIM_FILIAL = Tabela(
    "dim_filial",
    f"""
    SELECT f.id, f.codigo, f.nome, f.tipo, m.nome AS municipio, m.uf, r.nome AS regiao, f.dt_abertura, f.ativo
    FROM silver.cadastro.filial f LEFT JOIN silver.cadastro.endereco e ON e.id = f.endereco_id
    {_LUGAR.format(de="e")}
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS nome
    """,  # noqa: S608 # nosec B608
)

DIM_CLIENTE = Tabela(
    "dim_cliente",
    f"""
    SELECT c.id, c.razao_social, c.nome_fantasia, c.porte, c.setor, c.origem, m.nome AS municipio, m.uf,
           r.nome AS regiao, c.dt_primeiro_contrato, c.ativo
    FROM silver.comercial.cliente c {_LUGAR.format(de="c")}
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS razao_social, '{NAO_SE_APLICA}' AS nome_fantasia
    """,  # noqa: S608 # nosec B608
)

DIM_CONTRATO = Tabela(
    "dim_contrato",
    f"""
    WITH prorrogado AS (
      SELECT contrato_id, count(*) AS prorrogacoes FROM silver.comercial.contrato_aditivo
      WHERE tipo = 'PRORROGACAO' GROUP BY 1)
    SELECT k.id, k.numero, k.tipo_servico, k.status AS status_informado, k.situacao_derivada, k.q_com_01,
           k.dt_assinatura, k.vigencia_inicio, k.vigencia_fim, k.dt_encerramento, k.prazo_pagamento_dias,
           k.indice_reajuste, CAST(coalesce(p.prorrogacoes, 0) AS INTEGER) AS prorrogacoes, k.cliente_id, k.filial_id
    FROM silver.comercial.contrato k LEFT JOIN prorrogado p ON p.contrato_id = k.id
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS numero, CAST(0 AS BIGINT) AS cliente_id, CAST(0 AS BIGINT) AS filial_id
    """,  # noqa: S608 # nosec B608
    referencias={"cliente_id": "dim_cliente", "filial_id": "dim_filial"},
)

DIM_POSTO = Tabela(
    "dim_posto",
    f"""
    SELECT p.id, p.turno, e.codigo AS escala, e.horas_semanais, CAST(p.quantidade AS INTEGER) AS posicoes,
           p.vigencia_inicio, p.vigencia_fim, m.nome AS municipio, m.uf, p.q_com_02,
           p.contrato_id, k.cliente_id, p.funcao_id
    FROM silver.comercial.posto p JOIN silver.comercial.contrato k ON k.id = p.contrato_id
    LEFT JOIN silver.cadastro.escala e ON e.id = p.escala_id
    LEFT JOIN silver.cadastro.endereco l ON l.id = p.endereco_id
    LEFT JOIN silver.cadastro.municipio m ON m.id = l.municipio_id
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS turno, CAST(0 AS BIGINT) AS contrato_id,
                             CAST(0 AS BIGINT) AS cliente_id, CAST(0 AS BIGINT) AS funcao_id
    """,  # noqa: S608 # nosec B608
    referencias={
        "contrato_id": "dim_contrato",
        "cliente_id": "dim_cliente",
        "funcao_id": "dim_funcao",
    },
)

DIM_FUNCAO = Tabela(
    "dim_funcao",
    f"""
    SELECT id, codigo, nome, familia, nivel, cbo, fl_insalubre, fl_periculosidade, q_cad_01
    FROM silver.cadastro.funcao
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS nome
    """,  # noqa: S608 # nosec B608
)

DIM_COLABORADOR = Tabela(
    "dim_colaborador",
    """
    SELECT c.id, c.ano_nascimento, k.sexo, k.escolaridade, f.nome AS fonte_de_recrutamento,
           m.nome AS municipio, m.uf, c.dt_admissao_primeira, c.ativo
    FROM silver.pessoas.colaborador c LEFT JOIN silver.ats.candidato k ON k.id = c.candidato_id
    LEFT JOIN silver.ats.fonte_candidato f ON f.id = k.fonte_id
    LEFT JOIN silver.cadastro.municipio m ON m.id = c.municipio_id
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id
    """,
)

DIM_CANDIDATO = Tabela(
    "dim_candidato",
    f"""
    SELECT k.id, f.nome AS fonte, k.sexo, k.escolaridade, k.ano_nascimento, m.nome AS municipio, m.uf,
           k.dt_cadastro, k.q_ats_01, k.cadastro_canonico, k.pessoal_descartado
    FROM silver.ats.candidato k LEFT JOIN silver.ats.fonte_candidato f ON f.id = k.fonte_id
    LEFT JOIN silver.cadastro.municipio m ON m.id = k.municipio_id
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS fonte
    """,  # noqa: S608 # nosec B608
)

DIM_MOTIVO = Tabela(
    "dim_motivo",
    f"""
    SELECT id, tipo, codigo, descricao, grupo FROM silver.cadastro.motivo
    UNION ALL BY NAME SELECT CAST(0 AS BIGINT) AS id, '{NAO_SE_APLICA}' AS descricao
    """,  # noqa: S608 # nosec B608
)

# ------------------------------------------------------------------ a espinha da margem

FATO_FATURAMENTO = Tabela(
    "fato_faturamento",
    """
    WITH itens AS (
      SELECT i.id AS fatura_item_id, i.fatura_id, i.posto_id, i.valor_postos, i.valor_horas_extras,
             i.valor_descontos, i.valor_total, i.qtd_dias_trabalhados, i.qtd_faltas, i.q_fin_07,
             sum(i.valor_total) OVER (PARTITION BY i.fatura_id) AS total_dos_itens,
             row_number() OVER (PARTITION BY i.fatura_id ORDER BY i.id DESC) AS do_fim
      FROM silver.financeiro.fatura_item i),
    partes AS (  -- o imposto da fatura repartido pelos itens, arredondado ao centavo
      SELECT i.*, CAST(round(CAST(f.valor_impostos AS DOUBLE) * i.valor_total / nullif(i.total_dos_itens, 0), 2) AS DECIMAL(14, 2)) AS parte
      FROM itens i JOIN silver.financeiro.fatura f ON f.id = i.fatura_id),
    com_imposto AS (  -- o que o arredondamento deixou sobrar fica no último item
      SELECT p.*, CASE WHEN p.do_fim = 1
                       THEN f.valor_impostos - (sum(p.parte) OVER (PARTITION BY p.fatura_id) - p.parte)
                       ELSE p.parte END AS valor_impostos
      FROM partes p JOIN silver.financeiro.fatura f ON f.id = p.fatura_id),
    linhas AS (
      SELECT f.id AS fatura_id, i.fatura_item_id, f.numero, f.status, f.competencia, f.dt_emissao, f.cliente_id,
             f.contrato_id, i.posto_id, i.valor_postos, i.valor_horas_extras, i.valor_descontos,
             i.valor_total AS valor_bruto, i.valor_impostos, i.qtd_dias_trabalhados, i.qtd_faltas, f.q_fin_03, i.q_fin_07
      FROM com_imposto i JOIN silver.financeiro.fatura f ON f.id = i.fatura_id
      UNION ALL BY NAME
      SELECT f.id AS fatura_id, CAST(0 AS BIGINT) AS fatura_item_id, f.numero, f.status, f.competencia, f.dt_emissao,
             f.cliente_id, f.contrato_id, CAST(0 AS BIGINT) AS posto_id, f.valor_bruto, f.valor_impostos, f.q_fin_03
      FROM silver.financeiro.fatura f
      WHERE NOT EXISTS (SELECT 1 FROM silver.financeiro.fatura_item i WHERE i.fatura_id = f.id))
    SELECT l.fatura_id, l.fatura_item_id, l.numero, l.status,
           CAST(year(l.competencia) * 100 + month(l.competencia) AS INTEGER) AS mes_id,
           CAST(strftime(l.dt_emissao, '%Y%m%d') AS INTEGER) AS data_emissao_id,
           l.cliente_id, l.contrato_id, l.posto_id, k.filial_id, coalesce(p.funcao_id, 0) AS funcao_id,
           l.valor_postos, l.valor_horas_extras, l.valor_descontos, l.valor_bruto, l.valor_impostos,
           l.valor_bruto - l.valor_impostos AS valor_liquido,
           CAST(l.qtd_dias_trabalhados AS INTEGER) AS dias_trabalhados, CAST(l.qtd_faltas AS INTEGER) AS faltas,
           l.q_fin_03, l.q_fin_07, CAST(year(l.competencia) AS INTEGER) AS ano
    FROM linhas l JOIN silver.comercial.contrato k ON k.id = l.contrato_id
    LEFT JOIN silver.comercial.posto p ON p.id = l.posto_id
    """,
    chave=("fatura_id", "fatura_item_id"),
    referencias={
        "mes_id": "dim_mes",
        "data_emissao_id": "dim_data",
        "cliente_id": "dim_cliente",
        "contrato_id": "dim_contrato",
        "posto_id": "dim_posto",
        "filial_id": "dim_filial",
        "funcao_id": "dim_funcao",
    },
    particao="ano",
    conservacoes=(
        Conservacao(
            "faturas", "count(DISTINCT fatura_id)", "SELECT count(*) FROM silver.financeiro.fatura"
        ),
        Conservacao(
            "valor bruto",
            "sum(valor_bruto)",
            "SELECT sum(valor_bruto) FROM silver.financeiro.fatura",
        ),
        Conservacao(
            "impostos",
            "sum(valor_impostos)",
            "SELECT sum(valor_impostos) FROM silver.financeiro.fatura",
        ),
        Conservacao(
            "valor líquido",
            "sum(valor_liquido)",
            "SELECT sum(valor_liquido) FROM silver.financeiro.fatura",
        ),
    ),
)

FATO_CUSTO_PESSOAL = Tabela(
    "fato_custo_pessoal",
    """
    SELECT c.id, CAST(year(c.competencia) * 100 + month(c.competencia) AS INTEGER) AS mes_id, c.colaborador_id,
           c.alocacao_id, c.posto_id, c.contrato_id, k.cliente_id, k.filial_id, p.funcao_id, c.centro_custo_id,
           c.valor_salario, c.valor_encargos, c.valor_provisoes, c.valor_beneficios, c.custo_total,
           c.diferenca_rateio_folha, c.q_fol_01, c.q_fol_03, CAST(year(c.competencia) AS INTEGER) AS ano
    FROM silver.folha.rateio_custo c JOIN silver.comercial.contrato k ON k.id = c.contrato_id
    JOIN silver.comercial.posto p ON p.id = c.posto_id
    """,
    referencias={
        "mes_id": "dim_mes",
        "colaborador_id": "dim_colaborador",
        "posto_id": "dim_posto",
        "contrato_id": "dim_contrato",
        "cliente_id": "dim_cliente",
        "filial_id": "dim_filial",
        "funcao_id": "dim_funcao",
    },
    particao="ano",
    conservacoes=(
        Conservacao(
            "linhas de rateio", "count(*)", "SELECT count(*) FROM silver.folha.rateio_custo"
        ),
        Conservacao(
            "custo total",
            "sum(custo_total)",
            "SELECT sum(custo_total) FROM silver.folha.rateio_custo",
        ),
        Conservacao(
            "salário",
            "sum(valor_salario)",
            "SELECT sum(valor_salario) FROM silver.folha.rateio_custo",
        ),
    ),
)

_DIAS_DE_ALOCACAO = f"greatest(date_diff('day', a.dt_inicio, least(coalesce(a.dt_fim, {HORIZONTE}), {HORIZONTE})) + 1, 0)"
_PESSOA_DIAS_NA_SILVER = f"SELECT sum({_DIAS_DE_ALOCACAO}) FROM silver.pessoas.alocacao a"  # noqa: S608 # nosec B608
_ENTRADAS_NA_SILVER = (
    f"SELECT count(*) FROM silver.pessoas.alocacao a WHERE a.dt_inicio <= {HORIZONTE}"  # noqa: S608 # nosec B608
)

FATO_POSTO_MES = Tabela(
    "fato_posto_mes",
    f"""
    WITH postos AS (
      SELECT p.id AS posto_id, p.contrato_id, k.cliente_id, k.filial_id, p.funcao_id, p.quantidade,
             p.vigencia_inicio AS ini, least(coalesce(p.vigencia_fim, {HORIZONTE}), {HORIZONTE}) AS fim
      FROM silver.comercial.posto p JOIN silver.comercial.contrato k ON k.id = p.contrato_id),
    vigencia AS (  -- um mês por posto, do começo da vigência ao fim dela ou ao horizonte
      SELECT posto_id, CAST(unnest(generate_series(date_trunc('month', ini), date_trunc('month', fim), INTERVAL 1 MONTH)) AS DATE) AS mes
      FROM postos WHERE fim >= ini),
    receita AS (
      SELECT i.posto_id, f.competencia AS mes, sum(i.valor_total) AS receita
      FROM silver.financeiro.fatura_item i JOIN silver.financeiro.fatura f ON f.id = i.fatura_id GROUP BY 1, 2),
    custo AS (
      SELECT posto_id, competencia AS mes, sum(custo_total) AS custo, bool_or(q_fol_01) AS q_fol_01
      FROM silver.folha.rateio_custo GROUP BY 1, 2),
    grade AS (  -- a vigência, mais qualquer mês com receita ou custo: nenhum centavo fica sem linha
      SELECT posto_id, mes FROM vigencia UNION SELECT posto_id, mes FROM receita UNION SELECT posto_id, mes FROM custo),
    meses AS (
      SELECT g.posto_id, g.mes, least(last_day(g.mes), {HORIZONTE}) AS fim_do_mes, p.contrato_id, p.cliente_id,
             p.filial_id, p.funcao_id, p.quantidade, p.ini, p.fim
      FROM grade g JOIN postos p USING (posto_id)),
    alocacoes AS (
      SELECT a.posto_id, a.colaborador_id, a.dt_inicio AS ini, a.dt_fim,
             least(coalesce(a.dt_fim, {HORIZONTE}), {HORIZONTE}) AS fim, a.q_fin_06
      FROM silver.pessoas.alocacao a),
    ocupacao AS (
      SELECT m.posto_id, m.mes,
             sum(greatest(date_diff('day', greatest(a.ini, m.mes), least(a.fim, m.fim_do_mes)) + 1, 0)) AS pessoa_dias,
             count(DISTINCT a.colaborador_id) FILTER (WHERE a.ini <= m.fim_do_mes AND a.fim >= m.fim_do_mes) AS pessoas_no_fim,
             count(*) FILTER (WHERE a.ini BETWEEN m.mes AND m.fim_do_mes) AS entradas,
             count(*) FILTER (WHERE a.dt_fim BETWEEN m.mes AND m.fim_do_mes) AS saidas,
             bool_or(a.q_fin_06 AND date_trunc('month', a.ini) = m.mes) AS q_fin_06
      FROM meses m JOIN alocacoes a ON a.posto_id = m.posto_id AND a.ini <= m.fim_do_mes AND a.fim >= m.mes
      GROUP BY 1, 2),
    preco AS (  -- o preço vigente no último dia do posto dentro do mês
      SELECT m.posto_id, m.mes, arg_max(r.valor_mensal, r.vigencia_inicio) AS preco
      FROM meses m JOIN silver.comercial.posto_preco r ON r.posto_id = m.posto_id
       AND r.vigencia_inicio <= least(m.fim_do_mes, m.fim)
       AND coalesce(r.vigencia_fim, DATE '9999-12-31') >= least(m.fim_do_mes, m.fim)
      GROUP BY 1, 2),
    medidas AS (
      SELECT m.*, greatest(date_diff('day', greatest(m.ini, m.mes), least(m.fim, m.fim_do_mes)) + 1, 0) AS dias_vigentes,
             coalesce(o.pessoa_dias, 0) AS pessoa_dias, coalesce(o.pessoas_no_fim, 0) AS pessoas_no_fim,
             coalesce(o.entradas, 0) AS entradas, coalesce(o.saidas, 0) AS saidas, coalesce(o.q_fin_06, FALSE) AS q_fin_06,
             p.preco, r.receita IS NOT NULL AS faturado, coalesce(r.receita, 0) AS receita,
             coalesce(c.custo, 0) AS custo, coalesce(c.q_fol_01, FALSE) AS q_fol_01
      FROM meses m LEFT JOIN ocupacao o USING (posto_id, mes) LEFT JOIN preco p USING (posto_id, mes)
      LEFT JOIN receita r USING (posto_id, mes) LEFT JOIN custo c USING (posto_id, mes))
    SELECT CAST(year(mes) * 100 + month(mes) AS INTEGER) AS mes_id, posto_id, contrato_id, cliente_id, filial_id, funcao_id,
           mes = date_trunc('month', {HORIZONTE}) AS mes_parcial, dias_vigentes = 0 AS fora_da_vigencia,
           CAST(quantidade AS INTEGER) AS posicoes_contratadas, CAST(dias_vigentes AS INTEGER) AS dias_vigentes,
           CAST(quantidade * dias_vigentes AS INTEGER) AS posicao_dias_contratados,
           CAST(pessoa_dias AS INTEGER) AS pessoa_dias_alocados,
           CAST(greatest(quantidade * dias_vigentes - pessoa_dias, 0) AS INTEGER) AS posicao_dias_descobertos,
           CASE WHEN quantidade * dias_vigentes > 0 THEN pessoa_dias / CAST(quantidade * dias_vigentes AS DOUBLE) END AS taxa_de_ocupacao,
           CAST(pessoas_no_fim AS INTEGER) AS pessoas_no_fim_do_mes, CAST(entradas AS INTEGER) AS entradas,
           CAST(saidas AS INTEGER) AS saidas, preco AS preco_mensal_vigente, faturado, receita, custo AS custo_pessoal,
           receita - custo AS margem,
           CASE WHEN receita > 0 THEN CAST(receita - custo AS DOUBLE) / CAST(receita AS DOUBLE) END AS margem_pct,
           q_fin_06, q_fol_01, CAST(year(mes) AS INTEGER) AS ano
    FROM medidas
    """,  # noqa: S608 # nosec B608
    chave=("posto_id", "mes_id"),
    referencias={
        "mes_id": "dim_mes",
        "posto_id": "dim_posto",
        "contrato_id": "dim_contrato",
        "cliente_id": "dim_cliente",
        "filial_id": "dim_filial",
        "funcao_id": "dim_funcao",
    },
    particao="ano",
    conservacoes=(
        Conservacao(
            "receita dos postos",
            "sum(receita)",
            "SELECT sum(valor_total) FROM silver.financeiro.fatura_item",
        ),
        Conservacao(
            "custo de pessoal",
            "sum(custo_pessoal)",
            "SELECT sum(custo_total) FROM silver.folha.rateio_custo",
        ),
        Conservacao(
            "pessoa-dias alocados",
            "sum(pessoa_dias_alocados)",
            _PESSOA_DIAS_NA_SILVER,
        ),
        Conservacao(
            "entradas",
            "sum(entradas)",
            _ENTRADAS_NA_SILVER,
        ),
    ),
)

TABELAS: tuple[Tabela, ...] = (
    DIM_DATA,
    DIM_MES,
    DIM_FILIAL,
    DIM_CLIENTE,
    DIM_FUNCAO,
    DIM_MOTIVO,
    DIM_CONTRATO,
    DIM_POSTO,
    DIM_COLABORADOR,
    DIM_CANDIDATO,
    FATO_FATURAMENTO,
    FATO_CUSTO_PESSOAL,
    FATO_POSTO_MES,
)


def tabela(nome: str) -> Tabela:
    return next(t for t in TABELAS if t.nome == nome)


def preparar(con: duckdb.DuckDBPyConnection) -> str:
    """Fixa o horizonte da gold na conexão e o devolve (AAAA-MM-DD)."""
    con.execute(
        "SET VARIABLE horizonte = (SELECT greatest("
        "(SELECT max(data) FROM silver.ponto.apontamento), "
        "(SELECT max(greatest(dt_inicio, coalesce(dt_fim, dt_inicio))) FROM silver.pessoas.alocacao)))"
    )
    (horizonte,) = con.execute(f"SELECT {HORIZONTE}").fetchall()[0]
    if horizonte is None:
        raise RuntimeError("a silver não tem apontamento nem alocação: sem horizonte, não há gold")
    return str(horizonte)
