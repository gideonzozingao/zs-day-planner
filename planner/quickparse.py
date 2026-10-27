"""Natural-language quick add.

    parse("Deploy DPP staging tomorrow 2pm-3pm #dpp !high", today)
    -> title="Deploy DPP staging", date=tomorrow, start="14:00", end="15:00",
       tags=["dpp"], priority=2

Understands
  dates      today, tonight, tomorrow/tmr/tmrw, day after tomorrow, mon..sun,
             next fri (Friday of next week), in 3 days / in 2 weeks, next week,
             27/10, 27/10/2026, 27 oct, oct 27, 27th October   (day/month order)
  times      2pm, 2:30pm, 14:00, at 9, noon, 2-3pm, 14:00-15:30, 9am to 11,
             for 45m / for 1h / for 1.5h / for 1h30   (default length 30 min)
  tags       #dpp #aws
  priority   !high !h !!   !low !l   !normal !n
  star       *  (one of tomorrow's top tasks)
  literal    "text in quotes" is never interpreted (quotes removed)
Pure Python: no Qt, unit-testable.
"""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

DEFAULT_MINUTES = 30
LOW, NORMAL, HIGH = 0, 1, 2

# a fixed, legible palette; a tag with no chosen colour gets a stable one by hashing its name
TAG_PALETTE = [
    ("Blue", "#1A73E8"), ("Teal", "#00897B"), ("Green", "#2E7D32"), ("Amber", "#F9A825"),
    ("Orange", "#EF6C00"), ("Red", "#C62828"), ("Pink", "#D81B60"), ("Purple", "#8E24AA"),
    ("Indigo", "#3949AB"), ("Cyan", "#00838F"), ("Brown", "#6D4C41"), ("Slate", "#546E7A"),
]
_TAG_COLORS = [c for _, c in TAG_PALETTE]


def tag_color(tag: str) -> str:
    """Deterministic colour for a tag that has no explicit one (same tag -> same colour)."""
    import zlib
    return _TAG_COLORS[zlib.crc32(tag.lower().encode()) % len(_TAG_COLORS)]
PRIORITY_NAMES = {LOW: "Low", NORMAL: "Normal", HIGH: "High"}

_WEEKDAYS = {
    "mon": 0, "monday": 0, "tue": 1, "tues": 1, "tuesday": 1, "wed": 2, "weds": 2,
    "wednesday": 2, "thu": 3, "thur": 3, "thurs": 3, "thursday": 3, "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5, "sun": 6, "sunday": 6,
}
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4,
    "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
    "november": 11, "dec": 12, "december": 12,
}
_WD = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))
_MO = "|".join(sorted(_MONTHS, key=len, reverse=True))
_SEP = r"\s*(?:-|–|—|to|until|till)\s*"
_T = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?"          # one clock time, groups: h, m, ampm


@dataclass
class Parsed:
    title: str = ""
    date: date = None          # None -> caller's default day
    start: str = ""            # "HH:MM" or ""
    end: str = ""
    tags: list = field(default_factory=list)
    priority: int = None       # None -> caller's default (normal)
    pinned: bool = False
    found: list = field(default_factory=list)   # recognised fragments, for the preview


def _hhmm(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _to_minutes(h, m, ampm, assume_pm_small=False):
    h, m = int(h), int(m or 0)
    if h > 23 or m > 59:
        return None
    if ampm:
        if h > 12 or h == 0:
            return None
        h = (h % 12) + (12 if ampm == "pm" else 0)
    elif assume_pm_small and 1 <= h <= 6:
        h += 12                                   # "at 3" during a workday means 15:00
    return h * 60 + m


class _Text:
    """Text with protected (quoted) regions; matched fragments are cut out."""

    def __init__(self, raw):
        self.protected = []
        self.text = re.sub(r'"([^"]*)"', self._protect, raw)

    def _protect(self, m):
        self.protected.append(m.group(1))
        return f"\x00{len(self.protected) - 1}\x00"

    def find(self, pattern, flags=re.I):
        return re.search(pattern, self.text, flags)

    def cut(self, m):
        self.text = self.text[:m.start()] + " " + self.text[m.end():]

    def take(self, pattern, flags=re.I):
        """Find the first match, remove it, return the match (or None)."""
        m = self.find(pattern, flags)
        if m:
            self.cut(m)
        return m

    def take_all(self, pattern, flags=re.I):
        out = []
        while True:
            m = self.take(pattern, flags)
            if not m:
                return out
            out.append(m)

    def title(self):
        t = re.sub(r"\x00(\d+)\x00", lambda m: self.protected[int(m.group(1))], self.text)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"^(?:[-,:;]\s*)+|(?:\s*[-,:;])+$", "", t)          # dangling separators
        t = re.sub(r"\s+(?:on|at|by|due|from|for|in)$", "", t, flags=re.I)  # dangling prepositions
        return t.strip()


