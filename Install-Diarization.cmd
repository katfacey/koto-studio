@echo off
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" -Profile diarization
if errorlevel 1 (
  echo Diarization setup failed. Read the message above.
  pause
  exit /b 1
)
echo Diarization model files are ready. Restart KOTO and retry Speakers.
pause
