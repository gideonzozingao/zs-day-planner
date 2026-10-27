"""Regenerate packaging/assets/planner.ico (+ .png) from the app logo (planner/theme/icons.py).

    python packaging/make_icon.py        (needs PySide6 and Pillow)
"""
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image                                   # noqa: E402
from PySide6.QtCore import QBuffer, QByteArray, Qt      # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer                  # noqa: E402

from planner.theme.icons import logo_svg               # noqa: E402

SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def render(svg: str, px: int) -> Image.Image:
    img = QImage(px, px, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main():
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    out = ROOT / "packaging" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    # each size rendered natively (simplified mark at <=24 px), not downscaled
    frames = [render(logo_svg(small=s <= 24), s) for s in SIZES]
    frames[-1].save(out / "planner.png")
    render(logo_svg(), 512).save(out / "logo-512.png")
    render(logo_svg(fg="#1F5C5E", bg=None, knock="#FFFFFF"), 512).save(out / "logo-glyph-512.png")
    frames[-1].save(out / "planner.ico", format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=frames[:-1])
    print("wrote", out / "planner.ico")


if __name__ == "__main__":
    main()
