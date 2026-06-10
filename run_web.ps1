$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not $env:AGENT_SETUP_ASSUME_YES) {
  $env:AGENT_SETUP_ASSUME_YES = "1"
}

function Test-Command($Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Install-PythonIfMissing {
  if ((Test-Command py) -or (Test-Command python)) {
    return
  }

  if (-not (Test-Command winget)) {
    throw "Python was not found and winget is unavailable. Install Python 3.11+ from https://www.python.org/downloads/windows/ and retry."
  }

  Write-Host "Python was not found; installing Python via winget..."
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements

  if (-not ((Test-Command py) -or (Test-Command python))) {
    $machinePython = Join-Path $Env:LocalAppData "Programs\Python\Python312\python.exe"
    if (Test-Path $machinePython) {
      $script:PythonExe = $machinePython
      return
    }
    throw "Python installation completed but Python is not on PATH. Restart PowerShell and retry."
  }
}

function Get-PythonExe {
  if ($script:PythonExe) { return $script:PythonExe }
  if (Test-Command py) { return "py" }
  if (Test-Command python) { return "python" }
  throw "Python executable not found."
}

function Invoke-Python($Arguments) {
  $python = Get-PythonExe
  if ($python -eq "py") {
    & py -3 @Arguments
  } else {
    & $python @Arguments
  }
}

Install-PythonIfMissing

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating .venv..."
  Invoke-Python @("-m", "venv", ".venv")
}

& ".venv\Scripts\python.exe" -m ensurepip --upgrade | Out-Null
& ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m app.setup_auto

$hostName = if ($env:AGENT_WEB_HOST) { $env:AGENT_WEB_HOST } else { "127.0.0.1" }
$port = if ($env:AGENT_WEB_PORT) { $env:AGENT_WEB_PORT } else { "8000" }
& ".venv\Scripts\python.exe" -m uvicorn app.web:app --host $hostName --port $port @args
