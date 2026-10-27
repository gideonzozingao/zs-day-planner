"""Task and project time spans: every task and project has a start and an end date-time.

Stored as 'YYYY-MM-DDTHH:MM' strings, which sort and compare correctly as text.
Pure Python, no Qt.
"""
from datetime import date, datetime, time, timedelta

FMT = "%Y-%m-%dT%H:%M"
DEFAULT_WORKDAY = ("08:00", "16:30")


def to_dt(s) -> datetime:
    if isinstance(s, datetime):
        return s.replace(second=0, microsecond=0)
    return datetime.strptime(s[:16], FMT)


def to_str(dt) -> str:
    if isinstance(dt, str):
        return dt[:16]
    return dt.strftime(FMT)


def at(d: date, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime.combine(d, time(int(h), int(m)))


def make_span(d: date, start: str, end: str, workday=DEFAULT_WORKDAY):
    """A day plus optional HH:MM times -> (start_dt, end_dt).
    No time: the working day. End not after start: the end is on the next day."""
    if not start:
        start, end = workday
    s = at(d, start)
    e = at(d, end) if end else s + timedelta(minutes=30)
    if e <= s:
        e += timedelta(days=1)
    return s, e


def day_bounds(d: date):
    """Text bounds for 'overlaps day d': start_at < hi and end_at > lo."""
    return to_str(datetime.combine(d + timedelta(days=1), time())), to_str(datetime.combine(d, time()))


def shift_to(start_at, end_at, new_day: date):
    """Move a span so it starts on new_day at the same time, keeping its length."""
    s, e = to_dt(start_at), to_dt(end_at)
    ns = datetime.combine(new_day, s.time())
    return ns, ns + (e - s)


def fmt_length(seconds) -> str:
    """5400 -> '1 h 30 min', 90000 -> '1 day 1 h'."""
    m = int(seconds) // 60
    d, m = divmod(m, 1440)
    h, m = divmod(m, 60)
    parts = []
    if d:
        parts.append(f"{d} day" + ("s" if d != 1 else ""))
    if h:
        parts.append(f"{h} h")
    if m and not d:
        parts.append(f"{m} min")
    return " ".join(parts) or "0 min"


def _short_day(d: date, ref: date) -> str:
    if d == ref:
        return "Today"
    if d == ref + timedelta(days=1):
        return "Tomorrow"
    if d == ref - timedelta(days=1):
        return "Yesterday"
    return f"{d:%a %d %b}" + (f" {d.year}" if d.year != ref.year else "")


def span_label(start_at, end_at, day: date = None, today: date = None) -> str:
    """Time label for a task.
    With `day` (the day being viewed): '09:00–10:00', '14:00 → Thu 10:00', 'Mon 08:00 → 12:00',
    'All day (Mon → Thu)'. Without: 'Tue 27 Oct 09:00–10:00' or 'Tue 27 Oct 14:00 → Thu 29 Oct 10:00'."""
    s, e = to_dt(start_at), to_dt(end_at)
    today = today or date.today()
    last = (e - timedelta(minutes=1)).date() if e.time() == time() and e > s else e.date()
    end_txt = "24:00" if e.time() == time() and last == s.date() else f"{e:%H:%M}"
    if day is None:
        if s.date() == last:
            return f"{_short_day(s.date(), today)}  {s:%H:%M}–{end_txt}"
        return f"{_short_day(s.date(), today)} {s:%H:%M}  →  {_short_day(e.date(), today)} {e:%H:%M}"
    if s.date() == last:
        return f"{s:%H:%M}–{end_txt}"
    if s.date() == day:
        return f"{s:%H:%M} → {e:%a} {e:%H:%M}"
    if last == day:
        return f"{s:%a} {s:%H:%M} → {e:%H:%M}"
    return f"All day ({s:%a} → {e:%a})"


def default_start(d: date, now: datetime = None) -> datetime:
    """A sensible start on day d: now rounded to 5 min on today, else 09:00."""
    now = now or datetime.now()
    if d == now.date():
        return now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    return datetime.combine(d, time(9, 0))
