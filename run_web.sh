#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

install_deps() {
  local python_bin="$1"
  echo "Checking/installing Python dependencies..."
  if ! out=$("$python_bin" -m pip install -r requirements.txt 2>&1); then
    echo "$out"
    echo "Error: Failed to install Python dependencies." >&2
    exit 1
  fi
  local satisfied_count
  satisfied_count=$(echo "$out" | grep -c "Requirement already satisfied" || true)
  if [ "$satisfied_count" -gt 0 ]; then
    echo "  - $satisfied_count dependencies already satisfied."
  fi
  echo "$out" | grep -v "Requirement already satisfied" || true
}

if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  install_deps "${VIRTUAL_ENV}/bin/python"
  "${VIRTUAL_ENV}/bin/python" -m app.setup_auto
  exec "${VIRTUAL_ENV}/bin/python" -m uvicorn app.web:app --host 127.0.0.1 --port 8000 "$@"
fi

if [[ ! -x ".venv/bin/python" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  elif command -v python >/dev/null 2>&1; then
    python -m venv .venv
  fi
fi

if [[ -x ".venv/bin/python" ]]; then
  install_deps ".venv/bin/python"
  .venv/bin/python -m app.setup_auto
  exec .venv/bin/python -m uvicorn app.web:app --host 127.0.0.1 --port 8000 "$@"
fi

if command -v uv >/dev/null 2>&1; then
  uv run --with-requirements requirements.txt python -m app.setup_auto
  exec uv run --with-requirements requirements.txt python -m uvicorn app.web:app --host 127.0.0.1 --port 8000 "$@"
fi

echo "No Python environment found. Create one with 'uv venv && uv pip install -r requirements.txt' or 'python -m venv .venv && .venv/bin/pip install -r requirements.txt'." >&2
exit 1
