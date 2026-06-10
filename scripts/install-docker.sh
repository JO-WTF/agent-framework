#!/usr/bin/env bash
set -euo pipefail

log() { printf '[install-docker] %s\n' "$*"; }
fail() { printf '[install-docker] error: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

run_sudo() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  else
    fail "'$*' requires root privileges, but sudo is not installed."
  fi
}

assume_yes() {
  case "${AGENT_SETUP_ASSUME_YES:-}" in
    1|true|TRUE|yes|YES|y|Y) return 0 ;;
    0|false|FALSE|no|NO|n|N) return 1 ;;
  esac
  return 0
}

ensure_curl() {
  if have curl; then
    return 0
  fi
  log "curl is missing; installing curl first."
  if have apt-get; then
    run_sudo apt-get update
    run_sudo apt-get install -y curl ca-certificates
  elif have dnf; then
    run_sudo dnf install -y curl ca-certificates
  elif have yum; then
    run_sudo yum install -y curl ca-certificates
  elif have zypper; then
    run_sudo zypper --non-interactive install curl ca-certificates
  elif have pacman; then
    run_sudo pacman -Sy --noconfirm curl ca-certificates
  elif have apk; then
    run_sudo apk add --no-cache curl ca-certificates
  else
    fail "curl is required and no supported package manager was found."
  fi
}

install_homebrew() {
  if have brew; then
    return 0
  fi
  if ! assume_yes && [[ -t 0 ]]; then
    read -r -p "Homebrew is not installed. Install it first? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]] || return 1
  fi
  log "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
}

install_docker_macos_dmg() {
  local arch dmg_url dmg_path volume installer
  arch="$(uname -m)"
  if [[ "$arch" == "arm64" ]]; then
    dmg_url="https://desktop.docker.com/mac/main/arm64/Docker.dmg"
  else
    dmg_url="https://desktop.docker.com/mac/main/amd64/Docker.dmg"
  fi
  dmg_path="/tmp/Docker.dmg"
  volume="/Volumes/Docker"
  installer="$volume/Docker.app/Contents/MacOS/install"

  log "Downloading Docker DMG from $dmg_url..."
  curl -fL --retry 5 --retry-delay 2 -C - "$dmg_url" -o "$dmg_path"
  log "Mounting $dmg_path..."
  hdiutil detach "$volume" >/dev/null 2>&1 || true
  hdiutil attach -nobrowse -readonly "$dmg_path"
  trap 'hdiutil detach /Volumes/Docker >/dev/null 2>&1 || true' EXIT
  log "Running official installer (requires sudo privileges)..."
  run_sudo "$installer" --accept-license --user="$(whoami)"
  hdiutil detach "$volume" >/dev/null 2>&1 || true
  trap - EXIT
  rm -f "$dmg_path"
}

case "$(uname -s)" in
  Darwin)
    ensure_curl
    if have docker; then
      log "Docker CLI is already installed."
    elif install_homebrew && have brew; then
      log "Installing Docker Desktop via Homebrew Cask..."
      brew install --cask docker || install_docker_macos_dmg
    else
      log "Installing Docker Desktop via official DMG installer..."
      install_docker_macos_dmg
    fi
    open -a Docker || true
    log "Docker Desktop install/start requested. Wait for Docker Desktop to finish starting if setup continues to wait."
    ;;
  Linux)
    if [[ -f /proc/version ]] && grep -qi 'microsoft\|wsl' /proc/version 2>/dev/null; then
      log "WSL detected. Install Docker Desktop on Windows and enable WSL integration."
      log "Do not install Docker Engine directly inside WSL for this setup."
      exit 1
    fi
    if have docker; then
      log "Docker CLI is already installed."
    else
      ensure_curl
      tmp_script="$(mktemp -t agent-framework-docker.XXXXXX.sh)"
      curl -fsSL --retry 5 --retry-delay 2 https://get.docker.com -o "$tmp_script"
      run_sudo sh "$tmp_script"
      rm -f "$tmp_script"
    fi
    if have systemctl; then
      run_sudo systemctl enable --now docker || true
    elif have service; then
      run_sudo service docker start || true
    fi
    if [[ -n "${USER:-}" ]] && getent group docker >/dev/null 2>&1; then
      run_sudo usermod -aG docker "$USER" || true
      log "Added $USER to docker group. Log out and back in if docker still requires sudo."
    fi
    ;;
  *)
    fail "Unsupported platform for automatic Docker install: $(uname -s)"
    ;;
esac
