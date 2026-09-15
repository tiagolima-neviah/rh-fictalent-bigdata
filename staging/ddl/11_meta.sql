-- meta · a infraestrutura da carga (1 tabela, não é módulo de negócio)
-- A trilha de exclusões: uma linha apagada não tem atualizado_em para ser encontrada pela
-- marca d agua, então o gatilho de DELETE (card 2.3) grava aqui antes de a linha sumir.
-- A marca d agua em si fica do lado do pipeline, não dentro da réplica do cliente.
USE meta;

CREATE TABLE IF NOT EXISTS exclusao_auditoria (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  banco          VARCHAR(30)     NOT NULL COMMENT 'database da linha apagada',
  tabela         VARCHAR(60)     NOT NULL,
  registro_id    BIGINT UNSIGNED NOT NULL COMMENT '[sem FK] o id da linha apagada, que já não existe',
  dt_exclusao    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  usuario_banco  VARCHAR(100)    NULL COMMENT 'usuário de banco que executou o DELETE',
  criado_em      DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY ix_exclusao_auditoria_dt (dt_exclusao),
  KEY ix_exclusao_auditoria_tabela (banco, tabela, registro_id)
) COMMENT='Captura o DELETE que a marca d agua não veria; só insere, nunca atualiza';
