@echo off
cd /d "%~dp0"
echo This installs a local Ollama runtime and Qwen3 14B weights. Allow roughly 12 GB of disk space.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile translation
if errorlevel 1 echo Translation setup failed. Read the message above.
pause
