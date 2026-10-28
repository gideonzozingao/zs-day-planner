"""Database backups: consistent copies made with SQLite's online backup API (safe while the
app is running in WAL mode), named planner-YYYY-MM-DD_HHMMSS[-reason].db, oldest pruned.

- daily: the first time the app runs each day (if enabled)
- before an upgrade: whenever the schema is about to change
- manual: Settings → Back up now
Restoring is staged: the chosen copy is written to RESTORE_FILE and swapped in the next time
the app starts (before the database is opened), with the current database kept as a backup.
"""
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR, DB_FILE

DEFAULT_DIR = DATA_DIR / "backups"
RESTORE_FILE = DATA_DIR / "restore-pending.db"
PREFIX = "planner-"


def backup_dir(setting: str = "") -> Path:
    return Path(setting).expanduser() if setting else DEFAULT_DIR


def make_backup(db_path=DB_FILE, folder=None, reason="", keep=14, conn=None) -> Path:
    """Copy the database to `folder`. Uses `conn` (an open connection) if given."""
    folder = Path(folder or DEFAULT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{PREFIX}{datetime.now():%Y-%m-%d_%H%M%S}" + (f"-{reason}" if reason else "") + ".db"
    dest = folder / name
    src = conn or sqlite3.connect(str(db_path))
    try:
        out = sqlite3.connect(str(dest))
        with out:
            src.backup(out)
        out.close()
    finally:
        if conn is None:
            src.close()
    prune(folder, keep)
    return dest


def list_backups(folder=None):
    """[(path, datetime, size_bytes)] newest first."""
    folder = Path(folder or DEFAULT_DIR)
    if not folder.is_dir():
        return []
    out = []
    for p in folder.glob(f"{PREFIX}*.db"):
        try:
            stamp = datetime.strptime(p.stem[len(PREFIX):len(PREFIX) + 17], "%Y-%m-%d_%H%M%S")
        except ValueError:
            continue
        out.append((p, stamp, p.stat().st_size))
    return sorted(out, key=lambda x: x[1], reverse=True)


def prune(folder, keep):
    """Keep the newest `keep` backups (0 = keep everything)."""
    if keep and keep > 0:
        for p, _, _ in list_backups(folder)[keep:]:
            try:
                p.unlink()
            except OSError:
                pass


def last_backup_date(folder=None):
    b = list_backups(folder)
    return b[0][1].date() if b else None


def is_valid_db(path) -> bool:
    try:
        c = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            has_tasks = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'tasks'").fetchone() is not None
            return ok and has_tasks
        finally:
            c.close()
    except sqlite3.Error:
        return False


def stage_restore(path):
    """Schedule `path` to replace the database at the next start."""
    if not is_valid_db(path):
        raise ValueError("That file isn't a planner database (or it's damaged)")
    shutil.copy2(path, RESTORE_FILE)


def apply_pending_restore(db_path=DB_FILE, folder=None):
    """Called before the database is opened. Returns True if a restore was applied."""
    if not RESTORE_FILE.exists():
        return False
    db_path = Path(db_path)
    if db_path.exists():
        if folder is None:                      # use the backup folder chosen in Settings, if any
            try:
                import json
                c = sqlite3.connect(str(db_path))
                r = c.execute("SELECT value FROM settings WHERE key = 'backup_dir'").fetchone()
                c.close()
                folder = backup_dir(json.loads(r[0]) if r else "")
            except (sqlite3.Error, ValueError):
                folder = None
        make_backup(db_path, folder, reason="before-restore", keep=0)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            side.unlink()
    shutil.move(str(RESTORE_FILE), str(db_path))
    return True
