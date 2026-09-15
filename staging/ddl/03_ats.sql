-- ats · o funil de colocação (9 tabelas)
-- Do pedido do cliente à aprovação: um candidato, várias candidaturas, cada passagem
-- de etapa com data. É aqui que moram os duplicados, os CPF inválidos e o no-show.
USE ats;

CREATE TABLE IF NOT EXISTS fonte_candidato (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome          VARCHAR(15)     NOT NULL COMMENT 'INDICACAO, PORTAL, REDES, BANCO_INTERNO ou PRESENCIAL',
  custo_medio   DECIMAL(14,2)   NOT NULL DEFAULT 0 COMMENT 'custo médio por candidato captado',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_fonte_candidato_nome (nome),
  KEY ix_fonte_candidato_atualizado_em (atualizado_em),
  CONSTRAINT ck_fonte_candidato_nome CHECK (nome IN ('INDICACAO', 'PORTAL', 'REDES', 'BANCO_INTERNO', 'PRESENCIAL'))
) COMMENT='De onde o candidato veio: base do custo por contratação por fonte';

CREATE TABLE IF NOT EXISTS etapa_funil (
  id            BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo        VARCHAR(20)      NOT NULL,
  nome          VARCHAR(80)      NOT NULL,
  ordem         TINYINT UNSIGNED NOT NULL,
  criado_em     DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_etapa_funil_codigo (codigo),
  KEY ix_etapa_funil_atualizado_em (atualizado_em)
) COMMENT='Triagem, entrevista interna, encaminhamento, entrevista no cliente, aprovação';

CREATE TABLE IF NOT EXISTS requisicao (
  id                      BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  numero                  VARCHAR(20)       NOT NULL,
  cliente_id              BIGINT UNSIGNED   NOT NULL,
  contrato_id             BIGINT UNSIGNED   NOT NULL,
  posto_id                BIGINT UNSIGNED   NULL,
  quantidade              SMALLINT UNSIGNED NOT NULL,
  dt_abertura             DATE              NOT NULL,
  dt_necessidade          DATE              NOT NULL COMMENT 'quando o cliente precisa da pessoa no posto',
  prioridade              VARCHAR(8)        NOT NULL COMMENT 'BAIXA, NORMAL, ALTA ou URGENTE',
  status                  VARCHAR(15)       NOT NULL COMMENT 'ABERTA, EM_ATENDIMENTO, ATENDIDA ou CANCELADA',
  motivo_cancelamento_id  BIGINT UNSIGNED   NULL,
  criado_em               DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em           DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_requisicao_numero (numero),
  KEY ix_requisicao_atualizado_em (atualizado_em),
  CONSTRAINT fk_requisicao_cliente FOREIGN KEY (cliente_id) REFERENCES comercial.cliente (id),
  CONSTRAINT fk_requisicao_contrato FOREIGN KEY (contrato_id) REFERENCES comercial.contrato (id),
  CONSTRAINT fk_requisicao_posto FOREIGN KEY (posto_id) REFERENCES comercial.posto (id),
  CONSTRAINT fk_requisicao_motivo FOREIGN KEY (motivo_cancelamento_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_requisicao_prioridade CHECK (prioridade IN ('BAIXA', 'NORMAL', 'ALTA', 'URGENTE')),
  CONSTRAINT ck_requisicao_status CHECK (status IN ('ABERTA', 'EM_ATENDIMENTO', 'ATENDIDA', 'CANCELADA'))
) COMMENT='O pedido do cliente: o começo de tudo';

CREATE TABLE IF NOT EXISTS vaga (
  id                   BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  requisicao_id        BIGINT UNSIGNED   NOT NULL,
  codigo               VARCHAR(20)       NOT NULL,
  titulo               VARCHAR(120)      NOT NULL,
  funcao_id            BIGINT UNSIGNED   NOT NULL,
  filial_id            BIGINT UNSIGNED   NOT NULL COMMENT 'filial que atende a vaga',
  quantidade_posicoes  SMALLINT UNSIGNED NOT NULL,
  dt_abertura          DATE              NOT NULL,
  dt_fechamento        DATE              NULL,
  status               VARCHAR(12)       NOT NULL COMMENT 'ABERTA, EM_TRIAGEM, PREENCHIDA ou CANCELADA',
  salario_previsto     DECIMAL(14,2)     NOT NULL,
  criado_em            DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_vaga_codigo (codigo),
  KEY ix_vaga_abertura (dt_abertura),
  KEY ix_vaga_atualizado_em (atualizado_em),
  CONSTRAINT fk_vaga_requisicao FOREIGN KEY (requisicao_id) REFERENCES requisicao (id),
  CONSTRAINT fk_vaga_funcao FOREIGN KEY (funcao_id) REFERENCES cadastro.funcao (id),
  CONSTRAINT fk_vaga_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id),
  CONSTRAINT ck_vaga_status CHECK (status IN ('ABERTA', 'EM_TRIAGEM', 'PREENCHIDA', 'CANCELADA'))
) COMMENT='Cerca de 20 mil vagas no arco; o time-to-fill nasce de dt_abertura e dt_fechamento';

