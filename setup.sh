#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo "  H5P Automator - Setup"
echo "============================================"
echo

cd "$(dirname "$0")"

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python is not installed or not on PATH."
    read -rp "Press Enter to exit..."
    exit 1
fi

python3 --version

echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing Python dependencies..."
if ! pip install -r requirements.txt; then
    echo "ERROR: pip install failed."
    read -rp "Press Enter to exit..."
    exit 1
fi

echo
echo "Installing Playwright browser (Chromium)..."
if ! playwright install chromium; then
    echo "ERROR: Playwright browser install failed."
    read -rp "Press Enter to exit..."
    exit 1
fi
touch .playwright_installed

echo
echo "============================================"
echo "  Setup complete! Run: source .venv/bin/activate && python gui_h5p.py"
echo "============================================"
read -rp "Press Enter to exit..."
