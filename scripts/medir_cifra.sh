#!/usr/bin/env bash
# Mede o custo da cifra em repouso na réplica: escreve e lê 200 mil linhas numa tabela
# cifrada e numa tabela em claro, e imprime o tempo de cada uma. Os números do ADR-0002
# saíram daqui. Cria e apaga tabelas de medida em cadastro; não toca em dado de negócio.
#
# Uso:  bash scripts/medir_cifra.sh          (LINHAS=500000 bash scripts/medir_cifra.sh)
set -euo pipefail

cd "$(dirname "$0")/.."
senha=$(grep -E '^STAGING_ROOT_PASSWORD=' .env | cut -d= -f2-)
LINHAS="${LINHAS:-200000}"

sql() { docker exec -i -e MYSQL_PWD="$senha" fictalent_mysql_staging mysql -uroot -N --default-character-set=utf8mb4; }
mede() {
  local inicio fim
  inicio=$(date +%s%N)
  sql >/dev/null
  fim=$(date +%s%N)
  echo $(( (fim - inicio) / 1000000 ))
}

for cifra in N Y; do
  sql <<SQL
DROP TABLE IF EXISTS cadastro.medida_$cifra;
CREATE TABLE cadastro.medida_$cifra (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  cpf CHAR(11) NOT NULL,
  texto VARCHAR(200) NOT NULL
) ENCRYPTION='$cifra';
SQL
  escrita=$(mede <<SQL
SET SESSION cte_max_recursion_depth = $((LINHAS + 1));
INSERT INTO cadastro.medida_$cifra (cpf, texto)
WITH RECURSIVE n AS (SELECT 1 AS x UNION ALL SELECT x + 1 FROM n WHERE x < $LINHAS)
SELECT LPAD(x, 11, '0'), REPEAT('a', 150) FROM n;
SQL
)
  leitura=$(mede <<SQL
SELECT COUNT(*), SUM(LENGTH(texto)) FROM cadastro.medida_$cifra;
SQL
)
  tamanho=$(docker exec fictalent_mysql_staging sh -c "du -k /var/lib/mysql/cadastro/medida_$cifra.ibd | cut -f1")
  echo "ENCRYPTION='$cifra': escrita de $LINHAS linhas ${escrita} ms · leitura completa ${leitura} ms · ${tamanho} KB em disco"
  sql <<SQL
DROP TABLE cadastro.medida_$cifra;
SQL
done