CREATE TABLE IF NOT EXISTS candidato (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome           VARCHAR(160)    NOT NULL COMMENT '[LGPD:pessoal]',
  cpf            CHAR(11)        NULL COMMENT '[LGPD:pessoal] sem UNIQUE de propósito: duplicados e inválidos são sujeira de origem, medida na auditoria',
  dt_nascimento  DATE            NULL COMMENT '[LGPD:pessoal]',
  sexo           CHAR(1)         NULL COMMENT '[LGPD:pessoal] F, M ou N (não informado)',
  municipio_id   BIGINT UNSIGNED NULL,
  telefone       VARCHAR(20)     NULL COMMENT '[LGPD:pessoal]',
  email          VARCHAR(160)    NULL COMMENT '[LGPD:pessoal]',
  escolaridade   VARCHAR(20)     NULL COMMENT 'FUNDAMENTAL, MEDIO, TECNICO, SUPERIOR',
  fonte_id       BIGINT UNSIGNED NOT NULL,
  dt_cadastro    DATE            NOT NULL,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_candidato_cpf (cpf),
  KEY ix_candidato_atualizado_em (atualizado_em),
  CONSTRAINT fk_candidato_municipio FOREIGN KEY (municipio_id) REFERENCES cadastro.municipio (id),
  CONSTRAINT fk_candidato_fonte FOREIGN KEY (fonte_id) REFERENCES fonte_candidato (id),
  CONSTRAINT ck_candidato_sexo CHECK (sexo IN ('F', 'M', 'N'))
) COMMENT='Cerca de 60 mil candidatos; é aqui que moram os duplicados e os CPF inválidos. Prazo de retenção para não contratado definido em cadastro.parametro';

CREATE TABLE IF NOT EXISTS candidato_experiencia (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  candidato_id  BIGINT UNSIGNED NOT NULL,
  empresa       VARCHAR(160)    NOT NULL,
  funcao_id     BIGINT UNSIGNED NULL,
  dt_inicio     DATE            NOT NULL,
  dt_fim        DATE            NULL,
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_candidato_experiencia_atualizado_em (atualizado_em),
  CONSTRAINT fk_candidato_experiencia_candidato FOREIGN KEY (candidato_id) REFERENCES candidato (id),
  CONSTRAINT fk_candidato_experiencia_funcao FOREIGN KEY (funcao_id) REFERENCES cadastro.funcao (id)
) COMMENT='Experiências anteriores: matéria para triagem e para análise de aderência';

