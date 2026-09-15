#!/bin/sh
# Roda uma única vez, na criação do warehouse.
# Cria o usuário que o Grafana usa: só SELECT no warehouse, nada mais.
set -eu

mysql --protocol=socket -uroot -p"$MYSQL_ROOT_PASSWORD" <<SQL
CREATE USER IF NOT EXISTS 'grafana_leitor'@'%' IDENTIFIED BY '${GRAFANA_LEITOR_PASSWORD}';
GRANT SELECT, SHOW VIEW ON \`${MYSQL_DATABASE}\`.* TO 'grafana_leitor'@'%';
FLUSH PRIVILEGES;
SQL
