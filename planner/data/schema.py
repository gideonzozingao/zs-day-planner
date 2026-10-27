"""Database schema. Bump SCHEMA_VERSION when adding tables/columns.

v1: tasks, task_events, routine, settings
v2: subtasks (cascade-deleted with their task)
v3: tasks.priority / tags / pinned, focus_sessions (time tracking)
v4: tasks.recurrence / recur_parent, tag_colors
v5: tasks.status (open/in_progress/done/postponed/cancelled/blocked)
Every CREATE uses IF NOT EXISTS; columns added to existing tables are listed in
ADDED_COLUMNS and applied by Store._migrate(), so older databases upgrade in place.
"""
SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    date         TEXT NOT NULL,              -- YYYY-MM-DD
    start_time   TEXT NOT NULL DEFAULT '',   -- HH:MM or '' for anytime
    end_time     TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    completed_at TEXT,
    priority     INTEGER NOT NULL DEFAULT 1,  -- 0 low, 1 normal, 2 high
    tags         TEXT NOT NULL DEFAULT '',    -- space-separated, lowercase, no '#'
    pinned       INTEGER NOT NULL DEFAULT 0,  -- one of the day's top tasks
    recurrence   TEXT NOT NULL DEFAULT '',    -- '' | daily | weekdays | weekly | monthly
    recur_parent TEXT NOT NULL DEFAULT '',    -- id of the series' first task
    status       TEXT NOT NULL DEFAULT 'open' -- open|in_progress|done|postponed|cancelled|blocked
);
CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(date);
CREATE INDEX IF NOT EXISTS idx_tasks_series ON tasks(recur_parent);

CREATE TABLE IF NOT EXISTS tag_colors (
    tag   TEXT PRIMARY KEY,   -- lowercase, no '#'
    color TEXT NOT NULL       -- '#RRGGBB'
);

CREATE TABLE IF NOT EXISTS focus_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT NOT NULL,               -- no FK: history survives task deletion
    started_at  TEXT NOT NULL,
    ended_at    TEXT,                         -- NULL while running
    planned_min INTEGER NOT NULL,
    seconds     INTEGER NOT NULL DEFAULT 0,   -- focused time (pauses excluded)
    completed   INTEGER NOT NULL DEFAULT 0    -- ran to the end vs stopped early
);
CREATE INDEX IF NOT EXISTS idx_focus_task ON focus_sessions(task_id);
CREATE INDEX IF NOT EXISTS idx_focus_started ON focus_sessions(started_at);

CREATE TABLE IF NOT EXISTS subtasks (
    id           TEXT PRIMARY KEY,
    task_id      TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0,
    title        TEXT NOT NULL,
    done         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id, position);

CREATE TABLE IF NOT EXISTS task_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    action  TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT '',
    at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id);

CREATE TABLE IF NOT EXISTS routine (
    position   INTEGER PRIMARY KEY,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    title      TEXT NOT NULL,
    note       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL                      -- JSON-encoded
);
"""

# public task dict key -> SQL column
TASK_COLUMNS = {"date": "date", "start": "start_time", "end": "end_time",
                "title": "title", "note": "note", "done": "done",
                "priority": "priority", "tags": "tags", "pinned": "pinned",
                "recurrence": "recurrence", "recur_parent": "recur_parent", "status": "status"}
BOOL_FIELDS = ("done", "pinned")

# columns added after a table first shipped: (table, column, definition)
ADDED_COLUMNS = [
    ("tasks", "priority", "INTEGER NOT NULL DEFAULT 1"),
    ("tasks", "tags", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "pinned", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "recurrence", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "recur_parent", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "status", "TEXT NOT NULL DEFAULT 'open'"),
]
# after adding the status column to an old table, seed it from the done flag
MIGRATE_SQL = {
    5: "UPDATE tasks SET status = CASE WHEN done = 1 THEN 'done' ELSE 'open' END",
}

# tasks with subtask progress and tracked focus time
TASK_SELECT = ("SELECT t.*, COUNT(s.id) AS sub_total, COALESCE(SUM(s.done), 0) AS sub_done, "
               "(SELECT COALESCE(SUM(f.seconds), 0) FROM focus_sessions f WHERE f.task_id = t.id) "
               "AS focus_seconds "
               "FROM tasks t LEFT JOIN subtasks s ON s.task_id = t.id")
