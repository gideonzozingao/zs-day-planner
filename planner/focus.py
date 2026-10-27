"""Focus timer: one task at a time, pausable, with focused time saved to focus_sessions.

Time is measured with a monotonic clock (immune to clock changes and timer drift) and
written to the database every HEARTBEAT_S seconds, so a crash loses at most that much.
"""
import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from .timespan import to_dt

HEARTBEAT_S = 30
MAX_AUTO_MIN = 180
PRESETS = (15, 25, 50)


def default_minutes(task, now: datetime, fallback: int) -> int:
    """Rest of the task's span if it's running now, else the span's length; spans longer than
    MAX_AUTO_MIN (a whole day, several days) fall back to the default focus length."""
    if task.get("start_at") and task.get("end_at"):
        s, e = to_dt(task["start_at"]), to_dt(task["end_at"])
        if s <= now < e:
            left = int((e - now).total_seconds() // 60)
            return max(5, left) if left <= MAX_AUTO_MIN else fallback
        length = int((e - s).total_seconds() // 60)
        if 0 < length <= MAX_AUTO_MIN:
            return length
    return fallback


class FocusTimer(QObject):
    changed = Signal()               # started / paused / resumed / extended / ended
    tick = Signal(int, int)          # remaining seconds, total seconds
    finished = Signal(dict, int)     # task, focused seconds: ran to the end
    stopped = Signal(dict, int)      # task, focused seconds: stopped early

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.task = None
        self.sid = None
        self.total_s = 0
        self._acc = 0.0               # focused seconds banked before the current run
        self._since = None            # monotonic start of the current run (None = paused)
        self._last_beat = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)

    # ---- state
    @property
    def active(self):
        return self.task is not None

    @property
    def paused(self):
        return self.active and self._since is None

    def elapsed(self) -> float:
        return self._acc + (time.monotonic() - self._since if self._since is not None else 0.0)

    def remaining(self) -> int:
        return max(0, int(round(self.total_s - self.elapsed())))

    def is_on(self, tid) -> bool:
        return self.active and self.task["id"] == tid

    # ---- control
    def start(self, task, minutes):
        if self.active:
            self.stop()
        minutes = max(1, int(minutes))
        self.task = dict(task)
        self.total_s = minutes * 60
        self._acc, self._since, self._last_beat = 0.0, time.monotonic(), 0.0
        self.sid = self.store.focus_start(task["id"], minutes)
        self.timer.start()
        self.changed.emit()
        self._on_tick()

    def pause(self):
        if self.active and not self.paused:
            self._acc = self.elapsed()
            self._since = None
            self.store.focus_heartbeat(self.sid, self._acc)
            self.changed.emit()
            self._on_tick()

    def resume(self):
        if self.paused:
            self._since = time.monotonic()
            self.changed.emit()
            self._on_tick()

    def toggle_pause(self):
        self.resume() if self.paused else self.pause()

    def extend(self, minutes=5):
        if self.active:
            self.total_s += minutes * 60
            self.changed.emit()
            self._on_tick()

    def stop(self):
        if not self.active:
            return
        task, secs = self.task, int(self.elapsed())
        self.store.focus_end(self.sid, secs, completed=False)
        self._reset()
        self.stopped.emit(task, secs)

    def _finish(self):
        task, secs = self.task, int(self.total_s)
        self.store.focus_end(self.sid, secs, completed=True)
        self._reset()
        self.finished.emit(task, secs)

    def _reset(self):
        self.timer.stop()
        self.task = self.sid = None
        self.total_s, self._acc, self._since = 0, 0.0, None
        self.changed.emit()

    def _on_tick(self):
        if not self.active:
            return
        e = self.elapsed()
        if e >= self.total_s:
            self._finish()
            return
        if not self.paused and e - self._last_beat >= HEARTBEAT_S:
            self._last_beat = e
            self.store.focus_heartbeat(self.sid, e)
        self.tick.emit(self.remaining(), self.total_s)
