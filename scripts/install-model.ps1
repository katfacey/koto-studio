param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("whisper", "audio", "piper", "xtts", "translation", "models", "all")]
    [string]$Model,
    [string]$TranslationModel = ""
)
& (Join-Path $PSScriptRoot "install.ps1") -Profile $Model -TranslationModel $TranslationModel
if (-not $?) { exit 1 }
