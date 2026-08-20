@echo off
setlocal
cd /d "%~dp0"

echo [1/7] Checking NVIDIA GPU...
nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo ERROR: NVIDIA driver tools were not found. Install/update the NVIDIA driver first.
  pause
  exit /b 1
)

echo [2/7] Finding Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo Installing Python 3.11 for the current user...
  winget install --id Python.Python.3.11 --exact --scope user --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto :failed
)

echo [3/7] Creating the isolated environment...
if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv
if errorlevel 1 goto :failed

echo [4/7] Installing CUDA PyTorch 2.5.1...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
".venv\Scripts\python.exe" -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
if errorlevel 1 goto :failed

echo [5/7] Fetching pinned TripoSR and TripoSG sources...
".venv\Scripts\python.exe" scripts\prepare_third_party.py
if errorlevel 1 goto :failed

echo [6/7] Installing Fast mode and app dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo [7/7] Building the local Three.js frontend...
where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js/npm was not found. Install the current Node.js LTS release, then retry.
  goto :failed
)
call npm --prefix frontend install
call npm --prefix frontend run build
if errorlevel 1 goto :failed

".venv\Scripts\python.exe" scripts\verify_environment.py
if errorlevel 1 goto :failed

echo.
echo Setup complete. Run run.bat to launch Forge One.
pause
exit /b 0

:failed
echo.
echo Setup failed. Review the error above, then run setup.bat again.
pause
exit /b 1
