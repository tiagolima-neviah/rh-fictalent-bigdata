#!/usr/bin/env bash
# Verificação de saúde da plataforma Fictalent, em duas fases.
#
# Fase 1 · containers: espera cada serviço de longa duração ficar "healthy" e os jobs de
#          inicialização terminarem com sucesso (o que docker compose up --wait não faz
#          direito: ele trata um job que termina com 0 como falha).
# Fase 2 · ponta a ponta: prova o que está DENTRO dos containers. A réplica responde ao
#          usuário pipeline com as 76 tabelas, tem os 75 gatilhos, os tablespaces cifrados e o
#          keyring ativo; o lake tem o bucket; o warehouse aceita o grafana_leitor e conta as
#          métricas (e há quanto tempo foi o último sucesso); o Dagster carregou a code
#          location e tem os sensores ligados; o Grafana está vivo, com as fontes e o painel.
#
# Uso:  bash scripts/saude.sh                 (fase 1 e fase 2; sai com 0 só se tudo passou)
#       SO_CONTAINERS=1 bash scripts/saude.sh (só a fase 1, como a CI usa)
#       TEMPO_MAXIMO=600 bash scripts/saude.sh
set -uo pipefail

cd "$(dirname "$0")/.."

LONGA_DURACAO=(mysql-staging pg-dw pg-dagster s3 dagster-web dagster-daemon grafana)
JOBS=(s3-init keyring-init)
TEMPO_MAXIMO="${TEMPO_MAXIMO:-300}"
MODULOS="'cadastro','comercial','ats','pessoas','ponto','folha','financeiro','treinamento','sst','seguranca','meta'"

# ─────────────────────────────── fase 1 · containers ───────────────────────────────

estado() {
  local id
  id=$(docker compose ps -a -q "$1" 2>/dev/null)
  [ -z "$id" ] && { echo "ausente"; return; }
  docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.State.ExitCode}}' "$id"
}

