-- cadastro · as regras do jogo (12 tabelas)
-- Filiais, municípios, funções, convenções, escalas, motivos e parâmetros: a base de
-- toda dimensão do warehouse. Quase tudo aqui é catálogo (dezenas de linhas).
USE cadastro;

CREATE TABLE IF NOT EXISTS regiao (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome          VARCHAR(60)     NOT NULL,
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_regiao_nome (nome),
  KEY ix_regiao_atualizado_em (atualizado_em)
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Agrupamento comercial de municípios (eixo Fernão Dias, Vale, etc.)';

CREATE TABLE IF NOT EXISTS municipio (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome          VARCHAR(120)    NOT NULL,
  uf            CHAR(2)         NOT NULL,
  regiao_id     BIGINT UNSIGNED NOT NULL,
  codigo_ibge   CHAR(7)         NOT NULL COMMENT 'código IBGE de 7 dígitos, chave para a API de municípios',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_municipio_ibge (codigo_ibge),
  KEY ix_municipio_atualizado_em (atualizado_em),
  CONSTRAINT fk_municipio_regiao FOREIGN KEY (regiao_id) REFERENCES regiao (id)
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Município: usado por cliente, posto, colaborador e pela alíquota de ISS';

CREATE TABLE IF NOT EXISTS endereco (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  logradouro    VARCHAR(160)    NOT NULL COMMENT '[LGPD:pessoal] quando o endereço é de colaborador',
  numero        VARCHAR(20)     NULL,
  complemento   VARCHAR(60)     NULL,
  bairro        VARCHAR(80)     NULL,
  municipio_id  BIGINT UNSIGNED NOT NULL,
  cep           CHAR(8)         NULL COMMENT '[LGPD:pessoal] quando o endereço é de colaborador',
  tipo          VARCHAR(20)     NOT NULL COMMENT 'FILIAL, CLIENTE, LOCAL_TRABALHO ou COLABORADOR',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_endereco_atualizado_em (atualizado_em),
  CONSTRAINT fk_endereco_municipio FOREIGN KEY (municipio_id) REFERENCES municipio (id),
  CONSTRAINT ck_endereco_tipo CHECK (tipo IN ('FILIAL', 'CLIENTE', 'LOCAL_TRABALHO', 'COLABORADOR'))
) ENCRYPTION='Y' COMMENT='Endereços de filial, cliente, local de trabalho e colaborador';

CREATE TABLE IF NOT EXISTS filial (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo        VARCHAR(10)     NOT NULL,
  nome          VARCHAR(80)     NOT NULL,
  tipo          VARCHAR(10)     NOT NULL COMMENT 'MATRIZ ou FILIAL',
  endereco_id   BIGINT UNSIGNED NOT NULL,
  dt_abertura   DATE            NOT NULL,
  ativo         BOOLEAN         NOT NULL DEFAULT TRUE,
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_filial_codigo (codigo),
  KEY ix_filial_atualizado_em (atualizado_em),
  CONSTRAINT fk_filial_endereco FOREIGN KEY (endereco_id) REFERENCES endereco (id),
  CONSTRAINT ck_filial_tipo CHECK (tipo IN ('MATRIZ', 'FILIAL'))
) ENCRYPTION='Y' COMMENT='As três unidades: Atibaia (matriz), Bragança Paulista e Extrema';

CREATE TABLE IF NOT EXISTS motivo (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  tipo          VARCHAR(30)     NOT NULL COMMENT 'a que evento o motivo se aplica',
  codigo        VARCHAR(20)     NOT NULL,
  descricao     VARCHAR(160)    NOT NULL,
  grupo         VARCHAR(40)     NULL COMMENT 'agrupamento analítico (MERCADO, SERVICO, PESSOAL, LEGAL)',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_motivo_tipo_codigo (tipo, codigo),
  KEY ix_motivo_atualizado_em (atualizado_em),
  CONSTRAINT ck_motivo_tipo CHECK (tipo IN ('DESLIGAMENTO', 'REPROVACAO', 'CANCELAMENTO_VAGA', 'PERDA_CONTRATO', 'AFASTAMENTO', 'FIM_ALOCACAO', 'OCORRENCIA'))
) ENCRYPTION='Y' COMMENT='Catálogo único de motivos: desligamento, reprovação, cancelamento de vaga, perda de contrato, afastamento';

CREATE TABLE IF NOT EXISTS funcao (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo             VARCHAR(10)     NOT NULL,
  nome               VARCHAR(100)    NOT NULL,
  cbo                CHAR(6)         NULL COMMENT 'Classificação Brasileira de Ocupações',
  familia            VARCHAR(60)     NULL COMMENT 'PRODUCAO, LOGISTICA, ADMINISTRATIVO, COMERCIO',
  nivel              VARCHAR(20)     NULL COMMENT 'AUXILIAR, OPERADOR, TECNICO, LIDER',
  fl_insalubre       BOOLEAN         NOT NULL DEFAULT FALSE,
  fl_periculosidade  BOOLEAN         NOT NULL DEFAULT FALSE,
  criado_em          DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_funcao_codigo (codigo),
  KEY ix_funcao_atualizado_em (atualizado_em)
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Cerca de 40 funções: auxiliar de produção, operador de empilhadeira, conferente, repositor';

CREATE TABLE IF NOT EXISTS convencao_coletiva (
  id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  sindicato       VARCHAR(160)     NOT NULL,
  municipio_id    BIGINT UNSIGNED  NOT NULL,
  mes_data_base   TINYINT UNSIGNED NOT NULL COMMENT 'mês do reajuste anual (1 a 12)',
  vigencia_inicio DATE             NOT NULL,
  vigencia_fim    DATE             NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_convencao_coletiva_atualizado_em (atualizado_em),
  CONSTRAINT fk_convencao_municipio FOREIGN KEY (municipio_id) REFERENCES municipio (id),
  CONSTRAINT ck_convencao_mes CHECK (mes_data_base BETWEEN 1 AND 12)
) ENCRYPTION='Y' COMMENT='Convenção coletiva por sindicato e município: explica por que o mesmo cargo custa diferente por cidade';

CREATE TABLE IF NOT EXISTS piso_salarial (
  id                           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  convencao_id                 BIGINT UNSIGNED NOT NULL,
  funcao_id                    BIGINT UNSIGNED NOT NULL,
  valor_piso                   DECIMAL(14,2)   NOT NULL,
  adicional_insalubridade_pct  DECIMAL(7,4)    NOT NULL DEFAULT 0,
  vigencia_inicio              DATE            NOT NULL,
  vigencia_fim                 DATE            NULL COMMENT 'NULL = vigente',
  criado_em                    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em                DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_piso_salarial_atualizado_em (atualizado_em),
  CONSTRAINT fk_piso_convencao FOREIGN KEY (convencao_id) REFERENCES convencao_coletiva (id),
  CONSTRAINT fk_piso_funcao FOREIGN KEY (funcao_id) REFERENCES funcao (id)
) ENCRYPTION='Y' COMMENT='Piso por convenção e função, com vigência: a base do custo por cabeça';

CREATE TABLE IF NOT EXISTS feriado (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  data          DATE            NOT NULL,
  nome          VARCHAR(100)    NOT NULL,
  abrangencia   VARCHAR(10)     NOT NULL COMMENT 'NACIONAL, ESTADUAL ou MUNICIPAL',
  municipio_id  BIGINT UNSIGNED NULL COMMENT 'só para feriado municipal',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_feriado_data (data),
  KEY ix_feriado_atualizado_em (atualizado_em),
  CONSTRAINT fk_feriado_municipio FOREIGN KEY (municipio_id) REFERENCES municipio (id),
  CONSTRAINT ck_feriado_abrangencia CHECK (abrangencia IN ('NACIONAL', 'ESTADUAL', 'MUNICIPAL'))
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Feriados (vêm da BrasilAPI e dos municípios): quase todo indicador é medido em dias úteis';

CREATE TABLE IF NOT EXISTS escala (
  id              BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo          VARCHAR(10)      NOT NULL COMMENT '5x2, 6x1, 12x36',
  descricao       VARCHAR(100)     NOT NULL,
  horas_semanais  DECIMAL(5,2)     NOT NULL,
  dias_ciclo      TINYINT UNSIGNED NOT NULL COMMENT 'tamanho do ciclo em dias',
  criado_em       DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)      NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_escala_codigo (codigo),
  KEY ix_escala_atualizado_em (atualizado_em)
) ENCRYPTION='Y' COMMENT='[LGPD:publica] Escalas de trabalho: definem a jornada esperada no ponto';

CREATE TABLE IF NOT EXISTS parametro (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  chave           VARCHAR(60)     NOT NULL COMMENT 'ex.: PRAZO_TEMPORARIO_DIAS, MARKUP_PADRAO, ALERTA_ASO_DIAS',
  valor           VARCHAR(200)    NOT NULL,
  vigencia_inicio DATE            NOT NULL,
  vigencia_fim    DATE            NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_parametro_chave_vigencia (chave, vigencia_inicio),
  KEY ix_parametro_atualizado_em (atualizado_em)
) ENCRYPTION='Y' COMMENT='Parâmetros com vigência: prazos legais (180 e 90 dias), markup padrão, limites de alerta';

CREATE TABLE IF NOT EXISTS centro_custo (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo        VARCHAR(20)     NOT NULL,
  nome          VARCHAR(100)    NOT NULL,
  tipo          VARCHAR(12)     NOT NULL COMMENT 'FILIAL, RETAGUARDA ou CONTRATO',
  filial_id     BIGINT UNSIGNED NOT NULL,
  contrato_id   BIGINT UNSIGNED NULL COMMENT 'só para centro de custo de contrato; FK declarada em 02_comercial.sql',
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_centro_custo_codigo (codigo),
  KEY ix_centro_custo_atualizado_em (atualizado_em),
  CONSTRAINT fk_centro_custo_filial FOREIGN KEY (filial_id) REFERENCES filial (id),
  CONSTRAINT ck_centro_custo_tipo CHECK (tipo IN ('FILIAL', 'RETAGUARDA', 'CONTRATO'))
) ENCRYPTION='Y' COMMENT='O eixo do rateio de custo e da apuração de resultado';
