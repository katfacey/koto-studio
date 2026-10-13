@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install.ps1
if errorlevel 1 (
  echo Installation failed. Read the message above.
  pause
  exit /b 1
)
echo Installation complete. Double-click Start.cmd to open KOTO Studio.
pause
