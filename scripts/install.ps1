param(
    [Alias("Profile")]
    [ValidateSet("core", "whisper", "audio", "piper", "xtts", "translation", "models", "all")]
    [string]$SetupProfile = "core",
    [string]$TranslationModel = ""
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$StudioRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $StudioRoot "runtime"
$DownloadsDir = Join-Path $RuntimeDir "downloads"
$Manifest = Get-Content (Join-Path $PSScriptRoot "runtime-manifest.json") -Raw -Encoding UTF8 | ConvertFrom-Json
Set-Location -LiteralPath $StudioRoot

if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
    throw "This installer targets x64 Windows + NVIDIA. ARM64/x86 are not supported by this release."
}
New-Item -ItemType Directory -Force -Path $RuntimeDir, $DownloadsDir | Out-Null
$env:UV_CACHE_DIR = Join-Path $RuntimeDir "cache\uv"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeDir "python"
$env:UV_PYTHON_BIN_DIR = Join-Path $RuntimeDir "python\bin"
$env:UV_PYTHON_PREFERENCE = "only-managed"
$env:UV_PYTHON_INSTALL_REGISTRY = "0"
$env:UV_PYTHON_INSTALL_BIN = "0"
$env:HF_HOME = Join-Path $RuntimeDir "cache\huggingface"
$env:TORCH_HOME = Join-Path $RuntimeDir "cache\torch"

function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
}

