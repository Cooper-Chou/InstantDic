"""Regenerate assets/icon.ico (multi-size, PNG-compressed) and assets/icon.png from app/icon.py."""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from app.icon import render  # noqa: E402


def png_bytes(img):
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def main():
    QGuiApplication(sys.argv)
    sizes = (16, 20, 24, 32, 40, 48, 64, 256)
    images = [png_bytes(render(n)) for n in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for n, data in zip(sizes, images):
        dim = 0 if n >= 256 else n  # 0 means 256 in the ICO directory
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    (ROOT / "assets" / "icon.ico").write_bytes(header + entries + blobs)
    render(256).save(str(ROOT / "assets" / "icon.png"))
    print("wrote assets/icon.ico and assets/icon.png")


if __name__ == "__main__":
    main()
