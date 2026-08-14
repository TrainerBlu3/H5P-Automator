from PyQt6.QtGui import QPalette, QColor

from gui.constants import CHECK_SVG_PATH

# Green / light-green theme (structure mirrors brightspace-quiz-automator's
# gui/theme.py — same dict keys, same helper signatures — recolored on-brand).
T = {
    "bg":            "#0a140d",
    "sidebar_bg":    "#050a06",
    "card_bg":       "#0f1e13",
    "card_border":   "#1c3524",
    "accent":        "#22c55e",
    "accent_dim":    "#14532d",
    "accent_hover":  "#4ade80",
    "nav_hover":     "#0f1e13",
    "nav_active":    "#14532d",
    "text":          "#e7f7ec",
    "text_muted":    "#8fb89c",
    "text_dim":      "#4b6b56",
    "btn_primary":   "#22c55e",
    "btn_primary_h": "#4ade80",
    "btn_muted":     "#1c3524",
    "btn_muted_h":   "#25452f",
    "btn_danger":    "#6e1a1a",
    "btn_danger_h":  "#922222",
    "danger_text":   "#f85149",
    "btn_add":       "#14532d",
    "btn_add_h":     "#166534",
    "warn":          "#f59e0b",
    "success":       "#22c55e",
    "terminal_bg":   "#050e08",
}


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(T["bg"]))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(T["text"]))
    p.setColor(QPalette.ColorRole.Base,            QColor(T["card_bg"]))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(T["sidebar_bg"]))
    p.setColor(QPalette.ColorRole.Text,            QColor(T["text"]))
    p.setColor(QPalette.ColorRole.Button,          QColor(T["btn_muted"]))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(T["text"]))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(T["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#08150c"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(T["text_muted"]))
    p.setColor(QPalette.ColorRole.Mid,             QColor(T["card_border"]))
    return p


def _btn(bg: str, hover: str, text: str = "#08150c", radius: int = 8) -> str:
    return f"""
        QPushButton {{
            background: {bg}; color: {text}; border: none;
            border-radius: {radius}px; font-size: 13px;
            padding: 0 16px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:disabled {{ background: {T["btn_muted"]}; color: {T["text_dim"]}; }}
    """


def _card() -> str:
    return f"QFrame {{ background: {T['card_bg']}; border: 1px solid {T['card_border']}; border-radius: 10px; }}"


def _entry_style() -> str:
    return f"""
        QLineEdit {{
            background: {T["bg"]}; color: {T["text"]};
            border: 1px solid {T["card_border"]}; border-radius: 6px;
            padding: 0 12px; font-size: 13px;
        }}
        QLineEdit:focus {{ border: 1px solid {T["accent"]}; }}
    """


def _checkbox_style(warn: bool = False) -> str:
    color = T["warn"] if warn else T["text"]
    return f"""
        QCheckBox {{ color: {color}; font-size: 13px; spacing: 8px; padding: 5px 0px; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1px solid {T["card_border"]}; border-radius: 4px; background: {T["bg"]};
        }}
        QCheckBox::indicator:checked {{
            background: {T["accent"]}; border: 1px solid {T["accent"]};
            image: url({CHECK_SVG_PATH});
        }}
    """


def _log_style() -> str:
    return f"""
        QTextEdit {{
            background: {T["terminal_bg"]}; color: {T["text"]};
            border: none; border-left: 2px solid {T["accent_dim"]}; border-radius: 0px;
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
            font-size: 12px; padding: 10px 14px;
        }}
    """


def _tab_style() -> str:
    return f"""
        QTabWidget::pane {{ border: 1px solid {T["card_border"]}; border-radius: 8px; background: {T["card_bg"]}; }}
        QTabBar::tab {{
            background: {T["btn_muted"]}; color: {T["text_muted"]};
            padding: 8px 20px; border-radius: 6px; margin-right: 4px; font-size: 12px;
        }}
        QTabBar::tab:selected {{ background: {T["nav_active"]}; color: {T["accent"]}; font-weight: 600; }}
        QTabBar::tab:hover {{ background: {T["btn_muted_h"]}; color: {T["text"]}; }}
    """


def _scroll_style() -> str:
    return f"""
        QScrollArea {{ background: transparent; border: none; }}
        QWidget {{ background: transparent; }}
        QScrollBar:vertical {{
            background: {T["bg"]}; width: 6px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical {{ background: {T["card_border"]}; border-radius: 3px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    """
