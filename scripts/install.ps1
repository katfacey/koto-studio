$ErrorActionPreference = "Stop"
$StudioRoot = Split-Path -Parent $PSScriptRoot
Set-Location $StudioRoot

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
}

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Install Python 3.11 or 3.12 from python.org with the Python launcher enabled, then run Install.cmd again."
}
$PythonVersion = "-3.11"
try {
    & py -3.11 -c "import sys" 2>$null
    $Has311 = ($LASTEXITCODE -eq 0)
} catch { $Has311 = $false }
if (-not $Has311) {
    $PythonVersion = "-3.12"
    try {
        & py -3.12 -c "import sys" 2>$null
        $Has312 = ($LASTEXITCODE -eq 0)
    } catch { $Has312 = $false }
    if (-not $Has312) { throw "Python 3.11 or 3.12 is required." }
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Invoke-Checked "py" @($PythonVersion, "-m", "venv", ".venv")
}
Invoke-Checked ".venv\Scripts\python.exe" @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked ".venv\Scripts\python.exe" @("-m", "pip", "install", "-r", "backend\requirements.txt")
Invoke-Checked ".venv\Scripts\python.exe" @("scripts\build_frontend.py")
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "FFmpeg is missing. Install it with: winget install --id Gyan.FFmpeg -e"
    Write-Host "Then open a new terminal or restart Windows to refresh PATH. The editor can open before FFmpeg is installed."
}
Write-Host "Core editor installed. Optional model workers are installed separately with scripts/install-model.ps1."
