#!/usr/bin/env bash
# Shared bootstrap helpers for fresh Linux/macOS systems.
# shellcheck shell=bash

set -euo pipefail

if [[ -t 1 ]]; then
  C_RESET="$(printf '\033[0m')"
  C_BOLD="$(printf '\033[1m')"
  C_BLUE="$(printf '\033[34m')"
  C_CYAN="$(printf '\033[36m')"
  C_GREEN="$(printf '\033[32m')"
  C_MAGENTA="$(printf '\033[35m')"
  C_RED="$(printf '\033[31m')"
  C_YELLOW="$(printf '\033[33m')"
else
  C_RESET=""
  C_BOLD=""
  C_BLUE=""
  C_CYAN=""
  C_GREEN=""
  C_MAGENTA=""
  C_RED=""
  C_YELLOW=""
fi

BOOTSTRAP_LOG_DIR="${BOOTSTRAP_LOG_DIR:-logs/setup}"
BOOTSTRAP_LOG_FILE="${BOOTSTRAP_LOG_FILE:-$BOOTSTRAP_LOG_DIR/bootstrap-$(date +%Y%m%d-%H%M%S).log}"

log() {
  printf '%s[bootstrap]%s %s\n' "$C_CYAN" "$C_RESET" "$*"
}

step() {
  printf '%s▶%s %s%s%s\n' "$C_BLUE" "$C_RESET" "$C_BOLD" "$*" "$C_RESET"
}

success() {
  printf '%s✓%s %s\n' "$C_GREEN" "$C_RESET" "$*"
}

warn() {
  printf '%s[bootstrap] warning:%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2
}

fail() {
  printf '%s[bootstrap] error:%s %s\n' "$C_RED" "$C_RESET" "$*" >&2
  exit 1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

run_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  else
    fail "'$*' requires root privileges, but sudo is not installed. Re-run as root or install sudo."
  fi
}

progress_bar() {
  local label="$1"
  local pid="$2"
  local frames=("▱▱▱▱▱▱▱▱" "▰▱▱▱▱▱▱▱" "▰▰▱▱▱▱▱▱" "▰▰▰▱▱▱▱▱" "▰▰▰▰▱▱▱▱" "▰▰▰▰▰▱▱▱" "▰▰▰▰▰▰▱▱" "▰▰▰▰▰▰▰▱" "▰▰▰▰▰▰▰▰")
  local idx=0

  if [[ ! -t 1 ]]; then
    printf '%s ...\n' "$label"
    while kill -0 "$pid" >/dev/null 2>&1; do
      sleep 1
    done
    return 0
  fi

  while kill -0 "$pid" >/dev/null 2>&1; do
    printf '\r%s%s%s %s %s' "$C_MAGENTA" "${frames[$idx]}" "$C_RESET" "$label" "working"
    idx=$(((idx + 1) % ${#frames[@]}))
    sleep 0.18
  done
  printf '\r\033[K'
}

run_logged_progress() {
  local label="$1"
  shift
  mkdir -p "$BOOTSTRAP_LOG_DIR"
  step "$label"
  {
    printf '\n===== %s =====\n' "$label"
    printf 'Command:'
    printf ' %q' "$@"
    printf '\nStarted: %s\n\n' "$(date -Iseconds)"
  } >>"$BOOTSTRAP_LOG_FILE"

  set +e
  "$@" >>"$BOOTSTRAP_LOG_FILE" 2>&1 &
  local pid=$!
  progress_bar "$label" "$pid"
  wait "$pid"
  local status=$?
  set -e

  printf 'Finished: %s\nExit code: %s\n' "$(date -Iseconds)" "$status" >>"$BOOTSTRAP_LOG_FILE"
  if [[ "$status" -ne 0 ]]; then
    warn "$label failed. Full log: $BOOTSTRAP_LOG_FILE"
    if have tail; then
      printf '%sLast log lines:%s\n' "$C_YELLOW" "$C_RESET" >&2
      tail -n 40 "$BOOTSTRAP_LOG_FILE" >&2 || true
    fi
    return "$status"
  fi
  success "$label"
}

ensure_system_python() {
  if have python3 || have python; then
    return 0
  fi

  local os
  os="$(uname -s)"
  case "$os" in
    Darwin)
      if ! have brew; then
        log "Homebrew is required to install Python automatically on macOS; installing Homebrew first."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [[ -x /opt/homebrew/bin/brew ]]; then
          eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -x /usr/local/bin/brew ]]; then
          eval "$(/usr/local/bin/brew shellenv)"
        fi
      fi
      have brew || fail "Homebrew installation finished but brew is not on PATH. Restart the shell and retry."
      log "Installing Python via Homebrew."
      brew install python
      ;;
    Linux)
      log "Python was not found; attempting automatic Python installation for this Linux distribution."
      if have apt-get; then
        run_sudo apt-get update
        run_sudo apt-get install -y python3 python3-venv python3-pip curl ca-certificates
      elif have dnf; then
        run_sudo dnf install -y python3 python3-pip curl ca-certificates
      elif have yum; then
        run_sudo yum install -y python3 python3-pip curl ca-certificates
      elif have zypper; then
        run_sudo zypper --non-interactive install python3 python3-pip curl ca-certificates
      elif have pacman; then
        run_sudo pacman -Sy --noconfirm python python-pip curl ca-certificates
      elif have apk; then
        run_sudo apk add --no-cache python3 py3-pip curl ca-certificates
      else
        fail "Unsupported Linux package manager. Install Python 3.11+ with venv/pip, then retry."
      fi
      ;;
    *)
      fail "Unsupported platform '$os'. Install Python 3.11+ with venv/pip, then retry."
      ;;
  esac

  have python3 || have python || fail "Python installation did not put python3/python on PATH."
}

