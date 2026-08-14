import os
from pathlib import Path

APP_NAME = "H5P Automator"
VERSION = "v1.0.0"

_ROOT = Path(__file__).parent.parent
ICON_PATH = str(_ROOT / "assets" / "icon.ico")

if os.name == "nt":
    USERDATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "H5PAutomator"
else:
    USERDATA_DIR = Path.home() / ".local" / "share" / "H5PAutomator"
USERDATA_DIR.mkdir(parents=True, exist_ok=True)

_CHECK_SVG = USERDATA_DIR / "check.svg"
_CHECK_SVG.write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
    '<polyline points="1.5,6 4.5,9.5 10.5,2.5" stroke="white" stroke-width="1.8"'
    ' fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
CHECK_SVG_PATH = str(_CHECK_SVG).replace("\\", "/")

CONFIG_FILE = str(USERDATA_DIR / "config.json")
SESSION_FILE_GUI = str(USERDATA_DIR / "session.json")
