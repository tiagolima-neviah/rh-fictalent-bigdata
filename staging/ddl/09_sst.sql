-- sst · saúde, segurança e compliance (6 tabelas)
-- Exames, programas legais, riscos do posto, acidentes e a CAT. ASO vencido com pessoa
-- alocada é o alerta mais caro do painel. Dado de saúde é pessoal sensível.
USE sst;

CREATE TABLE IF NOT EXISTS tipo_exame (
  id                   BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  codigo               VARCHAR(15)       NOT NULL COMMENT 'ADMISSIONAL, PERIODICO, MUDANCA_FUNCAO, RETORNO ou DEMISSIONAL',
  periodicidade_meses  SMALLINT UNSIGNED NULL COMMENT 'só para periódico',
  criado_em            DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_tipo_exame_codigo (codigo),
  KEY ix_tipo_exame_atualizado_em (atualizado_em),
  CONSTRAINT ck_tipo_exame_codigo CHECK (codigo IN ('ADMISSIONAL', 'PERIODICO', 'MUDANCA_FUNCAO', 'RETORNO', 'DEMISSIONAL'))
) ENCRYPTION='Y' COMMENT='Catálogo de tipos de exame ocupacional';

CREATE TABLE IF NOT EXISTS aso (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id  BIGINT UNSIGNED NOT NULL,
  tipo_exame_id   BIGINT UNSIGNED NOT NULL,
  dt_exame        DATE            NOT NULL,
  dt_validade     DATE            NULL,
  resultado       VARCHAR(15)     NOT NULL COMMENT '[LGPD:sensivel] APTO, INAPTO ou APTO_RESTRICAO, dado de saúde',
  medico_crm      VARCHAR(20)     NULL,
  fornecedor_id   BIGINT UNSIGNED NULL,
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_aso_validade (dt_validade),
  KEY ix_aso_atualizado_em (atualizado_em),
  CONSTRAINT fk_aso_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_aso_tipo_exame FOREIGN KEY (tipo_exame_id) REFERENCES tipo_exame (id),
  CONSTRAINT fk_aso_fornecedor FOREIGN KEY (fornecedor_id) REFERENCES financeiro.fornecedor (id),
  CONSTRAINT ck_aso_resultado CHECK (resultado IN ('APTO', 'INAPTO', 'APTO_RESTRICAO'))
) ENCRYPTION='Y' COMMENT='Cerca de 40 mil: ASO vencido com pessoa alocada é o alerta mais caro do painel';

CREATE TABLE IF NOT EXISTS programa_sst (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tipo           VARCHAR(6)      NOT NULL COMMENT 'PGR, PCMSO ou LTCAT',
  cliente_id     BIGINT UNSIGNED NOT NULL,
  contrato_id    BIGINT UNSIGNED NULL,
  dt_elaboracao  DATE            NOT NULL,
  dt_validade    DATE            NOT NULL,
  responsavel    VARCHAR(120)    NULL,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_programa_sst_atualizado_em (atualizado_em),
  CONSTRAINT fk_programa_sst_cliente FOREIGN KEY (cliente_id) REFERENCES comercial.cliente (id),
  CONSTRAINT fk_programa_sst_contrato FOREIGN KEY (contrato_id) REFERENCES comercial.contrato (id),
  CONSTRAINT ck_programa_sst_tipo CHECK (tipo IN ('PGR', 'PCMSO', 'LTCAT'))
) ENCRYPTION='Y' COMMENT='Obrigação legal por cliente e contrato, com validade';

CREATE TABLE IF NOT EXISTS risco_posto (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  posto_id           BIGINT UNSIGNED NOT NULL,
  programa_sst_id    BIGINT UNSIGNED NOT NULL,
  agente_risco       VARCHAR(80)     NOT NULL COMMENT 'RUIDO, POEIRA, ERGONOMICO, QUIMICO, ALTURA',
  grau               VARCHAR(6)      NOT NULL COMMENT 'BAIXO, MEDIO ou ALTO',
  insalubridade_pct  DECIMAL(7,4)    NOT NULL DEFAULT 0,
  fl_periculosidade  BOOLEAN         NOT NULL DEFAULT FALSE,
  criado_em          DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_risco_posto_atualizado_em (atualizado_em),
  CONSTRAINT fk_risco_posto_posto FOREIGN KEY (posto_id) REFERENCES comercial.posto (id),
  CONSTRAINT fk_risco_posto_programa FOREIGN KEY (programa_sst_id) REFERENCES programa_sst (id),
  CONSTRAINT ck_risco_posto_grau CHECK (grau IN ('BAIXO', 'MEDIO', 'ALTO'))
) ENCRYPTION='Y' COMMENT='O adicional que entra na folha vem daqui';

CREATE TABLE IF NOT EXISTS acidente (
  id               BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  colaborador_id   BIGINT UNSIGNED   NOT NULL,
  alocacao_id      BIGINT UNSIGNED   NULL,
  dt_acidente      DATE              NOT NULL,
  tipo             VARCHAR(8)        NOT NULL COMMENT '[LGPD:sensivel] TIPICO, TRAJETO ou DOENCA',
  gravidade        VARCHAR(8)        NOT NULL COMMENT '[LGPD:sensivel] LEVE, MODERADA, GRAVE ou FATAL',
  dias_afastamento SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  afastamento_id   BIGINT UNSIGNED   NULL,
  criado_em        DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_acidente_atualizado_em (atualizado_em),
  CONSTRAINT fk_acidente_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_acidente_alocacao FOREIGN KEY (alocacao_id) REFERENCES pessoas.alocacao (id),
  CONSTRAINT fk_acidente_afastamento FOREIGN KEY (afastamento_id) REFERENCES pessoas.afastamento (id),
  CONSTRAINT ck_acidente_tipo CHECK (tipo IN ('TIPICO', 'TRAJETO', 'DOENCA')),
  CONSTRAINT ck_acidente_gravidade CHECK (gravidade IN ('LEVE', 'MODERADA', 'GRAVE', 'FATAL'))
) ENCRYPTION='Y' COMMENT='Cerca de 2 acidentes por 100 alocados por ano';

CREATE TABLE IF NOT EXISTS cat (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  acidente_id  BIGINT UNSIGNED NOT NULL,
  numero       VARCHAR(30)     NOT NULL,
  dt_emissao   DATE            NOT NULL,
  tipo_cat     VARCHAR(10)     NOT NULL COMMENT 'INICIAL, REABERTURA ou OBITO',
  criado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_cat_numero (numero),
  KEY ix_cat_atualizado_em (atualizado_em),
  CONSTRAINT fk_cat_acidente FOREIGN KEY (acidente_id) REFERENCES acidente (id),
  CONSTRAINT ck_cat_tipo CHECK (tipo_cat IN ('INICIAL', 'REABERTURA', 'OBITO'))
) ENCRYPTION='Y' COMMENT='A Comunicação de Acidente de Trabalho, obrigatória';