python_bin() {
  if have python3; then
    command -v python3
  elif have python; then
    command -v python
  else
    return 1
  fi
}

ensure_venv_support() {
  local py="$1"
  if "$py" -m venv --help >/dev/null 2>&1; then
    return 0
  fi

  if [[ "$(uname -s)" != "Linux" ]]; then
    fail "Python venv support is unavailable for $py. Install a Python distribution with venv support."
  fi

  log "Python venv support is missing; attempting to install the OS venv package."
  if have apt-get; then
    run_sudo apt-get update
    run_sudo apt-get install -y python3-venv python3-pip
  elif have dnf; then
    run_sudo dnf install -y python3 python3-pip
  elif have yum; then
    run_sudo yum install -y python3 python3-pip
  elif have zypper; then
    run_sudo zypper --non-interactive install python3 python3-pip
  elif have pacman; then
    run_sudo pacman -Sy --noconfirm python python-pip
  elif have apk; then
    run_sudo apk add --no-cache python3 py3-pip
  fi

  "$py" -m venv --help >/dev/null 2>&1 || fail "Python venv support is still unavailable after installation attempt."
}

create_or_repair_venv() {
  local py="$1"
  ensure_venv_support "$py"

  if [[ -x .venv/bin/python ]]; then
    return 0
  fi

  if ! run_logged_progress "Creating .venv with $py" "$py" -m venv .venv; then
    warn "Initial virtualenv creation failed; removing partial .venv and retrying once."
    rm -rf .venv
    run_logged_progress "Creating .venv with $py (retry)" "$py" -m venv .venv
  fi
}

install_python_deps() {
  local venv_python="$1"
  mkdir -p "$BOOTSTRAP_LOG_DIR"
  log "Setup log: $BOOTSTRAP_LOG_FILE"
  step "Preparing Python packaging tools"
  "$venv_python" -m ensurepip --upgrade >>"$BOOTSTRAP_LOG_FILE" 2>&1 || true
  run_logged_progress "Updating pip, setuptools and wheel" "$venv_python" -m pip install --upgrade --progress-bar off pip setuptools wheel

  run_logged_progress "Installing project dependencies from requirements.txt" "$venv_python" -m pip install --progress-bar off -r requirements.txt
}

bootstrap_python_env() {
  mkdir -p "$BOOTSTRAP_LOG_DIR"
  log "Setup log: $BOOTSTRAP_LOG_FILE"
  ensure_system_python
  local py
  py="$(python_bin)"
  create_or_repair_venv "$py"
  install_python_deps .venv/bin/python
}
