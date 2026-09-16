-- ponto · o dia a dia de quem está em campo (5 tabelas)
-- A marcação é o registro bruto do relógio (4 por dia); o apontamento é o dia
-- consolidado que a folha consome. Marcação faltante e duplicada são sujeira de origem.
USE ponto;

CREATE TABLE IF NOT EXISTS escala_colaborador (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id  BIGINT UNSIGNED NOT NULL,
  escala_id       BIGINT UNSIGNED NOT NULL,
  vigencia_inicio DATE            NOT NULL,
  vigencia_fim    DATE            NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_escala_colaborador_atualizado_em (atualizado_em),
  CONSTRAINT fk_escala_colaborador_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_escala_colaborador_escala FOREIGN KEY (escala_id) REFERENCES cadastro.escala (id)
) ENCRYPTION='Y' COMMENT='A jornada esperada muda quando a pessoa troca de posto';

CREATE TABLE IF NOT EXISTS marcacao (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id BIGINT UNSIGNED NOT NULL,
  data           DATE            NOT NULL,
  hora           TIME            NOT NULL,
  tipo           VARCHAR(20)     NOT NULL COMMENT 'ENTRADA, SAIDA_INTERVALO, RETORNO_INTERVALO ou SAIDA',
  origem         VARCHAR(8)      NOT NULL COMMENT 'RELOGIO, APP ou MANUAL',
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_marcacao_colaborador_data (colaborador_id, data),
  KEY ix_marcacao_atualizado_em (atualizado_em),
  CONSTRAINT fk_marcacao_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT ck_marcacao_tipo CHECK (tipo IN ('ENTRADA', 'SAIDA_INTERVALO', 'RETORNO_INTERVALO', 'SAIDA')),
  CONSTRAINT ck_marcacao_origem CHECK (origem IN ('RELOGIO', 'APP', 'MANUAL'))
) ENCRYPTION='Y' COMMENT='Cerca de 4,4 milhões: o registro bruto do relógio, 4 por dia. Sem UNIQUE de propósito: batida duplicada é sujeira de origem';

CREATE TABLE IF NOT EXISTS apontamento (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id     BIGINT UNSIGNED NOT NULL,
  alocacao_id        BIGINT UNSIGNED NULL COMMENT 'NULL quando o dia não tem posto (retaguarda, entre alocações)',
  data               DATE            NOT NULL,
  horas_trabalhadas  DECIMAL(5,2)    NOT NULL DEFAULT 0,
  horas_extras       DECIMAL(5,2)    NOT NULL DEFAULT 0,
  horas_noturnas     DECIMAL(5,2)    NOT NULL DEFAULT 0,
  status             VARCHAR(8)      NOT NULL COMMENT 'NORMAL, FALTA, ATESTADO, FERIADO ou FOLGA',
  criado_em          DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_apontamento_colaborador_data (colaborador_id, data),
  KEY ix_apontamento_data (data),
  KEY ix_apontamento_atualizado_em (atualizado_em),
  CONSTRAINT fk_apontamento_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_apontamento_alocacao FOREIGN KEY (alocacao_id) REFERENCES pessoas.alocacao (id),
  CONSTRAINT ck_apontamento_status CHECK (status IN ('NORMAL', 'FALTA', 'ATESTADO', 'FERIADO', 'FOLGA'))
) ENCRYPTION='Y' COMMENT='Cerca de 1,1 milhão: o dia consolidado a partir das marcações; é o que a folha consome';

CREATE TABLE IF NOT EXISTS ocorrencia_ponto (
  id             BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  apontamento_id BIGINT UNSIGNED   NOT NULL,
  tipo           VARCHAR(20)       NOT NULL COMMENT 'FALTA_JUSTIFICADA, FALTA_INJUSTIFICADA, ATRASO ou SAIDA_ANTECIPADA',
  minutos        SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  justificativa  VARCHAR(300)      NULL,
  criado_em      DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_ocorrencia_ponto_atualizado_em (atualizado_em),
  CONSTRAINT fk_ocorrencia_ponto_apontamento FOREIGN KEY (apontamento_id) REFERENCES apontamento (id),
  CONSTRAINT ck_ocorrencia_ponto_tipo CHECK (tipo IN ('FALTA_JUSTIFICADA', 'FALTA_INJUSTIFICADA', 'ATRASO', 'SAIDA_ANTECIPADA'))
) ENCRYPTION='Y' COMMENT='Absenteísmo por posto, que é o que o cliente sente';

CREATE TABLE IF NOT EXISTS banco_horas (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id  BIGINT UNSIGNED NOT NULL,
  competencia     DATE            NOT NULL COMMENT 'primeiro dia do mês',
  saldo_anterior  DECIMAL(7,2)    NOT NULL DEFAULT 0,
  creditos        DECIMAL(7,2)    NOT NULL DEFAULT 0,
  debitos         DECIMAL(7,2)    NOT NULL DEFAULT 0,
  saldo_final     DECIMAL(7,2)    NOT NULL DEFAULT 0,
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_banco_horas_colaborador_competencia (colaborador_id, competencia),
  KEY ix_banco_horas_atualizado_em (atualizado_em),
  CONSTRAINT fk_banco_horas_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id)
) ENCRYPTION='Y' COMMENT='Passivo que ninguém enxerga até a rescisão';
