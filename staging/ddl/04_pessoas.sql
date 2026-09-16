-- pessoas · quem foi admitido e onde está (8 tabelas)
-- O candidato depois de admitido, o vínculo CLT com prazo legal e a alocação no posto:
-- headcount, ocupação, dias descobertos e custo por contrato saem daqui.
USE pessoas;

CREATE TABLE IF NOT EXISTS colaborador (
  id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  candidato_id          BIGINT UNSIGNED NULL COMMENT 'o vínculo com o funil permite medir o custo de conversão',
  matricula             VARCHAR(12)     NOT NULL,
  nome                  VARCHAR(160)    NOT NULL COMMENT '[LGPD:pessoal]',
  cpf                   CHAR(11)        NOT NULL COMMENT '[LGPD:pessoal]',
  dt_nascimento         DATE            NOT NULL COMMENT '[LGPD:pessoal]',
  municipio_id          BIGINT UNSIGNED NOT NULL,
  endereco_id           BIGINT UNSIGNED NULL COMMENT '[LGPD:pessoal]',
  pis                   CHAR(11)        NULL COMMENT '[LGPD:pessoal]',
  dt_admissao_primeira  DATE            NOT NULL,
  ativo                 BOOLEAN         NOT NULL DEFAULT TRUE,
  criado_em             DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em         DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_colaborador_matricula (matricula),
  UNIQUE KEY uq_colaborador_cpf (cpf),
  UNIQUE KEY uq_colaborador_candidato (candidato_id),
  KEY ix_colaborador_atualizado_em (atualizado_em),
  CONSTRAINT fk_colaborador_candidato FOREIGN KEY (candidato_id) REFERENCES ats.candidato (id),
  CONSTRAINT fk_colaborador_municipio FOREIGN KEY (municipio_id) REFERENCES cadastro.municipio (id),
  CONSTRAINT fk_colaborador_endereco FOREIGN KEY (endereco_id) REFERENCES cadastro.endereco (id)
) ENCRYPTION='Y' COMMENT='O candidato depois de admitido. Uma pessoa, uma matrícula, vários contratos de trabalho ao longo do tempo';

CREATE TABLE IF NOT EXISTS colaborador_documento (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id BIGINT UNSIGNED NOT NULL,
  tipo           VARCHAR(12)     NOT NULL COMMENT 'RG, CTPS, TITULO, RESERVISTA ou CNH',
  numero         VARCHAR(30)     NOT NULL COMMENT '[LGPD:pessoal]',
  orgao          VARCHAR(30)     NULL,
  dt_emissao     DATE            NULL,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_colaborador_documento_atualizado_em (atualizado_em),
  CONSTRAINT fk_colaborador_documento_colaborador FOREIGN KEY (colaborador_id) REFERENCES colaborador (id),
  CONSTRAINT ck_colaborador_documento_tipo CHECK (tipo IN ('RG', 'CTPS', 'TITULO', 'RESERVISTA', 'CNH'))
) ENCRYPTION='Y' COMMENT='Documentação da admissão';

CREATE TABLE IF NOT EXISTS dependente (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id BIGINT UNSIGNED NOT NULL,
  nome           VARCHAR(160)    NOT NULL COMMENT '[LGPD:pessoal]',
  parentesco     VARCHAR(10)     NOT NULL COMMENT 'FILHO, CONJUGE, ENTEADO, PAI ou MAE',
  dt_nascimento  DATE            NOT NULL COMMENT '[LGPD:pessoal]',
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_dependente_atualizado_em (atualizado_em),
  CONSTRAINT fk_dependente_colaborador FOREIGN KEY (colaborador_id) REFERENCES colaborador (id),
  CONSTRAINT ck_dependente_parentesco CHECK (parentesco IN ('FILHO', 'CONJUGE', 'ENTEADO', 'PAI', 'MAE'))
) ENCRYPTION='Y' COMMENT='Dependentes: salário-família e IR na folha';

CREATE TABLE IF NOT EXISTS contrato_trabalho (
  id                  BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  colaborador_id      BIGINT UNSIGNED   NOT NULL,
  tipo                VARCHAR(12)       NOT NULL COMMENT 'TEMPORARIO, EFETIVO ou TERCEIRIZADO',
  funcao_id           BIGINT UNSIGNED   NOT NULL,
  filial_id           BIGINT UNSIGNED   NOT NULL,
  dt_admissao         DATE              NOT NULL,
  dt_prevista_termino DATE              NULL COMMENT 'só para temporário',
  dt_rescisao         DATE              NULL,
  salario_base        DECIMAL(14,2)     NOT NULL,
  escala_id           BIGINT UNSIGNED   NOT NULL,
  prazo_legal_dias    SMALLINT UNSIGNED NULL COMMENT 'temporário: 180 dias, mais 90 com prorrogação. Prazo estourado sem prorrogação é irregularidade',
  status              VARCHAR(10)       NOT NULL COMMENT 'ATIVO ou ENCERRADO',
  criado_em           DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em       DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_contrato_trabalho_admissao (dt_admissao),
  KEY ix_contrato_trabalho_atualizado_em (atualizado_em),
  CONSTRAINT fk_contrato_trabalho_colaborador FOREIGN KEY (colaborador_id) REFERENCES colaborador (id),
  CONSTRAINT fk_contrato_trabalho_funcao FOREIGN KEY (funcao_id) REFERENCES cadastro.funcao (id),
  CONSTRAINT fk_contrato_trabalho_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id),
  CONSTRAINT fk_contrato_trabalho_escala FOREIGN KEY (escala_id) REFERENCES cadastro.escala (id),
  CONSTRAINT ck_contrato_trabalho_tipo CHECK (tipo IN ('TEMPORARIO', 'EFETIVO', 'TERCEIRIZADO')),
  CONSTRAINT ck_contrato_trabalho_status CHECK (status IN ('ATIVO', 'ENCERRADO'))
) ENCRYPTION='Y' COMMENT='O vínculo CLT: o prazo legal do temporário mora aqui';

