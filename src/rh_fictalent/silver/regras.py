# ruff: noqa: E501
"""As regras aprovadas no catálogo de achados, escritas como SQL sobre a bronze.

Cada `Regra` é uma entrada aprovada do `docs/13_catalogo_de_achados.md` (card 6.3), com o
mesmo código. Ela se divide em uma ou mais `Derivacao`: um SELECT que devolve o `id` da
linha e as colunas que a silver acrescenta àquela tabela (marcas `q_<codigo>`, colunas
derivadas, a coluna conformada). A silver junta as derivações à tabela da bronze pelo `id` e
nada mais: não funde, não preenche, não apaga, não corrige.

Três convenções valem para todas:

- **Só linha viva entra na regra.** A linha marcada como excluída na bronze (`excluido_em`
  preenchido) segue na silver, mas as marcas dela ficam nulas: "não avaliada", não "falsa".
- **A data de referência é uma só por construção**, lida pela variável `referencia` do
  DuckDB (`preparar`). É o "hoje" do dado, o mesmo que a auditoria usou: a marca d'água mais
  recente da carga. Regra com prazo (vencido, além do prazo, vigente) depende dela.
- **Cada regra diz como se conta.** A `contagem` é o SQL que devolve o número que a auditoria
  gravou para o achado; a prestação de contas (`silver.contas`) exige que os dois sejam iguais
  na data da auditoria. A marca que não reproduz a medida da auditoria não entra.

O SQL de cada regra reproduz a medida do notebook que achou o problema, inclusive nos
detalhes (a tolerância de R$ 0,01, os dois dias da CAT, o prazo de 180 dias do temporário).
Onde o notebook juntou uma tabela sem filtrar as linhas excluídas dela, a regra faz o mesmo:
divergir da medida aprovada seria mudar a regra sem aprovação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import duckdb

REF = "CAST(getvariable('referencia') AS DATE)"  # o "hoje" do dado, uma data só
SEM_FIM = "DATE '9999-12-31'"
PRAZO_TEMPORARIO = 180  # dias; Lei 6.019/1974, art. 10, § 1º (a medida da auditoria)
PRAZO_CAT = 2  # dias de tolerância da auditoria; o prazo legal é o primeiro dia útil
TOLERANCIA = 0.01  # reais: diferença menor que um centavo não é diferença
ALOCADO_HOJE = (
    "a.excluido_em IS NULL AND a.dt_inicio <= {REF} AND coalesce(a.dt_fim, {SEM_FIM}) >= {REF}"
)

# O SQL das regras é escrito com marcadores `{NOME}` e as constantes acima entram por
# substituição de texto (`_sql`), não por f-string: o SQL fica legível como está, e fica
# explícito que nenhuma parte dele vem de fora do módulo (o bandit trata f-string com SQL como
# possível injeção, e aqui não há entrada nenhuma).
_CONSTANTES = {
    "ALOCADO_HOJE": ALOCADO_HOJE,  # primeiro: ele mesmo tem marcadores
    "REF": REF,
    "SEM_FIM": SEM_FIM,
    "PRAZO_TEMPORARIO": str(PRAZO_TEMPORARIO),
    "PRAZO_CAT": str(PRAZO_CAT),
    "TOLERANCIA": str(TOLERANCIA),
}


def _sql(texto: str) -> str:
    """O SQL da regra com as constantes no lugar dos marcadores; marcador sem constante falha."""
    for nome, valor in _CONSTANTES.items():
        texto = texto.replace("{" + nome + "}", valor)
    if "{" in texto or "}" in texto:
        raise ValueError(f"marcador sem constante no SQL da regra: {texto[:120]}")
    return texto


# Funções SQL que as regras usam, criadas em toda conexão por `preparar`. O dígito do CPF é
# escrito aqui em SQL (e não chamado do Python) para rodar dentro do DuckDB sobre 60 mil
# linhas; o teste o compara com `auditoria.checagens.cpf_valido`, a implementação que a
# auditoria usou, valor a valor.
MACROS = (
    "CREATE OR REPLACE MACRO normalizado(x) AS "
    "strip_accents(lower(regexp_replace(trim(CAST(x AS VARCHAR)), '\\s+', ' ', 'g')))",
    "CREATE OR REPLACE MACRO digitos(x) AS regexp_replace(CAST(x AS VARCHAR), '[^0-9]', '', 'g')",
    "CREATE OR REPLACE MACRO dv_modulo_11(d, n) AS ("
    "CASE WHEN list_sum(list_transform(range(n), lambda i: TRY_CAST(d[i + 1] AS INTEGER) * (n + 1 - i))) % 11 < 2 THEN 0 "
    "ELSE 11 - list_sum(list_transform(range(n), lambda i: TRY_CAST(d[i + 1] AS INTEGER) * (n + 1 - i))) % 11 END)",
    "CREATE OR REPLACE MACRO cpf_valido(x) AS ("
    "CASE WHEN x IS NULL THEN NULL "
    "WHEN length(digitos(x)) <> 11 THEN FALSE "
    "WHEN regexp_replace(digitos(x), left(digitos(x), 1), '', 'g') = '' THEN FALSE "
    "ELSE dv_modulo_11(digitos(x), 9) = TRY_CAST(digitos(x)[10] AS INTEGER) "
    "AND dv_modulo_11(digitos(x), 10) = TRY_CAST(digitos(x)[11] AS INTEGER) END)",
    # caixa de título sem inventar: cada palavra com a inicial maiúscula, as partículas do
    # nome em minúscula, o espaço normalizado; a inicial abreviada fica abreviada
    "CREATE OR REPLACE MACRO caixa_de_titulo(x) AS array_to_string(list_transform("
    "string_split(lower(regexp_replace(trim(x), '\\s+', ' ', 'g')), ' '), "
    "lambda p: CASE WHEN p IN ('da', 'das', 'de', 'di', 'do', 'dos', 'e') THEN p "
    "ELSE upper(left(p, 1)) || substr(p, 2) END), ' ')",
)


@dataclass(frozen=True)
class Derivacao:
    """O que uma regra acrescenta a uma tabela: um SELECT com `id` e as colunas novas."""

    tabela: str  # modulo.tabela, a que recebe as colunas
    colunas: tuple[str, ...]  # as colunas novas, na ordem em que entram na silver
    sql: str  # SELECT id, <colunas> ... (uma linha por id, no máximo)
    le: tuple[str, ...] = ()  # outras tabelas da bronze que o SQL lê (a linhagem)

    @property
    def marcas(self) -> tuple[str, ...]:
        return tuple(c for c in self.colunas if c.startswith("q_"))


@dataclass(frozen=True)
class Regra:
    codigo: str  # o código da entrada no catálogo (ATS-01)
    derivacoes: tuple[Derivacao, ...]
    contagem: str = ""  # SQL do número que a auditoria gravou; vazio = linhas com a marca

    @property
    def marca(self) -> str:
        return "q_" + self.codigo.lower().replace("-", "_")

    def nome(self, derivacao: Derivacao) -> str:
        """O nome da tabela em que a derivação é materializada, no catálogo `regra`."""
        return f"{self.marca[2:]}_{derivacao.tabela.split('.')[1]}"

    @property
    def sql_da_contagem(self) -> str:
        if self.contagem:
            return self.contagem
        (alvo,) = [d for d in self.derivacoes if self.marca in d.colunas]
        return f"SELECT count(*) FROM regra.{self.nome(alvo)} WHERE {self.marca}"  # noqa: S608 # nosec B608

    @property
    def tabelas(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(d.tabela for d in self.derivacoes))


def _marca_simples(
    codigo: str, tabela: str, condicao: str, le: tuple[str, ...] = (), de: str = ""
) -> Regra:
    """A regra mais comum: marcar as linhas vivas da tabela que atendem a condição."""
    marca = "q_" + codigo.lower().replace("-", "_")
    origem = de or f"{tabela} t"
    sql = f"SELECT DISTINCT t.id, TRUE AS {marca} FROM {origem} WHERE t.excluido_em IS NULL AND ({condicao})"  # noqa: S608 # nosec B608
    return Regra(codigo, (Derivacao(tabela, (marca,), sql, le),))


def _repetidos(
    codigo: str, tabela: str, colunas: tuple[str, ...], normalizar: tuple[str, ...] = ()
) -> Regra:
    """Marcar todas as linhas de cada grupo que repete a combinação de colunas (nunca fundir).

    É a medida de `checagens.repetidos`: só linhas vivas, só combinações sem nulo, o grupo
    com mais de uma linha; com `normalizar`, o texto dessas colunas compara sem acento, caixa
    e espaço sobrando.
    """
    marca = "q_" + codigo.lower().replace("-", "_")
    chave = ", ".join(
        f"normalizado({c}) AS k{i}" if c in normalizar else f"{c} AS k{i}"
        for i, c in enumerate(colunas)
    )
    nomes = ", ".join(f"k{i}" for i in range(len(colunas)))
    sem_nulo = " AND ".join(f"{c} IS NOT NULL" for c in colunas)
    sql = (  # noqa: S608
        f"WITH v AS (SELECT id, {chave} FROM {tabela} WHERE excluido_em IS NULL AND {sem_nulo}), "  # nosec B608
        f"g AS (SELECT {nomes} FROM v GROUP BY ALL HAVING count(*) > 1) "
        f"SELECT v.id, TRUE AS {marca} FROM v JOIN g USING ({nomes})"
    )
    return Regra(codigo, (Derivacao(tabela, (marca,), sql),))


# ---------------------------------------------------------------- cadastro e comercial

CAD_01 = _marca_simples("CAD-01", "cadastro.funcao", "t.cbo IS NULL")

COM_01 = Regra(
    "COM-01",
    (
        Derivacao(
            "comercial.contrato",
            ("situacao_derivada", "q_com_01"),
            _sql("""
            WITH prorrogado AS (
              SELECT contrato_id, max(vigencia_nova) AS ate FROM comercial.contrato_aditivo
              WHERE excluido_em IS NULL AND tipo = 'PRORROGACAO' GROUP BY 1),
            s AS (
              SELECT k.id, k.status,
                     CASE WHEN k.dt_encerramento IS NOT NULL AND k.dt_encerramento <= {REF} THEN 'encerrado'
                          WHEN k.vigencia_fim < {REF} AND coalesce(p.ate, DATE '1900-01-01') < {REF} THEN 'vencido'
                          ELSE 'vigente' END AS situacao_derivada
              FROM comercial.contrato k LEFT JOIN prorrogado p ON p.contrato_id = k.id
              WHERE k.excluido_em IS NULL)
            SELECT id, situacao_derivada, status = 'ATIVO' AND situacao_derivada <> 'vigente' AS q_com_01 FROM s
            """),
            ("comercial.contrato_aditivo",),
        ),
    ),
)

COM_02 = _repetidos(
    "COM-02",
    "comercial.posto",
    ("contrato_id", "funcao_id", "turno", "endereco_id", "vigencia_inicio"),
    normalizar=("turno",),
)

COM_03 = _marca_simples(
    "COM-03",
    "comercial.contrato_ocorrencia",
    f"t.dt_ocorrencia < k.vigencia_inicio OR t.dt_ocorrencia > coalesce(k.dt_encerramento, k.vigencia_fim, {SEM_FIM})",
    le=("comercial.contrato",),
    de="comercial.contrato_ocorrencia t JOIN comercial.contrato k ON k.id = t.contrato_id",
)

# ---------------------------------------------------------------- ats

ATS_01 = Regra(
    "ATS-01",
    (
        Derivacao(
            "ats.candidato",
            ("q_ats_01", "grupo_pessoa", "cadastro_canonico"),
            """
            WITH c AS (
              SELECT id, cpf, dt_cadastro, dt_nascimento, normalizado(cpf) AS chave,
                     coalesce(cpf_valido(cpf), FALSE) AS valido, normalizado(nome) AS pessoa
              FROM ats.candidato WHERE excluido_em IS NULL),
            repetidos AS (SELECT chave FROM c WHERE cpf IS NOT NULL GROUP BY 1 HAVING count(*) > 1),
            -- o cadastro sem CPF entra no grupo só se nome e nascimento apontam um CPF válido e um só
            por_nome AS (
              SELECT pessoa, dt_nascimento, min(chave) AS chave FROM c
              WHERE valido AND pessoa IS NOT NULL AND dt_nascimento IS NOT NULL
              GROUP BY 1, 2 HAVING count(DISTINCT chave) = 1),
            g AS (
              SELECT c.id, c.dt_cadastro, c.valido, c.chave IN (SELECT chave FROM repetidos) AS repetido,
                     CASE WHEN c.valido THEN c.chave WHEN c.cpf IS NULL THEN n.chave END AS grupo_pessoa
              FROM c LEFT JOIN por_nome n ON n.pessoa = c.pessoa AND n.dt_nascimento = c.dt_nascimento),
            canonico AS (
              SELECT grupo_pessoa, first(id ORDER BY dt_cadastro, id) AS cadastro_canonico
              FROM g WHERE valido GROUP BY 1)
            SELECT g.id, coalesce(g.repetido, FALSE) AS q_ats_01, g.grupo_pessoa, k.cadastro_canonico
            FROM g LEFT JOIN canonico k USING (grupo_pessoa)
            """,
        ),
    ),
)

ATS_02 = Regra(
    "ATS-02",
    (
        Derivacao(
            "ats.candidato",
            ("q_ats_02",),
            """
            WITH c AS (SELECT id, normalizado(nome) AS pessoa, dt_nascimento, cpf FROM ats.candidato WHERE excluido_em IS NULL),
            g AS (SELECT pessoa, dt_nascimento FROM c GROUP BY 1, 2 HAVING count(*) > 1 AND count(DISTINCT cpf) > 1)
            SELECT c.id, TRUE AS q_ats_02 FROM c JOIN g
              ON g.pessoa IS NOT DISTINCT FROM c.pessoa AND g.dt_nascimento IS NOT DISTINCT FROM c.dt_nascimento
            """,
        ),
    ),
)

ATS_03 = _marca_simples("ATS-03", "ats.candidato", "t.cpf IS NOT NULL AND NOT cpf_valido(t.cpf)")

ATS_04 = _marca_simples(
    "ATS-04",
    "ats.candidato",
    "t.dt_nascimento IS NOT NULL AND (date_diff('year', t.dt_nascimento, t.dt_cadastro) < 14 OR t.dt_nascimento < DATE '1930-01-01')",
)

ATS_05 = Regra(
    "ATS-05",
    (
        Derivacao(
            "ats.candidato",
            ("nome_conformado", "q_ats_05"),
            r"""
            SELECT id, caixa_de_titulo(nome) AS nome_conformado,
                   nome = upper(nome) OR regexp_matches(nome, ' [A-Z]\. ') AS q_ats_05
            FROM ats.candidato WHERE excluido_em IS NULL
            """,
        ),
    ),
)

ATS_06 = _marca_simples("ATS-06", "ats.candidato", "t.cpf IS NULL")

ATS_08 = _marca_simples(
    "ATS-08",
    "ats.candidato_experiencia",
    "k.dt_nascimento IS NOT NULL AND date_diff('year', k.dt_nascimento, t.dt_inicio) < 14",
    le=("ats.candidato",),
    de="ats.candidato_experiencia t JOIN ats.candidato k ON k.id = t.candidato_id",
)

# ---------------------------------------------------------------- pessoas

PES_01 = Regra(
    "PES-01",
    (
        Derivacao(
            "pessoas.contrato_trabalho",
            ("dias_de_vinculo", "dias_alem_do_prazo", "q_pes_01"),
            _sql("""
            WITH p AS (
              SELECT contrato_trabalho_id, count(*) AS prorrogacoes, sum(dias_adicionais) AS dias
              FROM pessoas.contrato_trabalho_prorrogacao WHERE excluido_em IS NULL GROUP BY 1),
            t AS (
              SELECT k.id, k.tipo, date_diff('day', k.dt_admissao, coalesce(k.dt_rescisao, {REF})) AS dias_de_vinculo,
                     coalesce(p.prorrogacoes, 0) AS prorrogacoes, coalesce(p.dias, 0) AS dias_prorrogados
              FROM pessoas.contrato_trabalho k LEFT JOIN p ON p.contrato_trabalho_id = k.id
              WHERE k.excluido_em IS NULL)
            SELECT id, dias_de_vinculo,
                   CASE WHEN tipo = 'TEMPORARIO' THEN greatest(dias_de_vinculo - ({PRAZO_TEMPORARIO} + dias_prorrogados), 0) END AS dias_alem_do_prazo,
                   tipo = 'TEMPORARIO' AND dias_de_vinculo > {PRAZO_TEMPORARIO} AND prorrogacoes = 0 AS q_pes_01
            FROM t
            """),
            ("pessoas.contrato_trabalho_prorrogacao",),
        ),
    ),
)

PES_02 = Regra(
    "PES-02",
    (
        Derivacao(
            "pessoas.contrato_trabalho",
            ("dias_de_atraso_do_lancamento", "q_pes_02"),
            """
            SELECT id, greatest(date_diff('day', dt_admissao, CAST(criado_em AS DATE)), 0) AS dias_de_atraso_do_lancamento,
                   dt_admissao < CAST(criado_em AS DATE) AS q_pes_02
            FROM pessoas.contrato_trabalho WHERE excluido_em IS NULL
            """,
        ),
    ),
)

PES_03 = Regra(
    "PES-03",
    (
        Derivacao(
            "pessoas.contrato_trabalho",
            ("dt_prevista_termino_derivada", "q_pes_03"),
            """
            SELECT id,
                   coalesce(dt_prevista_termino, CASE WHEN tipo = 'TEMPORARIO' THEN dt_admissao + CAST(prazo_legal_dias AS INTEGER) END) AS dt_prevista_termino_derivada,
                   tipo = 'TEMPORARIO' AND dt_prevista_termino IS NULL AS q_pes_03
            FROM pessoas.contrato_trabalho WHERE excluido_em IS NULL
            """,
        ),
    ),
)

PES_04 = _marca_simples(
    "PES-04",
    "pessoas.afastamento",
    f"b.excluido_em IS NULL AND t.dt_inicio <= coalesce(b.dt_fim, {SEM_FIM}) AND b.dt_inicio <= coalesce(t.dt_fim, {SEM_FIM})",
    de="pessoas.afastamento t JOIN pessoas.afastamento b ON b.colaborador_id = t.colaborador_id AND b.id <> t.id",
)

# ---------------------------------------------------------------- ponto

PON_01 = Regra(
    "PON-01",
    (
        Derivacao(
            "ponto.apontamento",
            ("q_pon_01",),
            """
            WITH d AS (SELECT colaborador_id, data FROM ponto.marcacao WHERE excluido_em IS NULL GROUP BY 1, 2 HAVING count(*) BETWEEN 2 AND 3)
            SELECT a.id, TRUE AS q_pon_01 FROM ponto.apontamento a JOIN d USING (colaborador_id, data) WHERE a.excluido_em IS NULL
            """,
            ("ponto.marcacao",),
        ),
    ),
    # a auditoria contou dias; a marca está no apontamento do dia
    contagem="SELECT count(*) FROM (SELECT DISTINCT a.colaborador_id, a.data FROM regra.pon_01_apontamento r JOIN ponto.apontamento a USING (id) WHERE r.q_pon_01)",
)

PON_02 = Regra(
    "PON-02",
    (
        Derivacao(
            "ponto.marcacao",
            ("q_pon_02", "batida_valida"),
            """
            SELECT id,
                   count(*) OVER (PARTITION BY colaborador_id, data, tipo) > 1 AS q_pon_02,
                   row_number() OVER (PARTITION BY colaborador_id, data, tipo ORDER BY hora, id) = 1 AS batida_valida
            FROM ponto.marcacao WHERE excluido_em IS NULL
            """,
        ),
    ),
)

PON_03 = _marca_simples("PON-03", "ponto.apontamento", "t.horas_noturnas > t.horas_trabalhadas")

PON_04 = Regra(
    "PON-04",
    (
        Derivacao(
            "ponto.marcacao",
            ("q_pon_04",),
            """
            WITH d AS (SELECT colaborador_id, data FROM ponto.marcacao WHERE excluido_em IS NULL GROUP BY 1, 2 HAVING count(*) = 1),
            soltas AS (
              SELECT d.* FROM d WHERE NOT EXISTS (
                SELECT 1 FROM ponto.apontamento a WHERE a.excluido_em IS NULL AND a.colaborador_id = d.colaborador_id AND a.data = d.data))
            SELECT m.id, TRUE AS q_pon_04 FROM ponto.marcacao m JOIN soltas USING (colaborador_id, data) WHERE m.excluido_em IS NULL
            """,
            ("ponto.apontamento",),
        ),
    ),
)

# ---------------------------------------------------------------- folha

FOL_01 = Regra(
    "FOL-01",
    (
        Derivacao(
            "folha.rateio_custo",
            ("diferenca_rateio_folha", "q_fol_01"),
            _sql("""
            WITH pago AS (
              SELECT f.competencia, i.colaborador_id,
                     sum(i.valor) FILTER (WHERE e.tipo = 'PROVENTO' AND e.codigo NOT IN ('RESC_13', 'RESC_FER', 'DEC_TERC')) AS proventos
              FROM folha.folha_item i JOIN folha.folha_competencia f ON f.id = i.folha_competencia_id
              JOIN folha.evento_folha e ON e.id = i.evento_id
              WHERE i.excluido_em IS NULL GROUP BY 1, 2),
            rateado AS (
              SELECT competencia, colaborador_id, sum(valor_salario) AS salario
              FROM folha.rateio_custo WHERE excluido_em IS NULL GROUP BY 1, 2),
            dif AS (SELECT competencia, colaborador_id, r.salario - p.proventos AS diferenca FROM rateado r JOIN pago p USING (competencia, colaborador_id))
            SELECT c.id, dif.diferenca AS diferenca_rateio_folha, abs(dif.diferenca) > {TOLERANCIA} AS q_fol_01
            FROM folha.rateio_custo c JOIN dif USING (competencia, colaborador_id) WHERE c.excluido_em IS NULL
            """),
            ("folha.folha_item", "folha.folha_competencia", "folha.evento_folha"),
        ),
    ),
    # a auditoria contou pessoa-mês; a marca está em cada linha de rateio da pessoa no mês
    contagem="SELECT count(*) FROM (SELECT DISTINCT c.competencia, c.colaborador_id FROM regra.fol_01_rateio_custo r JOIN folha.rateio_custo c USING (id) WHERE r.q_fol_01)",
)

FOL_02 = Regra(
    "FOL-02",
    (
        Derivacao(
            "folha.provisao",
            ("q_fol_02",),
            _sql("""
            WITH p AS (
              SELECT id, valor_mes, saldo_acumulado,
                     lag(saldo_acumulado) OVER (PARTITION BY colaborador_id, tipo ORDER BY competencia) AS saldo_anterior
              FROM folha.provisao WHERE excluido_em IS NULL)
            SELECT id, TRUE AS q_fol_02 FROM p
            WHERE saldo_anterior IS NOT NULL AND abs(saldo_anterior + valor_mes - saldo_acumulado) > {TOLERANCIA}
            """),
        ),
    ),
)

FOL_03 = _marca_simples("FOL-03", "folha.rateio_custo", "t.custo_total <= 0")

# ---------------------------------------------------------------- financeiro

FIN_03 = _marca_simples(
    "FIN-03",
    "financeiro.fatura",
    "k.dt_encerramento IS NOT NULL AND t.competencia > k.dt_encerramento",
    le=("comercial.contrato",),
    de="financeiro.fatura t JOIN comercial.contrato k ON k.id = t.contrato_id",
)

FIN_04 = Regra(
    "FIN-04",
    (
        Derivacao(
            "financeiro.titulo_receber",
            ("situacao_derivada",),
            _sql("""
            SELECT id,
                   CASE WHEN status = 'CANCELADO' THEN 'cancelado'
                        WHEN dt_pagamento IS NOT NULL AND dt_pagamento <= dt_vencimento THEN 'pago em dia'
                        WHEN dt_pagamento IS NOT NULL THEN 'pago com atraso'
                        WHEN dt_vencimento < {REF} THEN 'vencido'
                        ELSE 'em dia' END AS situacao_derivada
            FROM financeiro.titulo_receber WHERE excluido_em IS NULL
            """),
        ),
    ),
    # a regra aprovada não marca: deriva a situação; conta-se o ABERTO que a derivação diz vencido
    contagem="SELECT count(*) FROM regra.fin_04_titulo_receber r JOIN financeiro.titulo_receber t USING (id) WHERE t.status = 'ABERTO' AND r.situacao_derivada = 'vencido'",
)

FIN_05 = Regra(
    "FIN-05",
    (
        Derivacao(
            "financeiro.titulo_receber",
            ("diferenca_pagamento", "q_fin_05"),
            _sql("""
            SELECT id, valor_pago - valor AS diferenca_pagamento,
                   status = 'PAGO' AND abs(valor_pago - valor) > {TOLERANCIA} AS q_fin_05
            FROM financeiro.titulo_receber WHERE excluido_em IS NULL
            """),
        ),
    ),
)

FIN_06 = Regra(
    "FIN-06",
    (
        Derivacao(
            "pessoas.alocacao",
            ("q_fin_06",),
            _sql("""
            WITH x AS (SELECT DISTINCT date_trunc('month', dt_inicio) AS mes, posto_id FROM pessoas.alocacao WHERE excluido_em IS NULL),
            sem_item AS (
              SELECT * FROM x WHERE x.mes < date_trunc('month', {REF}) AND NOT EXISTS (
                SELECT 1 FROM financeiro.fatura_item i JOIN financeiro.fatura f ON f.id = i.fatura_id
                WHERE i.excluido_em IS NULL AND i.posto_id = x.posto_id AND f.competencia = x.mes))
            SELECT a.id, TRUE AS q_fin_06 FROM pessoas.alocacao a
            JOIN sem_item s ON s.posto_id = a.posto_id AND s.mes = date_trunc('month', a.dt_inicio)
            WHERE a.excluido_em IS NULL
            """),
            ("financeiro.fatura_item", "financeiro.fatura"),
        ),
    ),
    # a auditoria contou posto-mês; não existe linha de posto-mês, e o item de fatura que
    # faltou não existe: a marca fica na alocação que começou no mês sem item
    contagem="SELECT count(*) FROM (SELECT DISTINCT a.posto_id, date_trunc('month', a.dt_inicio) FROM regra.fin_06_alocacao r JOIN pessoas.alocacao a USING (id) WHERE r.q_fin_06)",
)

FIN_07 = _marca_simples(
    "FIN-07",
    "financeiro.fatura_item",
    f"abs(t.valor_total - (t.valor_postos + t.valor_horas_extras - t.valor_descontos)) > {TOLERANCIA}",
)

# ---------------------------------------------------------------- treinamento e sst

TSS_01 = Regra(
    "TSS-01",
    (
        Derivacao(
            "sst.aso",
            ("aso_valido", "dias_para_vencer"),
            _sql("""
            SELECT id, coalesce(dt_exame <= {REF} AND dt_validade >= {REF} AND resultado <> 'INAPTO', FALSE) AS aso_valido,
                   date_diff('day', {REF}, dt_validade) AS dias_para_vencer
            FROM sst.aso WHERE excluido_em IS NULL
            """),
        ),
        Derivacao(
            "pessoas.alocacao",
            ("q_tss_01",),
            _sql("""
            SELECT a.id, TRUE AS q_tss_01 FROM pessoas.alocacao a
            WHERE {ALOCADO_HOJE} AND NOT EXISTS (
              SELECT 1 FROM sst.aso s WHERE s.excluido_em IS NULL AND s.colaborador_id = a.colaborador_id
                AND s.dt_exame <= {REF} AND s.dt_validade >= {REF} AND s.resultado <> 'INAPTO')
            """),
            ("sst.aso",),
        ),
    ),
    # a auditoria contou pessoas alocadas na data de referência
    contagem="SELECT count(DISTINCT a.colaborador_id) FROM regra.tss_01_alocacao r JOIN pessoas.alocacao a USING (id) WHERE r.q_tss_01",
)

TSS_02 = Regra(
    "TSS-02",
    (
        Derivacao(
            "sst.aso",
            ("dias_de_atraso_do_admissional", "q_tss_02"),
            """
            WITH adm AS (
              SELECT a.id, a.dt_exame,
                     (SELECT min(k.dt_admissao) FROM pessoas.contrato_trabalho k
                      WHERE k.colaborador_id = a.colaborador_id AND k.dt_admissao >= a.dt_exame - INTERVAL 60 DAY) AS admissao
              FROM sst.aso a JOIN sst.tipo_exame e ON e.id = a.tipo_exame_id
              WHERE a.excluido_em IS NULL AND e.codigo = 'ADMISSIONAL')
            SELECT id, greatest(date_diff('day', admissao, dt_exame), 0) AS dias_de_atraso_do_admissional,
                   dt_exame > admissao AS q_tss_02
            FROM adm
            """,
            ("sst.tipo_exame", "pessoas.contrato_trabalho"),
        ),
    ),
)

TSS_03 = Regra(
    "TSS-03",
    (
        Derivacao(
            "sst.cat",
            ("dias_alem_do_prazo_da_cat", "q_tss_03"),
            _sql("""
            SELECT c.id, greatest(date_diff('day', a.dt_acidente, c.dt_emissao) - {PRAZO_CAT}, 0) AS dias_alem_do_prazo_da_cat,
                   c.dt_emissao > a.dt_acidente + INTERVAL {PRAZO_CAT} DAY AS q_tss_03
            FROM sst.cat c JOIN sst.acidente a ON a.id = c.acidente_id WHERE c.excluido_em IS NULL
            """),
            ("sst.acidente",),
        ),
    ),
)

TSS_04 = Regra(
    "TSS-04",
    (
        Derivacao(
            "sst.programa_sst",
            ("programa_vigente", "q_tss_04"),
            _sql("""
            WITH p AS (
              SELECT p.id, p.dt_validade, k.status,
                     EXISTS (SELECT 1 FROM sst.programa_sst q WHERE q.excluido_em IS NULL AND q.tipo = p.tipo
                             AND q.contrato_id = p.contrato_id AND q.dt_validade >= {REF}) AS programa_vigente
              FROM sst.programa_sst p LEFT JOIN comercial.contrato k ON k.id = p.contrato_id
              WHERE p.excluido_em IS NULL)
            SELECT id, programa_vigente, status = 'ATIVO' AND dt_validade < {REF} AND NOT programa_vigente AS q_tss_04 FROM p
            """),
            ("comercial.contrato",),
        ),
    ),
    # a auditoria contou contratos
    contagem="SELECT count(DISTINCT p.contrato_id) FROM regra.tss_04_programa_sst r JOIN sst.programa_sst p USING (id) WHERE r.q_tss_04",
)

TSS_05 = _repetidos("TSS-05", "treinamento.turma", ("curso_id", "filial_id", "dt_inicio"))

TSS_06 = Regra(
    "TSS-06",
    (
        Derivacao(
            "treinamento.certificado",
            ("certificado_valido",),
            f"SELECT id, coalesce(dt_validade, {SEM_FIM}) >= {REF} AS certificado_valido FROM treinamento.certificado WHERE excluido_em IS NULL",  # noqa: S608 # nosec B608
        ),
        Derivacao(
            "pessoas.alocacao",
            ("cursos_obrigatorios_sem_certificado", "q_tss_06"),
            _sql("""
            WITH vigentes AS (
              SELECT a.id, a.colaborador_id, k.funcao_id FROM pessoas.alocacao a
              JOIN pessoas.contrato_trabalho k ON k.id = a.contrato_trabalho_id WHERE {ALOCADO_HOJE}),
            faltando AS (
              SELECT v.id, cf.curso_id FROM vigentes v
              JOIN treinamento.curso_funcao cf ON cf.excluido_em IS NULL AND cf.funcao_id = v.funcao_id AND cf.fl_obrigatorio
              WHERE NOT EXISTS (
                SELECT 1 FROM treinamento.certificado c JOIN treinamento.turma_participante p ON p.id = c.turma_participante_id
                JOIN treinamento.turma t ON t.id = p.turma_id
                WHERE c.excluido_em IS NULL AND p.colaborador_id = v.colaborador_id AND t.curso_id = cf.curso_id
                  AND coalesce(c.dt_validade, {SEM_FIM}) >= {REF}))
            SELECT id, list(curso_id ORDER BY curso_id) AS cursos_obrigatorios_sem_certificado, TRUE AS q_tss_06
            FROM faltando GROUP BY id
            """),
            (
                "pessoas.contrato_trabalho",
                "treinamento.curso_funcao",
                "treinamento.certificado",
                "treinamento.turma_participante",
                "treinamento.turma",
            ),
        ),
    ),
    # a auditoria contou pessoa-curso exigido (pela função do contrato) sem certificado válido
    contagem="""
        SELECT count(*) FROM (
          SELECT DISTINCT a.colaborador_id, k.funcao_id, u.curso_id
          FROM regra.tss_06_alocacao r JOIN pessoas.alocacao a USING (id)
          JOIN pessoas.contrato_trabalho k ON k.id = a.contrato_trabalho_id,
          unnest(r.cursos_obrigatorios_sem_certificado) AS u(curso_id)
          WHERE r.q_tss_06)
    """,
)

# ---------------------------------------------------------------- segurança

SEG_01 = _marca_simples(
    "SEG-01",
    "seguranca.log_auditoria",
    """t.acao <> 'LOGIN' AND NOT EXISTS (
         SELECT 1 FROM seguranca.usuario_perfil up JOIN seguranca.permissao m ON m.perfil_id = up.perfil_id AND m.excluido_em IS NULL
         WHERE up.excluido_em IS NULL AND up.usuario_id = t.usuario_id
           AND CAST(t.dt_evento AS DATE) BETWEEN up.vigencia_inicio AND coalesce(up.vigencia_fim, DATE '9999-12-31')
           AND m.modulo = t.modulo AND m.acao = t.acao AND m.fl_permitido)""",
    le=("seguranca.usuario_perfil", "seguranca.permissao"),
)

REGRAS: tuple[Regra, ...] = (
    CAD_01,
    COM_01,
    COM_02,
    COM_03,
    ATS_01,
    ATS_02,
    ATS_03,
    ATS_04,
    ATS_05,
    ATS_06,
    ATS_08,
    PES_01,
    PES_02,
    PES_03,
    PES_04,
    PON_01,
    PON_02,
    PON_03,
    PON_04,
    FOL_01,
    FOL_02,
    FOL_03,
    FIN_03,
    FIN_04,
    FIN_05,
    FIN_06,
    FIN_07,
    TSS_01,
    TSS_02,
    TSS_03,
    TSS_04,
    TSS_05,
    TSS_06,
    SEG_01,
)

# As entradas aprovadas que não viram coluna na silver, com o motivo. Estão aqui para o teste
# poder dizer que o catálogo inteiro foi considerado: toda entrada ou tem regra, ou tem motivo.
FORA_DA_SILVER: dict[str, str] = {
    "CAD-02": "manter: a coluna segue como está e é documentada como não coletada; o modelo dimensional não a leva",
    "ATS-07": "manter: o telefone não vira chave nem contato; nada a acrescentar à tabela",
    "FIN-01": "gold: a operação é a fonte da verdade e o consolidado fica ao lado como série informada",
    "FIN-02": "gold: os dois números com a origem de cada um; a regra aprovada diz nada na silver",
    "SEG-02": "nada na silver: a auditoria de acesso usa o login; modelar a retaguarda é decisão do cliente",
    "SEG-03": "gold: o último acesso é derivado da trilha, não do campo",
}

_TABELA_NO_SQL = re.compile(r"\b([a-z_]+)\.([a-z_]+)\b")


def tabelas_lidas(derivacao: Derivacao) -> set[str]:
    """As tabelas `modulo.tabela` que o SQL da derivação cita (para o teste da linhagem)."""
    return {f"{m}.{t}" for m, t in _TABELA_NO_SQL.findall(derivacao.sql)}


def por_tabela() -> dict[str, list[tuple[Regra, Derivacao]]]:
    """As derivações agrupadas pela tabela que recebe as colunas, na ordem de `REGRAS`."""
    grupos: dict[str, list[tuple[Regra, Derivacao]]] = {}
    for regra in REGRAS:
        for derivacao in regra.derivacoes:
            grupos.setdefault(derivacao.tabela, []).append((regra, derivacao))
    return grupos


def preparar(con: duckdb.DuckDBPyConnection, referencia: object) -> None:
    """Deixa a conexão pronta para as regras: a data de referência, as funções e o catálogo
    `regra`, onde cada derivação é materializada."""
    con.execute("SET VARIABLE referencia = CAST(? AS DATE)", [referencia])
    for macro in MACROS:
        con.execute(macro)
    anexados = {
        linha[0] for linha in con.execute("SELECT database_name FROM duckdb_databases()").fetchall()
    }
    if "regra" not in anexados:
        con.execute("ATTACH ':memory:' AS regra")


def derivar(con: duckdb.DuckDBPyConnection, regra: Regra, derivacao: Derivacao) -> str:
    """Materializa a derivação em `regra.<nome>` e devolve o nome qualificado."""
    alvo = f"regra.{regra.nome(derivacao)}"
    con.execute(f"CREATE OR REPLACE TABLE {alvo} AS {derivacao.sql}")  # noqa: S608 # nosec B608
    return alvo
