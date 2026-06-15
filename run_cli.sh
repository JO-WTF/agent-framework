#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Keep CLI first-run behavior one-command as well: prepare Python deps and the
# Docker sandbox image before entering the app. Set AGENT_SKIP_SETUP=1 to skip.
export AGENT_SETUP_ASSUME_YES="${AGENT_SETUP_ASSUME_YES:-1}"

# shellcheck source=scripts/bootstrap-env.sh
source "scripts/bootstrap-env.sh"

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  log "Using active virtualenv: ${VIRTUAL_ENV}"
  install_python_deps "${VIRTUAL_ENV}/bin/python"
  if [[ "${AGENT_SKIP_SETUP:-0}" != "1" ]]; then
    run_logged_progress "Running automatic setup checks" "${VIRTUAL_ENV}/bin/python" -m app.setup_auto
  else
    warn "Skipping automatic setup checks because AGENT_SKIP_SETUP=1."
  fi
  success "Starting CLI"
  exec "${VIRTUAL_ENV}/bin/python" -m app.cli "$@"
fi

bootstrap_python_env

if [[ "${AGENT_SKIP_SETUP:-0}" != "1" ]]; then
  run_logged_progress "Running automatic setup checks" .venv/bin/python -m app.setup_auto
else
  warn "Skipping automatic setup checks because AGENT_SKIP_SETUP=1."
fi
success "Starting CLI"
exec .venv/bin/python -m app.cli "$@"
