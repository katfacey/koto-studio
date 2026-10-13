@echo off
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile xtts
if errorlevel 1 (
  echo XTTS reference voices setup failed. Read the message above.
  pause
  exit /b 1
)
echo XTTS reference voices are ready. Restart KOTO and retry Generate.
pause