def _future(d: date, today: date) -> date:
    """A day/month without a year that has already passed means next year."""
    return d if d >= today else d.replace(year=d.year + 1)


def _parse_date(tx: _Text, today: date, p: Parsed):
    pre = r"(?:\b(?:on|by|due)\s+)?"
    rules = [
        (pre + r"\bday after (?:tomorrow|tmrw?)\b", lambda m: today + timedelta(days=2)),
        (pre + r"\b(?:today|tonight|tod)\b", lambda m: today),
        (pre + r"\b(?:tomorrow|tomorow|tmrw|tmr)\b", lambda m: today + timedelta(days=1)),
        (r"\bnext week\b", lambda m: today + timedelta(days=7 - today.weekday())),
        (r"\bin\s+(\d{1,3})\s+(day|days|week|weeks)\b",
         lambda m: today + timedelta(days=int(m.group(1)) * (7 if m.group(2).startswith("week") else 1))),
        (pre + rf"\bnext\s+({_WD})\b",
         lambda m: today + timedelta(days=((_WEEKDAYS[m.group(1).lower()] - today.weekday()) % 7 or 7) + 7)),
        (pre + rf"\b(?:this\s+)?({_WD})\b",
         lambda m: today + timedelta(days=(_WEEKDAYS[m.group(1).lower()] - today.weekday()) % 7)),
        (pre + r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?\b", "numeric"),
        (pre + rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MO})\b(?:\s+(\d{{4}}))?", "day_month"),
        (pre + rf"\b({_MO})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", "month_day"),
    ]
    for pattern, make in rules:
        m = tx.find(pattern)
        if not m:
            continue
        try:
            if make == "numeric":
                d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
                year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else today.year
                value = date(year, mo, d)
                value = value if y else _future(value, today)
            elif make == "day_month":
                value = date(int(m.group(3) or today.year), _MONTHS[m.group(2).lower()], int(m.group(1)))
                value = value if m.group(3) else _future(value, today)
            elif make == "month_day":
                value = date(int(m.group(3) or today.year), _MONTHS[m.group(1).lower()], int(m.group(2)))
                value = value if m.group(3) else _future(value, today)
            else:
                value = make(m)
        except ValueError:          # 31/02 etc.: not a date, leave it in the title
            continue
        tx.cut(m)
        p.date = value
        p.found.append(("date", m.group(0).strip()))
        return


