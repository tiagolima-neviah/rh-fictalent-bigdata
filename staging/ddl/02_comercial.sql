-- comercial · a carteira que gera receita (8 tabelas)
-- O cliente contrata postos, não pessoas: o posto é a unidade de receita.
USE comercial;

CREATE TABLE IF NOT EXISTS cliente (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  razao_social         VARCHAR(160)    NOT NULL,
  nome_fantasia        VARCHAR(120)    NULL,
  cnpj                 CHAR(14)        NOT NULL,
  porte                VARCHAR(10)     NOT NULL COMMENT 'MEI, ME, EPP, MEDIA ou GRANDE',
  setor                VARCHAR(60)     NOT NULL COMMENT 'INDUSTRIA, LOGISTICA, VAREJO, SERVICOS, AGRO',
  municipio_id         BIGINT UNSIGNED NOT NULL,
  endereco_id          BIGINT UNSIGNED NULL,
  dt_primeiro_contrato DATE            NULL,
  origem               VARCHAR(12)     NOT NULL COMMENT 'como o cliente chegou: INDICACAO, PROSPECCAO, LICITACAO, SITE, RETORNO',
  ativo                BOOLEAN         NOT NULL DEFAULT TRUE,
  criado_em            DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_cliente_cnpj (cnpj),
  KEY ix_cliente_atualizado_em (atualizado_em),
  CONSTRAINT fk_cliente_municipio FOREIGN KEY (municipio_id) REFERENCES cadastro.municipio (id),
  CONSTRAINT fk_cliente_endereco FOREIGN KEY (endereco_id) REFERENCES cadastro.endereco (id),
  CONSTRAINT ck_cliente_porte CHECK (porte IN ('MEI', 'ME', 'EPP', 'MEDIA', 'GRANDE')),
  CONSTRAINT ck_cliente_origem CHECK (origem IN ('INDICACAO', 'PROSPECCAO', 'LICITACAO', 'SITE', 'RETORNO'))
) ENCRYPTION='Y' COMMENT='Cerca de 90 clientes ao longo do arco, cerca de 45 ativos hoje';

CREATE TABLE IF NOT EXISTS cliente_contato (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  cliente_id    BIGINT UNSIGNED NOT NULL,
  nome          VARCHAR(120)    NOT NULL COMMENT '[LGPD:pessoal]',
  cargo         VARCHAR(80)     NULL,
  email         VARCHAR(160)    NULL COMMENT '[LGPD:pessoal]',
  telefone      VARCHAR(20)     NULL COMMENT '[LGPD:pessoal]',
  fl_principal  BOOLEAN         NOT NULL DEFAULT FALSE,
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_cliente_contato_atualizado_em (atualizado_em),
  CONSTRAINT fk_cliente_contato_cliente FOREIGN KEY (cliente_id) REFERENCES cliente (id)
) ENCRYPTION='Y' COMMENT='Quem cobra o SLA do outro lado';

