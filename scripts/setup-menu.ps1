$ErrorActionPreference = "Stop"
Write-Host "KOTO optional model setup (all files remain inside the application folder)"
Write-Host "1. Audio separation + Japanese recognition + English Piper voice (several GB)"
Write-Host "2. XTTS reference voices + official local model weights (several GB)"
Write-Host "3. Local Ollama + Qwen3 14B translation model (roughly 12 GB)"
Write-Host "4. All workers + local translation (roughly 20+ GB; gated/model files may still need provisioning)"
Write-Host "5. Speaker diarization weights (Hugging Face access agreements + read token)"
Write-Host "6. Cancel"
$Choice = Read-Host "Choose 1-6"
$Profiles = @{ "1"="models"; "2"="xtts"; "3"="translation"; "4"="all"; "5"="diarization" }
if ($Choice -eq "6") { exit 0 }
if (-not $Profiles.ContainsKey($Choice)) { throw "Choose a number from 1 to 6" }
& (Join-Path $PSScriptRoot "install.ps1") -Profile $Profiles[$Choice]
