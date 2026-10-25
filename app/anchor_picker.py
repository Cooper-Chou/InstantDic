"""Nine-cell "screen" for choosing where the popup appears: click a cell (or use arrow keys)."""
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .i18n import tr
from .screens import ANCHOR_LABELS, ANCHORS


class AnchorPicker(QWidget):
    anchorChanged = Signal(str)

    MAX_W, MAX_H = 200, 150

    def __init__(self, anchor="top", parent=None):
        super().__init__(parent)
        self._anchor = anchor if anchor in ANCHORS else "top"
        self._hover = None
        self._aspect = 16 / 9  # width / height of the screen being configured
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setFixedSize(self.sizeHint())

    # ---------- API ----------
    def anchor(self):
        return self._anchor

    def setAnchor(self, anchor, emit=False):
        if anchor in ANCHORS and anchor != self._anchor:
            self._anchor = anchor
            self.update()
            if emit:
                self.anchorChanged.emit(anchor)

    def setAspect(self, aspect):
        """Match the selected monitor's shape (portrait monitors draw tall)."""
        self._aspect = max(0.3, min(4.0, aspect))
        self.setFixedSize(self.sizeHint())
        self.update()

    def sizeHint(self):
        w, h = self.MAX_W, self.MAX_W / self._aspect
        if h > self.MAX_H:
            h, w = self.MAX_H, self.MAX_H * self._aspect
        return QSize(int(w) + 2, int(h) + 2)

    # ---------- geometry ----------
    def _screen_rect(self):
        return QRectF(1, 1, self.width() - 2, self.height() - 2)

    def _cell(self, i):
        r = self._screen_rect()
        cw, ch = r.width() / 3, r.height() / 3
        return QRectF(r.left() + (i % 3) * cw, r.top() + (i // 3) * ch, cw, ch)

    def _index_at(self, pos):
        for i in range(9):
            if self._cell(i).contains(pos):
                return i
        return None

    # ---------- painting ----------
    def paintEvent(self, _):
        pal = self.palette()
        base, text = pal.base().color(), pal.text().color()
        border = pal.mid().color()
        accent = pal.link().color()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        screen = self._screen_rect()
        p.setPen(QPen(border, 1.5))
        p.setBrush(base)
        p.drawRoundedRect(screen, 6, 6)

        # faint 3x3 guide lines
        guide = QColor(border)
        guide.setAlpha(110)
        p.setPen(QPen(guide, 1, Qt.DashLine))
        for k in (1, 2):
            x = screen.left() + screen.width() * k / 3
            y = screen.top() + screen.height() * k / 3
            p.drawLine(int(x), int(screen.top() + 4), int(x), int(screen.bottom() - 4))
            p.drawLine(int(screen.left() + 4), int(y), int(screen.right() - 4), int(y))

        sel = ANCHORS.index(self._anchor)
        for i in range(9):
            cell = self._cell(i)
            # a small "window" placed the way the popup would sit in that region
            w, h = cell.width() * 0.42, cell.height() * 0.55
            col, row = i % 3, i // 3
            pad_x, pad_y = cell.width() * 0.12, cell.height() * 0.12
            x = [cell.left() + pad_x, cell.center().x() - w / 2, cell.right() - pad_x - w][col]
            y = [cell.top() + pad_y, cell.center().y() - h / 2, cell.bottom() - pad_y - h][row]
            win = QRectF(x, y, w, h)
            if i == sel:
                p.setPen(Qt.NoPen)
                fill = QColor(accent)
                fill.setAlpha(40)
                p.setBrush(fill)
                p.drawRoundedRect(cell.adjusted(3, 3, -3, -3), 4, 4)
                p.setBrush(accent)
                p.setPen(QPen(accent, 1))
            elif i == self._hover:
                hov = QColor(accent)
                hov.setAlpha(120)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(hov, 1.5))
            else:
                dim = QColor(text)
                dim.setAlpha(60)
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(dim, 1))
            p.drawRoundedRect(win, 2, 2)

        if self.hasFocus():
            p.setPen(QPen(accent, 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(screen.adjusted(2, 2, -2, -2), 5, 5)
        p.end()

    # ---------- interaction ----------
    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()
            if i is not None:
                QToolTip.showText(e.globalPosition().toPoint(), tr(ANCHOR_LABELS[ANCHORS[i]]), self)

    def leaveEvent(self, _):
        self._hover = None
        self.update()

    def mousePressEvent(self, e):
        i = self._index_at(e.position())
        if e.button() == Qt.LeftButton and i is not None:
            self.setAnchor(ANCHORS[i], emit=True)

    def keyPressEvent(self, e):
        i = ANCHORS.index(self._anchor)
        col, row = i % 3, i // 3
        moves = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in moves:
            dc, dr = moves[e.key()]
            col, row = min(2, max(0, col + dc)), min(2, max(0, row + dr))
            self.setAnchor(ANCHORS[row * 3 + col], emit=True)
        else:
            super().keyPressEvent(e)
