"""Small helpers shared across layers."""
from datetime import datetime


def mins(hhmm: str) -> int:
    """'HH:MM' -> minutes since midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def fmt_stamp(s) -> str:
    if not s:
        return ""
    try:
        return datetime.fromisoformat(s).strftime("%d %b %Y, %H:%M")
    except ValueError:
        return str(s)


def fmt_duration(seconds) -> str:
    """3900 -> '1h 05m', 1500 -> '25m', 40 -> '<1m'."""
    m = int(seconds) // 60
    if m < 1:
        return "<1m"
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def fmt_clock(seconds) -> str:
    """Countdown display: 1122 -> '18:42', 3725 -> '1:02:05'."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def rgba(hex_color: str, alpha: float) -> str:
    """'#1A73E8', 0.2 -> 'rgba(26,115,232,51)' for stylesheets (Qt reads 8-digit hex as #AARRGGBB,
    so appending an alpha byte to #RRGGBB gives the wrong colour)."""
    h = (hex_color or "#888888").lstrip("#")[:6]
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{int(alpha * 255)})"
