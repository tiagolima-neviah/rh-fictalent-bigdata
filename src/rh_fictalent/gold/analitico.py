# ruff: noqa: E501
"""SQL analítico sobre a gold: as perguntas do `docs/01` respondidas com funções de janela.

Uma função de janela calcula, para cada linha, um valor que depende das **outras linhas da
mesma janela** sem agrupar: a linha continua inteira e ganha colunas novas (a variação em
relação ao mês anterior, a posição no ranking, a média dos últimos três meses, a soma
acumulada). A janela é definida em três partes, e toda consulta aqui diz as três de propósito:

- `PARTITION BY`: onde a janela recomeça (a filial, o ano, o posto);
- `ORDER BY`: a ordem dentro da partição (o mês); sem ela, "anterior" não existe;
- o quadro (`ROWS BETWEEN ... AND ...`): quantas linhas, em volta da atual, entram no cálculo.
  `ROWS` conta linhas; `RANGE` conta valores (um intervalo de datas, por exemplo). O padrão,
  quando há `ORDER BY` e não se diz o quadro, é `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT
  ROW`, que é o acumulado, e que trata empates no `ORDER BY` como uma linha só.

Cada `Consulta` declara a pergunta que responde, a afirmação ou o indicador de onde ela vem,
o SQL e as janelas que usa, explicadas uma a uma. O SQL lê as views de
`lake.consulta.abrir_gold` (`gold.<tabela>`) e é o mesmo que roda no notebook
`notebooks/gold/01_sql_analitico.ipynb`, onde cada resultado ganha uma Nota Técnica.

A semântica é a do SQL padrão (SQL:2003), que o DuckDB implementa; o mesmo texto roda no
Postgres do warehouse (card 7.5) com duas trocas de sintaxe (`quantile_cont` e `//`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb
    import pandas as pd


@dataclass(frozen=True)
class Consulta:
    nome: str
    pergunta: str
    origem: str  # a afirmação (D1 a D6, A1) ou o indicador do docs/01 que a consulta serve
    sql: str
    janelas: tuple[str, ...]  # cada função de janela usada, com a partição, a ordem e o quadro


SERIE_DA_FILIAL = Consulta(
    "serie_da_filial",
    "Como cada filial cresceu mês a mês, em receita, pessoas, clientes e vagas, e quando parou?",
    "D1 (cresceu até 2024; depois, em quê?)",
    """
    WITH serie AS (
      SELECT r.filial_id, f.nome AS filial, r.mes_id, r.faturamento, r.resultado,
             r.pessoas_alocadas, r.clientes_ativos, r.vagas_abertas
      FROM gold.fato_resultado_mes r JOIN gold.dim_filial f ON f.id = r.filial_id
      WHERE NOT r.mes_parcial)  -- o mês parcial ainda não tem fatura: entraria como queda falsa
    SELECT filial, mes_id, faturamento,
           -- o mês anterior da mesma filial: LAG anda uma linha para trás na ordem da janela
           faturamento - LAG(faturamento) OVER filial_no_tempo AS variacao_mensal,
           -- doze linhas para trás é o mesmo mês do ano anterior, porque a série não tem buraco
           faturamento / NULLIF(LAG(faturamento, 12) OVER filial_no_tempo, 0) - 1 AS variacao_anual,
           -- o quadro de três linhas (a atual e as duas anteriores) é a média móvel trimestral
           AVG(faturamento) OVER (filial_no_tempo ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS media_movel_3m,
           -- a partição por ano faz a soma recomeçar em janeiro; a ordem faz dela um acumulado
           SUM(faturamento) OVER (PARTITION BY filial_id, mes_id // 100 ORDER BY mes_id) AS acumulado_no_ano,
           resultado, pessoas_alocadas,
           pessoas_alocadas - LAG(pessoas_alocadas) OVER filial_no_tempo AS variacao_de_pessoas,
           clientes_ativos, vagas_abertas
    FROM serie
    WINDOW filial_no_tempo AS (PARTITION BY filial_id ORDER BY mes_id)
    ORDER BY filial_id, mes_id
    """,
    (
        "LAG(faturamento) e LAG(faturamento, 12): partição por filial, ordem por mês; o valor da linha 1 ou 12 posições antes; nulo no começo da série",
        "AVG(...) ROWS BETWEEN 2 PRECEDING AND CURRENT ROW: a janela nomeada (`WINDOW filial_no_tempo`) ganha um quadro de três linhas",
        "SUM(...) PARTITION BY filial, ano ORDER BY mês: sem quadro explícito, o quadro é o acumulado até a linha atual",
    ),
)

PARETO_DE_CLIENTES = Consulta(
    "pareto_de_clientes",
    "Quais clientes carregam a receita de cada ano, com que margem, e quantos fazem 80% dela?",
    "D2 (margem por cliente e filial) e A1 (margem pelo porte do cliente)",
    """
    WITH por_cliente AS (
      SELECT p.ano, p.cliente_id, c.nome_fantasia AS cliente, c.porte,
             SUM(p.receita) AS receita, SUM(p.margem) AS margem
      FROM gold.fato_posto_mes p JOIN gold.dim_cliente c ON c.id = p.cliente_id
      GROUP BY ALL HAVING SUM(p.receita) > 0)
    SELECT ano, cliente, porte, receita, margem, margem / receita AS margem_pct,
           -- a posição do cliente na receita do ano; RANK repete a posição em empate e pula a seguinte
           RANK() OVER (PARTITION BY ano ORDER BY receita DESC) AS posicao,
           -- a partição sem ordem é o total do ano, repetido em cada linha: dá a participação
           receita / SUM(receita) OVER (PARTITION BY ano) AS participacao,
           -- a soma acumulada na ordem da receita, dividida pelo total, é a curva de Pareto
           SUM(receita) OVER (PARTITION BY ano ORDER BY receita DESC ROWS UNBOUNDED PRECEDING)
             / SUM(receita) OVER (PARTITION BY ano) AS participacao_acumulada,
           COUNT(*) OVER (PARTITION BY ano) AS clientes_no_ano,
           -- NTILE reparte os clientes do ano em quatro grupos de tamanho igual pela margem
           NTILE(4) OVER (PARTITION BY ano ORDER BY margem / receita DESC) AS quartil_de_margem
    FROM por_cliente
    ORDER BY ano, posicao
    """,
    (
        "RANK() PARTITION BY ano ORDER BY receita DESC: a posição; empate repete e pula (1, 1, 3)",
        "SUM(receita) OVER (PARTITION BY ano): sem ordem, o quadro é a partição inteira, o total do ano em toda linha",
        "SUM(receita) ... ORDER BY receita DESC ROWS UNBOUNDED PRECEDING: o acumulado dos maiores até a linha, para a curva 80/20",
        "NTILE(4) PARTITION BY ano ORDER BY margem percentual DESC: o quartil de margem de cada cliente",
    ),
)

O_AVISO_E_O_FIM = Consulta(
    "o_aviso_e_o_fim",
    "Em cada contrato encerrado, quando veio o primeiro aviso de rescisão, quantas reclamações houve nos seis meses finais, e a ocupação caiu antes do fim?",
    "D3 (a perda de contratos começou antes do que a diretoria diz?)",
    """
    WITH encerrados AS (
      SELECT k.contrato_id, d.numero, c.nome_fantasia AS cliente, f.data AS fim
      FROM gold.fato_contrato k JOIN gold.dim_contrato d ON d.id = k.contrato_id
      JOIN gold.dim_cliente c ON c.id = k.cliente_id JOIN gold.dim_data f ON f.id = k.data_encerramento_id
      WHERE k.encerrado),
    ocorrencias AS (
      SELECT o.contrato_id, d.data, o.aviso_de_rescisao, o.reclamacao
      FROM gold.fato_ocorrencia o JOIN gold.dim_data d ON d.id = o.data_id),
    avisos AS (
      SELECT e.contrato_id, MIN(o.data) AS primeiro_aviso
      FROM encerrados e LEFT JOIN ocorrencias o ON o.contrato_id = e.contrato_id AND o.aviso_de_rescisao
      GROUP BY 1),
    reclamacoes AS (
      SELECT e.contrato_id,
             COUNT(*) FILTER (WHERE o.data > e.fim - INTERVAL 6 MONTH AND o.data <= e.fim) AS reclamacoes_6m_finais,
             COUNT(*) FILTER (WHERE o.data <= e.fim - INTERVAL 6 MONTH) AS reclamacoes_antes
      FROM encerrados e LEFT JOIN ocorrencias o ON o.contrato_id = e.contrato_id AND o.reclamacao
      GROUP BY 1),
    ocupacao AS (  -- a ocupação do contrato, mês a mês, nos meses inteiros de vigência
      SELECT contrato_id, mes_id,
             SUM(pessoa_dias_alocados) / NULLIF(SUM(posicao_dias_contratados), 0) AS ocupacao
      FROM gold.fato_posto_mes WHERE dias_vigentes > 0 GROUP BY 1, 2),
    janelas AS (
      SELECT contrato_id, mes_id,
             -- os seis meses finais: a linha atual e as cinco anteriores
             AVG(ocupacao) OVER (contrato_no_tempo ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) AS ocupacao_6m_finais,
             -- o ano anterior a esses seis meses: da 17ª à 6ª linha antes da atual
             AVG(ocupacao) OVER (contrato_no_tempo ROWS BETWEEN 17 PRECEDING AND 6 PRECEDING) AS ocupacao_12m_anteriores,
             -- numerar do fim para o começo deixa o último mês do contrato com o número 1
             ROW_NUMBER() OVER (PARTITION BY contrato_id ORDER BY mes_id DESC) AS do_fim
      FROM ocupacao
      WINDOW contrato_no_tempo AS (PARTITION BY contrato_id ORDER BY mes_id))
    SELECT e.numero, e.cliente, e.fim, a.primeiro_aviso,
           DATE_DIFF('month', a.primeiro_aviso, e.fim) AS meses_de_antecedencia,
           r.reclamacoes_6m_finais, r.reclamacoes_antes,
           j.ocupacao_12m_anteriores, j.ocupacao_6m_finais,
           j.ocupacao_6m_finais - j.ocupacao_12m_anteriores AS queda_de_ocupacao
    FROM encerrados e LEFT JOIN avisos a USING (contrato_id) LEFT JOIN reclamacoes r USING (contrato_id)
    LEFT JOIN janelas j ON j.contrato_id = e.contrato_id AND j.do_fim = 1
    ORDER BY e.fim
    """,
    (
        "AVG(ocupacao) ROWS BETWEEN 5 PRECEDING AND CURRENT ROW: a média dos seis meses finais, lida na última linha do contrato",
        "AVG(ocupacao) ROWS BETWEEN 17 PRECEDING AND 6 PRECEDING: um quadro que termina antes da linha atual, para comparar com o período anterior",
        "ROW_NUMBER() PARTITION BY contrato ORDER BY mês DESC: numera do fim; `do_fim = 1` escolhe o último mês sem subconsulta",
    ),
)

_SERIE_DO_MERCADO = """
    mercado AS (  -- o segmento (grupo 78) nos três municípios do caso, somados
      SELECT m.mes_id, SUM(m.admissoes) AS admissoes_mercado, SUM(m.desligamentos) AS desligamentos_mercado, SUM(m.saldo) AS saldo_mercado
      FROM gold.fato_mercado_mes m JOIN gold.dim_escopo_mercado e ON e.id = m.escopo_mercado_id
      WHERE e.nivel = 'município' AND e.segmento_da_fictalent GROUP BY 1),
    vagas AS (
      SELECT data_abertura_id // 100 AS mes_id, COUNT(*) AS vagas_abertas,
             quantile_cont(dias_ate_preencher, 0.5) AS dias_ate_preencher_mediana
      FROM gold.fato_vaga GROUP BY 1),
    reclamacoes AS (SELECT data_id // 100 AS mes_id, COUNT(*) AS reclamacoes FROM gold.fato_ocorrencia WHERE reclamacao GROUP BY 1),
    perdas AS (SELECT data_encerramento_id // 100 AS mes_id, COUNT(*) AS contratos_encerrados FROM gold.fato_contrato WHERE encerrado GROUP BY 1),
    serie AS (
      SELECT m.mes_id, m.admissoes_mercado, m.desligamentos_mercado, m.saldo_mercado,
             COALESCE(v.vagas_abertas, 0) AS vagas_abertas, v.dias_ate_preencher_mediana,
             COALESCE(r.reclamacoes, 0) AS reclamacoes, COALESCE(p.contratos_encerrados, 0) AS contratos_encerrados
      FROM mercado m LEFT JOIN vagas v USING (mes_id) LEFT JOIN reclamacoes r USING (mes_id) LEFT JOIN perdas p USING (mes_id))
"""

MERCADO_E_SERVICO = Consulta(
    "mercado_e_servico",
    "Mês a mês, o que o mercado da região fez (CAGED) e o que a Fictalent fez ao mesmo tempo: vagas, tempo de preenchimento, reclamações, contratos perdidos?",
    "D4 (a queda é do mercado?)",
    f"""
    WITH {_SERIE_DO_MERCADO}
    SELECT mes_id, admissoes_mercado, desligamentos_mercado, saldo_mercado,
           -- a média móvel tira o serrilhado mensal do CAGED e deixa a tendência
           AVG(saldo_mercado) OVER (no_tempo ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS saldo_mercado_3m,
           -- o saldo de três e de seis meses antes, lado a lado com o mês: é o que a defasagem compara
           LAG(saldo_mercado, 3) OVER no_tempo AS saldo_mercado_3m_antes,
           LAG(saldo_mercado, 6) OVER no_tempo AS saldo_mercado_6m_antes,
           vagas_abertas, dias_ate_preencher_mediana, reclamacoes, contratos_encerrados
    FROM serie
    WINDOW no_tempo AS (ORDER BY mes_id)
    ORDER BY mes_id
    """,
    (
        "AVG(saldo_mercado) ROWS BETWEEN 2 PRECEDING AND CURRENT ROW, sem partição: uma série só, a região inteira",
        "LAG(saldo_mercado, 3) e LAG(saldo_mercado, 6): o mercado de três e seis meses antes, na mesma linha do mês",
    ),
)

_DEFASAGENS = range(7)

DEFASAGEM_DO_MERCADO = Consulta(
    "defasagem_do_mercado",
    "Com quantos meses de atraso o serviço acompanha o mercado (a correlação entre o saldo do CAGED de k meses antes e cada série da Fictalent, para k de 0 a 6)?",
    "D4 (a defasagem medida em meses)",
    f"""
    WITH {_SERIE_DO_MERCADO}
    SELECT defasagem_meses,
           CORR(saldo_defasado, reclamacoes) AS corr_reclamacoes,
           CORR(saldo_defasado, dias_ate_preencher_mediana) AS corr_dias_ate_preencher,
           CORR(saldo_defasado, contratos_encerrados) AS corr_contratos_encerrados,
           CORR(saldo_defasado, vagas_abertas) AS corr_vagas_abertas,
           COUNT(saldo_defasado) AS meses_comparados
    FROM (
    """
    + "\n      UNION ALL\n".join(
        f"      SELECT {k} AS defasagem_meses, LAG(saldo_mercado, {k}) OVER (ORDER BY mes_id) AS saldo_defasado, "
        "reclamacoes, dias_ate_preencher_mediana, contratos_encerrados, vagas_abertas FROM serie"
        for k in _DEFASAGENS
    )
    + """
    )
    GROUP BY defasagem_meses
    ORDER BY defasagem_meses
    """,
    (
        "LAG(saldo_mercado, k) OVER (ORDER BY mes_id), uma vez para cada k de 0 a 6: o deslocamento é constante por exigência do SQL, por isso são sete seleções unidas",
        "CORR(...) é agregação, não janela: ela recebe o par (mercado deslocado, série do mês) e resume os meses num número por defasagem",
    ),
)

FUNIL_POR_TRIMESTRE = Consulta(
    "funil_por_trimestre",
    "A cada trimestre, quantas candidaturas chegaram a cada etapa, quantas viraram admissão, em quantos dias, e como isso se compara ao mesmo trimestre do ano anterior?",
    "D5 (contratar mais assistente resolveria?)",
    """
    WITH por_trimestre AS (
      SELECT data_inscricao_id // 10000 AS ano, (data_inscricao_id // 100 % 100 - 1) // 3 + 1 AS trimestre,
             COUNT(*) AS candidaturas,
             COUNT(*) FILTER (WHERE chegou_a_entrevista_interna) AS entrevistadas,
             COUNT(*) FILTER (WHERE chegou_ao_encaminhamento) AS encaminhadas,
             COUNT(*) FILTER (WHERE aprovada) AS aprovadas,
             COUNT(*) FILTER (WHERE admitida) AS admitidas,
             COUNT(*) FILTER (WHERE aprovada_sem_admissao) AS aprovadas_que_nao_comecaram,
             quantile_cont(dias_no_funil, 0.5) FILTER (WHERE NOT em_andamento) AS dias_no_funil_mediana
      FROM gold.fato_candidatura GROUP BY 1, 2)
    SELECT ano, trimestre, candidaturas, entrevistadas, encaminhadas, aprovadas, admitidas, aprovadas_que_nao_comecaram,
           entrevistadas / candidaturas AS conversao_da_triagem,
           aprovadas / NULLIF(entrevistadas, 0) AS conversao_da_entrevista,
           admitidas / NULLIF(aprovadas, 0) AS conversao_da_admissao,
           admitidas / candidaturas AS conversao_total,
           -- quatro trimestres para trás é o mesmo trimestre do ano anterior
           admitidas / candidaturas - LAG(admitidas / candidaturas, 4) OVER no_tempo AS variacao_anual_da_conversao,
           dias_no_funil_mediana,
           dias_no_funil_mediana - LAG(dias_no_funil_mediana, 4) OVER no_tempo AS variacao_anual_dos_dias,
           -- a posição do trimestre entre todos, pela rapidez do funil
           RANK() OVER (ORDER BY dias_no_funil_mediana) AS posicao_pela_rapidez
    FROM por_trimestre
    WINDOW no_tempo AS (ORDER BY ano, trimestre)
    ORDER BY ano, trimestre
    """,
    (
        "LAG(x, 4) OVER (ORDER BY ano, trimestre): o mesmo trimestre do ano anterior, numa série trimestral sem buraco",
        "RANK() OVER (ORDER BY dias_no_funil_mediana): a posição sem partição, entre todos os trimestres",
    ),
)

INFORMADO_CONTRA_APURADO = Consulta(
    "informado_contra_apurado",
    "Mês a mês e por filial, quanto o faturamento informado pela gerência diverge do apurado na operação, desde quando, e por quantos meses seguidos?",
    "D6 (depois de 2022 os relatórios pararam de bater)",
    """
    WITH mensal AS (
      SELECT r.filial_id, f.nome AS filial, r.mes_id, r.faturamento, r.faturamento_informado, r.diferenca_faturamento,
             ABS(r.diferenca_faturamento) / NULLIF(r.faturamento, 0) AS divergencia_pct
      FROM gold.fato_resultado_mes r JOIN gold.dim_filial f ON f.id = r.filial_id
      WHERE r.informado),
    marcada AS (SELECT *, divergencia_pct > 0.01 AS diverge FROM mensal),
    ilhas AS (  -- gaps-and-islands: a diferença entre as duas numerações é constante dentro de uma sequência
      SELECT *,
             ROW_NUMBER() OVER (PARTITION BY filial_id ORDER BY mes_id)
             - ROW_NUMBER() OVER (PARTITION BY filial_id, diverge ORDER BY mes_id) AS ilha
      FROM marcada)
    SELECT filial, mes_id, faturamento, faturamento_informado, diferenca_faturamento, divergencia_pct, diverge,
           -- quantos meses divergentes até aqui: a soma acumulada de um indicador 0/1
           SUM(CASE WHEN diverge THEN 1 ELSE 0 END) OVER (PARTITION BY filial_id ORDER BY mes_id) AS meses_divergentes_ate_aqui,
           SUM(diferenca_faturamento) OVER (PARTITION BY filial_id ORDER BY mes_id) AS diferenca_acumulada,
           -- a ilha vira partição: o tamanho e o começo da sequência em que a linha está
           COUNT(*) OVER (PARTITION BY filial_id, diverge, ilha) AS meses_seguidos,
           MIN(mes_id) OVER (PARTITION BY filial_id, diverge, ilha) AS inicio_da_sequencia
    FROM ilhas
    ORDER BY filial_id, mes_id
    """,
    (
        "ROW_NUMBER() PARTITION BY filial ORDER BY mês menos ROW_NUMBER() PARTITION BY filial, diverge ORDER BY mês: o rótulo da ilha (gaps-and-islands)",
        "SUM(indicador) PARTITION BY filial ORDER BY mês: o acumulado de meses divergentes",
        "COUNT(*) e MIN(mes_id) PARTITION BY filial, diverge, ilha: o tamanho e o início da sequência, sem agrupar a tabela",
    ),
)

COORTE_DE_90_DIAS = Consulta(
    "coorte_de_90_dias",
    "De quem foi admitido em cada mês, que parte saiu cedo (pedido ou dispensa em até 90 dias), e como essa taxa anda numa média de doze meses?",
    "indicador de rotatividade (turnover em 90 dias) e D4",
    """
    WITH horizonte AS (SELECT MAX(d.data) AS dia FROM gold.fato_vinculo v JOIN gold.dim_data d ON d.id = v.data_admissao_id),
    coortes AS (
      SELECT v.data_admissao_id // 100 AS mes_de_admissao, COUNT(*) AS admitidos,
             -- saída precoce é a voluntária ou involuntária; o fim de contrato e a efetivação não são falha
             COUNT(*) FILTER (WHERE v.saiu_em_ate_90_dias AND v.tipo_de_desligamento IN ('VOLUNTARIO', 'INVOLUNTARIO')) AS sairam_em_90_dias,
             COUNT(*) FILTER (WHERE v.saiu_em_ate_90_dias) AS encerrados_em_90_dias,
             -- a coorte só está completa quando o 90º dia do último admitido já passou
             MAX(d.data) + INTERVAL 90 DAY <= (SELECT dia FROM horizonte) AS coorte_completa
      FROM gold.fato_vinculo v JOIN gold.dim_data d ON d.id = v.data_admissao_id
      GROUP BY 1)
    SELECT mes_de_admissao, admitidos, sairam_em_90_dias, encerrados_em_90_dias, coorte_completa,
           sairam_em_90_dias / admitidos AS taxa_90_dias,
           -- a taxa ponderada dos últimos doze meses: soma das saídas sobre soma dos admitidos no mesmo quadro
           SUM(sairam_em_90_dias) OVER doze_meses / SUM(admitidos) OVER doze_meses AS taxa_90_dias_12m,
           sairam_em_90_dias / admitidos - LAG(sairam_em_90_dias / admitidos, 12) OVER (ORDER BY mes_de_admissao) AS variacao_anual
    FROM coortes
    WINDOW doze_meses AS (ORDER BY mes_de_admissao ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
    ORDER BY mes_de_admissao
    """,
    (
        "SUM(...) OVER doze_meses, com ROWS BETWEEN 11 PRECEDING AND CURRENT ROW: duas somas no mesmo quadro, divididas depois, para a taxa ponderada (a média das taxas daria peso igual a meses de tamanhos diferentes)",
        "LAG(taxa, 12) OVER (ORDER BY mês): a mesma coorte um ano antes",
    ),
)

POSTOS_DESCOBERTOS_EM_SEQUENCIA = Consulta(
    "postos_descobertos_em_sequencia",
    "Quais postos ficaram abaixo de 90% de ocupação por mais meses seguidos, em que cliente, e quantos posição-dias faltaram nessa sequência?",
    "indicador de dias de posto descoberto e D2",
    """
    WITH meses AS (
      SELECT posto_id, cliente_id, mes_id, taxa_de_ocupacao, posicao_dias_descobertos,
             -- só o mês inteiro conta como descoberto: o mês de entrada ou saída do posto é parcial por natureza
             dias_vigentes >= 28 AND NOT mes_parcial AND taxa_de_ocupacao < 0.9 AS descoberto
      FROM gold.fato_posto_mes),
    ilhas AS (  -- gaps-and-islands: meses descobertos consecutivos recebem o mesmo rótulo
      SELECT *,
             ROW_NUMBER() OVER (PARTITION BY posto_id ORDER BY mes_id)
             - ROW_NUMBER() OVER (PARTITION BY posto_id, descoberto ORDER BY mes_id) AS ilha
      FROM meses),
    sequencias AS (
      SELECT posto_id, cliente_id, MIN(mes_id) AS inicio, MAX(mes_id) AS fim, COUNT(*) AS meses_seguidos,
             SUM(posicao_dias_descobertos) AS posicao_dias_descobertos, AVG(taxa_de_ocupacao) AS ocupacao_media
      FROM ilhas WHERE descoberto GROUP BY posto_id, cliente_id, ilha)
    SELECT c.nome_fantasia AS cliente, s.posto_id, s.inicio, s.fim, s.meses_seguidos, s.posicao_dias_descobertos, s.ocupacao_media,
           -- DENSE_RANK não pula posições em empate: a terceira maior sequência é sempre a posição 3
           DENSE_RANK() OVER (ORDER BY s.meses_seguidos DESC) AS posicao
    FROM sequencias s JOIN gold.dim_cliente c ON c.id = s.cliente_id
    ORDER BY s.meses_seguidos DESC, s.posicao_dias_descobertos DESC, s.inicio
    """,
    (
        "ROW_NUMBER() PARTITION BY posto menos ROW_NUMBER() PARTITION BY posto, descoberto: o rótulo da sequência; a série de meses do posto não tem buraco, condição do truque",
        "DENSE_RANK() OVER (ORDER BY meses_seguidos DESC): a posição sem pulos em empate",
    ),
)

CONSULTAS: tuple[Consulta, ...] = (
    SERIE_DA_FILIAL,
    PARETO_DE_CLIENTES,
    O_AVISO_E_O_FIM,
    MERCADO_E_SERVICO,
    DEFASAGEM_DO_MERCADO,
    FUNIL_POR_TRIMESTRE,
    INFORMADO_CONTRA_APURADO,
    COORTE_DE_90_DIAS,
    POSTOS_DESCOBERTOS_EM_SEQUENCIA,
)


def consulta(nome: str) -> Consulta:
    try:
        return next(c for c in CONSULTAS if c.nome == nome)
    except StopIteration:
        raise KeyError(
            f"consulta desconhecida: {nome}; há {', '.join(c.nome for c in CONSULTAS)}"
        ) from None


def executar(con: duckdb.DuckDBPyConnection, nome: str) -> pd.DataFrame:
    """Roda a consulta sobre as views `gold.<tabela>` da conexão e devolve o resultado."""
    return con.execute(consulta(nome).sql).df()
