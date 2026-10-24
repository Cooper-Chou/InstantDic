"""Tray icon and menu. Placement choices live here until the Console window (M5) exists."""
import os

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QMenu, QSystemTrayIcon

from .config import LOG_DIR
from .icon import make_icon
from .theme import THEME_LABELS
from .screens import friendly_name, screen_ids


class _ScreenLabel(QLabel):
    """Big overlay shown on each monitor by "识别屏幕"."""

    def __init__(self, screen, text):
        super().__init__(text, None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#1d4ed8; color:white; font-size:28px; padding:24px; border-radius:12px;")
        self.adjustSize()
        self.winId()
        self.windowHandle().setScreen(screen)
        a = screen.availableGeometry()
        self.move(a.center().x() - self.width() // 2, a.center().y() - self.height() // 2)
        self.show()
        QTimer.singleShot(4000, self.close)


class Tray(QSystemTrayIcon):
    def __init__(self, app_ctl):
        super().__init__(make_icon())
        self.ctl = app_ctl
        self.setToolTip("InstantDic 快捷查词")
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._rebuild)
        self.setContextMenu(self.menu)
        self.activated.connect(self._on_activated)
        self._overlays = []
        self._rebuild()

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.ctl.show_popup()

    def _rebuild(self):
        m = self.menu
        m.clear()
        m.addAction(f"打开查词窗口\t{self.ctl.cfg.data['hotkey']}", self.ctl.show_popup)
        m.addAction("设置（词典、排序、快捷键）…", self.ctl.show_console)
        m.addSeparator()
        self._build_theme(m.addMenu("主题"))
        m.addAction("识别屏幕", self.identify_screens)
        m.addAction("重置窗口", self.ctl.reset_popup)
        m.addSeparator()
        m.addAction("打开日志文件夹", lambda: os.startfile(LOG_DIR))
        m.addAction("退出", self.ctl.quit)

    def _build_theme(self, menu):
        group = QActionGroup(menu)
        current = self.ctl.cfg.data.get("theme", "system")
        for key, label in THEME_LABELS.items():
            act = QAction(label, menu, checkable=True)
            act.setChecked(key == current)
            act.triggered.connect(lambda _=False, k=key: self.ctl.set_theme(k))
            group.addAction(act)
            menu.addAction(act)

    def identify_screens(self):
        self._overlays = [
            _ScreenLabel(s, f"屏幕 {i}\n{friendly_name(s)}\n{s.devicePixelRatio() * 100:.0f}%")
            for i, s in enumerate(screen_ids().values(), 1)
        ]
