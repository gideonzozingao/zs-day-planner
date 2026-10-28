"""SQLite persistence: projects, tasks, subtasks, activity log, routine and settings.

Hierarchy: project -> tasks -> subtasks. A task outside any project has project_id ''.
Every task and every project has a start and an end date-time (timespan.py). A task shows
in the day view of every day its span overlaps; it may run over several days.

Tasks are handed to the UI as plain dicts:
    id, start_at, end_at ('YYYY-MM-DDTHH:MM'), date / start / end (start day, start time,
    end time: derived from the span), title, note, done, created_at, updated_at,
    completed_at, project_id, project_pos, sub_total, sub_done
Subtasks:
    id, task_id, position, title, done, created_at, completed_at
Projects:
    id, name, description, color, start_at, end_at, status, position,
    created_at, updated_at, completed_at
"""
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from .. import recurrence as R
from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS
from pathlib import Path

from ..config import DATA_DIR, DB_FILE, DEFAULT_ROUTINE, DEFAULT_SETTINGS, LEGACY_JSON
from ..utils import now_stamp
from .schema import (
    ADDED_COLUMNS, BOOL_FIELDS, ON_COLUMN_ADDED, PROJECT_COLUMNS, PROJECT_STATUSES, SCHEMA, SCHEMA_VERSION,
    TASK_COLUMNS, TASK_SELECT,
)

TASK_ORDER = " ORDER BY t.start_at, t.end_at, t.project_id, t.number, t.title COLLATE NOCASE"
PROJECT_TASK_ORDER = " ORDER BY t.project_pos, t.created_at"


def task_progress(tasks) -> float:
    """0..1 over a list of task dicts: a done task counts 1, an open one counts its
    subtask fraction, so ticking subtasks moves a project's bar too. Cancelled tasks are
    left out (they're no longer part of the work)."""
    tasks = [t for t in tasks if t.get("status") != STATUS.CANCELLED]
    if not tasks:
        return 0.0
    score = 0.0
    for t in tasks:
        if t["done"]:
            score += 1
        elif t.get("sub_total"):
            score += t["sub_done"] / t["sub_total"]
    return score / len(tasks)


