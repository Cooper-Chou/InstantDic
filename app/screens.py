"""Multi-monitor handling.

Screens are identified by EDID data (manufacturer/model/serial), never by Windows'
DISPLAYn index, because that index is reshuffled after sleep or monitor power cycles.
Popup geometry is recomputed from scratch on every show; nothing absolute is persisted.
"""
import logging

from PySide6.QtCore import QObject, QRect, QSize, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication

from .i18n import tr

log = logging.getLogger(__name__)

ANCHORS = [
    "top-left", "top", "top-right",
    "left", "center", "right",
    "bottom-left", "bottom", "bottom-right",
]
ANCHOR_LABELS = {
    "top-left": "左上", "top": "上中", "top-right": "右上",
    "left": "左中", "center": "正中", "right": "右中",
    "bottom-left": "左下", "bottom": "下中", "bottom-right": "右下",
}

# Wait this long after the last display event before trusting the screen layout:
# monitors come back one by one after wake, with transient resolutions/DPI.
SETTLE_MS = 1500


def _screen_key(s):
    parts = [s.manufacturer().strip(), s.model().strip(), s.serialNumber().strip()]
    if any(parts):
        return "|".join(parts)
    size = s.size() * s.devicePixelRatio()
    return f"{s.name()}|{size.width()}x{size.height()}"


def screen_ids():
    """Map stable id -> QScreen. Identical monitors without serials get a #n suffix by position."""
    screens = sorted(QGuiApplication.screens(), key=lambda s: (s.geometry().x(), s.geometry().y()))
    ids, seen = {}, {}
    for s in screens:
        key = _screen_key(s)
        n = seen.get(key, 0)
        seen[key] = n + 1
        ids[key if n == 0 else f"{key}#{n + 1}"] = s
    return ids


def describe_screen(s):
    g, a = s.geometry(), s.availableGeometry()
    dpr = s.devicePixelRatio()
    return (f"{s.name()!r} model={s.model()!r} manuf={s.manufacturer()!r} serial={s.serialNumber()!r} "
            f"geo={g.x()},{g.y()} {g.width()}x{g.height()} avail={a.x()},{a.y()} {a.width()}x{a.height()} "
            f"scale={dpr * 100:.0f}% primary={s == QGuiApplication.primaryScreen()}")


def friendly_name(s):
    return s.model() or s.name() or tr("未知显示器")


class ScreenManager(QObject):
    settled = Signal()

    def __init__(self, app):
        super().__init__()
        self._timer = QTimer(self, singleShot=True, interval=SETTLE_MS)
        self._timer.timeout.connect(self._on_settled)
        app.screenAdded.connect(lambda s: (self._watch(s), self.notify_change("screenAdded")))
        app.screenRemoved.connect(lambda s: self.notify_change("screenRemoved"))
        app.primaryScreenChanged.connect(lambda s: self.notify_change("primaryScreenChanged"))
        for s in app.screens():
            self._watch(s)
        self.log_layout("startup")

    def _watch(self, s):
        s.geometryChanged.connect(lambda *_: self.notify_change("geometryChanged"))
        s.availableGeometryChanged.connect(lambda *_: self.notify_change("availableGeometryChanged"))
        s.logicalDotsPerInchChanged.connect(lambda *_: self.notify_change("dpiChanged"))

    def notify_change(self, reason):
        log.info("display event: %s", reason)
        self._timer.start()  # restart: debounce bursts

    @property
    def settling(self):
        return self._timer.isActive()

    def _on_settled(self):
        self.log_layout("settled")
        self.settled.emit()

    def log_layout(self, tag):
        for sid, s in screen_ids().items():
            log.info("[%s] screen id=%r %s", tag, sid, describe_screen(s))

    def target_screen(self, popup_cfg):
        if popup_cfg.get("mode") == "fixed":
            s = screen_ids().get(popup_cfg.get("screen_id", ""))
            if s is not None:
                return s
            log.info("configured screen %r not present, using cursor screen", popup_cfg.get("screen_id"))
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def compute_geometry(self, popup_cfg):
        """Return (QScreen, QRect in logical coords) for the popup."""
        s = self.target_screen(popup_cfg)
        avail = s.availableGeometry()
        m = int(popup_cfg.get("margin", 40))
        m = max(0, min(m, avail.width() // 4, avail.height() // 4))
        w = max(320, min(int(popup_cfg["width"]), avail.width() - 2 * m))
        h = max(240, min(int(popup_cfg["height"]), avail.height() - 2 * m))
        anchor = popup_cfg.get("anchor", "top")
        if anchor not in ANCHORS:
            anchor = "top"
        col = ANCHORS.index(anchor) % 3
        row = ANCHORS.index(anchor) // 3
        x = [avail.left() + m, avail.left() + (avail.width() - w) // 2, avail.right() + 1 - m - w][col]
        y = [avail.top() + m, avail.top() + (avail.height() - h) // 2, avail.bottom() + 1 - m - h][row]
        return s, QRect(x, y, w, h)

    @staticmethod
    def clamp_size(size: QSize, s) -> QSize:
        a = s.availableGeometry()
        return QSize(min(size.width(), a.width()), min(size.height(), a.height()))
