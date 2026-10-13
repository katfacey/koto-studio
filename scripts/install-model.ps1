param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("whisper", "audio", "piper", "xtts")]
    [string]$Model
)
$ErrorActionPreference = "Stop"
$StudioRoot = Split-Path -Parent $PSScriptRoot
Set-Location $StudioRoot
function Invoke-Checked([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE" }
}
$WorkerDir = Join-Path ".workers" $Model
$WorkerPython = Join-Path $WorkerDir "Scripts\python.exe"
if (-not (Test-Path $WorkerPython)) {
    Invoke-Checked "py" @("-3.11", "-m", "venv", $WorkerDir)
}
Invoke-Checked $WorkerPython @("-m", "pip", "install", "--upgrade", "pip")
switch ($Model) {
    "whisper" {
        Invoke-Checked $WorkerPython @("-m", "pip", "install", "faster-whisper>=1.1,<2", "ctranslate2>=4.6,<5")
        Write-Host "CUDA speech recognition also needs compatible CUDA 12 cuBLAS and cuDNN 9 DLLs on PATH. CPU mode is available. See README.md."
    }
    "audio" {
        Invoke-Checked $WorkerPython @("-m", "pip", "install", "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu128")
        Invoke-Checked $WorkerPython @("-m", "pip", "install", "demucs>=4,<5", "pyannote.audio>=3.3,<4", "-c", "scripts\torch-constraints.txt")
        Invoke-Checked $WorkerPython @("scripts\check_gpu.py")
    }
    "piper" {
        Invoke-Checked $WorkerPython @("-m", "pip", "install", "piper-tts>=1.3,<2")
        Write-Host "Download an English Piper .onnx voice and matching .onnx.json, then choose the .onnx path in Model manager."
    }
    "xtts" {
        Invoke-Checked $WorkerPython @("-m", "pip", "install", "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cu128")
        Invoke-Checked $WorkerPython @("-m", "pip", "install", "coqui-tts>=0.27,<1", "soundfile", "-c", "scripts\torch-constraints.txt")
        Invoke-Checked $WorkerPython @("scripts\check_gpu.py")
        Write-Host "Provision XTTS v2 model files locally, configure their folder, and attach a speaker reference. Review the model license when obtaining the files."
    }
}
Write-Host "Worker installed. Click Refresh status in Model manager. Model weights are not included."
