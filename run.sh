#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PY=""
if command -v python3 &>/dev/null; then
    PY="python3"
elif command -v python &>/dev/null; then
    PY="python"
else
    echo "ERROR: Python is not installed or not on PATH."
    read -rp "Press Enter to exit..."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PY" -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import PyQt6" &>/dev/null 2>&1; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

if [ ! -f ".playwright_installed" ]; then
    echo "Installing Playwright browser (first time only)..."
    python -m playwright install chromium
    echo "installed" > .playwright_installed
fi

python gui_h5p.py