CREATE TABLE IF NOT EXISTS contrato_trabalho_prorrogacao (
  id                   BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  contrato_trabalho_id BIGINT UNSIGNED   NOT NULL,
  dt_assinatura        DATE              NOT NULL,
  dt_novo_termino      DATE              NOT NULL,
  dias_adicionais      SMALLINT UNSIGNED NOT NULL,
  criado_em            DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_contrato_trabalho_prorrogacao_atualizado_em (atualizado_em),
  CONSTRAINT fk_prorrogacao_contrato_trabalho FOREIGN KEY (contrato_trabalho_id) REFERENCES contrato_trabalho (id)
) ENCRYPTION='Y' COMMENT='A prorrogação legal do temporário; sua ausência com prazo estourado é irregularidade';

CREATE TABLE IF NOT EXISTS alocacao (
  id                        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id            BIGINT UNSIGNED NOT NULL,
  contrato_trabalho_id      BIGINT UNSIGNED NOT NULL,
  posto_id                  BIGINT UNSIGNED NOT NULL,
  dt_inicio                 DATE            NOT NULL,
  dt_fim                    DATE            NULL COMMENT 'NULL = alocado hoje',
  motivo_fim_id             BIGINT UNSIGNED NULL,
  substituindo_alocacao_id  BIGINT UNSIGNED NULL COMMENT 'quando esta alocação repõe outra (garantia de reposição)',
  criado_em                 DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em             DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_alocacao_posto_periodo (posto_id, dt_inicio, dt_fim),
  KEY ix_alocacao_atualizado_em (atualizado_em),
  CONSTRAINT fk_alocacao_colaborador FOREIGN KEY (colaborador_id) REFERENCES colaborador (id),
  CONSTRAINT fk_alocacao_contrato_trabalho FOREIGN KEY (contrato_trabalho_id) REFERENCES contrato_trabalho (id),
  CONSTRAINT fk_alocacao_posto FOREIGN KEY (posto_id) REFERENCES comercial.posto (id),
  CONSTRAINT fk_alocacao_motivo FOREIGN KEY (motivo_fim_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT fk_alocacao_substituida FOREIGN KEY (substituindo_alocacao_id) REFERENCES alocacao (id)
) ENCRYPTION='Y' COMMENT='A tabela mais importante do banco: headcount, ocupação, dias descobertos e custo por contrato saem dela';

CREATE TABLE IF NOT EXISTS afastamento (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  colaborador_id BIGINT UNSIGNED NOT NULL,
  tipo           VARCHAR(10)     NOT NULL COMMENT 'ATESTADO, ACIDENTE, LICENCA ou SUSPENSAO',
  dt_inicio      DATE            NOT NULL,
  dt_fim         DATE            NULL COMMENT 'NULL = afastado hoje',
  motivo_id      BIGINT UNSIGNED NULL,
  cid_grupo      VARCHAR(10)     NULL COMMENT '[LGPD:sensivel] grupo da CID, dado de saúde',
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_afastamento_atualizado_em (atualizado_em),
  CONSTRAINT fk_afastamento_colaborador FOREIGN KEY (colaborador_id) REFERENCES colaborador (id),
  CONSTRAINT fk_afastamento_motivo FOREIGN KEY (motivo_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_afastamento_tipo CHECK (tipo IN ('ATESTADO', 'ACIDENTE', 'LICENCA', 'SUSPENSAO'))
) ENCRYPTION='Y' COMMENT='Absenteísmo e vínculo com acidente';

CREATE TABLE IF NOT EXISTS desligamento (
  id                   BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  contrato_trabalho_id BIGINT UNSIGNED   NOT NULL,
  dt_desligamento      DATE              NOT NULL,
  tipo                 VARCHAR(20)       NOT NULL COMMENT 'VOLUNTARIO, INVOLUNTARIO, FIM_CONTRATO ou EFETIVACAO_CLIENTE',
  motivo_id            BIGINT UNSIGNED   NOT NULL,
  dias_aviso_previo    SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  valor_rescisao       DECIMAL(14,2)     NOT NULL DEFAULT 0,
  dt_homologacao       DATE              NULL,
  criado_em            DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em        DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_desligamento_contrato_trabalho (contrato_trabalho_id),
  KEY ix_desligamento_data (dt_desligamento),
  KEY ix_desligamento_atualizado_em (atualizado_em),
  CONSTRAINT fk_desligamento_contrato_trabalho FOREIGN KEY (contrato_trabalho_id) REFERENCES contrato_trabalho (id),
  CONSTRAINT fk_desligamento_motivo FOREIGN KEY (motivo_id) REFERENCES cadastro.motivo (id),
  CONSTRAINT ck_desligamento_tipo CHECK (tipo IN ('VOLUNTARIO', 'INVOLUNTARIO', 'FIM_CONTRATO', 'EFETIVACAO_CLIENTE'))
) ENCRYPTION='Y' COMMENT='Turnover por tipo; a efetivação pelo cliente é receita e perda ao mesmo tempo';