class Store:
    def __init__(self, path: Path = DB_FILE):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = Path(path)
        self.db = None
        try:
            self._open()
        except sqlite3.DatabaseError:
            # unreadable file: keep it for inspection and start clean
            if self.db is not None:
                self.db.close()
            self.path.replace(self.path.with_name(
                f"{self.path.stem}.corrupt-{datetime.now():%Y%m%d%H%M%S}.db"))
            self._open()
        self.settings = dict(DEFAULT_SETTINGS)
        self.settings.update(self._load_settings())

    # ------------------------------------------------------------------ lifecycle
    def _open(self):
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        self._migrate()                         # add v3 columns to an older tasks table first
        self.db.executescript(SCHEMA)          # then create anything missing
        self._backfill_spans()                 # v6: give older rows a start/end date-time
        self._backfill_numbers()               # v8: number project tasks and all subtasks
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS recur_skips (series TEXT NOT NULL, day TEXT NOT NULL, "
            "PRIMARY KEY (series, day));"
            "CREATE TABLE IF NOT EXISTS recur_series_dead (series TEXT PRIMARY KEY);")
        self._close_stale_focus_sessions()
        if version and version >= 4:          # fresh/upgraded db: top up repeating tasks
            self.ensure_recurrences()
        imported = False
        if version == 0:
            with self.db:
                self._write_routine([dict(zip(("start", "end", "title", "note"), r))
                                     for r in DEFAULT_ROUTINE])
                imported = self._import_legacy_json()
        if version < SCHEMA_VERSION:
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        if imported:
            LEGACY_JSON.replace(LEGACY_JSON.with_name("planner.migrated.json"))

    def _migrate(self):
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with self.db:
            for table, column, ddl in ADDED_COLUMNS:
                if table not in tables:
                    continue                    # fresh database: SCHEMA creates it complete
                cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
                if column not in cols:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                    if (table, column) in ON_COLUMN_ADDED:
                        self.db.execute(ON_COLUMN_ADDED[(table, column)])
                    if (table, column) == ("tasks", "number"):
                        self._adopt_manual_numbers = True

    def workday(self):
        """(start, end) HH:MM of the working day: first to last routine block, else 08:00-16:30.
        Used when a task is created without times."""
        rows = self.db.execute("SELECT MIN(start_time), MAX(end_time) FROM routine").fetchone()
        if rows and rows[0] and rows[1] and rows[1] > rows[0]:
            return rows[0], rows[1]
        return TS.DEFAULT_WORKDAY

    def _backfill_spans(self):
        """Rows from before v6 have no start_at/end_at. Timed tasks keep their block; tasks that
        were 'anytime' get the working day; unscheduled project tasks get today (or the project's
        start day if later); projects get their old dates at the working day's start and end."""
        if not (self.db.execute("SELECT 1 FROM tasks WHERE start_at = '' LIMIT 1").fetchone()
                or self.db.execute("SELECT 1 FROM projects WHERE start_at = '' LIMIT 1").fetchone()):
            return
        wd = self.workday()
        today = date.today()
        with self.db:
            projects = {}
            for r in self.db.execute("SELECT * FROM projects").fetchall():
                start = date.fromisoformat(r["start_date"]) if r["start_date"] else today
                end = date.fromisoformat(r["end_date"]) if r["end_date"] else start + timedelta(days=30)
                sa, ea = TS.at(start, wd[0]), TS.at(max(end, start), wd[1])
                projects[r["id"]] = start
                if not r["start_at"]:
                    self.db.execute("UPDATE projects SET start_at = ?, end_at = ? WHERE id = ?",
                                    (TS.to_str(sa), TS.to_str(ea), r["id"]))
            for r in self.db.execute("SELECT id, date, start_time, end_time, project_id FROM tasks "
                                     "WHERE start_at = ''").fetchall():
                d = date.fromisoformat(r["date"]) if r["date"] else max(today, projects.get(r["project_id"], today))
                sa, ea = TS.make_span(d, r["start_time"], r["end_time"], wd)
                self._write_span(r["id"], sa, ea)

    def _write_span(self, tid, sa, ea):
        """Store a span and keep the derived date/start_time/end_time columns in step."""
        sa, ea = TS.to_dt(sa), TS.to_dt(ea)
        self.db.execute("UPDATE tasks SET start_at = ?, end_at = ?, date = ?, start_time = ?, end_time = ? "
                        "WHERE id = ?", (TS.to_str(sa), TS.to_str(ea), sa.date().isoformat(),
                                         f"{sa:%H:%M}", f"{ea:%H:%M}", tid))

    def _span_of(self, t):
        """(start_dt, end_dt) for a task dict, deriving one from date/start/end if needed."""
        if t.get("start_at") and t.get("end_at"):
            return TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
        d = t.get("date") or date.today()
        d = date.fromisoformat(d) if isinstance(d, str) else d
        return TS.make_span(d, t.get("start", ""), t.get("end", ""), self.workday())

    def _close_stale_focus_sessions(self):
        """A session left open by a crash/power cut keeps the time recorded at its last heartbeat."""
        rows = self.db.execute("SELECT id, started_at, seconds FROM focus_sessions WHERE ended_at IS NULL")
        with self.db:
            for r in rows.fetchall():
                end = datetime.fromisoformat(r["started_at"]) + timedelta(seconds=r["seconds"])
                self.db.execute("UPDATE focus_sessions SET ended_at = ? WHERE id = ?",
                                (end.isoformat(timespec="seconds"), r["id"]))

    def close(self):
        try:
            self.db.close()
        except sqlite3.Error:
            pass

    # ------------------------------------------------------------------ internals
    def _import_legacy_json(self) -> bool:
        if not LEGACY_JSON.exists():
            return False
        try:
            raw = json.loads(LEGACY_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        stamp = now_stamp()
        for t in raw.get("tasks", []):
            tid = t.get("id") or uuid.uuid4().hex
            done = bool(t.get("done"))
            self._insert_task({"id": tid, "date": t["date"], "start": t.get("start", ""),
                               "end": t.get("end", ""), "title": t["title"], "note": t.get("note", ""),
                               "done": done, "created_at": stamp, "updated_at": stamp,
                               "completed_at": stamp if done else None}, mode="INSERT OR IGNORE")
            self._log(tid, "imported", "from planner.json")
        if raw.get("routine"):
            self._write_routine(raw["routine"])
        for k, v in raw.get("settings", {}).items():
            self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                            (k, json.dumps(v)))
        return True

    def _insert_task(self, t, mode="INSERT"):
        sa, ea = self._span_of(t)
        self.db.execute(
            f"{mode} INTO tasks (id, date, start_time, end_time, title, note, done, "
            f"created_at, updated_at, completed_at, priority, tags, pinned, recurrence, recur_parent, "
            f"project_id, project_pos, start_at, end_at, status, number, sub_seq) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t["id"], sa.date().isoformat(), f"{sa:%H:%M}", f"{ea:%H:%M}", t["title"], t["note"],
             int(bool(t["done"])),
             t["created_at"], t["updated_at"], t["completed_at"], int(t.get("priority", 1)),
             t.get("tags", ""), int(bool(t.get("pinned"))), t.get("recurrence", ""),
             t.get("recur_parent", ""), t.get("project_id", "") or "", int(t.get("project_pos", 0) or 0),
             TS.to_str(sa), TS.to_str(ea), STATUS.normalize(t.get("status", "open"), t.get("done")),
             int(t.get("number", 0) or 0), int(t.get("sub_seq", 0) or 0)))

    def _insert_subtask(self, tid, position, title, done, created_at=None, completed_at=None,
                        sid=None, mode="INSERT", number=None):
        """number=None hands out the task's next subtask number; restores pass the old one."""
        sid = sid or uuid.uuid4().hex
        stamp = now_stamp()
        if completed_at is None and done:
            completed_at = stamp
        if number is None:
            number = self._next_sub_no(tid)
        else:
            self.db.execute("UPDATE tasks SET sub_seq = MAX(sub_seq, ?) WHERE id = ?", (number, tid))
        self.db.execute(
            f"{mode} INTO subtasks (id, task_id, position, title, done, created_at, completed_at, number) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, tid, position, title, int(bool(done)), created_at or stamp,
             completed_at if done else None, int(number)))
        return sid

    # ------------------------------------------------------------------ numbering
    def _next_sub_no(self, tid) -> int:
        self.db.execute("UPDATE tasks SET sub_seq = sub_seq + 1 WHERE id = ?", (tid,))
        r = self.db.execute("SELECT sub_seq FROM tasks WHERE id = ?", (tid,)).fetchone()
        return r[0] if r else 1

    def _next_task_no(self, pid) -> int:
        """Next #n in a project. Never reuses a number, even after deletes."""
        if not pid:
            return 0
        self.db.execute("UPDATE projects SET task_seq = MAX(task_seq, "
                        "(SELECT COALESCE(MAX(number), 0) FROM tasks WHERE project_id = ?)) + 1 WHERE id = ?",
                        (pid, pid))
        r = self.db.execute("SELECT task_seq FROM projects WHERE id = ?", (pid,)).fetchone()
        return r[0] if r else 0

    def _backfill_numbers(self):
        """Give unnumbered project tasks and subtasks a number. The first time (when the column
        is added) titles already starting with a hand-typed '#12 ' keep 12 as their number and
        lose the prefix, so they don't read '#12 #12 …'."""
        adopt = getattr(self, "_adopt_manual_numbers", False)
        self._adopt_manual_numbers = False
        need_t = self.db.execute("SELECT 1 FROM tasks WHERE project_id != '' AND number = 0 LIMIT 1").fetchone()
        need_s = self.db.execute("SELECT 1 FROM subtasks WHERE number = 0 LIMIT 1").fetchone()
        if not (need_t or need_s or adopt):
            return
        with self.db:
            for p in self.db.execute("SELECT id FROM projects").fetchall():
                rows = self.db.execute("SELECT id, title, number FROM tasks WHERE project_id = ? "
                                       "ORDER BY project_pos, created_at", (p["id"],)).fetchall()
                used = {r["number"] for r in rows if r["number"]}
                pending = []
                for r in rows:
                    if r["number"]:
                        continue
                    n, title = NUM.split_manual(r["title"]) if adopt else (None, r["title"])
                    if n and n not in used:
                        used.add(n)
                        self.db.execute("UPDATE tasks SET number = ?, title = ? WHERE id = ?", (n, title, r["id"]))
                    else:
                        pending.append(r["id"])
                nxt = max(used, default=0)
                for tid in pending:
                    nxt += 1
                    self.db.execute("UPDATE tasks SET number = ? WHERE id = ?", (nxt, tid))
                self.db.execute("UPDATE projects SET task_seq = MAX(task_seq, ?) WHERE id = ?", (nxt, p["id"]))
            for t in self.db.execute("SELECT DISTINCT task_id FROM subtasks WHERE number = 0").fetchall():
                subs = self.db.execute("SELECT id, number FROM subtasks WHERE task_id = ? ORDER BY position",
                                       (t[0],)).fetchall()
                n = max((s["number"] for s in subs), default=0)
                for s in subs:
                    if not s["number"]:
                        n += 1
                        self.db.execute("UPDATE subtasks SET number = ? WHERE id = ?", (n, s["id"]))
                self.db.execute("UPDATE tasks SET sub_seq = MAX(sub_seq, ?) WHERE id = ?", (n, t[0]))

    def renumber_project(self, pid):
        """Number the project's tasks 1..n in their current order and each task's subtasks 1..m
        in checklist order. Returns a snapshot for restore_numbers()."""
        snap = {"pid": pid, "seq": self.project(pid)["task_seq"], "tasks": [], "subs": []}
        with self.db:
            for i, t in enumerate(self.project_tasks(pid), start=1):
                snap["tasks"].append((t["id"], t["number"], t["sub_seq"]))
                subs = self.subtasks(t["id"])
                for j, s in enumerate(subs, start=1):
                    snap["subs"].append((s["id"], s["number"]))
                    self.db.execute("UPDATE subtasks SET number = ? WHERE id = ?", (j, s["id"]))
                self.db.execute("UPDATE tasks SET number = ?, sub_seq = ? WHERE id = ?", (i, len(subs), t["id"]))
            self.db.execute("UPDATE projects SET task_seq = ? WHERE id = ?", (len(snap["tasks"]), pid))
        return snap

    def restore_numbers(self, snap):
        with self.db:
            for tid, n, seq in snap["tasks"]:
                self.db.execute("UPDATE tasks SET number = ?, sub_seq = ? WHERE id = ?", (n, seq, tid))
            for sid, n in snap["subs"]:
                self.db.execute("UPDATE subtasks SET number = ? WHERE id = ?", (n, sid))
            self.db.execute("UPDATE projects SET task_seq = ? WHERE id = ?", (snap["seq"], snap["pid"]))

    def _sync_subtasks(self, tid, items, quiet=False) -> bool:
        """Make the task's subtasks match `items` (list of {id?, title, done}) in that order.
        Existing ids are updated in place so their timestamps survive. No transaction here."""
        existing = {s["id"]: s for s in self.subtasks(tid)}
        kept, changed, pos = set(), False, 0
        stamp = now_stamp()
        for it in items:
            title = (it.get("title") or "").strip()
            if not title:
                continue
            done = bool(it.get("done"))
            old = existing.get(it.get("id"))
            if old:
                kept.add(old["id"])
                if (old["position"], old["title"], old["done"]) != (pos, title, done):
                    completed = old["completed_at"] if done == old["done"] else (stamp if done else None)
                    self.db.execute(
                        "UPDATE subtasks SET position = ?, title = ?, done = ?, completed_at = ? WHERE id = ?",
                        (pos, title, int(done), completed, old["id"]))
                    changed = True
                    if not quiet:
                        if title != old["title"]:
                            self._log(tid, "subtask renamed", f"{old['title']} → {title}")
                        if done != old["done"]:
                            self._log(tid, "subtask completed" if done else "subtask reopened", title)
            else:
                self._insert_subtask(tid, pos, title, done)
                changed = True
                if not quiet:
                    self._log(tid, "subtask added", title)
            pos += 1
        for sid, old in existing.items():
            if sid not in kept:
                self.db.execute("DELETE FROM subtasks WHERE id = ?", (sid,))
                changed = True
                if not quiet:
                    self._log(tid, "subtask removed", old["title"])
        return changed

    def _touch(self, tid):
        self.db.execute("UPDATE tasks SET updated_at = ? WHERE id = ?", (now_stamp(), tid))

    def _log(self, tid, action, detail=""):
        self.db.execute("INSERT INTO task_events (task_id, action, detail, at) VALUES (?, ?, ?, ?)",
                        (tid, action, detail, now_stamp()))

    def _write_routine(self, items):
        self.db.execute("DELETE FROM routine")
        self.db.executemany(
            "INSERT INTO routine (position, start_time, end_time, title, note) VALUES (?, ?, ?, ?, ?)",
            [(i, r["start"], r["end"], r["title"], r.get("note", "")) for i, r in enumerate(items)])

    def _load_settings(self):
        out = {}
        for r in self.db.execute("SELECT key, value FROM settings"):
            try:
                out[r["key"]] = json.loads(r["value"])
            except json.JSONDecodeError:
                pass
        return out

    @staticmethod
    def _task(row):
        if row is None:
            return None
        keys = row.keys()
        return {"id": row["id"], "date": row["date"], "start": row["start_time"], "end": row["end_time"],
                "start_at": row["start_at"] if "start_at" in keys else "",
                "end_at": row["end_at"] if "end_at" in keys else "",
                "title": row["title"], "note": row["note"], "done": bool(row["done"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "completed_at": row["completed_at"],
                "priority": row["priority"], "tags": row["tags"], "pinned": bool(row["pinned"]),
                "recurrence": row["recurrence"] if "recurrence" in keys else "",
                "recur_parent": row["recur_parent"] if "recur_parent" in keys else "",
                "project_id": row["project_id"] if "project_id" in keys else "",
                "project_pos": row["project_pos"] if "project_pos" in keys else 0,
                "number": row["number"] if "number" in keys else 0,
                "sub_seq": row["sub_seq"] if "sub_seq" in keys else 0,
                "status": STATUS.normalize(row["status"] if "status" in keys else "open", bool(row["done"])),
                "sub_total": row["sub_total"] if "sub_total" in keys else 0,
                "sub_done": row["sub_done"] if "sub_done" in keys else 0,
                "focus_seconds": row["focus_seconds"] if "focus_seconds" in keys else 0}

    @staticmethod
    def _project(row):
        return dict(row) if row is not None else None

    @staticmethod
    def _sub(row):
        return {"id": row["id"], "task_id": row["task_id"], "position": row["position"],
                "title": row["title"], "done": bool(row["done"]),
                "created_at": row["created_at"], "completed_at": row["completed_at"],
                "number": row["number"] if "number" in row.keys() else 0}

    # ------------------------------------------------------------ settings & routine
    def save_settings(self):
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                                [(k, json.dumps(v)) for k, v in self.settings.items()])

    @property
    def routine(self):
        return [{"start": r["start_time"], "end": r["end_time"], "title": r["title"], "note": r["note"]}
                for r in self.db.execute("SELECT * FROM routine ORDER BY position")]

    # ------------------------------------------------------------------- queries
    def for_day(self, d: date):
        """Tasks whose span overlaps day d (a multi-day task shows on each of its days)."""
        hi, lo = TS.day_bounds(d)
        rows = self.db.execute(TASK_SELECT + " WHERE t.start_at < ? AND t.end_at > ? GROUP BY t.id" + TASK_ORDER,
                               (hi, lo))
        return [self._task(r) for r in rows]

    def find(self, tid):
        if not tid:
            return None
        return self._task(self.db.execute(TASK_SELECT + " WHERE t.id = ? GROUP BY t.id",
                                          (tid,)).fetchone())

    def subtasks(self, tid):
        return [self._sub(r) for r in self.db.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY position", (tid,))]

    def subtasks_for_day(self, d: date):
        """-> {task_id: [subtask, ...]} for every task on that day."""
        out = {}
        hi, lo = TS.day_bounds(d)
        for r in self.db.execute(
                "SELECT s.* FROM subtasks s JOIN tasks t ON t.id = s.task_id "
                "WHERE t.start_at < ? AND t.end_at > ? ORDER BY s.task_id, s.position", (hi, lo)):
            out.setdefault(r["task_id"], []).append(self._sub(r))
        return out

    def exists(self, d: date, title: str, start: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM tasks WHERE date = ? AND title = ? AND start_time = ? LIMIT 1",
            (d.isoformat(), title, start)).fetchone() is not None

    def history(self, tid):
        return [dict(r) for r in self.db.execute(
            "SELECT action, detail, at FROM task_events WHERE task_id = ? ORDER BY id", (tid,))]

    def stats(self, start: date, end: date):
        """(done, total) for tasks dated within [start, end]."""
        r = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(done), 0) FROM tasks WHERE date BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat())).fetchone()
        return r[1], r[0]

    # ------------------------------------------------------------------ mutations
    def add(self, d, title, start="", end="", note="", done=False, subtasks=None,
            priority=1, tags="", pinned=False, recurrence="", recur_parent="", project_id="",
            start_at=None, end_at=None, status=None):
        """Create a task. Its span is start_at..end_at when given; otherwise day d (today if
        None) with HH:MM start/end, and with no times the working day (see workday())."""
        stamp = now_stamp()
        tid = uuid.uuid4().hex
        status = status if STATUS.is_valid(status) else STATUS.from_done(done)
        done = status == STATUS.DONE          # status is authoritative when given
        if start_at and end_at:
            sa, ea = TS.to_dt(start_at), TS.to_dt(end_at)
            if ea <= sa:
                ea = sa + timedelta(minutes=30)
        else:
            day = d if isinstance(d, date) else (date.fromisoformat(d) if d else date.today())
            sa, ea = TS.make_span(day, start, end, self.workday())
        d = sa.date()
        day = d.isoformat()
        project_id = project_id or ""
        t = {"id": tid, "date": day, "start": f"{sa:%H:%M}", "end": f"{ea:%H:%M}",
             "start_at": TS.to_str(sa), "end_at": TS.to_str(ea),
             "title": title, "note": note, "done": bool(done),
             "created_at": stamp, "updated_at": stamp, "completed_at": stamp if done else None,
             "priority": int(priority if priority is not None else 1), "tags": tags or "",
             "pinned": bool(pinned), "recurrence": recurrence if R.is_valid(recurrence) else "",
             "recur_parent": recur_parent, "project_id": project_id,
             "project_pos": self._next_project_pos(project_id) if project_id else 0, "status": status}
        n = sum(1 for s in subtasks or [] if (s.get("title") or "").strip())
        with self.db:
            t["number"] = self._next_task_no(project_id)      # #n in its project (0 outside one)
            self._insert_task(t)
            if n:
                self._sync_subtasks(t["id"], subtasks, quiet=True)
            detail = []
            if n:
                detail.append(f"with {n} subtask(s)")
            if t["recurrence"] and not recur_parent:
                detail.append(R.describe(t["recurrence"], d).lower())
            if project_id and not recur_parent:
                p = self.project(project_id)
                if p:
                    detail.append(f"in project {p['name']}")
            self._log(tid, "created", ", ".join(detail))
        if t["recurrence"] and not recur_parent:
            self.ensure_recurrences(series=tid)
        return self.find(tid)

    def update(self, tid, **fields):
        """Change task fields. The span can be set with start_at/end_at (date-times), moved
        with date= (a day: same times and length, starting that day), or retimed on its start
        day with start=/end= (HH:MM). date/start/end columns always follow the span."""
        t = self.find(tid)
        if not t:
            return None
        sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
        if "date" in fields:
            v = fields.pop("date")
            if v:
                v = v if isinstance(v, date) else date.fromisoformat(v)
                sa, ea = TS.shift_to(sa, ea, v)
        if "start" in fields or "end" in fields:
            st, en = fields.pop("start", t["start"]), fields.pop("end", t["end"])
            sa, ea = TS.make_span(sa.date(), st, en, self.workday())
        if "start_at" in fields or "end_at" in fields:
            sa = TS.to_dt(fields.pop("start_at", None) or sa)
            ea = TS.to_dt(fields.pop("end_at", None) or ea)
        if ea <= sa:
            ea = sa + timedelta(minutes=30)
        # keep status and the done checkbox consistent whichever one the caller set
        if "status" in fields and "done" not in fields:
            fields["done"] = fields["status"] == STATUS.DONE
        elif "done" in fields and "status" not in fields:
            want = bool(fields["done"])
            if want and t["status"] != STATUS.DONE:
                fields["status"] = STATUS.DONE
            elif not want and t["status"] == STATUS.DONE:
                fields["status"] = STATUS.OPEN
        span_changed = (TS.to_str(sa), TS.to_str(ea)) != (t["start_at"], t["end_at"])

        new = {}
        for k, v in fields.items():
            if k not in TASK_COLUMNS:
                raise KeyError(f"Unknown task field: {k}")
            if k == "project_id":
                v = v or ""
            if k in BOOL_FIELDS:
                v = bool(v)
            if k == "priority":
                v = int(v)
            if v != t[k]:
                new[k] = v
        if not new and not span_changed:
            return t
        stamp = now_stamp()
        sets = [f"{TASK_COLUMNS[k]} = ?" for k in new]
        vals = [int(v) if k in BOOL_FIELDS else v for k, v in new.items()]
        sets.append("updated_at = ?")
        vals.append(stamp)
        if "done" in new:
            sets.append("completed_at = ?")
            vals.append(stamp if new["done"] else None)
        if "project_id" in new and "project_pos" not in new and new["project_id"]:
            sets.append("project_pos = ?")
            vals.append(self._next_project_pos(new["project_id"]))
        if "project_id" in new and "number" not in new:
            # a task joining a project gets that project's next number; leaving one drops it
            sets.append("number = ?")
            vals.append(self._next_task_no(new["project_id"]) if new["project_id"] else 0)
        with self.db:
            self.db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", (*vals, tid))
            if span_changed:
                self._write_span(tid, sa, ea)
                old_label = TS.span_label(t["start_at"], t["end_at"])
                new_label = TS.span_label(sa, ea)
                moved = sa.date().isoformat() != t["date"]
                self._log(tid, "moved" if moved else "rescheduled", f"{new_label}   (was {old_label})")
            if "done" in new:
                self._log(tid, "completed" if new["done"] else "reopened")
            if "pinned" in new:
                self._log(tid, "starred" if new["pinned"] else "unstarred")
            if "project_id" in new:
                p = self.project(new["project_id"]) if new["project_id"] else None
                self._log(tid, "project", f"→ {p['name']}" if p else "removed from project")
            if "status" in new and new["status"] not in (STATUS.DONE, STATUS.OPEN):
                self._log(tid, "status", STATUS.label(new["status"]))
            edited = [k for k in new if k not in ("done", "pinned", "project_id", "project_pos", "status")]
            if edited:
                self._log(tid, "edited", ", ".join(edited))
        return self.find(tid)

    def set_subtasks(self, tid, items) -> bool:
        with self.db:
            changed = self._sync_subtasks(tid, items)
            if changed:
                self._touch(tid)
        return changed

    def set_subtask_done(self, sid, done):
        """Tick/untick one subtask. Returns its task id (or None)."""
        row = self.db.execute("SELECT * FROM subtasks WHERE id = ?", (sid,)).fetchone()
        if row is None:
            return None
        if bool(row["done"]) != bool(done):
            stamp = now_stamp()
            with self.db:
                self.db.execute("UPDATE subtasks SET done = ?, completed_at = ? WHERE id = ?",
                                (int(bool(done)), stamp if done else None, sid))
                self._touch(row["task_id"])
                self._log(row["task_id"], "subtask completed" if done else "subtask reopened", row["title"])
        return row["task_id"]

    def duplicate(self, tid):
        t = self.find(tid)
        if not t:
            return None
        subs = [{"title": s["title"], "done": False} for s in self.subtasks(tid)]
        return self.add(None, t["title"], note=t["note"], start_at=t["start_at"], end_at=t["end_at"],
                        subtasks=subs, priority=t["priority"], tags=t["tags"], project_id=t["project_id"])

    def delete(self, tid):
        """Delete a task (subtasks cascade). Returns a snapshot usable by restore().
        For a repeating occurrence, a tombstone stops it being regenerated (undo clears it)."""
        t = self.find(tid)
        if t:
            t["subtasks"] = self.subtasks(tid)
            with self.db:
                if t["recurrence"]:
                    self.db.execute("INSERT OR IGNORE INTO recur_skips (series, day) VALUES (?, ?)",
                                    (self.series_parent(t), t["date"]))
                self.db.execute("DELETE FROM tasks WHERE id = ?", (tid,))
                self._log(tid, "deleted")
        return t

    def restore(self, t):
        with self.db:
            if t.get("recurrence"):
                self.db.execute("DELETE FROM recur_skips WHERE series = ? AND day = ?",
                                (self.series_parent(t), t["date"]))
            self._insert_task(dict(t, updated_at=now_stamp()), mode="INSERT OR IGNORE")
            for s in t.get("subtasks", []):
                self._insert_subtask(t["id"], s["position"], s["title"], s["done"], s["created_at"],
                                     s["completed_at"], sid=s["id"], mode="INSERT OR IGNORE",
                                     number=s.get("number"))
            self._log(t["id"], "restored")

    def series_parent(self, t):
        return t["recur_parent"] or t["id"]

    def series_rule(self, series_id):
        row = self.db.execute("SELECT recurrence, date FROM tasks WHERE id = ?", (series_id,)).fetchone()
        return (row["recurrence"], date.fromisoformat(row["date"])) if row else ("", None)

    def ensure_recurrences(self, series=None, today=None):
        """Materialise each active series up to its horizon. Idempotent: skips dates that
        already exist, and never recreates an occurrence the user deleted (a tombstone row
        in recur_skips). Returns the number of new occurrences created."""
        today = today or date.today()
        if series:
            parents = [self.db.execute("SELECT * FROM tasks WHERE id = ?", (series,)).fetchone()]
        else:
            parents = self.db.execute(
                "SELECT * FROM tasks WHERE recurrence != '' AND recur_parent = ''").fetchall()
        created = 0
        for row in parents:
            if row is None or not R.is_valid(row["recurrence"]):
                continue
            pid, rule = row["id"], row["recurrence"]
            anchor = date.fromisoformat(row["date"])
            horizon = today + timedelta(days=R.HORIZON_DAYS.get(rule, 30))
            existing = {r["date"] for r in self.db.execute(
                "SELECT date FROM tasks WHERE id = ? OR recur_parent = ?", (pid, pid))}
            skipped = {r["day"] for r in self.db.execute(
                "SELECT day FROM recur_skips WHERE series = ?", (pid,))}
            template = self._task(row)
            for d in R.occurrences(rule, anchor, horizon):
                iso = d.isoformat()
                if iso in existing or iso in skipped:
                    continue
                sa, ea = TS.shift_to(template["start_at"], template["end_at"], d)
                self.add(d, template["title"], note=template["note"], start_at=sa, end_at=ea,
                         priority=template["priority"], tags=template["tags"],
                         recurrence=rule, recur_parent=pid, project_id=template["project_id"])
                created += 1
        return created

    def set_recurrence(self, tid, rule):
        """Turn repeating on/off for a task's series, anchored on this occurrence's date."""
        t = self.find(tid)
        if not t:
            return
        rule = rule if R.is_valid(rule) else ""
        parent = self.series_parent(t)
        with self.db:
            if rule:
                # re-anchor the series on this task and make it the parent
                self.db.execute("UPDATE tasks SET recurrence = ?, recur_parent = '' WHERE id = ?", (rule, tid))
                self.db.execute("UPDATE tasks SET recur_parent = ? WHERE recur_parent = ? AND id != ?",
                                (tid, parent, tid))
                self._log(tid, "recurrence set", R.describe(rule, date.fromisoformat(t["date"])).lower())
            else:
                self.db.execute("UPDATE tasks SET recurrence = '' WHERE id = ? OR recur_parent = ?", (tid, parent))
                self._log(tid, "recurrence stopped")
        if rule:
            self.ensure_recurrences(series=tid)

    def delete_series(self, tid):
        """Delete every occurrence of this task's series (past rows kept as history? no: all)."""
        t = self.find(tid)
        if not t:
            return 0
        parent = self.series_parent(t)
        ids = [r["id"] for r in self.db.execute(
            "SELECT id FROM tasks WHERE id = ? OR recur_parent = ?", (parent, parent))]
        with self.db:
            self.db.execute("DELETE FROM tasks WHERE id = ? OR recur_parent = ?", (parent, parent))
            self.db.execute("INSERT OR REPLACE INTO recur_series_dead (series) VALUES (?)", (parent,))
        return len(ids)

    def load_routine(self, d: date) -> int:
        n = 0
        for r in self.routine:
            if not self.exists(d, r["title"], r["start"]):
                self.add(d, r["title"], r["start"], r["end"], r.get("note", ""))
                n += 1
        return n

    def save_as_routine(self, d: date):
        with self.db:
            # same-day, non-project blocks shorter than the working day (not catch-all tasks)
            wd = self.workday()
            self._write_routine([t for t in self.for_day(d)
                                 if t["start_at"][:10] == t["end_at"][:10] == d.isoformat()
                                 and not t["project_id"] and (t["start"], t["end"]) != wd])

    def carry_over(self, src: date, dst: date) -> int:
        """Copy unfinished tasks that end on src (with their subtask checklist as-is) to another
        day: the copy ends on dst at the same time, with the same length. Tasks still running
        past src are left alone."""
        n = 0
        for t in self.for_day(src):
            sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
            if t["status"] in (STATUS.DONE, STATUS.CANCELLED) or (ea - timedelta(minutes=1)).date() > src:
                continue
            delta = dst - (ea - timedelta(minutes=1)).date()
            nsa, nea = sa + delta, ea + delta
            if not self.exists(nsa.date(), t["title"], f"{nsa:%H:%M}"):
                subs = [{"title": s["title"], "done": s["done"]} for s in self.subtasks(t["id"])]
                self.add(None, t["title"], note=t["note"], start_at=nsa, end_at=nea, subtasks=subs,
                         priority=t["priority"], tags=t["tags"], project_id=t["project_id"])
                n += 1
        return n

    # ------------------------------------------------------------------ focus tracking
    def focus_start(self, tid, planned_min) -> int:
        with self.db:
            cur = self.db.execute(
                "INSERT INTO focus_sessions (task_id, started_at, planned_min) VALUES (?, ?, ?)",
                (tid, now_stamp(), int(planned_min)))
        return cur.lastrowid

    def focus_heartbeat(self, sid, seconds):
        """Called periodically while focusing, so a crash loses at most one interval."""
        with self.db:
            self.db.execute("UPDATE focus_sessions SET seconds = ? WHERE id = ?", (int(seconds), sid))

    def focus_end(self, sid, seconds, completed):
        row = self.db.execute("SELECT task_id FROM focus_sessions WHERE id = ?", (sid,)).fetchone()
        if row is None:
            return
        with self.db:
            if seconds < 30:     # a misclick, not a session
                self.db.execute("DELETE FROM focus_sessions WHERE id = ?", (sid,))
                return
            self.db.execute("UPDATE focus_sessions SET seconds = ?, ended_at = ?, completed = ? WHERE id = ?",
                            (int(seconds), now_stamp(), int(bool(completed)), sid))
            self._log(row["task_id"], "focused",
                      f"{round(seconds / 60)} min" + ("" if completed else " (stopped early)"))

    def focus_seconds_on(self, d: date) -> int:
        """Total focused time in sessions started on day d."""
        r = self.db.execute("SELECT COALESCE(SUM(seconds), 0) FROM focus_sessions WHERE started_at LIKE ?",
                            (d.isoformat() + "%",)).fetchone()
        return r[0]

    # ------------------------------------------------------------------ tag colours
    def tag_colors(self) -> dict:
        return {r["tag"]: r["color"] for r in self.db.execute("SELECT tag, color FROM tag_colors")}

    def set_tag_color(self, tag, color):
        tag = tag.lower().lstrip("#")
        with self.db:
            if color:
                self.db.execute("INSERT OR REPLACE INTO tag_colors (tag, color) VALUES (?, ?)", (tag, color))
            else:
                self.db.execute("DELETE FROM tag_colors WHERE tag = ?", (tag,))

    def all_tags(self):
        """Every tag in use, most-used first, with how many open tasks carry it."""
        counts = {}
        for r in self.db.execute("SELECT tags FROM tasks WHERE tags != '' AND done = 0"):
            for tag in r["tags"].split():
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

    # ------------------------------------------------------------------ projects
    def _next_project_pos(self, pid) -> int:
        r = self.db.execute("SELECT COALESCE(MAX(project_pos), -1) FROM tasks WHERE project_id = ?",
                            (pid,)).fetchone()
        return r[0] + 1

    def projects(self, include_done=True):
        """Projects in display order: open ones by finish date, then done ones."""
        sql = "SELECT * FROM projects"
        if not include_done:
            sql += " WHERE status != 'done'"
        sql += (" ORDER BY status = 'done', end_at, position, "
                "name COLLATE NOCASE")
        return [self._project(r) for r in self.db.execute(sql)]

    def project(self, pid):
        if not pid:
            return None
        return self._project(self.db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone())

    def add_project(self, name, description="", color="", start_at=None, end_at=None, status=""):
        """start_at / end_at: date-times (or dates, which take the working day's start / end).
        Both are required; missing ones default to today and 30 days later."""
        stamp = now_stamp()
        pid = uuid.uuid4().hex
        sa, ea = self._project_span(start_at, end_at)
        start, end = TS.to_str(sa), TS.to_str(ea)
        if status not in PROJECT_STATUSES:
            status = "planned" if sa > datetime.now() else "active"
        pos = self.db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM projects").fetchone()[0]
        with self.db:
            self.db.execute(
                "INSERT INTO projects (id, name, description, color, start_date, end_date, start_at, end_at, "
                "status, position, created_at, updated_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, name.strip(), description, color, start[:10], end[:10], start, end, status, pos,
                 stamp, stamp, stamp if status == "done" else None))
        return self.project(pid)

    def _project_span(self, start_at, end_at):
        wd = self.workday()

        def conv(v, which):
            if isinstance(v, datetime) or (isinstance(v, str) and "T" in v):
                return TS.to_dt(v)
            if v:
                d = v if isinstance(v, date) else date.fromisoformat(v)
                return TS.at(d, wd[0] if which == 0 else wd[1])
            return None
        sa = conv(start_at, 0) or TS.at(date.today(), wd[0])
        ea = conv(end_at, 1) or TS.at(sa.date() + timedelta(days=30), wd[1])
        if ea <= sa:
            ea = sa + timedelta(hours=1)
        return sa, ea

    def update_project(self, pid, **fields):
        p = self.project(pid)
        if not p:
            return None
        new = {}
        for k, v in fields.items():
            if k not in PROJECT_COLUMNS:
                raise KeyError(f"Unknown project field: {k}")
            if k in ("start_at", "end_at"):
                v = TS.to_str(self._project_span(v, None)[0] if k == "start_at"
                              else self._project_span(fields.get("start_at") or p["start_at"], v)[1])
            if k == "status" and v not in PROJECT_STATUSES:
                continue
            if v != p[k]:
                new[k] = v
        if not new:
            return p
        stamp = now_stamp()
        sets = [f"{k} = ?" for k in new] + ["updated_at = ?"]
        vals = list(new.values()) + [stamp]
        if "status" in new:
            sets.append("completed_at = ?")
            vals.append(stamp if new["status"] == "done" else None)
        with self.db:
            self.db.execute(f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", (*vals, pid))
            self.db.execute("UPDATE projects SET start_date = substr(start_at, 1, 10), "
                            "end_date = substr(end_at, 1, 10) WHERE id = ?", (pid,))
        return self.project(pid)

    def project_tasks(self, pid):
        rows = self.db.execute(TASK_SELECT + " WHERE t.project_id = ? GROUP BY t.id" + PROJECT_TASK_ORDER,
                               (pid,))
        return [self._task(r) for r in rows]

    def subtasks_for_project(self, pid):
        """-> {task_id: [subtask, ...]} for every task in the project."""
        out = {}
        for r in self.db.execute(
                "SELECT s.* FROM subtasks s JOIN tasks t ON t.id = s.task_id "
                "WHERE t.project_id = ? ORDER BY s.task_id, s.position", (pid,)):
            out.setdefault(r["task_id"], []).append(self._sub(r))
        return out

    def project_summary(self, pid):
        """Counts and progress for one project. 'tasks' is the planned work (cancelled tasks
        excluded), 'all' includes them; 'counts' is {status: n}."""
        tasks = self.project_tasks(pid)
        now = TS.to_str(datetime.now())
        counts = {s: 0 for s in STATUS.ORDER}
        for t in tasks:
            counts[t["status"]] += 1
        planned = len(tasks) - counts[STATUS.CANCELLED]
        return {
            "all": len(tasks),
            "tasks": planned,
            "done": counts[STATUS.DONE],
            "counts": counts,
            "completion": counts[STATUS.DONE] / planned if planned else 0.0,
            "sub_total": sum(t["sub_total"] for t in tasks if t["status"] != STATUS.CANCELLED),
            "sub_done": sum(t["sub_done"] for t in tasks if t["status"] != STATUS.CANCELLED),
            "overdue": sum(1 for t in tasks if t["end_at"] <= now and t["status"] not in STATUS.INACTIVE),
            "focus_seconds": sum(t["focus_seconds"] for t in tasks),
            "progress": task_progress(tasks),
        }

    def project_counts(self):
        """-> {project_id: open task count} for tasks dated or not."""
        return {r[0]: r[1] for r in self.db.execute(
            "SELECT project_id, COUNT(*) FROM tasks WHERE project_id != '' AND done = 0 GROUP BY project_id")}

    def move_in_project(self, tid, delta) -> bool:
        """Swap a task with its neighbour in the project order."""
        t = self.find(tid)
        if not t or not t["project_id"]:
            return False
        ids = [x["id"] for x in self.project_tasks(t["project_id"])]
        i = ids.index(tid)
        j = i + delta
        if not 0 <= j < len(ids):
            return False
        ids[i], ids[j] = ids[j], ids[i]
        with self.db:
            self.db.executemany("UPDATE tasks SET project_pos = ? WHERE id = ?",
                                [(pos, x) for pos, x in enumerate(ids)])
        return True

    def add_subtask(self, tid, title) -> str:
        n = self.db.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM subtasks WHERE task_id = ?",
                            (tid,)).fetchone()[0]
        with self.db:
            sid = self._insert_subtask(tid, n, title.strip(), False)
            self._touch(tid)
            self._log(tid, "subtask added", title.strip())
        return sid

    def rename_subtask(self, sid, title):
        row = self.db.execute("SELECT * FROM subtasks WHERE id = ?", (sid,)).fetchone()
        title = (title or "").strip()
        if row is None or not title or title == row["title"]:
            return
        with self.db:
            self.db.execute("UPDATE subtasks SET title = ? WHERE id = ?", (title, sid))
            self._touch(row["task_id"])
            self._log(row["task_id"], "subtask renamed", f"{row['title']} → {title}")

    def delete_subtask(self, sid):
        """Remove one subtask. Returns its row as a dict (for undo via restore_subtask) or None."""
        row = self.db.execute("SELECT * FROM subtasks WHERE id = ?", (sid,)).fetchone()
        if row is None:
            return None
        with self.db:
            self.db.execute("DELETE FROM subtasks WHERE id = ?", (sid,))
            self._touch(row["task_id"])
            self._log(row["task_id"], "subtask removed", row["title"])
        return self._sub(row)

    def restore_subtask(self, s):
        with self.db:
            self._insert_subtask(s["task_id"], s["position"], s["title"], s["done"], s["created_at"],
                                 s["completed_at"], sid=s["id"], mode="INSERT OR IGNORE", number=s.get("number"))
            self._log(s["task_id"], "subtask added", s["title"])

    def delete_project(self, pid, with_tasks=False):
        """Delete a project. Its tasks are kept (detached) unless with_tasks.
        Returns a snapshot for restore_project()."""
        p = self.project(pid)
        if not p:
            return None
        tasks = self.project_tasks(pid)
        snap = {"project": p, "with_tasks": with_tasks, "tasks": []}
        with self.db:
            for t in tasks:
                if with_tasks:
                    t["subtasks"] = self.subtasks(t["id"])
                    self.db.execute("DELETE FROM tasks WHERE id = ?", (t["id"],))
                    self._log(t["id"], "deleted", f"with project {p['name']}")
                else:
                    self.db.execute("UPDATE tasks SET project_id = '', project_pos = 0, number = 0 WHERE id = ?",
                                    (t["id"],))
                    self._log(t["id"], "project", f"project {p['name']} deleted")
                snap["tasks"].append(t)
            self.db.execute("DELETE FROM projects WHERE id = ?", (pid,))
        return snap

    def restore_project(self, snap):
        p = snap["project"]
        cols = ", ".join(p.keys())
        with self.db:
            self.db.execute(f"INSERT OR IGNORE INTO projects ({cols}) VALUES ({', '.join('?' * len(p))})",
                            tuple(p.values()))
            for t in snap["tasks"]:
                if snap["with_tasks"]:
                    self._insert_task(t, mode="INSERT OR IGNORE")
                    for s in t.get("subtasks", []):
                        self._insert_subtask(t["id"], s["position"], s["title"], s["done"], s["created_at"],
                                             s["completed_at"], sid=s["id"], mode="INSERT OR IGNORE",
                                             number=s.get("number"))
                    self._log(t["id"], "restored")
                else:
                    self.db.execute("UPDATE tasks SET project_id = ?, project_pos = ?, number = ? WHERE id = ?",
                                    (p["id"], t["project_pos"], t.get("number", 0), t["id"]))

    def tag_to_project(self, tag, color=""):
        """Make a project from a tag: every task carrying it joins the project and loses the tag.
        Returns (project, undo snapshot)."""
        tag = tag.lower().lstrip("#")
        rows = [r for r in self.db.execute(
            "SELECT id, start_at, end_at, tags, project_id, number FROM tasks ORDER BY start_at")
            if tag in r["tags"].split()]
        p = self.add_project(tag, color=color or self.tag_colors().get(tag, ""),
                             start_at=min(r["start_at"] for r in rows) if rows else None,
                             end_at=max(r["end_at"] for r in rows) if rows else None, status="active")
        snap = {"project_id": p["id"], "tasks": []}
        with self.db:
            for pos, r in enumerate(rows):
                snap["tasks"].append({"id": r["id"], "tags": r["tags"], "project_id": r["project_id"],
                                      "number": r["number"]})
                tags = " ".join(x for x in r["tags"].split() if x != tag)
                self.db.execute("UPDATE tasks SET project_id = ?, project_pos = ?, tags = ?, number = ?, "
                                "updated_at = ? WHERE id = ?",
                                (p["id"], pos, tags, self._next_task_no(p["id"]), now_stamp(), r["id"]))
                self._log(r["id"], "project", f"→ {p['name']} (from #{tag})")
        return p, snap

    def undo_tag_to_project(self, snap):
        with self.db:
            for t in snap["tasks"]:
                self.db.execute("UPDATE tasks SET project_id = ?, tags = ?, number = ? WHERE id = ?",
                                (t["project_id"], t["tags"], t.get("number", 0), t["id"]))
            self.db.execute("DELETE FROM projects WHERE id = ?", (snap["project_id"],))

    # ------------------------------------------------------------------ status & stats
    def set_status(self, tid, status):
        return self.update(tid, status=status)

    def status_counts(self, start: date = None, end: date = None) -> dict:
        """{status: count}. Whole table if no range, else tasks starting in [start, end]."""
        if start and end:
            rows = self.db.execute(
                "SELECT status, COUNT(*) n FROM tasks WHERE date BETWEEN ? AND ? GROUP BY status",
                (start.isoformat(), end.isoformat()))
        else:
            rows = self.db.execute("SELECT status, COUNT(*) n FROM tasks GROUP BY status")
        out = {s: 0 for s in STATUS.ORDER}
        for r in rows:
            out[STATUS.normalize(r["status"], r["status"] == STATUS.DONE)] += r["n"]
        return out

    def overview(self, d: date) -> dict:
        """Everything the daily stats view needs for one day (tasks overlapping that day)."""
        tasks = self.for_day(d)
        counts = {s: 0 for s in STATUS.ORDER}
        for t in tasks:
            counts[t["status"]] += 1
        planned = sum(counts[s] for s in STATUS.COUNTS_AS_PLANNED)
        done = counts[STATUS.DONE]
        return {
            "date": d, "total": len(tasks), "counts": counts, "planned": planned, "done": done,
            "completion": (done / planned) if planned else 0.0,
            "focus_seconds": self.focus_seconds_on(d),
            "sub_total": sum(t["sub_total"] for t in tasks),
            "sub_done": sum(t["sub_done"] for t in tasks),
            "tags": self._tag_breakdown(tasks),
            "projects": self._project_breakdown(tasks),
        }

    @staticmethod
    def _tag_breakdown(tasks):
        out = {}
        for t in tasks:
            for tag in (t["tags"].split() or ["(untagged)"]):
                b = out.setdefault(tag, {"total": 0, "done": 0})
                b["total"] += 1
                b["done"] += t["status"] == STATUS.DONE
        return dict(sorted(out.items(), key=lambda kv: -kv[1]["total"]))

    def _project_breakdown(self, tasks):
        """{project_id: {total, done}} for the given tasks ('' = no project)."""
        out = {}
        for t in tasks:
            if t["status"] == STATUS.CANCELLED:
                continue
            b = out.setdefault(t["project_id"], {"total": 0, "done": 0})
            b["total"] += 1
            b["done"] += t["status"] == STATUS.DONE
        return out

    def _overdue_count(self, now: datetime, project_id=None) -> int:
        sql = ("SELECT COUNT(*) FROM tasks WHERE status IN ('open','in_progress','blocked') "
               "AND end_at <= ?")
        args = [TS.to_str(now)]
        if project_id is not None:
            sql += " AND project_id = ?"
            args.append(project_id)
        return self.db.execute(sql, args).fetchone()[0]

    def global_stats(self, today: date) -> dict:
        """Totals across all time plus a few rolling numbers for the overall view."""
        counts = self.status_counts()
        total = sum(counts.values())
        active = total - counts[STATUS.DONE] - counts[STATUS.CANCELLED]
        planned = sum(counts[s] for s in STATUS.COUNTS_AS_PLANNED)
        fr = self.db.execute("SELECT COALESCE(SUM(seconds),0) FROM focus_sessions").fetchone()[0]
        return {
            "counts": counts, "total": total, "active": active, "planned": planned,
            "completion": (counts[STATUS.DONE] / planned) if planned else 0.0,
            "focus_seconds": fr, "overdue": self._overdue_count(datetime.now()),
            "trend": self._trend(today),
            "tags": self._global_tag_breakdown(),
        }

    def _trend(self, today: date, days=14, project_id=None):
        """Per day for the last `days`: tasks starting that day, done / planned."""
        out = []
        extra, args = ("", []) if project_id is None else (" AND project_id = ?", [project_id])
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            c = self.db.execute(
                "SELECT COUNT(*) total, COALESCE(SUM(status='done'),0) done, "
                "COALESCE(SUM(status='cancelled'),0) cancelled FROM tasks WHERE date = ?" + extra,
                (d.isoformat(), *args)).fetchone()
            pl = c["total"] - c["cancelled"]
            out.append({"date": d, "done": c["done"], "planned": pl, "rate": (c["done"] / pl) if pl else None})
        return out

    def _completed_trend(self, today: date, days=14, project_id=None):
        """Per day for the last `days`: how many tasks were completed that day (by completed_at)."""
        extra, args = ("", []) if project_id is None else (" AND project_id = ?", [project_id])
        out = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            n = self.db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done' AND completed_at LIKE ?" + extra,
                                (d.isoformat() + "%", *args)).fetchone()[0]
            out.append({"date": d, "done": n})
        return out

    def _global_tag_breakdown(self):
        out = {}
        for r in self.db.execute("SELECT tags, status FROM tasks WHERE tags != ''"):
            for tag in r["tags"].split():
                b = out.setdefault(tag, {"total": 0, "done": 0})
                b["total"] += 1
                b["done"] += r["status"] == STATUS.DONE
        return dict(sorted(out.items(), key=lambda kv: -kv[1]["total"])[:12])

    def project_stats(self, pid, now: datetime = None) -> dict:
        """Everything the per-project stats need: the summary (status counts, completion,
        weighted progress, overdue, focus) plus timing against the project's start/finish,
        the next due tasks, tag breakdown and a 14-day completion history."""
        now = now or datetime.now()
        p = self.project(pid)
        if not p:
            return None
        s = self.project_summary(pid)
        tasks = self.project_tasks(pid)
        start, end = TS.to_dt(p["start_at"]), TS.to_dt(p["end_at"])
        span = max(60.0, (end - start).total_seconds())
        used = min(1.0, max(0.0, (now - start).total_seconds() / span))
        open_tasks = [t for t in tasks if t["status"] not in STATUS.INACTIVE]
        now_s = TS.to_str(now)
        due = sorted((t for t in open_tasks if t["end_at"] > now_s), key=lambda t: t["end_at"])[:5]
        done_times = [TS.to_dt(t["completed_at"]) for t in tasks if t["status"] == STATUS.DONE and t["completed_at"]]
        # pace: tasks done per week since the project started, and what's needed to finish on time
        weeks_in = max(1 / 7, (min(now, end) - start).total_seconds() / 604800) if now > start else None
        weeks_left = (end - now).total_seconds() / 604800 if end > now else 0
        remaining = s["tasks"] - s["done"]
        return dict(s, **{
            "project": p,
            "time_used": used,
            "behind": p["status"] != "done" and s["tasks"] > 0 and used - s["progress"] > 0.15,
            "remaining": remaining,
            "pace": (s["done"] / weeks_in) if weeks_in else None,
            "needed_pace": (remaining / weeks_left) if weeks_left > 0 else None,
            "next_due": due,
            "last_done": max(done_times) if done_times else None,
            "tags": self._tag_breakdown([t for t in tasks if t["status"] != STATUS.CANCELLED]),
            "history": self._completed_trend(now.date(), 14, pid),
        })

    def all_project_stats(self, include_done=True):
        return [self.project_stats(p["id"]) for p in self.projects(include_done=include_done)]
