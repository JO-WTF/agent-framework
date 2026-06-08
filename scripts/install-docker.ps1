$ErrorActionPreference = "Stop"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
  Write-Host "winget is required to install Docker Desktop automatically on Windows."
  Write-Host "Install Docker Desktop manually from https://www.docker.com/products/docker-desktop/ and run setup again."
  exit 1
}

winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements

$dockerDesktop = Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
if (Test-Path $dockerDesktop) {
  Start-Process $dockerDesktop
}

Write-Host "Docker Desktop install requested. Enable Linux containers/WSL integration if prompted, wait for Docker to start, then run setup again."
