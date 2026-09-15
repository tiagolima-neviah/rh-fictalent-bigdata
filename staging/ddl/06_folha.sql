-- folha · o custo por cabeça (7 tabelas)
-- Do evento de folha ao rateio que leva o custo de cada pessoa até o posto onde ela
-- trabalhou: é o rateio que torna a margem por cliente possível.
USE folha;

CREATE TABLE IF NOT EXISTS evento_folha (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo          VARCHAR(10)     NOT NULL,
  descricao       VARCHAR(100)    NOT NULL,
  tipo            VARCHAR(10)     NOT NULL COMMENT 'PROVENTO, DESCONTO, ENCARGO ou PROVISAO',
  fl_incide_inss  BOOLEAN         NOT NULL DEFAULT FALSE,
  fl_incide_fgts  BOOLEAN         NOT NULL DEFAULT FALSE,
  fl_incide_ir    BOOLEAN         NOT NULL DEFAULT FALSE,
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_evento_folha_codigo (codigo),
  KEY ix_evento_folha_atualizado_em (atualizado_em),
  CONSTRAINT ck_evento_folha_tipo CHECK (tipo IN ('PROVENTO', 'DESCONTO', 'ENCARGO', 'PROVISAO'))
) COMMENT='Cerca de 30 eventos: salário, adicional noturno, HE 50 e 100, DSR, INSS, FGTS, VT, VR';

CREATE TABLE IF NOT EXISTS beneficio (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo        VARCHAR(10)     NOT NULL,
  nome          VARCHAR(80)     NOT NULL,
  tipo          VARCHAR(6)      NOT NULL COMMENT 'VT, VR, VA ou PLANO',
  valor_padrao  DECIMAL(14,2)   NOT NULL,
  desconto_pct  DECIMAL(7,4)    NOT NULL DEFAULT 0 COMMENT 'parte descontada do colaborador',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_beneficio_codigo (codigo),
  KEY ix_beneficio_atualizado_em (atualizado_em),
  CONSTRAINT ck_beneficio_tipo CHECK (tipo IN ('VT', 'VR', 'VA', 'PLANO'))
) COMMENT='Benefícios por convenção';

CREATE TABLE IF NOT EXISTS folha_competencia (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  competencia      DATE            NOT NULL COMMENT 'primeiro dia do mês',
  filial_id        BIGINT UNSIGNED NOT NULL,
  dt_fechamento    DATE            NULL,
  status           VARCHAR(8)      NOT NULL COMMENT 'ABERTA, FECHADA ou REABERTA',
  total_proventos  DECIMAL(14,2)   NOT NULL DEFAULT 0,
  total_descontos  DECIMAL(14,2)   NOT NULL DEFAULT 0,
  total_encargos   DECIMAL(14,2)   NOT NULL DEFAULT 0,
  criado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_folha_competencia_filial (competencia, filial_id),
  KEY ix_folha_competencia_atualizado_em (atualizado_em),
  CONSTRAINT fk_folha_competencia_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id),
  CONSTRAINT ck_folha_competencia_status CHECK (status IN ('ABERTA', 'FECHADA', 'REABERTA'))
) COMMENT='O fechamento mensal da folha por filial';

CREATE TABLE IF NOT EXISTS folha_item (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  folha_competencia_id BIGINT UNSIGNED NOT NULL,
  colaborador_id       BIGINT UNSIGNED NOT NULL,
  contrato_trabalho_id BIGINT UNSIGNED NOT NULL,
  evento_id            BIGINT UNSIGNED NOT NULL,
  referencia           DECIMAL(10,2)   NULL COMMENT 'base do evento: horas, dias, percentual',
  valor                DECIMAL(14,2)   NOT NULL COMMENT '[LGPD:pessoal] remuneração individual',
  criado_em            DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_folha_item_colaborador (colaborador_id),
  KEY ix_folha_item_atualizado_em (atualizado_em),
  CONSTRAINT fk_folha_item_competencia FOREIGN KEY (folha_competencia_id) REFERENCES folha_competencia (id),
  CONSTRAINT fk_folha_item_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_folha_item_contrato_trabalho FOREIGN KEY (contrato_trabalho_id) REFERENCES pessoas.contrato_trabalho (id),
  CONSTRAINT fk_folha_item_evento FOREIGN KEY (evento_id) REFERENCES evento_folha (id)
) COMMENT='Cerca de 860 mil: uma linha por pessoa e evento em cada competência';

