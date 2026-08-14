import os
from pathlib import Path

if os.name == "nt":
    USERDATA_DIR = Path(os.environ["APPDATA"]) / "H5PAutomator"
else:
    USERDATA_DIR = Path.home() / ".local" / "share" / "H5PAutomator"

USERDATA_DIR.mkdir(parents=True, exist_ok=True)

# Playwright storage_state file. Shared by both the Brightspace login flow
# (browser.py) and the Moodle scrape flow (content_checker.py._scrape_moodle) —
# they run in the same browser context, so one file covers both sessions.
SESSION_FILE = str(USERDATA_DIR / "session.json")

CONFIG_FILE = str(USERDATA_DIR / "h5p_automator_config.json")

DOWNLOADS_DIR = USERDATA_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
