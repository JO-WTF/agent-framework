#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# A one-command deployment should not stop on setup prompts. Users can override
# with AGENT_SETUP_ASSUME_YES=0 when they want manual confirmation.
export AGENT_SETUP_ASSUME_YES="${AGENT_SETUP_ASSUME_YES:-1}"

# Reuse an already activated virtualenv, otherwise build/repair the local .venv.
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  "${VIRTUAL_ENV}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "${VIRTUAL_ENV}/bin/python" -m pip install --upgrade pip setuptools wheel
  "${VIRTUAL_ENV}/bin/python" -m pip install -r requirements.txt
  "${VIRTUAL_ENV}/bin/python" -m app.setup_auto
  exec "${VIRTUAL_ENV}/bin/python" -m uvicorn app.web:app --host "${AGENT_WEB_HOST:-127.0.0.1}" --port "${AGENT_WEB_PORT:-8000}" "$@"
fi

# shellcheck source=scripts/bootstrap-env.sh
source "scripts/bootstrap-env.sh"
bootstrap_python_env

.venv/bin/python -m app.setup_auto
exec .venv/bin/python -m uvicorn app.web:app --host "${AGENT_WEB_HOST:-127.0.0.1}" --port "${AGENT_WEB_PORT:-8000}" "$@"
