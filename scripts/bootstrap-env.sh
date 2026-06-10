#!/usr/bin/env bash
# Shared bootstrap helpers for fresh Linux/macOS systems.
# shellcheck shell=bash

set -euo pipefail

log() {
  printf '[bootstrap] %s\n' "$*"
}

warn() {
  printf '[bootstrap] warning: %s\n' "$*" >&2
}

fail() {
  printf '[bootstrap] error: %s\n' "$*" >&2
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

  log "Creating .venv with $py."
  if ! "$py" -m venv .venv; then
    warn "Initial virtualenv creation failed; removing partial .venv and retrying once."
    rm -rf .venv
    "$py" -m venv .venv
  fi
}

install_python_deps() {
  local venv_python="$1"
  log "Installing/updating Python packaging tools."
  "$venv_python" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$venv_python" -m pip install --upgrade pip setuptools wheel

  log "Installing project Python dependencies from requirements.txt."
  "$venv_python" -m pip install -r requirements.txt
}

bootstrap_python_env() {
  ensure_system_python
  local py
  py="$(python_bin)"
  create_or_repair_venv "$py"
  install_python_deps .venv/bin/python
}
