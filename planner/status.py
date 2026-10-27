"""Task status model. Pure data, no Qt, so colours and rules are testable and reused
by the list, the task dialog, the stats page and the reminder popup.

`done` (the checkbox) stays the source of truth for "completed": DONE <-> done=1, every
other status is done=0. The store keeps the two in sync, so progress bars, carry-over,
reminders and the review all keep working unchanged.
"""
OPEN = "open"
IN_PROGRESS = "in_progress"
DONE = "done"
POSTPONED = "postponed"
CANCELLED = "cancelled"
BLOCKED = "blocked"

ORDER = [OPEN, IN_PROGRESS, BLOCKED, POSTPONED, DONE, CANCELLED]

# label, swatch colour (light theme reference), short symbol for tight spots
META = {
    OPEN:        ("Open",        "#6B7785", "○"),
    IN_PROGRESS: ("In progress", "#1A73E8", "◐"),
    DONE:        ("Done",        "#2E7D32", "✓"),
    POSTPONED:   ("Postponed",   "#F9A825", "»"),
    CANCELLED:   ("Cancelled",   "#C62828", "✕"),
    BLOCKED:     ("Blocked",     "#8E24AA", "⊘"),
}

# statuses that count as "no longer needing action" (excluded from overdue/reminders)
INACTIVE = {DONE, CANCELLED, POSTPONED}
# statuses that count against "planned work" in completion stats
COUNTS_AS_PLANNED = {OPEN, IN_PROGRESS, DONE, BLOCKED, POSTPONED}   # cancelled is dropped


def is_valid(s):
    return s in META


def label(s):
    return META.get(s, META[OPEN])[0]


def color(s):
    return META.get(s, META[OPEN])[1]


def symbol(s):
    return META.get(s, META[OPEN])[2]


def from_done(done):
    return DONE if done else OPEN


def normalize(status, done):
    """Reconcile a stored status with the done flag (done wins for the DONE/OPEN pair)."""
    if done and status != DONE:
        return DONE
    if not done and status == DONE:
        return OPEN
    return status if is_valid(status) else from_done(done)
