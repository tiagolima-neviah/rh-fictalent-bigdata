-- financeiro · receita, títulos e impostos (10 tabelas)
-- A nota do mês, a medição posto a posto, o que entra, o que sai, o imposto apurado
-- conforme o regime vigente e a planilha gerencial carregada no sistema.
USE financeiro;

CREATE TABLE IF NOT EXISTS regime_tributario (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  regime          VARCHAR(16)     NOT NULL COMMENT 'LUCRO_PRESUMIDO ou LUCRO_REAL. Simples é vedado para cessão de mão de obra',
  vigencia_inicio DATE            NOT NULL,
  vigencia_fim    DATE            NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_regime_tributario_atualizado_em (atualizado_em),
  CONSTRAINT ck_regime_tributario_regime CHECK (regime IN ('LUCRO_PRESUMIDO', 'LUCRO_REAL'))
) ENCRYPTION='Y' COMMENT='O regime tributário é parâmetro por competência';

CREATE TABLE IF NOT EXISTS tributo (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo        VARCHAR(10)     NOT NULL COMMENT 'ISS, PIS, COFINS, IRPJ, CSLL',
  descricao     VARCHAR(80)     NOT NULL,
  esfera        VARCHAR(10)     NOT NULL COMMENT 'FEDERAL, ESTADUAL ou MUNICIPAL',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_tributo_codigo (codigo),
  KEY ix_tributo_atualizado_em (atualizado_em),
  CONSTRAINT ck_tributo_esfera CHECK (esfera IN ('FEDERAL', 'ESTADUAL', 'MUNICIPAL'))
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Catálogo de tributos';

CREATE TABLE IF NOT EXISTS aliquota (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tributo_id          BIGINT UNSIGNED NOT NULL,
  municipio_id        BIGINT UNSIGNED NULL COMMENT 'só para ISS, que muda por município',
  aliquota            DECIMAL(7,4)    NOT NULL,
  base_presumida_pct  DECIMAL(7,4)    NULL COMMENT 'base de presunção no lucro presumido',
  vigencia_inicio     DATE            NOT NULL,
  vigencia_fim        DATE            NULL COMMENT 'NULL = vigente',
  criado_em           DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_aliquota_atualizado_em (atualizado_em),
  CONSTRAINT fk_aliquota_tributo FOREIGN KEY (tributo_id) REFERENCES tributo (id),
  CONSTRAINT fk_aliquota_municipio FOREIGN KEY (municipio_id) REFERENCES cadastro.municipio (id)
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Alíquota por tributo, município e vigência: ISS de Atibaia e Bragança difere do de Extrema';

CREATE TABLE IF NOT EXISTS fornecedor (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  razao_social  VARCHAR(160)    NOT NULL,
  cnpj          CHAR(14)        NOT NULL,
  tipo          VARCHAR(12)     NOT NULL COMMENT 'EXAMES, TREINAMENTO, BENEFICIOS ou SERVICOS',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_fornecedor_cnpj (cnpj),
  KEY ix_fornecedor_atualizado_em (atualizado_em),
  CONSTRAINT ck_fornecedor_tipo CHECK (tipo IN ('EXAMES', 'TREINAMENTO', 'BENEFICIOS', 'SERVICOS'))
) ENCRYPTION='Y' COMMENT='A outra ponta do contas a pagar';

CREATE TABLE IF NOT EXISTS fatura (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  numero          VARCHAR(20)     NOT NULL,
  cliente_id      BIGINT UNSIGNED NOT NULL,
  contrato_id     BIGINT UNSIGNED NOT NULL,
  competencia     DATE            NOT NULL COMMENT 'primeiro dia do mês medido',
  dt_emissao      DATE            NOT NULL,
  valor_bruto     DECIMAL(14,2)   NOT NULL,
  valor_impostos  DECIMAL(14,2)   NOT NULL DEFAULT 0,
  valor_liquido   DECIMAL(14,2)   NOT NULL,
  status          VARCHAR(10)     NOT NULL COMMENT 'EMITIDA, EM_ABERTO, QUITADA ou CANCELADA',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_fatura_numero (numero),
  KEY ix_fatura_competencia (competencia),
  KEY ix_fatura_atualizado_em (atualizado_em),
  CONSTRAINT fk_fatura_cliente FOREIGN KEY (cliente_id) REFERENCES comercial.cliente (id),
  CONSTRAINT fk_fatura_contrato FOREIGN KEY (contrato_id) REFERENCES comercial.contrato (id),
  CONSTRAINT ck_fatura_status CHECK (status IN ('EMITIDA', 'EM_ABERTO', 'QUITADA', 'CANCELADA'))
) ENCRYPTION='Y' COMMENT='A nota de serviço do mês';

CREATE TABLE IF NOT EXISTS fatura_item (
  id                    BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  fatura_id             BIGINT UNSIGNED   NOT NULL,
  posto_id              BIGINT UNSIGNED   NOT NULL,
  qtd_dias_trabalhados  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  qtd_faltas            SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  valor_postos          DECIMAL(14,2)     NOT NULL DEFAULT 0,
  valor_horas_extras    DECIMAL(14,2)     NOT NULL DEFAULT 0,
  valor_descontos       DECIMAL(14,2)     NOT NULL DEFAULT 0,
  valor_total           DECIMAL(14,2)     NOT NULL DEFAULT 0,
  criado_em             DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em         DATETIME(6)       NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_fatura_item_atualizado_em (atualizado_em),
  CONSTRAINT fk_fatura_item_fatura FOREIGN KEY (fatura_id) REFERENCES fatura (id),
  CONSTRAINT fk_fatura_item_posto FOREIGN KEY (posto_id) REFERENCES comercial.posto (id)
) ENCRYPTION='Y' COMMENT='Cerca de 52 mil: a medição do mês, posto a posto';

CREATE TABLE IF NOT EXISTS titulo_receber (
  id             BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  fatura_id      BIGINT UNSIGNED  NOT NULL,
  cliente_id     BIGINT UNSIGNED  NOT NULL,
  numero_parcela TINYINT UNSIGNED NOT NULL DEFAULT 1,
  dt_vencimento  DATE             NOT NULL,
  valor          DECIMAL(14,2)    NOT NULL,
  status         VARCHAR(10)      NOT NULL COMMENT 'ABERTO, PAGO, ATRASADO ou CANCELADO',
  dt_pagamento   DATE             NULL,
  valor_pago     DECIMAL(14,2)    NULL,
  criado_em      DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_titulo_receber_fatura_parcela (fatura_id, numero_parcela),
  KEY ix_titulo_receber_vencimento (dt_vencimento),
  KEY ix_titulo_receber_atualizado_em (atualizado_em),
  CONSTRAINT fk_titulo_receber_fatura FOREIGN KEY (fatura_id) REFERENCES fatura (id),
  CONSTRAINT fk_titulo_receber_cliente FOREIGN KEY (cliente_id) REFERENCES comercial.cliente (id),
  CONSTRAINT ck_titulo_receber_status CHECK (status IN ('ABERTO', 'PAGO', 'ATRASADO', 'CANCELADO'))
) ENCRYPTION='Y' COMMENT='Inadimplência e prazo médio de recebimento';

CREATE TABLE IF NOT EXISTS titulo_pagar (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tipo             VARCHAR(12)     NOT NULL COMMENT 'FOLHA, ENCARGOS, IMPOSTOS, FORNECEDOR ou BENEFICIOS',
  fornecedor_id    BIGINT UNSIGNED NULL,
  centro_custo_id  BIGINT UNSIGNED NOT NULL,
  competencia      DATE            NOT NULL COMMENT 'primeiro dia do mês',
  dt_vencimento    DATE            NOT NULL,
  valor            DECIMAL(14,2)   NOT NULL,
  status           VARCHAR(10)     NOT NULL COMMENT 'ABERTO, PAGO, ATRASADO ou CANCELADO',
  dt_pagamento     DATE            NULL,
  criado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_titulo_pagar_competencia (competencia),
  KEY ix_titulo_pagar_atualizado_em (atualizado_em),
  CONSTRAINT fk_titulo_pagar_fornecedor FOREIGN KEY (fornecedor_id) REFERENCES fornecedor (id),
  CONSTRAINT fk_titulo_pagar_centro_custo FOREIGN KEY (centro_custo_id) REFERENCES cadastro.centro_custo (id),
  CONSTRAINT ck_titulo_pagar_tipo CHECK (tipo IN ('FOLHA', 'ENCARGOS', 'IMPOSTOS', 'FORNECEDOR', 'BENEFICIOS')),
  CONSTRAINT ck_titulo_pagar_status CHECK (status IN ('ABERTO', 'PAGO', 'ATRASADO', 'CANCELADO'))
) ENCRYPTION='Y' COMMENT='O que sai';

CREATE TABLE IF NOT EXISTS imposto_apurado (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  competencia      DATE            NOT NULL COMMENT 'primeiro dia do mês',
  tributo_id       BIGINT UNSIGNED NOT NULL,
  municipio_id     BIGINT UNSIGNED NULL COMMENT 'só para ISS',
  base_calculo     DECIMAL(14,2)   NOT NULL,
  aliquota         DECIMAL(7,4)    NOT NULL,
  valor_devido     DECIMAL(14,2)   NOT NULL,
  titulo_pagar_id  BIGINT UNSIGNED NULL,
  criado_em        DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_imposto_apurado_atualizado_em (atualizado_em),
  CONSTRAINT fk_imposto_apurado_tributo FOREIGN KEY (tributo_id) REFERENCES tributo (id),
  CONSTRAINT fk_imposto_apurado_municipio FOREIGN KEY (municipio_id) REFERENCES cadastro.municipio (id),
  CONSTRAINT fk_imposto_apurado_titulo_pagar FOREIGN KEY (titulo_pagar_id) REFERENCES titulo_pagar (id)
) ENCRYPTION='Y' COMMENT='Apuração mês a mês conforme o regime vigente';

CREATE TABLE IF NOT EXISTS consolidado_gerencial (
  id                       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  competencia              DATE            NOT NULL COMMENT 'primeiro dia do mês',
  filial_id                BIGINT UNSIGNED NOT NULL,
  headcount_informado      INT UNSIGNED    NOT NULL,
  vagas_abertas_informado  INT UNSIGNED    NOT NULL,
  faturamento_informado    DECIMAL(14,2)   NOT NULL,
  custo_informado          DECIMAL(14,2)   NOT NULL,
  dt_lancamento            DATE            NOT NULL,
  origem                   VARCHAR(10)     NOT NULL DEFAULT 'PLANILHA',
  criado_em                DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em            DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_consolidado_gerencial_competencia_filial (competencia, filial_id),
  KEY ix_consolidado_gerencial_atualizado_em (atualizado_em),
  CONSTRAINT fk_consolidado_gerencial_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id),
  CONSTRAINT ck_consolidado_gerencial_origem CHECK (origem IN ('PLANILHA'))
) ENCRYPTION='Y' COMMENT='A planilha gerencial carregada no sistema: diverge da operação a partir de 2022 e é o achado central da auditoria';
