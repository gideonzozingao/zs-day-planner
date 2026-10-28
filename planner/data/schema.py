"""Database schema. Bump SCHEMA_VERSION when adding tables/columns.

v1: tasks, task_events, routine, settings
v2: subtasks (cascade-deleted with their task)
v3: tasks.priority / tags / pinned, focus_sessions (time tracking)
v4: tasks.recurrence / recur_parent, tag_colors
v5: projects; tasks.project_id / project_pos
v7: tasks.status (open/in_progress/done/postponed/cancelled/blocked), seeded from done
    when the column is first added (works whichever branch the database came from)
v6: every task and project has a start and end date-time: tasks.start_at / end_at,
    projects.start_at / end_at ('YYYY-MM-DDTHH:MM'). tasks.date / start_time / end_time are
    kept in step with start_at / end_at (start day, start time, end time) for indexes and
    older code paths. Older rows are filled in by Store._backfill_spans().
v8: automatic numbering: tasks.number (per project, #1 #2 …) + tasks.sub_seq (subtask counter),
    subtasks.number, projects.task_seq (task counter). Filled in by Store._backfill_numbers().
Every CREATE uses IF NOT EXISTS; columns added to existing tables are listed in
ADDED_COLUMNS and applied by Store._migrate(), so older databases upgrade in place.
"""
SCHEMA_VERSION = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id           TEXT PRIMARY KEY,
    date         TEXT NOT NULL,              -- YYYY-MM-DD: day of start_at
    start_time   TEXT NOT NULL DEFAULT '',   -- HH:MM of start_at
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
    project_id   TEXT NOT NULL DEFAULT '',    -- '' = not in a project
    project_pos  INTEGER NOT NULL DEFAULT 0,  -- order within the project
    start_at     TEXT NOT NULL DEFAULT '',    -- YYYY-MM-DDTHH:MM
    end_at       TEXT NOT NULL DEFAULT '',    -- YYYY-MM-DDTHH:MM, after start_at (may be days later)
    status       TEXT NOT NULL DEFAULT 'open', -- open|in_progress|done|postponed|cancelled|blocked
    number       INTEGER NOT NULL DEFAULT 0,  -- #n within its project (0 = not in a project)
    sub_seq      INTEGER NOT NULL DEFAULT 0   -- last subtask number handed out
);
CREATE INDEX IF NOT EXISTS idx_tasks_span ON tasks(start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_tasks_date ON tasks(date);
CREATE INDEX IF NOT EXISTS idx_tasks_series ON tasks(recur_parent);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id, project_pos);

CREATE TABLE IF NOT EXISTS projects (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    color        TEXT NOT NULL DEFAULT '',    -- '#RRGGBB'
    start_date   TEXT NOT NULL DEFAULT '',    -- v5 only (superseded by start_at)
    end_date     TEXT NOT NULL DEFAULT '',    -- v5 only (superseded by end_at)
    start_at     TEXT NOT NULL DEFAULT '',    -- YYYY-MM-DDTHH:MM
    end_at       TEXT NOT NULL DEFAULT '',    -- target finish, YYYY-MM-DDTHH:MM
    status       TEXT NOT NULL DEFAULT 'active',   -- planned | active | on_hold | done
    position     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    completed_at TEXT,
    task_seq     INTEGER NOT NULL DEFAULT 0   -- last task number handed out
);

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
    completed_at TEXT,
    number       INTEGER NOT NULL DEFAULT 0   -- 1, 2, … within its task (shown as 9.1 under #9)
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
                "recurrence": "recurrence", "recur_parent": "recur_parent",
                "project_id": "project_id", "project_pos": "project_pos",
                "start_at": "start_at", "end_at": "end_at", "status": "status",
                "number": "number"}
BOOL_FIELDS = ("done", "pinned")

# columns added after a table first shipped: (table, column, definition)
ADDED_COLUMNS = [
    ("tasks", "priority", "INTEGER NOT NULL DEFAULT 1"),
    ("tasks", "tags", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "pinned", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "recurrence", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "recur_parent", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "project_id", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "project_pos", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "start_at", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "end_at", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "start_at", "TEXT NOT NULL DEFAULT ''"),
    ("projects", "end_at", "TEXT NOT NULL DEFAULT ''"),
    ("tasks", "status", "TEXT NOT NULL DEFAULT 'open'"),
    ("tasks", "number", "INTEGER NOT NULL DEFAULT 0"),
    ("tasks", "sub_seq", "INTEGER NOT NULL DEFAULT 0"),
    ("subtasks", "number", "INTEGER NOT NULL DEFAULT 0"),
    ("projects", "task_seq", "INTEGER NOT NULL DEFAULT 0"),
]
# one-time data fixes run right after a column is added to an existing table
ON_COLUMN_ADDED = {
    ("tasks", "status"): "UPDATE tasks SET status = CASE WHEN done = 1 THEN 'done' ELSE 'open' END",
}

PROJECT_STATUSES = ("planned", "active", "on_hold", "done")
PROJECT_STATUS_NAMES = {"planned": "Planned", "active": "Active", "on_hold": "On hold", "done": "Done"}
PROJECT_COLUMNS = ("name", "description", "color", "start_at", "end_at", "status")

# tasks with subtask progress and tracked focus time
TASK_SELECT = ("SELECT t.*, COUNT(s.id) AS sub_total, COALESCE(SUM(s.done), 0) AS sub_done, "
               "(SELECT COALESCE(SUM(f.seconds), 0) FROM focus_sessions f WHERE f.task_id = t.id) "
               "AS focus_seconds "
               "FROM tasks t LEFT JOIN subtasks s ON s.task_id = t.id")
