$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not $env:AGENT_SETUP_ASSUME_YES) {
  $env:AGENT_SETUP_ASSUME_YES = "1"
}

$LogDir = Join-Path $ProjectRoot "logs\setup"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("bootstrap-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

function Write-Step($Message) {
  Write-Host "▶ " -ForegroundColor Blue -NoNewline
  Write-Host $Message -ForegroundColor White
}

function Write-Success($Message) {
  Write-Host "✓ " -ForegroundColor Green -NoNewline
  Write-Host $Message -ForegroundColor Green
}

function Write-Warn($Message) {
  Write-Host "[bootstrap] warning: " -ForegroundColor Yellow -NoNewline
  Write-Host $Message -ForegroundColor Yellow
}

function Test-Command($Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-LoggedStep($Label, [string[]]$CommandLine) {
  Write-Step $Label
  Add-Content -Path $LogFile -Encoding UTF8 -Value ""
  Add-Content -Path $LogFile -Encoding UTF8 -Value "===== $Label ====="
  Add-Content -Path $LogFile -Encoding UTF8 -Value ("Command: " + ($CommandLine -join " "))
  Add-Content -Path $LogFile -Encoding UTF8 -Value ("Started: " + (Get-Date -Format o))

  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $CommandLine[0]
  for ($i = 1; $i -lt $CommandLine.Count; $i++) {
    [void]$psi.ArgumentList.Add($CommandLine[$i])
  }
  $psi.WorkingDirectory = $ProjectRoot
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $process = [System.Diagnostics.Process]::Start($psi)

  $frames = @("▱▱▱▱▱▱▱▱", "▰▱▱▱▱▱▱▱", "▰▰▱▱▱▱▱▱", "▰▰▰▱▱▱▱▱", "▰▰▰▰▱▱▱▱", "▰▰▰▰▰▱▱▱", "▰▰▰▰▰▰▱▱", "▰▰▰▰▰▰▰▱", "▰▰▰▰▰▰▰▰")
  $idx = 0
  while (-not $process.HasExited) {
    Write-Progress -Activity $Label -Status $frames[$idx] -PercentComplete (($idx + 1) * 100 / $frames.Count)
    $idx = ($idx + 1) % $frames.Count
    Start-Sleep -Milliseconds 180
  }
  Write-Progress -Activity $Label -Completed

  $stdout = $process.StandardOutput.ReadToEnd()
  $stderr = $process.StandardError.ReadToEnd()
  if ($stdout) { Add-Content -Path $LogFile -Encoding UTF8 -Value $stdout }
  if ($stderr) { Add-Content -Path $LogFile -Encoding UTF8 -Value $stderr }
  Add-Content -Path $LogFile -Encoding UTF8 -Value ("Finished: " + (Get-Date -Format o))
  Add-Content -Path $LogFile -Encoding UTF8 -Value ("Exit code: " + $process.ExitCode)

  if ($process.ExitCode -ne 0) {
    Write-Warn "$Label failed. Full log: $LogFile"
    if (Test-Path $LogFile) {
      Write-Host "Last log lines:" -ForegroundColor Yellow
      Get-Content $LogFile -Tail 40
    }
    throw "$Label failed with exit code $($process.ExitCode)"
  }
  Write-Success $Label
}

function Install-PythonIfMissing {
  if ((Test-Command py) -or (Test-Command python)) {
    return
  }

  if (-not (Test-Command winget)) {
    throw "Python was not found and winget is unavailable. Install Python 3.11+ from https://www.python.org/downloads/windows/ and retry."
  }

  Invoke-LoggedStep "Installing Python via winget" @("winget", "install", "-e", "--id", "Python.Python.3.12", "--accept-package-agreements", "--accept-source-agreements")

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
  Write-Step "Creating .venv..."
  Invoke-Python @("-m", "venv", ".venv")
  Write-Success "Created .venv"
}

Write-Host "[bootstrap] Setup log: $LogFile" -ForegroundColor Cyan
& ".venv\Scripts\python.exe" -m ensurepip --upgrade *> $null
Invoke-LoggedStep "Updating pip, setuptools and wheel" @(".venv\Scripts\python.exe", "-m", "pip", "install", "--upgrade", "--progress-bar", "off", "pip", "setuptools", "wheel")
Invoke-LoggedStep "Installing project dependencies from requirements.txt" @(".venv\Scripts\python.exe", "-m", "pip", "install", "--progress-bar", "off", "-r", "requirements.txt")
Invoke-LoggedStep "Running automatic setup checks" @(".venv\Scripts\python.exe", "-m", "app.setup_auto")

$hostName = if ($env:AGENT_WEB_HOST) { $env:AGENT_WEB_HOST } else { "127.0.0.1" }
$port = if ($env:AGENT_WEB_PORT) { $env:AGENT_WEB_PORT } else { "8000" }
Write-Success "Starting web server on ${hostName}:${port}"
& ".venv\Scripts\python.exe" -m uvicorn app.web:app --host $hostName --port $port @args