esperar_containers() {
  local inicio pendentes falhas s status saude codigo
  inicio=$(date +%s)
  while true; do
    pendentes=()
    falhas=()
    for s in "${LONGA_DURACAO[@]}"; do
      read -r status saude _ <<<"$(estado "$s")"
      case "$status/$saude" in
        running/healthy) ;;
        running/unhealthy) falhas+=("$s (unhealthy)") ;;
        ausente/*) falhas+=("$s (não existe: rode docker compose up -d)") ;;
        exited/*|dead/*) falhas+=("$s ($status)") ;;
        *) pendentes+=("$s ($saude)") ;;
      esac
    done
    for s in "${JOBS[@]}"; do
      read -r status _ codigo <<<"$(estado "$s")"
      case "$status" in
        exited) [ "$codigo" = "0" ] || falhas+=("$s (terminou com código $codigo)") ;;
        ausente) falhas+=("$s (não existe)") ;;
        *) pendentes+=("$s ($status)") ;;
      esac
    done
    if [ ${#falhas[@]} -gt 0 ]; then
      echo "FALHA na plataforma:"
      printf '  - %s\n' "${falhas[@]}"
      echo "Veja os logs: docker compose logs <serviço>"
      return 1
    fi
    if [ ${#pendentes[@]} -eq 0 ]; then
      echo "OK: ${#LONGA_DURACAO[@]} serviços saudáveis e ${#JOBS[@]} jobs de inicialização concluídos ($(( $(date +%s) - inicio )) s)."
      return 0
    fi
    if [ $(( $(date +%s) - inicio )) -ge "$TEMPO_MAXIMO" ]; then
      echo "TEMPO ESGOTADO (${TEMPO_MAXIMO} s). Ainda subindo:"
      printf '  - %s\n' "${pendentes[@]}"
      return 1
    fi
    sleep 3
  done
}

esperar_containers || exit 1
[ -n "${SO_CONTAINERS:-}" ] && exit 0

# ─────────────────────────────── fase 2 · ponta a ponta ───────────────────────────────

[ -f .env ] || { echo "sem .env: a fase 2 precisa das senhas (docs/08, seção 2)"; exit 1; }
set -a; . ./.env; set +a
DAGSTER="http://127.0.0.1:${DAGSTER_PORT:-3010}"
GRAFANA="http://127.0.0.1:${GRAFANA_PORT:-3011}"
passou=0; falhou=0; avisos=0

ok()    { printf '  ✓ %s\n' "$1"; passou=$((passou + 1)); }
falha() { printf '  ✗ %s\n' "$1"; falhou=$((falhou + 1)); }
aviso() { printf '  ! %s\n' "$1"; avisos=$((avisos + 1)); }

mysql_root()     { docker exec -e MYSQL_PWD="$STAGING_ROOT_PASSWORD" fictalent_mysql_staging mysql -uroot -N --default-character-set=utf8mb4 -e "$1" 2>/dev/null; }
mysql_pipeline() { docker exec -e MYSQL_PWD="$PIPELINE_PASSWORD" fictalent_mysql_staging mysql -upipeline -N --default-character-set=utf8mb4 -e "$1" 2>/dev/null; }
psql_admin()     { docker exec -e PGPASSWORD="$DW_ADMIN_PASSWORD" fictalent_pg_dw psql -U "${DW_ADMIN_USER:-fictalent_admin}" -d "${DW_DB:-dw_fictalent}" -tAc "$1" 2>/dev/null; }
psql_leitor()    { docker exec fictalent_pg_dw psql -U grafana_leitor -d "${DW_DB:-dw_fictalent}" -tAc "$1" 2>/dev/null; }
grafana_api()    { curl -s -u "${GRAFANA_ADMIN_USER:-admin}:${GRAFANA_ADMIN_PASSWORD}" "$GRAFANA$1"; }
graphql()        { curl -s -X POST "$DAGSTER/graphql" -H "Content-Type: application/json" -d "{\"query\":\"$1\"}"; }

echo "Réplica (MySQL)"
n=$(mysql_pipeline "SELECT COUNT(*) FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema IN ($MODULOS)")
[ "${n:-0}" = "76" ] && ok "usuário pipeline lê as 76 tabelas" || falha "usuário pipeline: ${n:-sem resposta} tabelas (esperadas 76)"
n=$(mysql_root "SELECT COUNT(*) FROM information_schema.triggers WHERE event_manipulation='DELETE' AND trigger_schema IN ($MODULOS)")
[ "${n:-0}" = "75" ] && ok "75 gatilhos da trilha de exclusões" || falha "gatilhos: ${n:-sem resposta} (esperados 75)"
n=$(mysql_root "SELECT COUNT(*) FROM information_schema.innodb_tablespaces WHERE encryption='Y' AND SUBSTRING_INDEX(name,'/',1) IN ($MODULOS)")
[ "${n:-0}" = "76" ] && ok "76 tablespaces cifrados" || falha "cifra: ${n:-sem resposta} tablespaces cifrados (esperados 76)"
n=$(mysql_root "SELECT status_value FROM performance_schema.keyring_component_status WHERE status_key='Component_status'")
[ "${n:-}" = "Active" ] && ok "keyring ativo" || falha "keyring: ${n:-sem resposta}"

echo "Lake (SeaweedFS)"
lista=$(docker compose exec -T s3 sh -c 'echo "s3.bucket.list" | weed shell -master localhost:9333' 2>/dev/null)
echo "$lista" | grep -q "${S3_BUCKET:-fictalent-lake}" && ok "bucket ${S3_BUCKET:-fictalent-lake} existe" || falha "bucket ${S3_BUCKET:-fictalent-lake} não encontrado"

echo "Warehouse (Postgres)"
n=$(psql_leitor "SELECT 1")
[ "${n:-}" = "1" ] && ok "grafana_leitor conecta" || falha "grafana_leitor não conecta"
existe=$(psql_admin "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='observabilidade' AND table_name='execucao'")
if [ "${existe:-0}" = "1" ]; then
  n=$(psql_admin "SELECT COUNT(*) FROM observabilidade.execucao")
  minutos=$(psql_admin "SELECT COALESCE(ROUND(EXTRACT(EPOCH FROM (now()-MAX(fim)))/60)::int, -1) FROM observabilidade.execucao WHERE status='SUCESSO'")
  ok "métricas: ${n:-0} execuções registradas"
  if [ "${minutos:--1}" -lt 0 ]; then aviso "frescor: nenhuma execução com sucesso ainda"
  elif [ "$minutos" -gt 1560 ]; then aviso "frescor: último sucesso há ${minutos} min (mais de 26 h: o alerta do Grafana está aceso)"
  else ok "frescor: último sucesso há ${minutos} min"; fi
else
  aviso "métricas: ainda sem execução registrada (rode o job verificar_plataforma)"
fi

echo "Dagster"
versao=$(curl -s "$DAGSTER/server_info" | grep -o '"dagster_version": *"[^"]*"' | cut -d'"' -f4)
[ -n "$versao" ] && ok "webserver responde (Dagster $versao)" || falha "webserver não responde em $DAGSTER"
n=$(graphql '{ assetNodes { assetKey { path } } }' | grep -o '"path"' | wc -l)
[ "${n:-0}" -ge 3 ] && ok "code location carregada: $n assets" || falha "code location: $n assets (esperados ao menos 3)"
n=$(graphql '{ sensorsOrError(repositorySelector:{repositoryName:\"__repository__\", repositoryLocationName:\"rh_fictalent.orquestracao.definicoes\"}) { ... on Sensors { results { sensorState { status } } } } }' | grep -o '"RUNNING"' | wc -l)
[ "${n:-0}" = "3" ] && ok "3 sensores de métricas ligados" || falha "sensores ligados: $n (esperados 3)"

echo "Grafana"
curl -s "$GRAFANA/api/health" | grep -q '"database": *"ok"' && ok "responde" || falha "não responde em $GRAFANA"
for fonte in dagster-metadados warehouse-postgres; do
  grafana_api "/api/datasources/uid/$fonte/health" | grep -q '"status": *"OK"' && ok "fonte $fonte OK" || falha "fonte $fonte com problema"
done
grafana_api "/api/search?type=dash-db&query=Fictalent" | grep -q '"fictalent-execucoes"' && ok "painel de execuções provisionado" || falha "painel de execuções ausente"
n=$(grafana_api "/api/v1/provisioning/alert-rules" | grep -o '"uid": *"fictalent-' | wc -l)
[ "${n:-0}" = "2" ] && ok "2 regras de alerta provisionadas" || falha "regras de alerta: $n (esperadas 2)"

echo
if [ "$falhou" -eq 0 ]; then
  echo "PLATAFORMA OK: $passou verificações passaram, $avisos avisos."
  exit 0
fi
echo "PLATAFORMA COM $falhou FALHA(S) ($passou passaram, $avisos avisos)."
exit 1
