$ErrorActionPreference = "Stop"
$Failed = $false
Get-ChildItem -LiteralPath $PSScriptRoot -Filter "*.ps1" -File | ForEach-Object {
    $Tokens = $null
    $ParseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$Tokens, [ref]$ParseErrors) | Out-Null
    if ($ParseErrors.Count -gt 0) {
        $Failed = $true
        Write-Host "Parse errors in $($_.Name):"
        $ParseErrors | ForEach-Object { Write-Host $_.Message }
    }
}
if ($Failed) { exit 1 }
Write-Host "All PowerShell installers parsed successfully."