CREATE TABLE IF NOT EXISTS contrato (
  id                       BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  numero                   VARCHAR(20)       NOT NULL,
  cliente_id               BIGINT UNSIGNED   NOT NULL,
  tipo_servico             VARCHAR(15)       NOT NULL COMMENT 'TEMPORARIO, TERCEIRIZACAO, RECRUTAMENTO ou TREINAMENTO',
  filial_id                BIGINT UNSIGNED   NOT NULL,
  centro_custo_id          BIGINT UNSIGNED   NOT NULL,
  dt_assinatura            DATE              NOT NULL,
  vigencia_inicio          DATE              NOT NULL,
  vigencia_fim             DATE              NULL COMMENT 'NULL = prazo indeterminado',
  prazo_pagamento_dias     SMALLINT UNSIGNED NOT NULL DEFAULT 30,
  indice_reajuste          VARCHAR(20)       NULL COMMENT 'IPCA, INPC, CONVENCAO',
  garantia_reposicao_dias  SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'prazo para repor um colaborador sem custo',
  status                   VARCHAR(10)       NOT NULL COMMENT 'ATIVO, SUSPENSO ou ENCERRADO. O sistema real guarda status e vigência; a auditoria confere se batem',
  dt_encerramento          DATE              NULL,
  motivo_encerramento_id   BIGINT UNSIGNED   NULL COMMENT 'responde se o cliente saiu por mercado ou por serviço',
  criado_em                DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em            DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_contrato_numero (numero),
  KEY ix_contrato_atualizado_em (atualizado_em),
  CONSTRAINT fk_contrato_cliente FOREIGN KEY (cliente_id) REFERENCES cliente (id),
  CONSTRAINT fk_contrato_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id),
  CONSTRAINT fk_contrato_centro_custo FOREIGN KEY (centro_custo_id) REFERENCES cadastro.centro_custo (id),
  CONSTRAINT fk_contrato_motivo FOREIGN KEY (motivo_encerramento_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_contrato_tipo CHECK (tipo_servico IN ('TEMPORARIO', 'TERCEIRIZACAO', 'RECRUTAMENTO', 'TREINAMENTO')),
  CONSTRAINT ck_contrato_status CHECK (status IN ('ATIVO', 'SUSPENSO', 'ENCERRADO'))
) ENCRYPTION='Y' COMMENT='O vínculo comercial; o encerramento com motivo é o que responde por que a empresa perdeu contratos';

-- fecha o ciclo centro_custo <-> contrato (a coluna existe desde 01_cadastro.sql)
SET @existe = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
               WHERE CONSTRAINT_SCHEMA = 'cadastro' AND CONSTRAINT_NAME = 'fk_centro_custo_contrato');
SET @sql = IF(@existe = 0,
  'ALTER TABLE cadastro.centro_custo ADD CONSTRAINT fk_centro_custo_contrato FOREIGN KEY (contrato_id) REFERENCES comercial.contrato (id)',
  'SELECT 1');
PREPARE fk_ciclo FROM @sql; EXECUTE fk_ciclo; DEALLOCATE PREPARE fk_ciclo;

CREATE TABLE IF NOT EXISTS contrato_aditivo (
  id                   BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  contrato_id          BIGINT UNSIGNED   NOT NULL,
  numero               SMALLINT UNSIGNED NOT NULL,
  tipo                 VARCHAR(12)       NOT NULL COMMENT 'PRORROGACAO, REAJUSTE ou ESCOPO',
  dt_assinatura        DATE              NOT NULL,
  vigencia_nova        DATE              NULL,
  percentual_reajuste  DECIMAL(7,4)      NULL,
  criado_em            DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_contrato_aditivo_numero (contrato_id, numero),
  KEY ix_contrato_aditivo_atualizado_em (atualizado_em),
  CONSTRAINT fk_contrato_aditivo_contrato FOREIGN KEY (contrato_id) REFERENCES contrato (id),
  CONSTRAINT ck_contrato_aditivo_tipo CHECK (tipo IN ('PRORROGACAO', 'REAJUSTE', 'ESCOPO'))
) ENCRYPTION='Y' COMMENT='A linha do tempo do contrato: prorrogações, reajustes e mudanças de escopo';

CREATE TABLE IF NOT EXISTS posto (
  id              BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  contrato_id     BIGINT UNSIGNED   NOT NULL,
  funcao_id       BIGINT UNSIGNED   NOT NULL,
  quantidade      SMALLINT UNSIGNED NOT NULL COMMENT 'posições contratadas neste posto',
  turno           VARCHAR(12)       NOT NULL COMMENT 'MANHA, TARDE, NOITE, COMERCIAL ou REVEZAMENTO',
  escala_id       BIGINT UNSIGNED   NOT NULL,
  endereco_id     BIGINT UNSIGNED   NOT NULL COMMENT 'local de trabalho',
  vigencia_inicio DATE              NOT NULL,
  vigencia_fim    DATE              NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_posto_atualizado_em (atualizado_em),
  CONSTRAINT fk_posto_contrato FOREIGN KEY (contrato_id) REFERENCES contrato (id),
  CONSTRAINT fk_posto_funcao FOREIGN KEY (funcao_id) REFERENCES cadastro.funcao (id),
  CONSTRAINT fk_posto_escala FOREIGN KEY (escala_id) REFERENCES cadastro.escala (id),
  CONSTRAINT fk_posto_endereco FOREIGN KEY (endereco_id) REFERENCES cadastro.endereco (id),
  CONSTRAINT ck_posto_turno CHECK (turno IN ('MANHA', 'TARDE', 'NOITE', 'COMERCIAL', 'REVEZAMENTO'))
) ENCRYPTION='Y' COMMENT='A unidade de receita: o cliente contrata postos, não pessoas';