CREATE TABLE IF NOT EXISTS provisao (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  competencia      DATE            NOT NULL COMMENT 'primeiro dia do mês',
  colaborador_id   BIGINT UNSIGNED NOT NULL,
  tipo             VARCHAR(16)     NOT NULL COMMENT 'DECIMO_TERCEIRO, FERIAS ou ENCARGOS',
  valor_mes        DECIMAL(14,2)   NOT NULL,
  saldo_acumulado  DECIMAL(14,2)   NOT NULL,
  criado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_provisao_competencia_colaborador_tipo (competencia, colaborador_id, tipo),
  KEY ix_provisao_atualizado_em (atualizado_em),
  CONSTRAINT fk_provisao_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT ck_provisao_tipo CHECK (tipo IN ('DECIMO_TERCEIRO', 'FERIAS', 'ENCARGOS'))
) COMMENT='Cerca de 114 mil: a provisão aperta a margem exatamente no mês de maior receita';

CREATE TABLE IF NOT EXISTS colaborador_beneficio (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id  BIGINT UNSIGNED NOT NULL,
  beneficio_id    BIGINT UNSIGNED NOT NULL,
  valor           DECIMAL(14,2)   NOT NULL,
  vigencia_inicio DATE            NOT NULL,
  vigencia_fim    DATE            NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_colaborador_beneficio_atualizado_em (atualizado_em),
  CONSTRAINT fk_colaborador_beneficio_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_colaborador_beneficio_beneficio FOREIGN KEY (beneficio_id) REFERENCES beneficio (id)
) COMMENT='Quem recebe o quê, e desde quando';

CREATE TABLE IF NOT EXISTS rateio_custo (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  competencia      DATE            NOT NULL COMMENT 'primeiro dia do mês',
  colaborador_id   BIGINT UNSIGNED NOT NULL,
  alocacao_id      BIGINT UNSIGNED NOT NULL,
  centro_custo_id  BIGINT UNSIGNED NOT NULL,
  contrato_id      BIGINT UNSIGNED NOT NULL,
  posto_id         BIGINT UNSIGNED NOT NULL,
  valor_salario    DECIMAL(14,2)   NOT NULL DEFAULT 0,
  valor_encargos   DECIMAL(14,2)   NOT NULL DEFAULT 0,
  valor_provisoes  DECIMAL(14,2)   NOT NULL DEFAULT 0,
  valor_beneficios DECIMAL(14,2)   NOT NULL DEFAULT 0,
  custo_total      DECIMAL(14,2)   NOT NULL DEFAULT 0,
  criado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_rateio_custo_competencia_contrato (competencia, contrato_id),
  KEY ix_rateio_custo_atualizado_em (atualizado_em),
  CONSTRAINT fk_rateio_custo_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_rateio_custo_alocacao FOREIGN KEY (alocacao_id) REFERENCES pessoas.alocacao (id),
  CONSTRAINT fk_rateio_custo_centro_custo FOREIGN KEY (centro_custo_id) REFERENCES cadastro.centro_custo (id),
  CONSTRAINT fk_rateio_custo_contrato FOREIGN KEY (contrato_id) REFERENCES comercial.contrato (id),
  CONSTRAINT fk_rateio_custo_posto FOREIGN KEY (posto_id) REFERENCES comercial.posto (id)
) COMMENT='A tabela que torna a margem por cliente possível: leva o custo de cada pessoa até o posto onde ela trabalhou';
