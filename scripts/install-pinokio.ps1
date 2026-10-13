param([string]$PinokioHome = "")
$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
if (-not $PinokioHome) {
    Add-Type -AssemblyName System.Windows.Forms
    $Picker = New-Object System.Windows.Forms.FolderBrowserDialog
    $Picker.Description = "Select your Pinokio HOME folder (the folder containing api). Find its location in Pinokio Settings."
    $DefaultHome = Join-Path $env:USERPROFILE "pinokio"
    if (Test-Path -LiteralPath $DefaultHome) { $Picker.SelectedPath = $DefaultHome }
    try {
        if ($Picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { Write-Host "Cancelled"; exit 0 }
        $PinokioHome = $Picker.SelectedPath
    } finally { $Picker.Dispose() }
}
$PinokioHome = [IO.Path]::GetFullPath($PinokioHome)
$ApiDirectory = Join-Path $PinokioHome "api"
if (-not (Test-Path -LiteralPath $ApiDirectory -PathType Container)) {
    throw "The selected folder does not contain api. Select Pinokio's Home folder from Settings."
}
$TargetApp = Join-Path $ApiDirectory "koto-studio"
$SameFolder = [IO.Path]::GetFullPath($SourceRoot).TrimEnd('\') -eq [IO.Path]::GetFullPath($TargetApp).TrimEnd('\')
if (-not $SameFolder) {
    if (Test-Path -LiteralPath $TargetApp) {
        $Entry = Join-Path $TargetApp "pinokio.js"
        if (-not (Test-Path -LiteralPath $Entry) -or -not (Select-String -LiteralPath $Entry -Pattern "KOTO Studio" -Quiet)) {
            throw "The target folder already contains another application. Nothing was overwritten."
        }
    }
    New-Item -ItemType Directory -Force -Path $TargetApp | Out-Null
    $SourceFiles = Get-Content (Join-Path $PSScriptRoot "source-files.json") -Raw | ConvertFrom-Json
    foreach ($RelativePath in $SourceFiles) {
        $SourceFile = [IO.Path]::GetFullPath((Join-Path $SourceRoot $RelativePath))
        $TargetFile = [IO.Path]::GetFullPath((Join-Path $TargetApp $RelativePath))
        if (-not $SourceFile.StartsWith(([IO.Path]::GetFullPath($SourceRoot).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase) -or -not $TargetFile.StartsWith(([IO.Path]::GetFullPath($TargetApp).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
            throw "Invalid source file entry"
        }
        if (-not (Test-Path -LiteralPath $SourceFile -PathType Leaf)) { throw "Source archive is incomplete: $RelativePath" }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TargetFile) | Out-Null
        Copy-Item -LiteralPath $SourceFile -Destination $TargetFile -Force
    }
}
& (Join-Path $TargetApp "scripts\install.ps1") -Profile core
if (-not $?) { throw "Core installation failed" }
Write-Host "Installed at $TargetApp"
Write-Host "Open or restart Pinokio, go to Downloaded, select KOTO Studio, then Start."
Write-Host "Optional model installers are in the KOTO menu. Your project data and installed runtimes were preserved."