def _parse_time(tx: _Text, p: Parsed):
    duration = None
    m = tx.take(r"\bfor\s+(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)(?:\s*(\d{1,2})\s*(?:m|min|mins)?)?\b")
    if m:
        duration = round(float(m.group(1)) * 60) + int(m.group(3) or 0)
    else:
        m = tx.take(r"\bfor\s+(\d{1,3})\s*(m|min|mins|minute|minutes)\b")
        if m:
            duration = int(m.group(1))
    if m:
        p.found.append(("duration", m.group(0).strip()))

    start = end = None
    # ranges: need a colon or am/pm somewhere (or a lead-in) so "2-3 items" isn't a time
    m = tx.find(rf"(?:\b(?:from|at)\s+|@\s*)?\b{_T}{_SEP}{_T}\b")
    if m:
        h1, m1, ap1, h2, m2, ap2 = m.groups()
        lead = re.match(r"\s*(?:from|at|@)", m.group(0), re.I)
        if ap1 or ap2 or m1 or m2 or lead:
            if not ap1 and ap2:                      # "2-3pm" -> 2pm; "11-1pm" -> 11am
                ap1 = ap2
                if _to_minutes(h1, m1, ap1) is not None and _to_minutes(h2, m2, ap2) is not None \
                        and _to_minutes(h1, m1, ap1) >= _to_minutes(h2, m2, ap2):
                    ap1 = "am"
            s = _to_minutes(h1, m1, ap1, assume_pm_small=not (m1 or ap1))
            e = _to_minutes(h2, m2, ap2, assume_pm_small=not (m2 or ap2))
            if s is not None and e is not None:
                if e <= s and not ap2 and e + 12 * 60 > s:   # "9 to 1" -> 9:00-13:00
                    e += 12 * 60
                if e > s:
                    start, end = s, e
                    tx.cut(m)
                    p.found.append(("time", m.group(0).strip()))
    if start is None:
        for pattern, kind in ((r"\b(?:at\s+|@\s*)?(noon|midday)\b", "noon"),
                              (r"(?:\bat\s+|@\s*)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", "ampm"),
                              (r"(?:\bat\s+|@\s*)?\b([01]?\d|2[0-3]):([0-5]\d)\b", "24h"),
                              (r"(?:\bat\s+|@\s*)\b(\d{1,2})\b", "at")):
            m = tx.take(pattern)
            if not m:
                continue
            if kind == "noon":
                start = 12 * 60
            elif kind == "ampm":
                start = _to_minutes(m.group(1), m.group(2), m.group(3).lower())
            elif kind == "24h":
                start = _to_minutes(m.group(1), m.group(2), None)
            else:
                start = _to_minutes(m.group(1), None, None, assume_pm_small=True)
            if start is not None:
                p.found.append(("time", m.group(0).strip()))
                break
    if start is not None:
        end = end if end is not None else start + (duration or DEFAULT_MINUTES)
        p.start, p.end = _hhmm(start), _hhmm(max(end, start + 1))


def parse(text: str, today: date) -> Parsed:
    p = Parsed()
    tx = _Text(text or "")
    m = tx.take(r"(?<!\S)(!!|!high|!h|!low|!l|!normal|!n|!med|!medium)(?!\S)")
    if m:
        tok = m.group(1).lower()
        p.priority = HIGH if tok in ("!!", "!high", "!h") else LOW if tok in ("!low", "!l") else NORMAL
        p.found.append(("priority", m.group(0).strip()))
    for m in tx.take_all(r"(?<!\S)#([A-Za-z0-9_][\w-]*)"):
        tag = m.group(1).lower()
        if tag not in p.tags:
            p.tags.append(tag)
    if p.tags:
        p.found.append(("tags", " ".join("#" + t for t in p.tags)))
    if tx.take(r"(?<!\S)\*(?!\S)"):
        p.pinned = True
        p.found.append(("star", "*"))
    _parse_time(tx, p)       # before dates, so "at 3" isn't mistaken for anything else
    _parse_date(tx, today, p)
    p.title = tx.title()
    return p


def normalize_tags(text: str) -> str:
    """'#DPP, aws  #aws' -> 'dpp aws' (stored form: space-separated, lowercase, unique)."""
    out = []
    for t in re.findall(r"#?([A-Za-z0-9_][\w-]*)", text or ""):
        t = t.lower()
        if t not in out:
            out.append(t)
    return " ".join(out)


def describe(p: Parsed, default_day: date, today: date) -> str:
    """One-line preview, e.g. 'Tue 28 Oct · 14:00–15:00 · #dpp · High priority'."""
    d = p.date or default_day
    if d == today:
        day = "Today"
    elif d == today + timedelta(days=1):
        day = "Tomorrow"
    else:
        day = f"{d:%a %d %b}" + (f" {d.year}" if d.year != today.year else "")
    parts = [day, f"{p.start}–{p.end}" if p.start else "Anytime"]
    if p.tags:
        parts.append(" ".join("#" + t for t in p.tags))
    if p.priority is not None and p.priority != NORMAL:
        parts.append(f"{PRIORITY_NAMES[p.priority]} priority")
    if p.pinned:
        parts.append("★ Top task")
    return "  ·  ".join(parts)
