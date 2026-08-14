"""Check the rolling "latest" GitHub release for a build newer than this one.

CI (.github/workflows/main-latest.yml) force-moves a "latest" tag to the tip
of `main` on every push and publishes a prerelease with per-OS zips attached,
stamping each build with the commit SHA it was built from
(gui/_build_info.py, generated at build time — not committed, so source
checkouts have no BUILD_SHA and update checks are simply inert).
"""
import json
import sys
import urllib.error
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

try:
    from gui._build_info import BUILD_SHA
except ImportError:
    BUILD_SHA = None

GITHUB_OWNER = "TrainerBlu3"
GITHUB_REPO = "H5P-Automator"
_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

ASSET_NAME = {
    "win32": "H5PAutomator-Windows.zip",
    "darwin": "H5PAutomator-macOS.zip",
    "linux": "H5PAutomator-Linux.zip",
}.get(sys.platform)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def check_for_update():
    """Returns (available, download_url, error) — all falsy on 'nothing to do'."""
    if not BUILD_SHA or not ASSET_NAME:
        return False, None, None
    try:
        ref = _get_json(f"{_API}/git/refs/tags/latest")
        remote_sha = ref["object"]["sha"]
        if remote_sha == BUILD_SHA:
            return False, None, None
        release = _get_json(f"{_API}/releases/tags/latest")
        for asset in release.get("assets", []):
            if asset["name"] == ASSET_NAME:
                return True, asset["browser_download_url"], None
        return True, None, "no matching asset in latest release"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # No "latest" release published yet (e.g. before the first
            # main-branch build) — not an error worth surfacing.
            return False, None, None
        return False, None, str(e)
    except Exception as e:
        return False, None, str(e)


def download_update(url: str, dest_path, progress_cb=None):
    """Streams `url` to `dest_path`, calling progress_cb(read, total) as it goes."""
    req = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        read = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                read += len(chunk)
                if progress_cb:
                    progress_cb(read, total)


class UpdateCheckThread(QThread):
    result = pyqtSignal(bool, str, str)

    def run(self):
        available, url, error = check_for_update()
        self.result.emit(available, url or "", error or "")


class UpdateDownloadThread(QThread):
    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, url: str, dest_path, parent=None):
        super().__init__(parent)
        self._url = url
        self._dest_path = dest_path

    def run(self):
        try:
            download_update(self._url, self._dest_path, progress_cb=self.progress.emit)
            self.finished_ok.emit(str(self._dest_path))
        except Exception as e:
            self.failed.emit(str(e))
