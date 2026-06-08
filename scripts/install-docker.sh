#!/usr/bin/env bash
set -euo pipefail

case "$(uname -s)" in
  Darwin)
    INSTALL_BREW="no"
    if ! command -v brew >/dev/null 2>&1; then
      echo "Homebrew is not installed."
      # Check if standard input is a tty
      if [ -t 0 ]; then
        read -p "Do you want to install Homebrew first? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
          INSTALL_BREW="yes"
        fi
      else
        echo "Non-interactive terminal, falling back to official Docker DMG installation."
      fi
      
      if [ "$INSTALL_BREW" = "yes" ]; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Try to find brew again and add to path for current session
        if [ -f "/opt/homebrew/bin/brew" ]; then
          eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f "/usr/local/bin/brew" ]; then
          eval "$(/usr/local/bin/brew shellenv)"
        fi
      fi
    fi

    if command -v brew >/dev/null 2>&1; then
      echo "Installing Docker Desktop via Homebrew Cask..."
      brew install --cask docker
    else
      echo "Installing Docker Desktop via official DMG installer..."
      ARCH=$(uname -m)
      if [ "$ARCH" = "arm64" ]; then
        DMG_URL="https://desktop.docker.com/mac/main/arm64/Docker.dmg"
      else
        DMG_URL="https://desktop.docker.com/mac/main/amd64/Docker.dmg"
      fi
      DMG_PATH="/tmp/Docker.dmg"
      echo "Downloading Docker DMG from $DMG_URL..."
      curl -L "$DMG_URL" -o "$DMG_PATH"
      echo "Mounting $DMG_PATH..."
      hdiutil attach -nobrowse -readonly "$DMG_PATH"
      echo "Running official installer (requires sudo privileges)..."
      sudo /Volumes/Docker/Docker.app/Contents/MacOS/install --accept-license --user="$(whoami)"
      echo "Detaching /Volumes/Docker..."
      hdiutil detach /Volumes/Docker || true
      rm -f "$DMG_PATH"
    fi
    open -a Docker || true
    echo "Docker Desktop install requested. Wait for Docker Desktop to finish starting, then run setup again."
    ;;
  Linux)
    if [ -f /proc/version ] && grep -qi 'microsoft\|wsl' /proc/version 2>/dev/null; then
      echo "WSL detected. Install Docker Desktop on Windows and enable WSL integration."
      echo "Do not install Docker Engine directly inside WSL for this setup."
      exit 1
    fi
    tmp_script="$(mktemp -t agent-framework-docker.XXXXXX.sh)"
    curl -fsSL https://get.docker.com -o "$tmp_script"
    sudo sh "$tmp_script"
    rm -f "$tmp_script"
    if command -v systemctl >/dev/null 2>&1; then
      sudo systemctl enable --now docker || true
    fi
    if [ -n "${USER:-}" ]; then
      sudo usermod -aG docker "$USER" || true
      echo "Added $USER to docker group. Log out and back in if docker still requires sudo."
    fi
    ;;
  *)
    echo "Unsupported platform for automatic Docker install: $(uname -s)"
    exit 1
    ;;
esac
