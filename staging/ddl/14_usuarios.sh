#!/bin/sh
# Usuários de serviço da réplica, com senha do .env, cada um com o seu papel (13_papeis.sql).
#
# Roda sozinho na primeira inicialização do container (docker-entrypoint-initdb.d) e de
# novo por scripts/aplicar_ddl.sh. Idempotente: CREATE IF NOT EXISTS + ALTER para a senha
# acompanhar o .env (a do root não acompanha: veja docs/08, seção 5).
set -eu

: "${PIPELINE_PASSWORD:?defina PIPELINE_PASSWORD no .env}"
: "${RELATORIOS_PASSWORD:?defina RELATORIOS_PASSWORD no .env}"
: "${REPLICADOR_PASSWORD:?defina REPLICADOR_PASSWORD no .env}"

MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket -uroot <<SQL
CREATE USER IF NOT EXISTS 'pipeline'@'%'           IDENTIFIED BY '${PIPELINE_PASSWORD}';
CREATE USER IF NOT EXISTS 'relatorios_cliente'@'%' IDENTIFIED BY '${RELATORIOS_PASSWORD}';
CREATE USER IF NOT EXISTS 'replicador'@'%'         IDENTIFIED BY '${REPLICADOR_PASSWORD}';
ALTER USER 'pipeline'@'%'           IDENTIFIED BY '${PIPELINE_PASSWORD}';
ALTER USER 'relatorios_cliente'@'%' IDENTIFIED BY '${RELATORIOS_PASSWORD}';
ALTER USER 'replicador'@'%'         IDENTIFIED BY '${REPLICADOR_PASSWORD}';
GRANT papel_pipeline   TO 'pipeline'@'%';
GRANT papel_relatorios TO 'relatorios_cliente'@'%';
GRANT papel_replicador TO 'replicador'@'%';
SET DEFAULT ROLE ALL TO 'pipeline'@'%', 'relatorios_cliente'@'%', 'replicador'@'%';
FLUSH PRIVILEGES;
SQL
