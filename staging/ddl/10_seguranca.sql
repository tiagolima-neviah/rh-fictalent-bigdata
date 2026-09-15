-- seguranca · quem pode ver o quê (5 tabelas)
-- Usuários internos, os cinco perfis do autoatendimento, o escopo por filial, a matriz
-- de permissão por módulo e a trilha de auditoria do sistema.
USE seguranca;

CREATE TABLE IF NOT EXISTS perfil (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  codigo        VARCHAR(12)     NOT NULL COMMENT 'SOCIO, GERENTE, COORDENADOR, ASSISTENTE, FINANCEIRO ou TI',
  nome          VARCHAR(60)     NOT NULL,
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_perfil_codigo (codigo),
  KEY ix_perfil_atualizado_em (atualizado_em),
  CONSTRAINT ck_perfil_codigo CHECK (codigo IN ('SOCIO', 'GERENTE', 'COORDENADOR', 'ASSISTENTE', 'FINANCEIRO', 'TI'))
) COMMENT='Os níveis do autoatendimento';

CREATE TABLE IF NOT EXISTS usuario (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  login          VARCHAR(40)     NOT NULL,
  nome           VARCHAR(120)    NOT NULL COMMENT '[LGPD:pessoal]',
  email          VARCHAR(160)    NOT NULL COMMENT '[LGPD:pessoal]',
  colaborador_id BIGINT UNSIGNED NULL COMMENT 'quando o usuário também é colaborador',
  filial_id      BIGINT UNSIGNED NOT NULL,
  ativo          BOOLEAN         NOT NULL DEFAULT TRUE,
  dt_criacao     DATE            NOT NULL,
  ultimo_acesso  DATETIME(6)     NULL,
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em  DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_usuario_login (login),
  KEY ix_usuario_atualizado_em (atualizado_em),
  CONSTRAINT fk_usuario_colaborador FOREIGN KEY (colaborador_id) REFERENCES pessoas.colaborador (id),
  CONSTRAINT fk_usuario_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id)
) COMMENT='Cerca de 40 usuários internos ao longo do arco';

-- fecha a referência de ats.entrevista.usuario_id (a coluna existe desde 03_ats.sql)
SET @existe = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
               WHERE CONSTRAINT_SCHEMA = 'ats' AND CONSTRAINT_NAME = 'fk_entrevista_usuario');
SET @sql = IF(@existe = 0,
  'ALTER TABLE ats.entrevista ADD CONSTRAINT fk_entrevista_usuario FOREIGN KEY (usuario_id) REFERENCES seguranca.usuario (id)',
  'SELECT 1');
PREPARE fk_ciclo FROM @sql; EXECUTE fk_ciclo; DEALLOCATE PREPARE fk_ciclo;

CREATE TABLE IF NOT EXISTS usuario_perfil (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id      BIGINT UNSIGNED NOT NULL,
  perfil_id       BIGINT UNSIGNED NOT NULL,
  filial_id       BIGINT UNSIGNED NULL COMMENT 'escopo: NULL = todas as filiais',
  vigencia_inicio DATE            NOT NULL,
  vigencia_fim    DATE            NULL COMMENT 'NULL = vigente',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_usuario_perfil_atualizado_em (atualizado_em),
  CONSTRAINT fk_usuario_perfil_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id),
  CONSTRAINT fk_usuario_perfil_perfil FOREIGN KEY (perfil_id) REFERENCES perfil (id),
  CONSTRAINT fk_usuario_perfil_filial FOREIGN KEY (filial_id) REFERENCES cadastro.filial (id)
) COMMENT='O escopo: a assistente vê a filial dela, a coordenadora vê o setor';

CREATE TABLE IF NOT EXISTS permissao (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  perfil_id     BIGINT UNSIGNED NOT NULL,
  modulo        VARCHAR(20)     NOT NULL COMMENT 'nome do módulo (cadastro, comercial, ats, ...)',
  acao          VARCHAR(10)     NOT NULL COMMENT 'LER, CRIAR, EDITAR, EXCLUIR ou EXPORTAR',
  fl_permitido  BOOLEAN         NOT NULL DEFAULT FALSE,
  criado_em     DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_permissao_perfil_modulo_acao (perfil_id, modulo, acao),
  KEY ix_permissao_atualizado_em (atualizado_em),
  CONSTRAINT fk_permissao_perfil FOREIGN KEY (perfil_id) REFERENCES perfil (id),
  CONSTRAINT ck_permissao_acao CHECK (acao IN ('LER', 'CRIAR', 'EDITAR', 'EXCLUIR', 'EXPORTAR'))
) COMMENT='Matriz de permissão por módulo';

CREATE TABLE IF NOT EXISTS log_auditoria (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id      BIGINT UNSIGNED NOT NULL,
  dt_evento       DATETIME(6)     NOT NULL,
  modulo          VARCHAR(20)     NOT NULL,
  tabela          VARCHAR(60)     NOT NULL,
  registro_id     BIGINT UNSIGNED NULL COMMENT '[sem FK] aponta para a tabela indicada na coluna tabela',
  acao            VARCHAR(10)     NOT NULL COMMENT 'CRIAR, EDITAR, EXCLUIR, EXPORTAR ou LOGIN',
  valor_anterior  JSON            NULL COMMENT '[LGPD:pessoal] pode carregar o dado alterado',
  valor_novo      JSON            NULL COMMENT '[LGPD:pessoal] pode carregar o dado alterado',
  criado_em       DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  atualizado_em   DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_log_auditoria_evento (dt_evento),
  KEY ix_log_auditoria_atualizado_em (atualizado_em),
  CONSTRAINT fk_log_auditoria_usuario FOREIGN KEY (usuario_id) REFERENCES usuario (id),
  CONSTRAINT ck_log_auditoria_acao CHECK (acao IN ('CRIAR', 'EDITAR', 'EXCLUIR', 'EXPORTAR', 'LOGIN'))
) COMMENT='Quem alterou o quê, com data: a trilha que o sistema futuro vai usar';