CREATE TABLE IF NOT EXISTS candidatura (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  vaga_id               BIGINT UNSIGNED NOT NULL,
  candidato_id          BIGINT UNSIGNED NOT NULL,
  dt_inscricao          DATE            NOT NULL,
  etapa_atual_id        BIGINT UNSIGNED NOT NULL,
  status                VARCHAR(12)     NOT NULL COMMENT 'EM_ANDAMENTO, APROVADA, REPROVADA, DESISTENCIA ou CANCELADA',
  dt_conclusao          DATE            NULL,
  motivo_reprovacao_id  BIGINT UNSIGNED NULL,
  criado_em             DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em         DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_candidatura_candidato (candidato_id),
  KEY ix_candidatura_atualizado_em (atualizado_em),
  CONSTRAINT fk_candidatura_vaga FOREIGN KEY (vaga_id) REFERENCES vaga (id),
  CONSTRAINT fk_candidatura_candidato FOREIGN KEY (candidato_id) REFERENCES candidato (id),
  CONSTRAINT fk_candidatura_etapa FOREIGN KEY (etapa_atual_id) REFERENCES etapa_funil (id),
  CONSTRAINT fk_candidatura_motivo FOREIGN KEY (motivo_reprovacao_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_candidatura_status CHECK (status IN ('EM_ANDAMENTO', 'APROVADA', 'REPROVADA', 'DESISTENCIA', 'CANCELADA'))
) COMMENT='Cerca de 300 mil: a linha do funil. Um candidato, várias candidaturas';

CREATE TABLE IF NOT EXISTS candidatura_etapa (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  candidatura_id BIGINT UNSIGNED NOT NULL,
  etapa_id       BIGINT UNSIGNED NOT NULL,
  dt_entrada     DATETIME(6)     NOT NULL,
  dt_saida       DATETIME(6)     NULL,
  resultado      VARCHAR(10)     NOT NULL DEFAULT 'PENDENTE' COMMENT 'APROVADO, REPROVADO, DESISTIU ou PENDENTE',
  motivo_id      BIGINT UNSIGNED NULL,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_candidatura_etapa_atualizado_em (atualizado_em),
  CONSTRAINT fk_candidatura_etapa_candidatura FOREIGN KEY (candidatura_id) REFERENCES candidatura (id),
  CONSTRAINT fk_candidatura_etapa_etapa FOREIGN KEY (etapa_id) REFERENCES etapa_funil (id),
  CONSTRAINT fk_candidatura_etapa_motivo FOREIGN KEY (motivo_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_candidatura_etapa_resultado CHECK (resultado IN ('APROVADO', 'REPROVADO', 'DESISTIU', 'PENDENTE'))
) COMMENT='Cerca de 750 mil: cada passagem de etapa com data, o que produz conversão e tempo por etapa';

CREATE TABLE IF NOT EXISTS entrevista (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  candidatura_id BIGINT UNSIGNED NOT NULL,
  tipo           VARCHAR(8)      NOT NULL COMMENT 'INTERNA ou CLIENTE',
  dt_agendada    DATETIME(6)     NOT NULL,
  dt_realizada   DATETIME(6)     NULL,
  fl_compareceu  BOOLEAN         NULL COMMENT 'NULL enquanto não aconteceu; FALSE é o no-show',
  usuario_id     BIGINT UNSIGNED NULL COMMENT 'quem conduziu; FK declarada em 10_seguranca.sql',
  resultado      VARCHAR(15)     NULL COMMENT 'APROVADO, REPROVADO, REAGENDAR ou NAO_COMPARECEU',
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_entrevista_atualizado_em (atualizado_em),
  CONSTRAINT fk_entrevista_candidatura FOREIGN KEY (candidatura_id) REFERENCES candidatura (id),
  CONSTRAINT ck_entrevista_tipo CHECK (tipo IN ('INTERNA', 'CLIENTE')),
  CONSTRAINT ck_entrevista_resultado CHECK (resultado IN ('APROVADO', 'REPROVADO', 'REAGENDAR', 'NAO_COMPARECEU'))
) COMMENT='O no-show de entrevista mora aqui';
