$ErrorActionPreference = "Stop"
Write-Host "KOTO optional model setup (all files remain inside the application folder)"
Write-Host "1. Audio separation + Japanese recognition + English Piper voice (several GB)"
Write-Host "2. XTTS reference voices + official local model weights (several GB)"
Write-Host "3. Local Ollama + Qwen3 14B translation model (roughly 12 GB)"
Write-Host "4. All workers + local translation (roughly 20+ GB; gated/model files may still need provisioning)"
Write-Host "5. Speaker diarization weights (Hugging Face access agreements + read token)"
Write-Host "6. UVR-style separation worker (MDX / VR / BS-RoFormer; choose weights in the editor)"
Write-Host "7. Qwen reusable reference voices"
Write-Host "8. Qwen reference voices + voice design"
Write-Host "9. Cancel"
$Choice = Read-Host "Choose 1-9"
$Profiles = @{ "1"="models"; "2"="xtts"; "3"="translation"; "4"="all"; "5"="diarization"; "6"="separator"; "7"="qwen"; "8"="qwen-design" }
if ($Choice -eq "9") { exit 0 }
if (-not $Profiles.ContainsKey($Choice)) { throw "Choose a number from 1 to 9" }
& (Join-Path $PSScriptRoot "install.ps1") -Profile $Profiles[$Choice]
