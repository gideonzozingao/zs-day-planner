"""Material icon paths (24x24 viewBox) rendered to QIcons in theme colours."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICONS = {
    "add": "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
    "delete": "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
    "edit": "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
    "chevron_left": "M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z",
    "chevron_right": "M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z",
    "today": "M19 3h-1V1h-2v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V8h14v11zM7 10h5v5H7z",
    "event": "M17 12h-5v5h5v-5zM16 1v2H8V1H6v2H5c-1.11 0-1.99.9-1.99 2L3 19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2h-1V1h-2zm3 18H5V8h14v11z",
    "palette": "M12 3a9 9 0 0 0 0 18c.83 0 1.5-.67 1.5-1.5 0-.39-.15-.74-.39-1.01-.23-.26-.38-.61-.38-.99 0-.83.67-1.5 1.5-1.5H16c2.76 0 5-2.24 5-5 0-4.42-4.03-8-9-8zm-5.5 9c-.83 0-1.5-.67-1.5-1.5S5.67 9 6.5 9 8 9.67 8 10.5 7.33 12 6.5 12zm3-4C8.67 8 8 7.33 8 6.5S8.67 5 9.5 5s1.5.67 1.5 1.5S10.33 8 9.5 8zm5 0c-.83 0-1.5-.67-1.5-1.5S13.67 5 14.5 5s1.5.67 1.5 1.5S15.33 8 14.5 8zm3 4c-.83 0-1.5-.67-1.5-1.5S16.67 9 17.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z",
    "more": "M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
    "close": "M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
    "bell": "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z",
    "copy": "M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z",
    "check": "M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
    "checklist": "M22 7h-9v2h9V7zm0 8h-9v2h9v-2zM5.54 11 2 7.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 11zm0 8L2 15.46l1.41-1.41 2.12 2.12 4.24-4.24 1.41 1.41L5.54 19z",
    "undo": "M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z",
    "chart": "M3.5 18.5l6-6 4 4L22 6.92 20.59 5.5l-7.09 8-4-4L2 16z",
    "flag": "M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6z",
    "timer": "M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61 1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9 9-4.03 9-9c0-2.12-.74-4.07-1.97-5.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z",
    "play": "M8 5v14l11-7z",
    "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "stop": "M6 6h12v12H6z",
    "star": "M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z",
    "star_outline": "m22 9.24-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03L22 9.24zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28L12 15.4z",
    "done_all": "M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41 6 19l1.41-1.41L1.83 12 .41 13.41z",
    "bolt": "M7 2v11h3v9l7-12h-4l4-8z",
    "folder": "M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z",
    "subdirectory": "M19 15l-6 6-1.42-1.42L15.17 16H4V4h2v10h9.17l-3.59-3.58L13 9l6 6z",
    "arrow_up": "M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z",
    "arrow_down": "M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z",
    "history": "M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.954 8.954 0 0 0 13 21a9 9 0 0 0 0-18zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z",
}
CHECK_PATH = ICONS["check"]
ARROW_PATH = "M7 10l5 5 5-5z"


def _render(svg: str, px: int) -> QPixmap:
    pix = QPixmap(px, px)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return pix


def make_icon(name, off, on=None, size=24):
    ic = QIcon()
    for state, col in ((QIcon.State.Off, off), (QIcon.State.On, on or off)):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               f'<path fill="{col}" d="{ICONS[name]}"/></svg>')
        pix = _render(svg, size * 2)
        pix.setDevicePixelRatio(2)
        ic.addPixmap(pix, QIcon.Mode.Normal, state)
    return ic


# ----------------------------------------------------------------------------- app logo
BRAND_TEAL = "#1F5C5E"


def logo_svg(fg="#FFFFFF", bg=BRAND_TEAL, small=False, knock=None):
    """App mark on a 64x64 grid: an outlined T with an inline, crossed by a two-way
    flow arrow that passes through the stem.

    bg     badge colour (rounded square) or None for the bare glyph
    small  simplified solid version for 16-24 px, where fine lines turn to mush
    knock  gap colour around the arrow for a bare glyph (defaults to bg)
    """
    badge = f'<rect width="64" height="64" rx="15" fill="{bg}"/>' if bg else ""
    stroke = f'fill="none" stroke="{fg}" stroke-linejoin="miter"'
    if small:
        glyph = (f'<path fill="{fg}" d="M12 10H52V23H38V56H26V23H12Z"/>'
                 f'<g {stroke} stroke-width="5.5" stroke-linecap="square">'
                 f'<path d="M18 33 L10 41 L18 49"/><path d="M46 33 L54 41 L46 49"/><path d="M12 41H52"/></g>')
    else:
        gap = knock or bg
        glyph = (f'<g {stroke} stroke-width="3.6">'
                 f'<path d="M12 10H52V22H38V56H26V22H12Z"/>'               # outlined T
                 f'<path d="M18 16H46M32 16V37"/></g>'                      # inline, ends at the arrow
                 + (f'<path d="M23 41H41" stroke="{gap}" stroke-width="10"/>' if gap else "")
                 + f'<g {stroke} stroke-width="3.6">'
                 f'<path d="M20 32.5 L11.5 41 L20 49.5"/><path d="M44 32.5 L52.5 41 L44 49.5"/>'
                 f'<path d="M13 41H51"/></g>')                              # two-way arrow
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{badge}{glyph}</svg>'


def render_logo(px, **kw) -> QPixmap:
    """Logo pixmap at an exact pixel size, using the small variant at 24 px and below."""
    kw.setdefault("small", px <= 24)
    return _render(logo_svg(**kw), px)


def app_icon(c=None):
    """Window, taskbar and tray icon. Always the brand colour (not the theme seed), so it
    matches the .exe, Start Menu and installer icons."""
    ic = QIcon()
    for px in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        ic.addPixmap(render_logo(px))
    return ic


def focus_icon(fraction_left: float, minutes_left: int, paused=False):
    """Tray icon while focusing: brand tile with a ring that empties as time runs out.
    The minutes are printed from 32 px up; paused shows two bars."""
    ic = QIcon()
    for px in (16, 20, 24, 32, 48, 64):
        pm = QPixmap(px * 2, px * 2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        size = px * 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(BRAND_TEAL))
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.23, size * 0.23)
        w = max(2.0, size * 0.11)
        ring = QRectF(w / 2 + size * 0.08, w / 2 + size * 0.08, size - w - size * 0.16, size - w - size * 0.16)
        p.setPen(QPen(QColor(255, 255, 255, 70), w))
        p.drawEllipse(ring)
        p.setPen(QPen(QColor("#FFFFFF"), w, Qt.SolidLine, Qt.FlatCap))
        span = int(-360 * 16 * max(0.0, min(1.0, fraction_left)))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        if paused:
            bw, bh = size * 0.09, size * 0.3
            p.drawRect(QRectF(size / 2 - bw * 1.6, size / 2 - bh / 2, bw, bh))
            p.drawRect(QRectF(size / 2 + bw * 0.6, size / 2 - bh / 2, bw, bh))
        elif px >= 32:
            f = QFont()
            f.setPixelSize(int(size * (0.34 if minutes_left < 100 else 0.27)))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, str(minutes_left))
        else:
            d = size * 0.2
            p.drawEllipse(QRectF(size / 2 - d / 2, size / 2 - d / 2, d, d))
        p.end()
        pm.setDevicePixelRatio(2)
        ic.addPixmap(pm)
    return ic


def status_dot(color_hex, size=12):
    """A small filled circle used as a status swatch."""
    from PySide6.QtGui import QBrush, QColor as _QC
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(_QC(color_hex)))
    p.drawEllipse(1, 1, size * 2 - 2, size * 2 - 2)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)
