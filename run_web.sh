#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# A one-command deployment should not stop on setup prompts. Users can override
# with AGENT_SETUP_ASSUME_YES=0 when they want manual confirmation.
export AGENT_SETUP_ASSUME_YES="${AGENT_SETUP_ASSUME_YES:-1}"

# shellcheck source=scripts/bootstrap-env.sh
source "scripts/bootstrap-env.sh"

# Reuse an already activated virtualenv, otherwise build/repair the local .venv.
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  log "Using active virtualenv: ${VIRTUAL_ENV}"
  install_python_deps "${VIRTUAL_ENV}/bin/python"
  run_logged_progress "Running automatic setup checks" "${VIRTUAL_ENV}/bin/python" -m app.setup_auto
  success "Starting web server on ${AGENT_WEB_HOST:-127.0.0.1}:${AGENT_WEB_PORT:-8000}"
  exec "${VIRTUAL_ENV}/bin/python" -m uvicorn app.web:app --host "${AGENT_WEB_HOST:-127.0.0.1}" --port "${AGENT_WEB_PORT:-8000}" "$@"
fi

bootstrap_python_env

run_logged_progress "Running automatic setup checks" .venv/bin/python -m app.setup_auto
success "Starting web server on ${AGENT_WEB_HOST:-127.0.0.1}:${AGENT_WEB_PORT:-8000}"
exec .venv/bin/python -m uvicorn app.web:app --host "${AGENT_WEB_HOST:-127.0.0.1}" --port "${AGENT_WEB_PORT:-8000}" "$@"
