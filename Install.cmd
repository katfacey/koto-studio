@echo off
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile core
if errorlevel 1 (
  echo Installation failed. Read the message above.
  pause
  exit /b 1
)
echo Installation complete. Double-click Start.cmd to open KOTO Studio.
pause
