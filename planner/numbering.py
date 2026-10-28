"""Automatic numbering: project tasks get #1, #2, … in the order they're created, and every
task's subtasks get 1, 2, … (shown as 9.1, 9.2 under project task #9).

Numbers are stable labels, like issue numbers: reordering doesn't change them and a deleted
number is never reused (each project and each task keeps a counter). Projects have a
"Renumber" action to make them sequential again in the current order.
Pure Python, no Qt.
"""
import re

MANUAL_PREFIX = re.compile(r"^\s*#\s*(\d{1,5})[\s.:)\-–—]+")


def task_no(t) -> str:
    """'#9' for a numbered (project) task, else ''."""
    n = t.get("number") or 0
    return f"#{n}" if n else ""


def titled(t) -> str:
    """'#9 CQRS in Python' (or just the title for a task outside a project)."""
    n = task_no(t)
    return f"{n} {t['title']}" if n else t["title"]


def sub_no(task, s) -> str:
    """'9.2' under project task #9, '2' under a task with no number, '' if unnumbered."""
    n = s.get("number") or 0
    if not n:
        return ""
    tn = (task or {}).get("number") or 0
    return f"{tn}.{n}" if tn else f"{n}"


def sub_titled(task, s) -> str:
    n = sub_no(task, s)
    return f"{n}  {s['title']}" if n else s["title"]


def split_manual(title):
    """'#12 Foo' -> (12, 'Foo'); anything else -> (None, title). Used once, when numbering
    is introduced, to adopt numbers people had typed into titles by hand."""
    m = MANUAL_PREFIX.match(title or "")
    if not m or not title[m.end():].strip():
        return None, title
    return int(m.group(1)), title[m.end():].strip()
