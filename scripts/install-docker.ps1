$ErrorActionPreference = "Stop"

function Test-Command($Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

if (Test-Command docker) {
  Write-Host "Docker CLI is already installed."
} else {
  if (-not (Test-Command winget)) {
    Write-Host "winget is required to install Docker Desktop automatically on Windows."
    Write-Host "Install Docker Desktop manually from https://www.docker.com/products/docker-desktop/ and run setup again."
    exit 1
  }

  Write-Host "Installing Docker Desktop via winget..."
  winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
}

$dockerDesktopCandidates = @(
  (Join-Path $Env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
  (Join-Path $Env:LocalAppData "Docker\Docker Desktop.exe")
)

foreach ($dockerDesktop in $dockerDesktopCandidates) {
  if (Test-Path $dockerDesktop) {
    Start-Process $dockerDesktop
    Write-Host "Docker Desktop start requested: $dockerDesktop"
    break
  }
}

Write-Host "Docker Desktop install/start requested. Enable Linux containers/WSL integration if prompted, wait for Docker to start, then run setup again if this run times out."
