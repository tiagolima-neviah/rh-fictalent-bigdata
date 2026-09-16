#!/usr/bin/env bash
# Verificação de saúde da plataforma Fictalent.
#
# Espera cada serviço de longa duração ficar "healthy" e o job de inicialização
# do lake terminar com sucesso. Sai com 0 quando tudo está pronto e com 1 se algo
# ficar doente ou estourar o tempo, listando o que falhou.
#
# Uso:  bash scripts/saude.sh            (espera até 300 s)
#       TEMPO_MAXIMO=600 bash scripts/saude.sh
#
# Por que não "docker compose up --wait": ele trata o job de inicialização que
# termina com sucesso (s3-init, exit 0) como falha e sai com erro.
set -uo pipefail

cd "$(dirname "$0")/.."

LONGA_DURACAO=(mysql-staging pg-dw pg-dagster s3 dagster-web dagster-daemon grafana)
JOBS=(s3-init keyring-init)
TEMPO_MAXIMO="${TEMPO_MAXIMO:-300}"
inicio=$(date +%s)

estado() {
  local id
  id=$(docker compose ps -a -q "$1" 2>/dev/null)
  [ -z "$id" ] && { echo "ausente"; return; }
  docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.State.ExitCode}}' "$id"
}

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
    exit 1
  fi
  if [ ${#pendentes[@]} -eq 0 ]; then
    echo "OK: ${#LONGA_DURACAO[@]} serviços saudáveis e ${#JOBS[@]} jobs de inicialização concluídos ($(( $(date +%s) - inicio )) s)."
    exit 0
  fi
  if [ $(( $(date +%s) - inicio )) -ge "$TEMPO_MAXIMO" ]; then
    echo "TEMPO ESGOTADO (${TEMPO_MAXIMO} s). Ainda subindo:"
    printf '  - %s\n' "${pendentes[@]}"
    exit 1
  fi
  sleep 3
done
