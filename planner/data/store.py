"""SQLite persistence: tasks, subtasks, activity log, routine and settings.

Tasks are handed to the UI as plain dicts:
    id, date, start, end, title, note, done, created_at, updated_at, completed_at,
    sub_total, sub_done
Subtasks:
    id, task_id, position, title, done, created_at, completed_at
"""
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from .. import recurrence as R
from pathlib import Path

from ..config import DATA_DIR, DB_FILE, DEFAULT_ROUTINE, DEFAULT_SETTINGS, LEGACY_JSON
from ..utils import now_stamp
from .. import status as STATUS
from .schema import (
    ADDED_COLUMNS, BOOL_FIELDS, MIGRATE_SQL, SCHEMA, SCHEMA_VERSION, TASK_COLUMNS, TASK_SELECT,
)

TASK_ORDER = " ORDER BY t.start_time = '', t.start_time, t.title COLLATE NOCASE"


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
        self._migrate(version)                  # add newer columns to an older tasks table first
        self.db.executescript(SCHEMA)          # then create anything missing
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

    def _migrate(self, version):
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        with self.db:
            for table, column, ddl in ADDED_COLUMNS:
                if table not in tables:
                    continue                    # fresh database: SCHEMA creates it complete
                cols = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
                if column not in cols:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            # one-time data fixes for each schema version the db is below
            if version:                         # skip on a brand-new (version 0) database
                for target, sql in sorted(MIGRATE_SQL.items()):
                    if version < target:
                        self.db.execute(sql)

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
        self.db.execute(
            f"{mode} INTO tasks (id, date, start_time, end_time, title, note, done, "
            f"created_at, updated_at, completed_at, priority, tags, pinned, recurrence, recur_parent, "
            f"status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (t["id"], t["date"], t["start"], t["end"], t["title"], t["note"], int(bool(t["done"])),
             t["created_at"], t["updated_at"], t["completed_at"], int(t.get("priority", 1)),
             t.get("tags", ""), int(bool(t.get("pinned"))), t.get("recurrence", ""),
             t.get("recur_parent", ""),
             STATUS.normalize(t.get("status", "open"), t.get("done"))))

    def _insert_subtask(self, tid, position, title, done, created_at=None, completed_at=None,
                        sid=None, mode="INSERT"):
        sid = sid or uuid.uuid4().hex
        stamp = now_stamp()
        if completed_at is None and done:
            completed_at = stamp
        self.db.execute(
            f"{mode} INTO subtasks (id, task_id, position, title, done, created_at, completed_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sid, tid, position, title, int(bool(done)), created_at or stamp,
             completed_at if done else None))
        return sid

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
                "title": row["title"], "note": row["note"], "done": bool(row["done"]),
                "created_at": row["created_at"], "updated_at": row["updated_at"],
                "completed_at": row["completed_at"],
                "priority": row["priority"], "tags": row["tags"], "pinned": bool(row["pinned"]),
                "recurrence": row["recurrence"] if "recurrence" in keys else "",
                "recur_parent": row["recur_parent"] if "recur_parent" in keys else "",
                "status": STATUS.normalize(row["status"] if "status" in keys else "open", bool(row["done"])),
                "sub_total": row["sub_total"] if "sub_total" in keys else 0,
                "sub_done": row["sub_done"] if "sub_done" in keys else 0,
                "focus_seconds": row["focus_seconds"] if "focus_seconds" in keys else 0}

    @staticmethod
    def _sub(row):
        return {"id": row["id"], "task_id": row["task_id"], "position": row["position"],
                "title": row["title"], "done": bool(row["done"]),
                "created_at": row["created_at"], "completed_at": row["completed_at"]}

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
        rows = self.db.execute(TASK_SELECT + " WHERE t.date = ? GROUP BY t.id" + TASK_ORDER,
                               (d.isoformat(),))
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
        for r in self.db.execute(
                "SELECT s.* FROM subtasks s JOIN tasks t ON t.id = s.task_id "
                "WHERE t.date = ? ORDER BY s.task_id, s.position", (d.isoformat(),)):
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
    def add(self, d: date, title, start="", end="", note="", done=False, subtasks=None,
            priority=1, tags="", pinned=False, recurrence="", recur_parent="", status=None):
        stamp = now_stamp()
        tid = uuid.uuid4().hex
        status = status if STATUS.is_valid(status) else STATUS.from_done(done)
        done = status == STATUS.DONE          # status is authoritative when given
        t = {"id": tid, "date": d.isoformat(), "start": start, "end": end,
             "title": title, "note": note, "done": bool(done),
             "created_at": stamp, "updated_at": stamp, "completed_at": stamp if done else None,
             "priority": int(priority if priority is not None else 1), "tags": tags or "",
             "pinned": bool(pinned), "recurrence": recurrence if R.is_valid(recurrence) else "",
             "recur_parent": recur_parent, "status": status}
        n = sum(1 for s in subtasks or [] if (s.get("title") or "").strip())
        with self.db:
            self._insert_task(t)
            if n:
                self._sync_subtasks(t["id"], subtasks, quiet=True)
            detail = []
            if n:
                detail.append(f"with {n} subtask(s)")
            if t["recurrence"] and not recur_parent:
                detail.append(R.describe(t["recurrence"], d).lower())
            self._log(tid, "created", ", ".join(detail))
        if t["recurrence"] and not recur_parent:
            self.ensure_recurrences(series=tid)
        return self.find(tid)

    def update(self, tid, **fields):
        t = self.find(tid)
        if not t:
            return None
        # keep status and the done checkbox consistent whichever one the caller set
        if "status" in fields and "done" not in fields:
            fields["done"] = fields["status"] == STATUS.DONE
        elif "done" in fields and "status" not in fields:
            want = bool(fields["done"])
            if want and t["status"] != STATUS.DONE:
                fields["status"] = STATUS.DONE
            elif not want and t["status"] == STATUS.DONE:
                fields["status"] = STATUS.OPEN
        new = {}
        for k, v in fields.items():
            if k not in TASK_COLUMNS:
                raise KeyError(f"Unknown task field: {k}")
            if k == "date" and isinstance(v, date):
                v = v.isoformat()
            if k in BOOL_FIELDS:
                v = bool(v)
            if k == "priority":
                v = int(v)
            if v != t[k]:
                new[k] = v
        if not new:
            return t
        stamp = now_stamp()
        sets = [f"{TASK_COLUMNS[k]} = ?" for k in new]
        vals = [int(v) if k in BOOL_FIELDS else v for k, v in new.items()]
        sets.append("updated_at = ?")
        vals.append(stamp)
        if "done" in new:
            sets.append("completed_at = ?")
            vals.append(stamp if new["done"] else None)
        with self.db:
            self.db.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", (*vals, tid))
            if "done" in new:
                self._log(tid, "completed" if new["done"] else "reopened")
            if "date" in new:
                self._log(tid, "moved", f"{t['date']} → {new['date']}")
            if "pinned" in new:
                self._log(tid, "starred" if new["pinned"] else "unstarred")
            if "status" in new and new["status"] not in (STATUS.DONE, STATUS.OPEN):
                self._log(tid, "status", STATUS.label(new["status"]))
            edited = [k for k in new if k not in ("done", "date", "pinned", "status")]
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
        return self.add(date.fromisoformat(t["date"]), t["title"], t["start"], t["end"], t["note"],
                        subtasks=subs, priority=t["priority"], tags=t["tags"])

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
                                     s["completed_at"], sid=s["id"], mode="INSERT OR IGNORE")
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
                self.add(d, template["title"], template["start"], template["end"], template["note"],
                         priority=template["priority"], tags=template["tags"],
                         recurrence=rule, recur_parent=pid)
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
            self._write_routine([t for t in self.for_day(d) if t["start"]])

    def carry_over(self, src: date, dst: date) -> int:
        """Copy unfinished tasks (with their subtask checklist as-is) to another day."""
        n = 0
        for t in self.for_day(src):
            if not t["done"] and not self.exists(dst, t["title"], t["start"]):
                subs = [{"title": s["title"], "done": s["done"]} for s in self.subtasks(t["id"])]
                self.add(dst, t["title"], t["start"], t["end"], t["note"], subtasks=subs,
                         priority=t["priority"], tags=t["tags"])
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

    # ------------------------------------------------------------------ status & stats
    def set_status(self, tid, status):
        return self.update(tid, status=status)

    def status_counts(self, start: date = None, end: date = None) -> dict:
        """{status: count}. Whole table if no range, else tasks dated in [start, end]."""
        if start and end:
            rows = self.db.execute(
                "SELECT status, COUNT(*) n FROM tasks WHERE date BETWEEN ? AND ? GROUP BY status",
                (start.isoformat(), end.isoformat()))
        else:
            rows = self.db.execute("SELECT status, COUNT(*) n FROM tasks GROUP BY status")
        out = {s: 0 for s in STATUS.ORDER}
        for r in rows:
            out[STATUS.normalize(r["status"], r["status"] == STATUS.DONE)] = r["n"]
        return out

    def overview(self, d: date) -> dict:
        """Everything the daily stats view needs for one day."""
        tasks = self.for_day(d)
        counts = {s: 0 for s in STATUS.ORDER}
        for t in tasks:
            counts[t["status"]] += 1
        planned = sum(counts[s] for s in STATUS.COUNTS_AS_PLANNED)
        done = counts[STATUS.DONE]
        sub_total = sum(t["sub_total"] for t in tasks)
        sub_done = sum(t["sub_done"] for t in tasks)
        return {
            "date": d, "total": len(tasks), "counts": counts, "planned": planned, "done": done,
            "completion": (done / planned) if planned else 0.0,
            "focus_seconds": self.focus_seconds_on(d),
            "sub_total": sub_total, "sub_done": sub_done,
            "tags": self._tag_breakdown(tasks),
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

    def global_stats(self, today: date) -> dict:
        """Totals across all time plus a few rolling numbers for the global view."""
        counts = self.status_counts()
        total = sum(counts.values())
        active = total - counts[STATUS.DONE] - counts[STATUS.CANCELLED]
        planned = sum(counts[s] for s in STATUS.COUNTS_AS_PLANNED)
        # last 14 days completion trend (done / planned per day)
        trend = []
        for i in range(13, -1, -1):
            d = today - timedelta(days=i)
            c = self.db.execute(
                "SELECT COUNT(*) total, COALESCE(SUM(status='done'),0) done, "
                "COALESCE(SUM(status='cancelled'),0) cancelled FROM tasks WHERE date = ?",
                (d.isoformat(),)).fetchone()
            pl = c["total"] - c["cancelled"]
            trend.append({"date": d, "done": c["done"], "planned": pl,
                          "rate": (c["done"] / pl) if pl else None})
        fr = self.db.execute("SELECT COALESCE(SUM(seconds),0) FROM focus_sessions").fetchone()[0]
        overdue = self.db.execute(
            "SELECT COUNT(*) FROM tasks WHERE status IN ('open','in_progress','blocked') "
            "AND date < ?", (today.isoformat(),)).fetchone()[0]
        return {
            "counts": counts, "total": total, "active": active, "planned": planned,
            "completion": (counts[STATUS.DONE] / planned) if planned else 0.0,
            "focus_seconds": fr, "overdue": overdue, "trend": trend,
            "tags": self._global_tag_breakdown(),
        }

    def _global_tag_breakdown(self):
        out = {}
        for r in self.db.execute("SELECT tags, status FROM tasks WHERE tags != ''"):
            for tag in r["tags"].split():
                b = out.setdefault(tag, {"total": 0, "done": 0})
                b["total"] += 1
                b["done"] += r["status"] == STATUS.DONE
        return dict(sorted(out.items(), key=lambda kv: -kv[1]["total"])[:12])
