#!/bin/sh
# Roda uma única vez, na criação do banco de metadados do Dagster.
# Cria o papel que o Grafana usa: só leitura, sem poder criar nada.
set -eu

# a senha entra como variável do psql, nunca interpolada no texto do SQL
psql -v ON_ERROR_STOP=1 -v senha="$GRAFANA_LEITOR_PASSWORD" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE grafana_leitor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD :'senha';
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
REVOKE ALL ON DATABASE "$POSTGRES_DB" FROM PUBLIC;
GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO grafana_leitor;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO grafana_leitor;
-- as tabelas do Dagster são criadas depois, pelo próprio Dagster: o privilégio padrão cobre as futuras
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public GRANT SELECT ON TABLES TO grafana_leitor;
SQL
