#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Keep CLI first-run behavior one-command as well: prepare Python deps and the
# Docker sandbox image before entering the app. Set AGENT_SKIP_SETUP=1 to skip.
export AGENT_SETUP_ASSUME_YES="${AGENT_SETUP_ASSUME_YES:-1}"

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  "${VIRTUAL_ENV}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "${VIRTUAL_ENV}/bin/python" -m pip install --upgrade pip setuptools wheel
  "${VIRTUAL_ENV}/bin/python" -m pip install -r requirements.txt
  if [[ "${AGENT_SKIP_SETUP:-0}" != "1" ]]; then
    "${VIRTUAL_ENV}/bin/python" -m app.setup_auto
  fi
  exec "${VIRTUAL_ENV}/bin/python" -m app.cli "$@"
fi

# shellcheck source=scripts/bootstrap-env.sh
source "scripts/bootstrap-env.sh"
bootstrap_python_env

if [[ "${AGENT_SKIP_SETUP:-0}" != "1" ]]; then
  .venv/bin/python -m app.setup_auto
fi
exec .venv/bin/python -m app.cli "$@"
