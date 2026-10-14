@echo off
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile separator
if errorlevel 1 (
  echo Separation worker setup failed. Read the message above.
  pause
  exit /b 1
)
echo Separation worker ready. Restart KOTO, open Separate, and download your chosen model.
pause
