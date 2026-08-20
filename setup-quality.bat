@echo off
setlocal
cd /d "%~dp0"

echo Creating the isolated TripoSG Quality environment...
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run setup.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\prepare_third_party.py
if errorlevel 1 goto :failed
if not exist ".venv-quality\Scripts\python.exe" py -3.11 -m venv .venv-quality
if errorlevel 1 goto :failed
".venv-quality\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
".venv-quality\Scripts\python.exe" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 goto :failed
".venv-quality\Scripts\python.exe" -m pip install -r requirements-quality.txt
if errorlevel 1 goto :failed
echo Quality mode is installed. Its official weights download on the first Quality generation.
pause
exit /b 0

:failed
echo Quality setup failed. Review the error above and run setup-quality.bat again.
pause
exit /b 1
