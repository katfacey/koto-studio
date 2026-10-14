@echo off
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile qwen-design
if errorlevel 1 (
  echo Voice setup failed. Read the message above.
  pause
  exit /b 1
)
echo Voice worker ready. Restart KOTO.
pause
