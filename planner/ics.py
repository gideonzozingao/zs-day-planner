"""iCalendar (.ics) export of tasks, so time blocks show up in Outlook / Google Calendar.

Times are written in UTC (converted from this PC's local time), so any calendar app places
them correctly. Each task keeps a stable UID, so importing a newer export updates the same
events instead of duplicating them (in apps that honour UIDs on import). Pure Python, no Qt.
"""
from datetime import datetime, timezone

from . import numbering as NUM
from . import status as STATUS
from . import timespan as TS

PRODID = "-//Zuqongtech//Daily Planner//EN"


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n") \
        .replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines over 75 octets continue on the next line after a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\r\n ".join(out)


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")   # naive dt = local time


def build_ics(tasks, projects=None, calendar_name="Daily Planner") -> str:
    """tasks: task dicts (start_at/end_at). projects: {id: project} for names in the event."""
    projects = projects or {}
    now = _utc(datetime.now())
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_esc(calendar_name)}"]
    for t in tasks:
        sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
        p = projects.get(t.get("project_id") or "")
        desc = []
        if p:
            desc.append(f"Project: {p['name']}")
        desc.append(f"Status: {STATUS.label(t['status'])}")
        if t.get("note"):
            desc.append("")
            desc.append(t["note"])
        cats = ([p["name"]] if p else []) + (t.get("tags") or "").split()
        lines += [
            "BEGIN:VEVENT",
            f"UID:{t['id']}@zuqongtech-planner",
            f"DTSTAMP:{now}",
            f"DTSTART:{_utc(sa)}",
            f"DTEND:{_utc(ea)}",
            f"SUMMARY:{_esc(NUM.titled(t))}",
            f"DESCRIPTION:{_esc(chr(10).join(desc))}",
            f"STATUS:{'CANCELLED' if t['status'] == STATUS.CANCELLED else 'CONFIRMED'}",
            "TRANSP:OPAQUE" if t["status"] not in STATUS.INACTIVE else "TRANSP:TRANSPARENT",
            f"LAST-MODIFIED:{_utc(datetime.fromisoformat(t['updated_at']))}" if t.get("updated_at") else None,
        ]
        if cats:
            lines.append("CATEGORIES:" + ",".join(_esc(c) for c in cats))
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines if x is not None) + "\r\n"
