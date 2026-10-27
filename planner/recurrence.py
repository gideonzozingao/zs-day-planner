"""Repeating-task rules. Pure date maths, no Qt or DB, so it's unit-testable.

A repeating task is materialised a window ahead (Store.ensure_recurrences): the series
keeps its own rows, so any single occurrence can be edited, moved or deleted on its own,
and the rule can be changed or stopped without rewriting history.
"""
from calendar import monthrange
from datetime import date, timedelta

NONE = ""
DAILY = "daily"
WEEKDAYS = "weekdays"
WEEKLY = "weekly"
MONTHLY = "monthly"

RULES = (DAILY, WEEKDAYS, WEEKLY, MONTHLY)
LABELS = {NONE: "Does not repeat", DAILY: "Every day", WEEKDAYS: "Every weekday (Mon-Fri)",
          WEEKLY: "Every week", MONTHLY: "Every month"}

# how far ahead to pre-create occurrences, per rule (kept small; topped up on each run)
HORIZON_DAYS = {DAILY: 14, WEEKDAYS: 21, WEEKLY: 70, MONTHLY: 120}


def is_valid(rule) -> bool:
    return rule in RULES


def describe(rule, anchor: date = None) -> str:
    if rule == WEEKLY and anchor:
        return f"Every {anchor:%A}"
    if rule == MONTHLY and anchor:
        return f"Monthly on the {_ordinal(anchor.day)}"
    return LABELS.get(rule, LABELS[NONE])


def short_label(rule) -> str:
    return {DAILY: "Daily", WEEKDAYS: "Weekdays", WEEKLY: "Weekly", MONTHLY: "Monthly"}.get(rule, "")


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _nth_month(anchor: date, k: int) -> date:
    """anchor shifted k months, keeping anchor's day-of-month, clamped per month.
    Anchored on the original day so 31 Jan -> 28 Feb -> 31 Mar (not stuck at 28)."""
    m0 = anchor.year * 12 + (anchor.month - 1) + k
    y, m = divmod(m0, 12)
    m += 1
    return date(y, m, min(anchor.day, monthrange(y, m)[1]))


def next_after(rule, anchor: date, after: date) -> date:
    """First occurrence strictly after `after`, for a series anchored on `anchor`."""
    if rule == DAILY:
        return max(anchor, after + timedelta(days=1))
    if rule == WEEKDAYS:
        d = after + timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        return d
    if rule == WEEKLY:
        if after < anchor:
            return anchor
        days = (after - anchor).days
        return anchor + timedelta(days=(days // 7 + 1) * 7)
    if rule == MONTHLY:
        k = 1
        while True:
            d = _nth_month(anchor, k)
            if d > after:
                return d
            k += 1
    raise ValueError(f"Unknown recurrence rule: {rule!r}")


def occurrences(rule, anchor: date, until: date):
    """All occurrences in [anchor, until] inclusive (anchor first)."""
    if not is_valid(rule) or until < anchor:
        return
    d = anchor
    if rule == WEEKDAYS:
        while d.weekday() >= 5:          # if the anchor lands on a weekend, start Monday
            d += timedelta(days=1)
    if rule == MONTHLY:
        k = 0
        while True:
            d = _nth_month(anchor, k)
            if d > until:
                return
            if d >= anchor:
                yield d
            k += 1
        return
    guard = 0
    while d <= until and guard < 2000:
        yield d
        guard += 1
        d = next_after(rule, anchor, d)
