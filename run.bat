@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Setup is incomplete. Run setup.bat first.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo Frontend build is missing. Run setup.bat first.
  pause
  exit /b 1
)

start "" http://127.0.0.1:7860
".venv\Scripts\python.exe" -m backend.main

