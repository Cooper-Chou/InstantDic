"""Light / dark themes. Every color is set explicitly (Fusion style + full palette), so Windows'
own dark-mode text colors can never leak in and produce white-on-white text."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette

THEMES = {
    "light": {
        "scheme": "light", "bg": "#ffffff", "panel": "#f4f5f7", "text": "#1f2328", "muted": "#6b7280",
        "border": "#d0d4da", "hover": "#e4e7eb", "accent": "#2563eb", "accent_bg": "#dbeafe",
        "input_bg": "#ffffff", "selection": "#bfdbfe",
        # Fusion bevel/border roles (checkbox frames, spin box arrows, scrollbars)
        "light": "#ffffff", "midlight": "#e5e7eb", "mid": "#b8bdc4", "dark": "#8b9098", "shadow": "#5f6670",
    },
    "dark": {
        "scheme": "dark", "bg": "#1e1f22", "panel": "#2b2d31", "text": "#e8e8e8", "muted": "#9aa0a6",
        "border": "#3f4248", "hover": "#383a40", "accent": "#60a5fa", "accent_bg": "#1e3a5f",
        "input_bg": "#1e1f22", "selection": "#264f78",
        "light": "#55585f", "midlight": "#46494f", "mid": "#6b7078", "dark": "#151618", "shadow": "#000000",
    },
}
THEME_LABELS = {"system": "跟随系统", "light": "亮色", "dark": "暗色"}


def resolve(setting):
    if setting in ("light", "dark"):
        return setting
    return "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"


def palette(c):
    p = QPalette()
    roles = {
        QPalette.Window: c["panel"], QPalette.WindowText: c["text"], QPalette.Base: c["input_bg"],
        QPalette.AlternateBase: c["panel"], QPalette.Text: c["text"], QPalette.Button: c["panel"],
        QPalette.ButtonText: c["text"], QPalette.ToolTipBase: c["panel"], QPalette.ToolTipText: c["text"],
        QPalette.PlaceholderText: c["muted"], QPalette.Highlight: c["selection"],
        QPalette.HighlightedText: c["text"], QPalette.Link: c["accent"], QPalette.BrightText: c["text"],
        QPalette.Light: c["light"], QPalette.Midlight: c["midlight"], QPalette.Mid: c["mid"],
        QPalette.Dark: c["dark"], QPalette.Shadow: c["shadow"],
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(c["muted"]))
    return p


def stylesheet(c):
    return f"""
QWidget {{ color: {c['text']}; }}
#popup {{ background: {c['panel']}; }}
#card {{ background: {c['bg']}; border: none; }}
#header {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; }}
QLineEdit {{ border: 1px solid {c['border']}; border-radius: 4px; padding: 3px 6px;
            background: {c['input_bg']}; color: {c['text']}; selection-background-color: {c['selection']}; }}
#header QLineEdit {{ border-radius: 6px; padding: 6px 8px; font-size: 15px; }}
QLineEdit:focus {{ border-color: {c['accent']}; }}
QToolButton {{ border: none; padding: 4px 6px; border-radius: 4px; color: {c['muted']}; font-size: 14px; }}
QToolButton:hover {{ background: {c['hover']}; }}
QToolButton:checked {{ background: {c['accent_bg']}; color: {c['accent']}; }}
#grip {{ color: {c['muted']}; font-size: 16px; padding: 0 4px; }}
QListView {{ background: {c['input_bg']}; color: {c['text']}; border: 1px solid {c['border']}; }}
QListView::item:selected {{ background: {c['selection']}; color: {c['text']}; }}
QCheckBox::indicator, QListView::indicator {{ width: 13px; height: 13px; border: 1px solid {c['dark']};
            border-radius: 3px; background: {c['input_bg']}; }}
QCheckBox::indicator:checked, QListView::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QCheckBox::indicator:hover, QListView::indicator:hover {{ border-color: {c['accent']}; }}
QMenu {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; }}
QMenu::item:selected {{ background: {c['hover']}; }}
"""


def apply(app, setting):
    """Apply theme app-wide; returns the resolved name ("light" / "dark")."""
    name = resolve(setting)
    c = THEMES[name]
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setPalette(palette(c))
    app.setStyleSheet(stylesheet(c))
    return name
