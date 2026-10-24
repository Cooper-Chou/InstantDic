"""App / tray icon, drawn in code so it stays crisp at every size and DPI.

Design: a blue-to-violet rounded tile with a white magnifier; from 24 px up a small
lightning bolt sits in the lens ("instant lookup"). scripts/make_icon.py writes the
same artwork to assets/icon.ico for the exe and installer.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)

    # tile
    grad = QLinearGradient(0, 0, s, s)
    grad.setColorAt(0, QColor("#0ea5e9"))
    grad.setColorAt(1, QColor("#6d28d9"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    inset = s * 0.03
    p.drawRoundedRect(QRectF(inset, inset, s - 2 * inset, s - 2 * inset), s * 0.22, s * 0.22)

    # magnifier: lens ring + handle
    white = QColor("white")
    cx, cy, r = s * 0.44, s * 0.44, s * 0.22
    ring = max(1.6, s * 0.085)
    p.setPen(QPen(white, ring, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setPen(QPen(white, max(2.0, s * 0.12), Qt.SolidLine, Qt.RoundCap))
    d = r * 0.72
    p.drawLine(QPointF(cx + d + ring * 0.3, cy + d + ring * 0.3), QPointF(s * 0.80, s * 0.80))

    # lightning bolt inside the lens (too small to read below 24 px)
    if size >= 24:
        k = r * 0.95
        bolt = QPainterPath()
        pts = [(0.15, -0.95), (-0.55, 0.12), (-0.02, 0.12), (-0.18, 0.95), (0.55, -0.15), (0.02, -0.15)]
        bolt.moveTo(cx + pts[0][0] * k, cy + pts[0][1] * k)
        for x, y in pts[1:]:
            bolt.lineTo(cx + x * k, cy + y * k)
        bolt.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fde047"))
        p.drawPath(bolt)
    p.end()
    return img


def make_icon():
    from PySide6.QtGui import QPixmap
    icon = QIcon()
    for n in SIZES:
        icon.addPixmap(QPixmap.fromImage(render(n)))
    return icon
