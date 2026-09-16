-- treinamento · turmas com validade (5 tabelas)
-- NR-06, NR-11, NR-35 e cursos vendidos: o certificado tem prazo, e prazo vira alerta.
USE treinamento;

CREATE TABLE IF NOT EXISTS curso (
  id              BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  codigo          VARCHAR(10)       NOT NULL,
  nome            VARCHAR(120)      NOT NULL,
  tipo            VARCHAR(15)       NOT NULL COMMENT 'NR, TECNICO ou COMPORTAMENTAL',
  carga_horaria   DECIMAL(5,1)      NOT NULL,
  validade_meses  SMALLINT UNSIGNED NULL COMMENT 'NULL = não vence',
  criado_em       DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_curso_codigo (codigo),
  KEY ix_curso_atualizado_em (atualizado_em),
  CONSTRAINT ck_curso_tipo CHECK (tipo IN ('NR', 'TECNICO', 'COMPORTAMENTAL'))
) ENCRYPTION='Y' COMMENT='Catálogo de cursos, com validade quando a norma exige reciclagem';

CREATE TABLE IF NOT EXISTS curso_funcao (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  curso_id        BIGINT UNSIGNED NOT NULL,
  funcao_id       BIGINT UNSIGNED NOT NULL,
  fl_obrigatorio  BOOLEAN         NOT NULL DEFAULT TRUE,
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_curso_funcao (curso_id, funcao_id),
  KEY ix_curso_funcao_atualizado_em (atualizado_em),
  CONSTRAINT fk_curso_funcao_curso FOREIGN KEY (curso_id) REFERENCES curso (id),
  CONSTRAINT fk_curso_funcao_funcao FOREIGN KEY (funcao_id) REFERENCES cadastro.funcao (id)
) ENCRYPTION='Y' COMMENT='Quais treinamentos são exigidos para qual função';

CREATE TABLE IF NOT EXISTS turma (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  curso_id       BIGINT UNSIGNED NOT NULL,
  filial_id      BIGINT UNSIGNED NOT NULL,
  cliente_id     BIGINT UNSIGNED NULL COMMENT 'preenchido quando o treinamento é vendido ao cliente',
  dt_inicio      DATE            NOT NULL,
  dt_fim         DATE            NOT NULL,
  instrutor      VARCHAR(120)    NULL,
  custo_total    DECIMAL(14,2)   NOT NULL DEFAULT 0,
  fornecedor_id  BIGINT UNSIGNED NULL COMMENT 'quando a turma é comprada de terceiro',
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_turma_atualizado_em (atualizado_em),
  CONSTRAINT fk_turma_curso FOREIGN KEY (curso_id) REFERENCES curso (id),
  CONSTRAINT fk_turma_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id),
  CONSTRAINT fk_turma_cliente FOREIGN KEY (cliente_id) REFERENCES comercial.cliente (id),
  CONSTRAINT fk_turma_fornecedor FOREIGN KEY (fornecedor_id) REFERENCES financeiro.fornecedor (id)
) ENCRYPTION='Y' COMMENT='Turma interna ou treinamento vendido ao cliente';

CREATE TABLE IF NOT EXISTS turma_participante (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  turma_id        BIGINT UNSIGNED NOT NULL,
  colaborador_id  BIGINT UNSIGNED NOT NULL,
  presenca_pct    DECIMAL(5,2)    NOT NULL DEFAULT 0,
  fl_aprovado     BOOLEAN         NOT NULL DEFAULT FALSE,
  nota            DECIMAL(4,1)    NULL,
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_turma_participante (turma_id, colaborador_id),
  KEY ix_turma_participante_atualizado_em (atualizado_em),
  CONSTRAINT fk_turma_participante_turma FOREIGN KEY (turma_id) REFERENCES turma (id),
  CONSTRAINT fk_turma_participante_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id)
) ENCRYPTION='Y' COMMENT='Quem fez a turma';

CREATE TABLE IF NOT EXISTS certificado (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  turma_participante_id BIGINT UNSIGNED NOT NULL,
  numero                VARCHAR(30)     NOT NULL,
  dt_emissao            DATE            NOT NULL,
  dt_validade           DATE            NULL COMMENT 'NULL = não vence',
  criado_em             DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em         DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_certificado_participante (turma_participante_id),
  UNIQUE KEY uq_certificado_numero (numero),
  KEY ix_certificado_validade (dt_validade),
  KEY ix_certificado_atualizado_em (atualizado_em),
  CONSTRAINT fk_certificado_participante FOREIGN KEY (turma_participante_id) REFERENCES turma_participante (id)
) ENCRYPTION='Y' COMMENT='O documento com prazo, que é o que vira alerta';
