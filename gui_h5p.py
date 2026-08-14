"""
H5P Automator — entry point.

Single-window PyQt6 GUI. Downloads H5P activities from a Moodle course and
embeds them into the matching Brightspace (D2L) course modules by driving
run_h5p_only() (src/h5p_runner.py), which reuses ContentChecker's
Brightspace-TOC fetch + Moodle scrape + H5PHandler embed pipeline extracted
from brightspace-page-automator.

Run with:  python gui_h5p.py
"""
import asyncio
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

# A --windowed PyInstaller build has no console, so sys.stdout/stderr are
# None — and plain print() (used throughout src/) crashes with
# AttributeError the first time it runs. Give the process harmless
# stand-ins before anything else can print.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

sys.path.insert(0, str(Path(__file__).parent / "src"))

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressDialog, QPushButton, QTextEdit,
    QToolButton, QVBoxLayout, QWidget,
)

from gui.constants import CONFIG_FILE, ICON_PATH, USERDATA_DIR, VERSION
from gui.settings_dialog import SettingsDialog, load_config, save_config
from gui.theme import T, _btn, _dark_palette, _entry_style, _log_style
from gui.updater import ASSET_NAME, UpdateCheckThread, UpdateDownloadThread

# A PyInstaller onefile build extracts its bundled files (including the
# bundled playwright driver, from --collect-all playwright) to a fresh
# per-launch temp dir (_MEIxxxxx) that's wiped on exit. Left alone,
# Playwright installs/looks for Chromium relative to that ephemeral
# location — so a browser "installed" during one run is gone by the next,
# forever re-triggering first-time setup. Pin it to a stable directory
# before anything touches playwright.
if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(USERDATA_DIR / "playwright-browsers"))

UPDATE_CHECK_INTERVAL_MS = 30 * 60 * 1000  # 30 min
UPDATE_CHECK_STARTUP_DELAY_MS = 10 * 1000  # let the window paint first
UPDATE_BLINK_INTERVAL_MS = 600


