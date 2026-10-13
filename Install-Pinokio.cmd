@echo off
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0scripts\install-pinokio.ps1" %*
if errorlevel 1 echo Pinokio setup failed. Read the message above.
pause
