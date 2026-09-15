#!/bin/sh
# Roda uma única vez, na criação do warehouse.
# Cria o papel que o Grafana usa para frescor e contagens: só leitura, sem poder criar nada.
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
-- os schemas dim e fato entram com a carga (v0.7.0) e recebem o próprio GRANT no DCL do warehouse;
-- aqui fica só o privilégio padrão do schema public, para as tabelas de controle
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA public GRANT SELECT ON TABLES TO grafana_leitor;
SQL