def _ensure_playwright_browser(app: QApplication) -> None:
    """Download the Chromium build Playwright needs, if it isn't there.

    ``run.bat``/``run.sh`` do this for source checkouts, but a packaged
    PyInstaller build has no shell wrapper — so the frozen exe/app must do
    it itself on first launch. A frozen ``sys.executable`` *is* the app
    binary, not a Python interpreter, so shelling out to
    ``sys.executable -m playwright`` (what the source-checkout path could
    do) would just re-launch the GUI. Instead we call Playwright's own
    installer entry point in-process, which is what it uses internally
    regardless of how it's invoked.

    Checks the actual executable rather than a "we installed it once"
    marker file, so it self-heals if the browser ever goes missing (e.g.
    it was previously installed into a onefile build's ephemeral temp
    extraction dir, which is wiped on every exit).
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            if Path(p.chromium.executable_path).exists():
                return
    except Exception:
        pass  # fall through and (re)install

    dlg = QProgressDialog(
        "Downloading browser components (one-time, ~1 min)…", None, 0, 0
    )
    dlg.setWindowTitle("H5P Automator — First-time Setup")
    dlg.setMinimumDuration(0)
    dlg.setCancelButton(None)
    dlg.show()
    app.processEvents()

    result = {"ok": False, "error": None}

    def worker():
        try:
            from playwright.__main__ import main as playwright_main
            old_argv = sys.argv
            sys.argv = ["playwright", "install", "chromium"]
            try:
                playwright_main()
            except SystemExit as e:
                if e.code not in (0, None):
                    raise RuntimeError(f"playwright install exited with {e.code}")
            finally:
                sys.argv = old_argv
            result["ok"] = True
        except Exception as e:
            result["error"] = str(e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    while t.is_alive():
        app.processEvents()
        t.join(timeout=0.05)
    dlg.close()

    if not result["ok"]:
        QMessageBox.warning(
            None, "Browser setup failed",
            "Could not download the browser Playwright needs:\n"
            f"{result['error']}\n\nYou can try again by restarting the app.",
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("H5P Automator")
        self.resize(420, 760)
        self.setMinimumSize(380, 560)
        self.setStyleSheet(f"background: {T['bg']}; color: {T['text']};")
        if Path(ICON_PATH).exists():
            self.setWindowIcon(QIcon(ICON_PATH))

        self._log_queue: queue.Queue = queue.Queue()
        self._moodle_ready_event = None
        self._h5p_ready_event = None
        self._h5p_skip_flag = [False]
        self._run_stop_flag = None
        self._run_handle: dict = {}

        self._update_available = False
        self._update_pending_notice = False
        self._update_download_url = None
        self._update_check_thread = None
        self._update_download_thread = None
        self._blink_on = False

        self._build_ui()
        self._load_config()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_log)
        self._poll_timer.start(100)

        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._tick_update_blink)
        self._blink_timer.start(UPDATE_BLINK_INTERVAL_MS)

        self._update_check_timer = QTimer(self)
        self._update_check_timer.timeout.connect(self._check_for_update)
        self._update_check_timer.start(UPDATE_CHECK_INTERVAL_MS)
        QTimer.singleShot(UPDATE_CHECK_STARTUP_DELAY_MS, self._check_for_update)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(0)

        # 1. Brand
        brand = QLabel("H5P Automator")
        brand.setStyleSheet(
            f"color: {T['text']}; font-size: 20px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(brand)
        sub = QLabel("Moodle → Brightspace H5P sync")
        sub.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px; background: transparent;")
        layout.addWidget(sub)
        layout.addSpacing(16)

        # 2. URL fields
        layout.addWidget(self._label("BRIGHTSPACE COURSE URL"))
        layout.addSpacing(4)
        self._bs_entry = QLineEdit()
        self._bs_entry.setPlaceholderText("https://learn.okanagancollege.ca/d2l/le/content/<id>/home")
        self._bs_entry.setFixedHeight(36)
        self._bs_entry.setStyleSheet(_entry_style())
        layout.addWidget(self._bs_entry)
        layout.addSpacing(10)

        layout.addWidget(self._label("MOODLE COURSE URL"))
        layout.addSpacing(4)
        self._moodle_entry = QLineEdit()
        self._moodle_entry.setPlaceholderText("https://mymoodle.okanagan.bc.ca/course/view.php?id=…")
        self._moodle_entry.setFixedHeight(36)
        self._moodle_entry.setStyleSheet(_entry_style())
        layout.addWidget(self._moodle_entry)
        layout.addSpacing(10)

        self._skip_grade_cb = QCheckBox("Skip grade item (don't add to gradebook)")
        self._skip_grade_cb.setChecked(True)
        self._skip_grade_cb.setStyleSheet(f"color: {T['text_muted']}; font-size: 12px; background: transparent;")
        layout.addWidget(self._skip_grade_cb)
        layout.addSpacing(14)

        # 5. Run button
        self._run_btn = QPushButton("Run")
        self._run_btn.setFixedHeight(44)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(_btn(T["btn_primary"], T["btn_primary_h"]) + "QPushButton { font-size: 15px; }")
        self._run_btn.clicked.connect(self._start_run)
        layout.addWidget(self._run_btn)
        layout.addSpacing(8)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setStyleSheet(_btn(T["btn_danger"], T["btn_danger_h"]))
        self._stop_btn.clicked.connect(self._stop_run)
        self._stop_btn.hide()
        layout.addWidget(self._stop_btn)
        layout.addSpacing(8)

        # Pause-point buttons (hidden until worker signals it's waiting)
        self._ready_btn = QPushButton("Ready — Scrape Now")
        self._ready_btn.setFixedHeight(36)
        self._ready_btn.setStyleSheet(_btn(T["success"], T["accent_hover"]))
        self._ready_btn.hide()
        layout.addWidget(self._ready_btn)

        h5p_row = QHBoxLayout()
        h5p_row.setSpacing(8)
        self._h5p_ready_btn = QPushButton("Ready — Download H5P")
        self._h5p_ready_btn.setFixedHeight(36)
        self._h5p_ready_btn.setStyleSheet(_btn(T["success"], T["accent_hover"]))
        self._h5p_ready_btn.hide()
        self._h5p_skip_btn = QPushButton("Skip H5P")
        self._h5p_skip_btn.setFixedHeight(36)
        self._h5p_skip_btn.setFixedWidth(110)
        self._h5p_skip_btn.setStyleSheet(_btn(T["btn_muted"], T["btn_muted_h"], text=T["text"]))
        self._h5p_skip_btn.hide()
        h5p_row.addWidget(self._h5p_ready_btn, 1)
        h5p_row.addWidget(self._h5p_skip_btn)
        layout.addLayout(h5p_row)
        layout.addSpacing(10)

        # 6. Log panel — dominant element, fills remaining space
        layout.addWidget(self._label("LOG"))
        layout.addSpacing(4)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(_log_style())
        layout.addWidget(self._log, 1)
        layout.addSpacing(10)

        # 7. Bottom-left settings gear
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        self._gear_btn = QToolButton()
        self._gear_btn.setText("⚙")
        self._gear_btn.setToolTip("Settings")
        self._gear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gear_btn.setFixedSize(32, 32)
        self._gear_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent; color: {T["text_muted"]};
                border: 1px solid {T["card_border"]}; border-radius: 16px; font-size: 15px;
            }}
            QToolButton:hover {{ background: {T["btn_muted"]}; color: {T["text"]}; }}
        """)
        self._gear_btn.clicked.connect(self._open_settings)
        bottom_row.addWidget(self._gear_btn)

        self._update_btn = QToolButton()
        self._update_btn.setText("⭯")
        self._update_btn.setToolTip("Update available — click to download")
        self._update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_btn.setFixedSize(32, 32)
        self._set_update_btn_style(lit=False)
        self._update_btn.clicked.connect(self._start_update_download)
        self._update_btn.hide()
        bottom_row.addWidget(self._update_btn)

        bottom_row.addStretch()
        version_lbl = QLabel(VERSION)
        version_lbl.setStyleSheet(f"color: {T['text_dim']}; font-size: 10px; background: transparent;")
        bottom_row.addWidget(version_lbl)
        layout.addLayout(bottom_row)

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {T['text_muted']}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; background: transparent;"
        )
        return lbl

    # ── Settings dialog ──────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self, parent=self)
        dlg.exec()

    # ── Auto-update ──────────────────────────────────────────────────────

    def _set_update_btn_style(self, lit: bool):
        color = T["success"] if lit else T["text_muted"]
        border = T["success"] if lit else T["card_border"]
        self._update_btn.setStyleSheet(f"""
            QToolButton {{
                background: transparent; color: {color};
                border: 1px solid {border}; border-radius: 16px; font-size: 16px;
            }}
            QToolButton:hover {{ background: {T["btn_muted"]}; }}
        """)

    def _tick_update_blink(self):
        if not self._update_available or self._update_btn.isHidden():
            return
        self._blink_on = not self._blink_on
        self._set_update_btn_style(lit=self._blink_on)

    def _check_for_update(self):
        if self._update_check_thread and self._update_check_thread.isRunning():
            return
        self._update_check_thread = UpdateCheckThread(self)
        self._update_check_thread.result.connect(self._on_update_check_result)
        self._update_check_thread.start()

    def _on_update_check_result(self, available: bool, url: str, error: str):
        if not available:
            return
        self._update_available = True
        self._update_download_url = url or None
        # A run in progress shouldn't be interrupted by a glowing icon —
        # defer showing it until __DONE__ fires in _poll_log.
        if self._run_btn.isEnabled():
            self._show_update_glow()
        else:
            self._update_pending_notice = True

    def _show_update_glow(self):
        self._update_pending_notice = False
        self._update_btn.show()
        self._set_update_btn_style(lit=True)
        self._blink_on = True

    def _start_update_download(self):
        if not self._update_download_url:
            self._append_log(
                "A new version is available on GitHub, but this build "
                "can't fetch it automatically — check the Releases page.",
                "warning",
            )
            return
        if self._update_download_thread and self._update_download_thread.isRunning():
            return

        downloads_dir = Path.home() / "Downloads"
        if not downloads_dir.exists():
            downloads_dir = Path(CONFIG_FILE).parent
        dest = downloads_dir / (ASSET_NAME or "H5PAutomator-update.zip")

        dlg = QProgressDialog("Downloading update…", None, 0, 100, self)
        dlg.setWindowTitle("H5P Automator — Update")
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        dlg.show()

        self._update_download_thread = UpdateDownloadThread(self._update_download_url, dest, self)
        self._update_download_thread.progress.connect(
            lambda read, total: dlg.setValue(int(read * 100 / total) if total else 0)
        )
        self._update_download_thread.finished_ok.connect(
            lambda path: (dlg.close(), self._on_update_downloaded(path))
        )
        self._update_download_thread.failed.connect(
            lambda err: (dlg.close(), self._on_update_download_failed(err))
        )
        self._update_download_thread.start()

    def _on_update_downloaded(self, path: str):
        self._update_available = False
        self._update_btn.hide()
        try:
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", path])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", path])
            else:
                subprocess.run(["xdg-open", str(Path(path).parent)])
        except Exception:
            pass
        self._append_log(
            f"Update downloaded to {path}. Close this app and run the new "
            "version to finish updating.",
            "success",
        )

    def _on_update_download_failed(self, error: str):
        self._append_log(f"Update download failed: {error}", "error")

    # ── Config persistence ───────────────────────────────────────────────

    def _load_config(self):
        cfg = load_config()
        if cfg.get("h5p_bs_url"):
            self._bs_entry.setText(cfg["h5p_bs_url"])
        if cfg.get("h5p_moodle_url"):
            self._moodle_entry.setText(cfg["h5p_moodle_url"])
        self._skip_grade_cb.setChecked(bool(cfg.get("skip_grade_item", True)))

    def _save_state(self):
        save_config({
            "h5p_bs_url": self._bs_entry.text().strip(),
            "h5p_moodle_url": self._moodle_entry.text().strip(),
            "skip_grade_item": self._skip_grade_cb.isChecked(),
        })

    # ── Run ───────────────────────────────────────────────────────────────

    def _start_run(self):
        bs_url = self._bs_entry.text().strip()
        moodle_url = self._moodle_entry.text().strip()
        if not bs_url or not moodle_url:
            self._append_log("Enter both a Brightspace and a Moodle course URL.", "warning")
            return

        self._save_state()
        skip_grade_item = self._skip_grade_cb.isChecked()

        moodle_ev = threading.Event()
        h5p_ev = threading.Event()
        skip_flag = [False]
        stop_flag = [False]
        run_handle: dict = {}
        self._moodle_ready_event = moodle_ev
        self._h5p_ready_event = h5p_ev
        self._h5p_skip_flag = skip_flag
        self._run_stop_flag = stop_flag
        self._run_handle = run_handle

        self._ready_btn.hide()
        self._h5p_ready_btn.hide()
        self._h5p_skip_btn.hide()

        self._run_btn.setText("Running…")
        self._run_btn.setEnabled(False)
        self._stop_btn.setText("Stop")
        self._stop_btn.setEnabled(True)
        self._stop_btn.show()
        self._log.clear()

        cfg = load_config()
        q = self._log_queue

        def worker():
            done_sent = [False]

            def on_done():
                if not done_sent[0]:
                    done_sent[0] = True
                    q.put(("__DONE__", ""))

            try:
                from h5p_runner import run_h5p_only
                asyncio.run(run_h5p_only(
                    bs_url=bs_url,
                    moodle_url=moodle_url,
                    log=lambda msg, tag="info": q.put((msg, tag)),
                    on_complete=on_done,
                    moodle_ready_event=moodle_ev,
                    on_moodle_waiting=lambda: q.put(("__H5P_MOODLE_WAITING__", "")),
                    h5p_ready_event=h5p_ev,
                    on_h5p_waiting=lambda: q.put(("__H5P_WAITING__", "")),
                    h5p_skip_flag=skip_flag,
                    bs_username=cfg.get("bs_username", ""),
                    bs_password=cfg.get("bs_password", ""),
                    sso_email=cfg.get("sso_email", ""),
                    sso_password=cfg.get("sso_password", ""),
                    moodle_username=cfg.get("moodle_username", ""),
                    moodle_password=cfg.get("moodle_password", ""),
                    skip_grade_item=skip_grade_item,
                    stop_flag=stop_flag,
                    run_handle=run_handle,
                ))
            except Exception as e:
                if not stop_flag[0]:
                    q.put((f"✗ Error: {e}", "error"))
            finally:
                on_done()

        threading.Thread(target=worker, daemon=True).start()

    def _stop_run(self):
        handle = self._run_handle
        loop = handle.get("loop")
        browser = handle.get("browser")
        if not loop or not browser:
            self._append_log("Nothing running to stop yet — try again in a moment.", "warning")
            return

        if self._run_stop_flag is not None:
            self._run_stop_flag[0] = True
        self._stop_btn.setEnabled(False)
        self._stop_btn.setText("Stopping…")
        self._append_log("⏹ Stopping — closing browser…", "warning")

        # Unblock any pending "Ready — Scrape Now" / "Ready — Download H5P"
        # pause-point wait so it doesn't sit there forever after the browser
        # it was waiting to act on is gone.
        for ev in (handle.get("moodle_ready_event"), handle.get("h5p_ready_event")):
            if ev is not None:
                ev.set()

        async def _close():
            try:
                if browser.is_connected():
                    await browser.close()
            except Exception:
                pass

        asyncio.run_coroutine_threadsafe(_close(), loop)

    # ── Log polling ───────────────────────────────────────────────────────

    def _append_log(self, msg: str, tag: str = "info"):
        color = {
            "success": T["success"], "error": T["danger_text"],
            "warning": T["warn"], "dim": T["text_dim"],
        }.get(tag, T["text"])
        self._log.append(f'<span style="color:{color}">{msg}</span>')
        scrollbar = self._log.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _poll_log(self):
        try:
            while True:
                msg, tag = self._log_queue.get_nowait()
                if msg == "__DONE__":
                    self._run_btn.setText("Run")
                    self._run_btn.setEnabled(True)
                    self._stop_btn.hide()
                    self._run_stop_flag = None
                    self._run_handle = {}
                    self._ready_btn.hide()
                    self._h5p_ready_btn.hide()
                    self._h5p_skip_btn.hide()
                    if self._update_pending_notice:
                        self._show_update_glow()
                elif msg == "__H5P_MOODLE_WAITING__":
                    self._ready_btn.setText("Ready — Scrape Now")
                    try:
                        self._ready_btn.clicked.disconnect()
                    except TypeError:
                        pass
                    self._ready_btn.clicked.connect(self._moodle_ready)
                    self._ready_btn.show()
                elif msg == "__H5P_WAITING__":
                    self._h5p_ready_btn.show()
                    self._h5p_skip_btn.show()
                    try:
                        self._h5p_ready_btn.clicked.disconnect()
                    except TypeError:
                        pass
                    try:
                        self._h5p_skip_btn.clicked.disconnect()
                    except TypeError:
                        pass
                    self._h5p_ready_btn.clicked.connect(self._h5p_ready)
                    self._h5p_skip_btn.clicked.connect(self._h5p_skip)
                else:
                    self._append_log(msg, tag)
        except queue.Empty:
            pass

    def _moodle_ready(self):
        self._ready_btn.hide()
        if self._moodle_ready_event:
            self._moodle_ready_event.set()

    def _h5p_ready(self):
        self._h5p_ready_btn.hide()
        self._h5p_skip_btn.hide()
        if self._h5p_ready_event:
            self._h5p_ready_event.set()

    def _h5p_skip(self):
        self._h5p_ready_btn.hide()
        self._h5p_skip_btn.hide()
        self._h5p_skip_flag[0] = True
        if self._h5p_ready_event:
            self._h5p_ready_event.set()


if __name__ == "__main__":
    if sys.platform == "win32":
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("H5PAutomator")
        except Exception:
            pass
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setFont(QFont("Segoe UI", 10))
    if Path(ICON_PATH).exists():
        app.setWindowIcon(QIcon(ICON_PATH))

    _ensure_playwright_browser(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
