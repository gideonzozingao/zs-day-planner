"""Which tasks the reminder popup should show."""
from datetime import datetime

from ..config import LOOKAHEAD_MIN
from ..utils import mins


def reminder_sections(store, now: datetime, snoozed=None):
    """-> (current, overdue, upcoming, anytime) lists of task dicts for today.
    snoozed: {task_id: datetime} tasks to hide until their snooze expires."""
    nm = now.hour * 60 + now.minute
    snoozed = snoozed or {}
    today = [t for t in store.for_day(now.date()) if not (t["id"] in snoozed and now < snoozed[t["id"]])]
    timed = [t for t in today if t["start"]]
    current = [t for t in timed if mins(t["start"]) <= nm < mins(t["end"])]
    overdue = [t for t in timed if not t["done"] and mins(t["end"]) <= nm]
    upcoming = [t for t in timed if not t["done"] and nm < mins(t["start"]) <= nm + LOOKAHEAD_MIN]
    anytime = [t for t in today if not t["start"] and not t["done"]]
    return current, overdue, upcoming, anytime
