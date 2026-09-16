#!/usr/bin/env bash
# Espelho local da CI (.github/workflows/ci.yml): roda antes de abrir o PR.
#
#   qualidade   ruff (lint e formato), mypy, pytest
#   segurança   bandit, pip-audit; gitleaks e trivy por container, se o docker estiver disponível
#
# Os testes de integração rodam se a réplica estiver de pé (docker compose up -d), senão pulam.
# Uso:  bash scripts/esteira.sh          (SEM_DOCKER=1 pula gitleaks e trivy)
set -uo pipefail

cd "$(dirname "$0")/.."
PY=.venv/bin
falhas=0
passo() { printf '\n== %s\n' "$1"; }
confere() { if "$@"; then echo "ok"; else echo "FALHOU"; falhas=$((falhas + 1)); fi; }

passo "lint (ruff)";            confere "$PY/ruff" check .
passo "formato (ruff)";         confere "$PY/ruff" format --check .
passo "tipos (mypy)";           confere "$PY/mypy"
passo "testes (pytest)";        confere "$PY/pytest" -q
passo "código (bandit)";        confere "$PY/bandit" -c pyproject.toml -r src -q
passo "dependências (pip-audit)"
"$PY/python" -c "import sys; sys.exit(0)" && {
  UV="${UV:-$(command -v uv || echo "$HOME/.local/share/mise/installs/uv/0.11.26/uv-x86_64-unknown-linux-musl/uv")}"
  "$UV" export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requisitos-auditoria.txt >/dev/null
  # o lock já vem totalmente pinado: audita a lista como está, sem resolver dependências
  confere "$PY/pip-audit" -r /tmp/requisitos-auditoria.txt --no-deps --disable-pip --strict
}

if [ -z "${SEM_DOCKER:-}" ] && command -v docker >/dev/null; then
  passo "segredos no histórico (gitleaks)"
  confere docker run --rm -v "$PWD:/repo:ro" zricethezav/gitleaks:v8.21.2 detect --source /repo --no-banner --redact
  passo "repositório (trivy: vulnerabilidade, segredo, má configuração)"
  confere docker run --rm -v "$PWD:/repo:ro" aquasec/trivy:0.58.0 fs --scanners vuln,secret,misconfig \
    --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 --quiet /repo
fi

printf '\n%s\n' "$([ "$falhas" -eq 0 ] && echo "ESTEIRA VERDE" || echo "ESTEIRA COM $falhas FALHA(S)")"
exit "$falhas"
