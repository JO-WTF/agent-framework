#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  exec "${VIRTUAL_ENV}/bin/python" -m uvicorn app.web:app --host 127.0.0.1 --port 8000 "$@"
fi

if [[ -x ".venv/bin/python" ]]; then
  exec .venv/bin/python -m uvicorn app.web:app --host 127.0.0.1 --port 8000 "$@"
fi

if command -v uv >/dev/null 2>&1; then
  exec uv run --with-requirements requirements.txt python -m uvicorn app.web:app --host 127.0.0.1 --port 8000 "$@"
fi

echo "No Python environment found. Create one with 'uv venv && uv pip install -r requirements.txt' or 'python -m venv .venv && .venv/bin/pip install -r requirements.txt'." >&2
exit 1
