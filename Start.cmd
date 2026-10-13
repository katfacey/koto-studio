@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0runtime\installed.json" goto setup
if not exist "%~dp0.venv\Scripts\python.exe" goto setup
"%~dp0.venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 goto setup
:run
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\launch.py" %*
if errorlevel 1 pause
exit /b
:setup
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile core
if errorlevel 1 (
  pause
  exit /b 1
)
goto run
