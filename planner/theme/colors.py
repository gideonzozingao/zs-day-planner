"""Material 3 colour scheme generated from a seed colour in OKLCH. Pure Python, no Qt."""
import math


def _lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gam(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_oklch(hx):
    hx = hx.lstrip("#")
    r, g, b = (_lin(int(hx[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return L, math.hypot(a, bb), math.degrees(math.atan2(bb, a)) % 360


def oklch_hex(L, C, h):
    """OKLCH -> hex, reducing chroma until the colour fits sRGB."""
    while True:
        a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
        l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
        m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
        s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
        rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
               -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
               -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
        if C <= 0 or all(-1e-4 <= x <= 1 + 1e-4 for x in rgb):
            break
        C = max(0.0, C - 0.004)
    return "#%02x%02x%02x" % tuple(round(_gam(x) * 255) for x in rgb)


def tone_L(t):
    if t <= 0:
        return 0.0
    return (t + 16) / 116 if t > 8 else (t / 903.3) ** (1 / 3)


def tone(hue, chroma, t):
    taper = 1.0 if t <= 80 else max(0.4, 1 - (t - 80) / 33)  # pastel at high tones
    return oklch_hex(tone_L(t), chroma * taper, hue)


def _rgb(hx):
    hx = hx.lstrip("#")
    return tuple(int(hx[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def on_color(hx):
    return "#000000" if hex_to_oklch(hx)[0] > 0.72 else "#ffffff"


# role: (palette, light tone, dark tone)
ROLES = {
    "primary": ("p", 40, 80), "onPrimary": ("p", 100, 20),
    "primaryContainer": ("p", 90, 30), "onPrimaryContainer": ("p", 10, 90),
    "inversePrimary": ("p", 80, 40),
    "secondary": ("s", 40, 80), "onSecondary": ("s", 100, 20),
    "secondaryContainer": ("s", 90, 30), "onSecondaryContainer": ("s", 10, 90),
    "tertiary": ("t", 40, 80), "onTertiary": ("t", 100, 20),
    "tertiaryContainer": ("t", 90, 30), "onTertiaryContainer": ("t", 10, 90),
    "surface": ("n", 98, 6), "onSurface": ("n", 10, 90),
    "surfaceContainerLowest": ("n", 100, 4), "surfaceContainerLow": ("n", 96, 10),
    "surfaceContainer": ("n", 94, 12), "surfaceContainerHigh": ("n", 92, 17),
    "surfaceContainerHighest": ("n", 90, 22),
    "onSurfaceVariant": ("nv", 30, 80), "outline": ("nv", 50, 60),
    "outlineVariant": ("nv", 80, 30),
    "inverseSurface": ("n", 20, 90), "inverseOnSurface": ("n", 95, 20),
}
ERROR = {
    False: {"error": "#B3261E", "onError": "#FFFFFF", "errorContainer": "#F9DEDC", "onErrorContainer": "#410E0B"},
    True: {"error": "#F2B8B5", "onError": "#601410", "errorContainer": "#8C1D18", "onErrorContainer": "#F9DEDC"},
}


def make_scheme(seed, variant, dark):
    _, cs, h = hex_to_oklch(seed)
    f = max(cs, 0.06)
    cfg = {
        "Tonal": dict(p=(0, .11), s=(0, .045), t=(60, .07), n=.006, nv=.012),
        "Vibrant": dict(p=(0, .20), s=(15, .10), t=(70, .14), n=.012, nv=.022),
        "Faithful": dict(p=(0, f), s=(0, f * .4), t=(60, f * .6), n=.010, nv=.016),
        "Neutral": dict(p=(0, .035), s=(0, .02), t=(60, .03), n=.004, nv=.008),
        "Mono": dict(p=(0, 0), s=(0, 0), t=(0, 0), n=0, nv=0),
    }[variant]
    pal = {"p": (h + cfg["p"][0], cfg["p"][1]), "s": (h + cfg["s"][0], cfg["s"][1]),
           "t": (h + cfg["t"][0], cfg["t"][1]), "n": (h, cfg["n"]), "nv": (h, cfg["nv"])}
    c = {}
    for role, (p, lt, dt) in ROLES.items():
        c[role] = tone(pal[p][0], pal[p][1], dt if dark else lt)
    c.update(ERROR[dark])
    c["primaryHover"] = mix(c["primary"], c["onPrimary"], .08)
    c["primaryPressed"] = mix(c["primary"], c["onPrimary"], .12)
    c["secondaryHover"] = mix(c["secondaryContainer"], c["onSecondaryContainer"], .08)
    c["secondaryPressed"] = mix(c["secondaryContainer"], c["onSecondaryContainer"], .12)
    c["primaryContainerHover"] = mix(c["primaryContainer"], c["onPrimaryContainer"], .08)
    return c
