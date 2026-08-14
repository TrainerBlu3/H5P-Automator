@echo off
cd /d "%~dp0"

set PY=
py --version >nul 2>&1
if not errorlevel 1 set PY=py
if "%PY%"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 set PY=python
)
if "%PY%"=="" (
    echo ERROR: Python is not installed or not on PATH.
    echo Download it from https://www.python.org/downloads/
    pause
    exit /b 1
)

%PY% -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    %PY% -m pip install -r requirements.txt
)

if not exist ".playwright_installed" (
    echo Installing Playwright browser ^(first time only^)...
    %PY% -m playwright install chromium
    echo installed > .playwright_installed
)

%PY% gui_h5p.py
pause
