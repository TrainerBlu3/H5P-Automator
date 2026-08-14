@echo off
echo ============================================
echo   H5P Automator - Setup
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not on PATH.
    echo Download it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

echo Installing Python dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)

echo.
echo Installing Playwright browser (Chromium)...
playwright install chromium
if errorlevel 1 (
    echo ERROR: Playwright browser install failed.
    pause
    exit /b 1
)
type nul > .playwright_installed

echo.
echo ============================================
echo   Setup complete! Run run.bat to start.
echo ============================================
pause
