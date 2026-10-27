"""Which tasks the reminder popup should show."""
from datetime import datetime, timedelta

from .. import status as STATUS
from ..config import LOOKAHEAD_MIN
from ..timespan import to_str


def reminder_sections(store, now: datetime, snoozed=None):
    """-> (current, overdue, upcoming, later) lists of task dicts for today.
    current: running now. overdue: ended (today) and not done. upcoming: starting within
    LOOKAHEAD_MIN. later: open tasks starting later today.
    snoozed: {task_id: datetime} tasks to hide until their snooze expires."""
    snoozed = snoozed or {}
    n = to_str(now)
    soon = to_str(now + timedelta(minutes=LOOKAHEAD_MIN))
    today = [t for t in store.for_day(now.date()) if not (t["id"] in snoozed and now < snoozed[t["id"]])]
    current = [t for t in today if t["start_at"] <= n < t["end_at"] and t["status"] != STATUS.CANCELLED]
    active = [t for t in today if t["status"] not in STATUS.INACTIVE]   # not done/cancelled/postponed
    overdue = [t for t in active if t["end_at"] <= n]
    upcoming = [t for t in active if n < t["start_at"] <= soon]
    later = [t for t in active if t["start_at"] > soon]
    return current, overdue, upcoming, later