CREATE TABLE IF NOT EXISTS posto_preco (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  posto_id         BIGINT UNSIGNED NOT NULL,
  valor_mensal     DECIMAL(14,2)   NOT NULL,
  valor_hora       DECIMAL(14,2)   NOT NULL,
  markup_aplicado  DECIMAL(7,4)    NOT NULL COMMENT 'multiplicador sobre o custo estimado',
  vigencia_inicio  DATE            NOT NULL,
  vigencia_fim     DATE            NULL COMMENT 'NULL = vigente',
  criado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_posto_preco_atualizado_em (atualizado_em),
  CONSTRAINT fk_posto_preco_posto FOREIGN KEY (posto_id) REFERENCES posto (id)
) ENCRYPTION='Y' COMMENT='Preço do posto com vigência própria, para o reajuste não reescrever o passado';

CREATE TABLE IF NOT EXISTS sla_contrato (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contrato_id    BIGINT UNSIGNED NOT NULL,
  indicador      VARCHAR(15)     NOT NULL COMMENT 'TIME_TO_FILL, REPOSICAO ou ABSENTEISMO',
  meta_valor     DECIMAL(10,2)   NOT NULL,
  unidade        VARCHAR(20)     NOT NULL COMMENT 'DIAS ou PCT',
  penalidade_pct DECIMAL(7,4)    NOT NULL DEFAULT 0,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_sla_contrato_indicador (contrato_id, indicador),
  KEY ix_sla_contrato_atualizado_em (atualizado_em),
  CONSTRAINT fk_sla_contrato_contrato FOREIGN KEY (contrato_id) REFERENCES contrato (id),
  CONSTRAINT ck_sla_indicador CHECK (indicador IN ('TIME_TO_FILL', 'REPOSICAO', 'ABSENTEISMO'))
) ENCRYPTION='Y' COMMENT='Metas contratuais: é o que permite dizer se o cliente saiu por mercado ou por serviço';

CREATE TABLE IF NOT EXISTS contrato_ocorrencia (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  contrato_id    BIGINT UNSIGNED NOT NULL,
  posto_id       BIGINT UNSIGNED NULL,
  dt_ocorrencia  DATE            NOT NULL,
  tipo           VARCHAR(15)     NOT NULL COMMENT 'RECLAMACAO, ELOGIO, ADVERTENCIA ou AVISO_RESCISAO',
  descricao      VARCHAR(500)    NULL,
  motivo_id      BIGINT UNSIGNED NULL,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_contrato_ocorrencia_data (contrato_id, dt_ocorrencia),
  KEY ix_contrato_ocorrencia_atualizado_em (atualizado_em),
  CONSTRAINT fk_contrato_ocorrencia_contrato FOREIGN KEY (contrato_id) REFERENCES contrato (id),
  CONSTRAINT fk_contrato_ocorrencia_posto FOREIGN KEY (posto_id) REFERENCES posto (id),
  CONSTRAINT fk_contrato_ocorrencia_motivo FOREIGN KEY (motivo_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_contrato_ocorrencia_tipo CHECK (tipo IN ('RECLAMACAO', 'ELOGIO', 'ADVERTENCIA', 'AVISO_RESCISAO'))
) ENCRYPTION='Y' COMMENT='A curva de reclamações que antecede a saída do cliente em 6 a 9 meses';