function Get-Download([string]$Url, [string]$Destination, [string]$Sha256 = "") {
    if (Test-Path -LiteralPath $Destination) {
        if ($Sha256 -and (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -eq $Sha256.ToLowerInvariant()) { return }
        if (-not $Sha256) { return }
    }
    Write-Host "Downloading $Url"
    $TemporaryDownload = "$Destination.partial"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $TemporaryDownload -TimeoutSec 7200
        if ($Sha256 -and (Get-FileHash -LiteralPath $TemporaryDownload -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256.ToLowerInvariant()) {
            throw "Checksum mismatch for $Url. The download was not installed."
        }
        Move-Item -LiteralPath $TemporaryDownload -Destination $Destination -Force
    } finally {
        if (Test-Path -LiteralPath $TemporaryDownload) { Remove-Item -LiteralPath $TemporaryDownload -Force }
    }
}

function Install-ArchiveTool([string]$Name, $Release, [string]$ExecutableName, [string]$Destination) {
    $VersionMarker = Join-Path $Destination "VERSION"
    if ((Test-Path -LiteralPath (Join-Path $Destination $ExecutableName)) -and (Test-Path -LiteralPath $VersionMarker)) {
        if ((Get-Content -LiteralPath $VersionMarker -Raw).Trim() -eq $Release.version) { return }
    }
    $Archive = Join-Path $DownloadsDir "$Name-$($Release.version).zip"
    Get-Download $Release.url $Archive $Release.sha256
    $Staging = Join-Path $DownloadsDir "$Name-staging"
    if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Staging, $Destination | Out-Null
    try {
        Expand-Archive -LiteralPath $Archive -DestinationPath $Staging -Force
        $Found = Get-ChildItem -LiteralPath $Staging -Filter $ExecutableName -Recurse -File | Select-Object -First 1
        if (-not $Found) { throw "$Name archive does not contain $ExecutableName" }
        Get-ChildItem -LiteralPath $Found.Directory.FullName -Force | Copy-Item -Destination $Destination -Recurse -Force
        Set-Content -LiteralPath $VersionMarker -Value $Release.version -Encoding ASCII
    } finally {
        if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
    }
}

Install-ArchiveTool "uv" $Manifest.uv "uv.exe" (Join-Path $RuntimeDir "uv")
$UvExe = Join-Path $RuntimeDir "uv\uv.exe"
Invoke-Checked $UvExe @("--no-config", "python", "install", "--no-bin", "--no-registry", $Manifest.python)
$PythonOutput = & $UvExe --no-config python find --system $Manifest.python
if ($LASTEXITCODE -ne 0) { throw "Managed Python could not be located" }
$ManagedPython = ($PythonOutput | Select-Object -Last 1).Trim()
if (-not (Test-Path -LiteralPath $ManagedPython)) { throw "Managed Python is missing: $ManagedPython" }
$ManagedPythonRoot = [IO.Path]::GetFullPath($env:UV_PYTHON_INSTALL_DIR).TrimEnd('\') + '\'
if (-not ([IO.Path]::GetFullPath($ManagedPython).StartsWith($ManagedPythonRoot, [StringComparison]::OrdinalIgnoreCase))) {
    throw "Python must be owned by this application's runtime directory"
}

function Ensure-StudioEnvironment([string]$Directory) {
    $WorkerPython = Join-Path $Directory "Scripts\python.exe"
    $Config = Join-Path $Directory "pyvenv.cfg"
    $Recreate = $true
    if ((Test-Path -LiteralPath $WorkerPython) -and (Test-Path -LiteralPath $Config)) {
        $ConfigText = Get-Content -LiteralPath $Config -Raw -Encoding UTF8
        if ($ConfigText.IndexOf($env:UV_PYTHON_INSTALL_DIR, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            try { & $WorkerPython -c "import sys" 2>$null; $Recreate = ($LASTEXITCODE -ne 0) } catch { $Recreate = $true }
        }
    }
    if ($Recreate) {
        Invoke-Checked $UvExe @("--no-config", "venv", "--clear", "--seed", "--python", $ManagedPython, $Directory)
    }
    return $WorkerPython
}

Install-ArchiveTool "ffmpeg" $Manifest.ffmpeg "ffmpeg.exe" (Join-Path $RuntimeDir "ffmpeg\bin")
$CorePython = Ensure-StudioEnvironment (Join-Path $StudioRoot ".venv")
Invoke-Checked $UvExe @("--no-config", "pip", "install", "--python", $CorePython, "-r", (Join-Path $StudioRoot "backend\requirements.txt"))
Invoke-Checked $CorePython @((Join-Path $PSScriptRoot "build_frontend.py"))
foreach ($Tool in @("ffmpeg", "ffprobe")) {
    Invoke-Checked (Join-Path $RuntimeDir "ffmpeg\bin\$Tool.exe") @("-version")
}
$Receipt = @{ version=$Manifest.version; python=$ManagedPython; core=$CorePython; ffmpeg=(Join-Path $RuntimeDir "ffmpeg\bin\ffmpeg.exe"); installed=(Get-Date).ToUniversalTime().ToString("o") }
$Receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $RuntimeDir "installed.json") -Encoding UTF8

function Install-StudioWorker([string]$Worker) {
    $WorkerPython = Ensure-StudioEnvironment (Join-Path $StudioRoot ".workers\$Worker")
    if ($Worker -in @("audio", "xtts", "whisper")) {
        # Torch provides app-owned cuBLAS/cuDNN DLLs for CTranslate2 as well.
        Invoke-Checked $UvExe @("--no-config", "pip", "install", "--python", $WorkerPython, "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu128")
    }
    switch ($Worker) {
        "whisper" { $Packages = @("faster-whisper>=1.1,<2", "ctranslate2>=4.6,<5") }
        "audio" { $Packages = @("demucs>=4,<5", "pyannote.audio>=3.3,<4", "-c", (Join-Path $PSScriptRoot "torch-constraints.txt")) }
        "piper" { $Packages = @("piper-tts>=1.3,<2") }
        "xtts" { $Packages = @("coqui-tts>=0.27,<1", "soundfile", "-c", (Join-Path $PSScriptRoot "torch-constraints.txt")) }
    }
    Invoke-Checked $UvExe (@("--no-config", "pip", "install", "--python", $WorkerPython) + $Packages)
    if ($Worker -in @("audio", "xtts", "whisper")) { Invoke-Checked $WorkerPython @((Join-Path $PSScriptRoot "check_gpu.py")) }
    if ($Worker -eq "piper") {
        $VoiceDir = Join-Path $RuntimeDir "models\piper"
        New-Item -ItemType Directory -Force -Path $VoiceDir | Out-Null
        $Repo = Invoke-RestMethod -Uri "https://huggingface.co/api/models/rhasspy/piper-voices"
        $Revision = $Repo.sha
        if ($Revision -notmatch '^[0-9a-f]{40}$') { throw "Could not resolve the Piper voice revision" }
        $Tree = Invoke-RestMethod -Uri "https://huggingface.co/api/models/rhasspy/piper-voices/tree/$Revision/en/en_US/lessac/medium"
        $VoiceName = "en_US-lessac-medium.onnx"
        $Entry = $Tree | Where-Object { $_.path -eq "en/en_US/lessac/medium/$VoiceName" } | Select-Object -First 1
        $VoiceHash = $Entry.lfs.oid
        if ($VoiceHash -notmatch '^[0-9a-f]{64}$') { throw "Could not verify the Piper voice checksum" }
        $BaseUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/$Revision/en/en_US/lessac/medium"
        Get-Download "$BaseUrl/$VoiceName" (Join-Path $VoiceDir $VoiceName) $VoiceHash
        $ConfigPath = Join-Path $VoiceDir "$VoiceName.json"
        Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/$VoiceName.json" -OutFile $ConfigPath
        # Phoneme keys are Unicode and case-sensitive; Windows PowerShell's JSON
        # object conversion can reject valid keys, and Get-Content defaults to ANSI.
        Invoke-Checked $CorePython @("-c", "import json, pathlib, sys; json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))", $ConfigPath)
        @{revision=$Revision;sha256=$VoiceHash;voice=$VoiceName} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $VoiceDir "source.json") -Encoding UTF8
    }
}

function Install-StudioTranslation {
    Install-ArchiveTool "ollama" $Manifest.ollama "ollama.exe" (Join-Path $RuntimeDir "ollama")
    $SelectedModel = $TranslationModel
    if (-not $SelectedModel) { $SelectedModel = $Manifest.translation_model }
    Invoke-Checked $CorePython @((Join-Path $PSScriptRoot "translation_setup.py"), "--model", $SelectedModel)
}

switch ($SetupProfile) {
    "core" { }
    "models" { foreach ($Worker in @("audio","whisper","piper")) { Install-StudioWorker $Worker } }
    "all" { foreach ($Worker in @("audio","whisper","piper","xtts")) { Install-StudioWorker $Worker }; Install-StudioTranslation }
    "translation" { Install-StudioTranslation }
    default { Install-StudioWorker $SetupProfile }
}
Write-Host "KOTO $SetupProfile setup complete. Tools and caches are inside $StudioRoot. No system PATH changes were made."
Write-Host "Restart KOTO after adding optional runtimes. Use Start.cmd."
