"""
Settings dialog — Brightspace credentials + MS SSO + Moodle credentials +
session management. Modelled on brightspace-quiz-automator's Settings panel
(gui/panels/settings.py): plaintext JSON config in the app's userdata dir,
same "Login to Brightspace" worker-thread pattern, same "Clear Session" button.
"""
import asyncio
import json
import os
import sys
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from gui.constants import CONFIG_FILE, SESSION_FILE_GUI
from gui.theme import T, _btn, _card, _entry_style


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(patch: dict) -> None:
    cfg = load_config()
    cfg.update(patch)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


class SettingsDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self.setWindowTitle("Settings")
        self.setMinimumSize(420, 560)
        self.setStyleSheet(f"background: {T['bg']}; color: {T['text']};")
        self._build()
        self._load()

    def _field(self, layout: QVBoxLayout, label: str, password: bool = False) -> QLineEdit:
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {T['text_muted']}; font-size: 11px; background: transparent;")
        layout.addWidget(lbl)
        entry = QLineEdit()
        entry.setFixedHeight(34)
        entry.setStyleSheet(_entry_style())
        if password:
            entry.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(entry)
        return entry

    def _section(self, title: str) -> QVBoxLayout:
        lbl = QLabel(title)
        lbl.setStyleSheet(
            f"color: {T['text_muted']}; font-size: 10px; font-weight: 700; "
            f"letter-spacing: 1px; background: transparent;"
        )
        self._outer.addWidget(lbl)
        self._outer.addSpacing(6)
        frame = QFrame()
        frame.setStyleSheet(_card())
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        self._outer.addWidget(frame)
        self._outer.addSpacing(16)
        return layout

    def _build(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {T['bg']}; border: none; }}")
        inner = QWidget()
        inner.setStyleSheet(f"background: {T['bg']};")
        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self._outer = QVBoxLayout(inner)
        self._outer.setContentsMargins(20, 20, 20, 20)
        self._outer.setSpacing(0)

        title = QLabel("Settings")
        title.setStyleSheet(f"color: {T['text']}; font-size: 18px; font-weight: 700; background: transparent;")
        self._outer.addWidget(title)
        self._outer.addSpacing(16)

        # Brightspace
        bs = self._section("BRIGHTSPACE")
        self._bs_username = self._field(bs, "Username")
        self._bs_password = self._field(bs, "Password", password=True)
        session_exists = os.path.exists(SESSION_FILE_GUI)
        self._bs_status = QLabel("Session saved" if session_exists else "No session — log in first")
        self._bs_status.setStyleSheet(
            f"color: {T['success'] if session_exists else T['warn']}; font-size: 12px; background: transparent;"
        )
        bs.addWidget(self._bs_status)
        bs.addSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        self._bs_login_btn = QPushButton("Login to Brightspace")
        self._bs_login_btn.setFixedHeight(34)
        self._bs_login_btn.setStyleSheet(_btn(T["btn_primary"], T["btn_primary_h"]))
        self._bs_login_btn.clicked.connect(self._start_bs_login)
        row.addWidget(self._bs_login_btn)
        bs.addLayout(row)

        # Microsoft SSO (optional)
        sso = self._section("MICROSOFT SSO (OPTIONAL)")
        self._sso_email = self._field(sso, "SSO Email")
        self._sso_password = self._field(sso, "SSO Password", password=True)

        # Moodle
        moodle = self._section("MOODLE")
        self._moodle_username = self._field(moodle, "Username")
        self._moodle_password = self._field(moodle, "Password", password=True)

        # Session management
        sess = self._section("SESSION")
        clear_btn = QPushButton("Clear Session")
        clear_btn.setFixedHeight(34)
        clear_btn.setStyleSheet(_btn(T["btn_danger"], T["btn_danger_h"]))
        clear_btn.clicked.connect(self._clear_session)
        sess.addWidget(clear_btn)

        # Save
        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(42)
        self._save_btn.setStyleSheet(_btn(T["btn_primary"], T["btn_primary_h"]))
        self._save_btn.clicked.connect(self._save)
        self._outer.addWidget(self._save_btn)
        self._outer.addStretch()

    def _load(self):
        cfg = load_config()
        self._bs_username.setText(cfg.get("bs_username", ""))
        self._bs_password.setText(cfg.get("bs_password", ""))
        self._sso_email.setText(cfg.get("sso_email", ""))
        self._sso_password.setText(cfg.get("sso_password", ""))
        self._moodle_username.setText(cfg.get("moodle_username", ""))
        self._moodle_password.setText(cfg.get("moodle_password", ""))

    def _save(self):
        save_config({
            "bs_username": self._bs_username.text().strip(),
            "bs_password": self._bs_password.text().strip(),
            "sso_email": self._sso_email.text().strip(),
            "sso_password": self._sso_password.text().strip(),
            "moodle_username": self._moodle_username.text().strip(),
            "moodle_password": self._moodle_password.text().strip(),
        })
        self._save_btn.setText("Saved")
        QTimer.singleShot(1200, lambda: self._save_btn.setText("Save"))
        if hasattr(self._mw, "_refresh_status_dots"):
            self._mw._refresh_status_dots()

    def _start_bs_login(self):
        self._bs_login_btn.setEnabled(False)
        self._bs_login_btn.setText("Opening browser…")
        q = self._mw._log_queue

        bs_user = self._bs_username.text().strip()
        bs_pass = self._bs_password.text().strip()
        sso_email = self._sso_email.text().strip()
        sso_password = self._sso_password.text().strip()

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
                QTimer.singleShot(0, lambda: (
                    self._bs_status.setText("Session saved"),
                    self._bs_status.setStyleSheet(f"color: {T['success']}; font-size: 12px; background: transparent;"),
                ))
            except Exception as e:
                q.put((f"✗ Brightspace login failed: {e}", "error"))
            finally:
                QTimer.singleShot(0, lambda: (
                    self._bs_login_btn.setEnabled(True),
                    self._bs_login_btn.setText("Login to Brightspace"),
                ))
                if hasattr(self._mw, "_refresh_status_dots"):
                    QTimer.singleShot(0, self._mw._refresh_status_dots)

        threading.Thread(target=worker, daemon=True).start()

    def _clear_session(self):
        if os.path.exists(SESSION_FILE_GUI):
            os.remove(SESSION_FILE_GUI)
        self._bs_status.setText("No session — log in first")
        self._bs_status.setStyleSheet(f"color: {T['warn']}; font-size: 12px; background: transparent;")
        if hasattr(self._mw, "_refresh_status_dots"):
            self._mw._refresh_status_dots()
