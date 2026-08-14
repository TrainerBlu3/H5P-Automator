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
import json
import os
import queue
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
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QProgressDialog, QPushButton, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from gui.constants import CONFIG_FILE, ICON_PATH, SESSION_FILE_GUI, VERSION
from gui.settings_dialog import SettingsDialog, load_config, save_config
from gui.theme import T, _btn, _checkbox_style, _dark_palette, _entry_style, _log_style


def _ensure_playwright_browser(app: QApplication) -> None:
    """Download the Chromium build Playwright needs, once.

    ``run.bat``/``run.sh`` do this for source checkouts, but a packaged
    PyInstaller build has no shell wrapper — so the frozen exe/app must do
    it itself on first launch. A frozen ``sys.executable`` *is* the app
    binary, not a Python interpreter, so shelling out to
    ``sys.executable -m playwright`` (what the source-checkout path could
    do) would just re-launch the GUI. Instead we call Playwright's own
    installer entry point in-process, which is what it uses internally
    regardless of how it's invoked.
    """
    marker = Path(CONFIG_FILE).parent / ".playwright_installed"
    if marker.exists():
        return

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

    if result["ok"]:
        marker.write_text("ok")
    else:
        from PyQt6.QtWidgets import QMessageBox
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

        self._build_ui()
        self._load_config()
        self._refresh_status_dots()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_log)
        self._poll_timer.start(100)

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

        # 2. Moodle row
        layout.addWidget(self._platform_row(
            "Moodle", "moodle",
            login_slot=self._start_moodle_login,
        ))
        layout.addSpacing(10)

        # 3. Brightspace row
        layout.addWidget(self._platform_row(
            "Brightspace", "brightspace",
            login_slot=self._start_bs_login,
        ))
        layout.addSpacing(16)

        # 4. URL fields
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
        layout.addSpacing(14)

        # 5. Run button
        self._run_btn = QPushButton("Run")
        self._run_btn.setFixedHeight(44)
        self._run_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_btn.setStyleSheet(_btn(T["btn_primary"], T["btn_primary_h"]) + "QPushButton { font-size: 15px; }")
        self._run_btn.clicked.connect(self._start_run)
        layout.addWidget(self._run_btn)
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

    def _platform_row(self, title: str, key: str, login_slot) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background: {T['card_bg']}; border: 1px solid {T['card_border']}; border-radius: 8px; }}"
        )
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        dot = QLabel("●")
        dot.setFixedWidth(14)
        top.addWidget(dot)
        name = QLabel(title)
        name.setStyleSheet(f"color: {T['text']}; font-size: 13px; font-weight: 600; background: transparent;")
        top.addWidget(name)
        top.addStretch()
        login_btn = QPushButton("Log in")
        login_btn.setFixedHeight(28)
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.setStyleSheet(_btn(T["btn_muted"], T["btn_muted_h"], text=T["text"]))
        login_btn.clicked.connect(login_slot)
        top.addWidget(login_btn)
        outer.addLayout(top)

        skip_cb = QCheckBox("Skip grade item")
        skip_cb.setStyleSheet(_checkbox_style())
        outer.addWidget(skip_cb)

        if key == "moodle":
            self._moodle_dot, self._moodle_login_btn, self._moodle_skip_cb = dot, login_btn, skip_cb
        else:
            self._bs_dot, self._bs_login_btn, self._bs_skip_cb = dot, login_btn, skip_cb
        return frame

    def _refresh_status_dots(self):
        # Moodle and Brightspace share one browser-context session file
        # (SESSION_FILE_GUI) since run_h5p_only logs into both in the same
        # context — so both dots reflect whether that session exists.
        ok = os.path.exists(SESSION_FILE_GUI)
        color = T["success"] if ok else T["warn"]
        for dot in (getattr(self, "_moodle_dot", None), getattr(self, "_bs_dot", None)):
            if dot:
                dot.setStyleSheet(f"color: {color}; font-size: 13px; background: transparent;")

    # ── Settings dialog ──────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self, parent=self)
        dlg.exec()
        self._refresh_status_dots()

    # ── Config persistence ───────────────────────────────────────────────

    def _load_config(self):
        cfg = load_config()
        if cfg.get("h5p_bs_url"):
            self._bs_entry.setText(cfg["h5p_bs_url"])
        if cfg.get("h5p_moodle_url"):
            self._moodle_entry.setText(cfg["h5p_moodle_url"])
        self._moodle_skip_cb.setChecked(bool(cfg.get("moodle_skip_grade_item", False)))
        self._bs_skip_cb.setChecked(bool(cfg.get("bs_skip_grade_item", False)))

    def _save_state(self):
        save_config({
            "h5p_bs_url": self._bs_entry.text().strip(),
            "h5p_moodle_url": self._moodle_entry.text().strip(),
            "moodle_skip_grade_item": self._moodle_skip_cb.isChecked(),
            "bs_skip_grade_item": self._bs_skip_cb.isChecked(),
        })

    # ── Moodle login (standalone) ────────────────────────────────────────

    def _start_moodle_login(self):
        self._moodle_login_btn.setEnabled(False)
        self._moodle_login_btn.setText("Opening…")
        moodle_url = self._moodle_entry.text().strip()
        cfg = load_config()
        moodle_user = cfg.get("moodle_username", "")
        moodle_pass = cfg.get("moodle_password", "")
        sso_pass = cfg.get("sso_password", "")
        q = self._log_queue

        def worker():
            async def _run():
                from browser import launch_browser
                from moodle_login import run_moodle_login_only

                def log_fn(msg, tag="dim"):
                    q.put((msg, tag))

                p, browser_obj, context, page = await launch_browser(log_fn=log_fn)
                try:
                    await run_moodle_login_only(
                        context, moodle_url,
                        moodle_username=moodle_user, moodle_password=moodle_pass,
                        sso_password=sso_pass, log_fn=log_fn,
                    )
                finally:
                    if browser_obj.is_connected():
                        await browser_obj.close()
                    await p.stop()

            try:
                asyncio.run(_run())
            except Exception as e:
                q.put((f"✗ Moodle login failed: {e}", "error"))
            finally:
                QTimer.singleShot(0, lambda: (
                    self._moodle_login_btn.setEnabled(True),
                    self._moodle_login_btn.setText("Log in"),
                ))
                QTimer.singleShot(0, self._refresh_status_dots)

        threading.Thread(target=worker, daemon=True).start()

    # ── Brightspace login (standalone) ───────────────────────────────────

    def _start_bs_login(self):
        self._bs_login_btn.setEnabled(False)
        self._bs_login_btn.setText("Opening…")
        cfg = load_config()
        bs_user = cfg.get("bs_username", "")
        bs_pass = cfg.get("bs_password", "")
        sso_email = cfg.get("sso_email", "")
        sso_password = cfg.get("sso_password", "")
        q = self._log_queue

        def worker():
            from browser import run_login_only

            def log_fn(msg, tag="dim"):
                q.put((msg, tag))

            try:
                asyncio.run(run_login_only(
                    bs_username=bs_user, bs_password=bs_pass,
                    sso_email=sso_email, sso_password=sso_password,
                    log_fn=log_fn,
                ))
            except Exception as e:
                q.put((f"✗ Brightspace login failed: {e}", "error"))
            finally:
                QTimer.singleShot(0, lambda: (
                    self._bs_login_btn.setEnabled(True),
                    self._bs_login_btn.setText("Log in"),
                ))
                QTimer.singleShot(0, self._refresh_status_dots)

        threading.Thread(target=worker, daemon=True).start()

    # ── Run ───────────────────────────────────────────────────────────────

    def _start_run(self):
        bs_url = self._bs_entry.text().strip()
        moodle_url = self._moodle_entry.text().strip()
        if not bs_url or not moodle_url:
            self._append_log("Enter both a Brightspace and a Moodle course URL.", "warning")
            return

        self._save_state()

        moodle_ev = threading.Event()
        h5p_ev = threading.Event()
        skip_flag = [False]
        self._moodle_ready_event = moodle_ev
        self._h5p_ready_event = h5p_ev
        self._h5p_skip_flag = skip_flag

        self._ready_btn.hide()
        self._h5p_ready_btn.hide()
        self._h5p_skip_btn.hide()

        self._run_btn.setText("Running…")
        self._run_btn.setEnabled(False)
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
                ))
            except Exception as e:
                q.put((f"✗ Error: {e}", "error"))
            finally:
                on_done()

        threading.Thread(target=worker, daemon=True).start()

    # ── Log polling ───────────────────────────────────────────────────────

    def _append_log(self, msg: str, tag: str = "info"):
        color = {
            "success": T["success"], "error": T["danger_text"],
            "warning": T["warn"], "dim": T["text_dim"],
        }.get(tag, T["text"])
        self._log.append(f'<span style="color:{color}">{msg}</span>')
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def _poll_log(self):
        try:
            while True:
                msg, tag = self._log_queue.get_nowait()
                if msg == "__DONE__":
                    self._run_btn.setText("Run")
                    self._run_btn.setEnabled(True)
                    self._ready_btn.hide()
                    self._h5p_ready_btn.hide()
                    self._h5p_skip_btn.hide()
                    self._refresh_status_dots()
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
