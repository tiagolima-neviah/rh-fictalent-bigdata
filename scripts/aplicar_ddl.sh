#!/usr/bin/env bash
# Aplica a DDL da réplica (staging/ddl/*.sql, em ordem) num container já inicializado.
#
# Na primeira subida isso acontece sozinho: o compose monta staging/ddl em
# /docker-entrypoint-initdb.d e o MySQL executa os arquivos ao criar o volume. Este
# script serve para um volume que já existia antes da DDL, ou depois de mudar a DDL.
# Tudo é idempotente (IF NOT EXISTS, ALTER guardado): pode rodar quantas vezes quiser.
#
# Uso:  bash scripts/aplicar_ddl.sh
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "sem .env: veja docs/08_manual_de_operacao.md, seção 2"; exit 1; }
senha=$(grep -E '^STAGING_ROOT_PASSWORD=' .env | cut -d= -f2-)
[ -n "$senha" ] || { echo "STAGING_ROOT_PASSWORD vazio no .env"; exit 1; }

for arquivo in staging/ddl/*.sql; do
  printf '%s ... ' "$arquivo"
  docker exec -i -e MYSQL_PWD="$senha" fictalent_mysql_staging mysql -uroot < "$arquivo"
  echo ok
done

for script in staging/ddl/*.sh; do
  printf '%s ... ' "$script"
  docker exec fictalent_mysql_staging sh "/docker-entrypoint-initdb.d/$(basename "$script")"
  echo ok
done

for script in staging/ddl/*.sh; do
  printf '%s ... ' "$script"
  docker exec fictalent_mysql_staging sh "/docker-entrypoint-initdb.d/$(basename "$script")"
  echo ok
done

echo "tabelas por módulo:"
docker exec -e MYSQL_PWD="$senha" fictalent_mysql_staging mysql -uroot -e \
  "SELECT table_schema AS modulo, COUNT(*) AS tabelas
     FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
      AND table_schema NOT IN ('mysql', 'sys', 'information_schema', 'performance_schema')
    GROUP BY table_schema ORDER BY table_schema"
