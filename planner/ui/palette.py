"""Command palette (Ctrl+K): one box to find any task or project and run any action.

Type to search tasks (by title, #number, tag or project), projects and actions. Commands:
    #9 done            set #9's status (open, in progress, blocked, postponed, done, cancelled)
    move #9 to done    the same, in words
    focus #9           start a focus session on #9
    edit #9            open #9 in the task dialog
    #9                 jump to #9
When several projects have a #9, each gets its own row (the current project first).
Up/Down pick, Enter runs, Esc closes.
"""
import re

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS
from .dialogs import FadeDialog
from .helpers import set_role
from .project_dialog import dot_icon
from ..theme.icons import status_dot

STATUS_WORDS = {
    "open": STATUS.OPEN, "todo": STATUS.OPEN, "reopen": STATUS.OPEN,
    "in progress": STATUS.IN_PROGRESS, "progress": STATUS.IN_PROGRESS, "doing": STATUS.IN_PROGRESS,
    "start": STATUS.IN_PROGRESS, "started": STATUS.IN_PROGRESS, "wip": STATUS.IN_PROGRESS,
    "blocked": STATUS.BLOCKED, "block": STATUS.BLOCKED,
    "postponed": STATUS.POSTPONED, "postpone": STATUS.POSTPONED, "later": STATUS.POSTPONED,
    "done": STATUS.DONE, "complete": STATUS.DONE, "completed": STATUS.DONE, "finish": STATUS.DONE,
    "cancelled": STATUS.CANCELLED, "canceled": STATUS.CANCELLED, "cancel": STATUS.CANCELLED,
}
STATUS_CMD = re.compile(r"^(?:move|set|mark)?\s*#\s*(\d+)\s*(?:to|as|->|→|=)?\s*([a-z ]+?)\s*$", re.I)
VERB_CMD = re.compile(r"^(focus|edit|open|go to|goto|start focus on|start focus)\s*#\s*(\d+)\s*$", re.I)
JUMP_CMD = re.compile(r"^#\s*(\d+)\s*$")


def score(query: str, hay: str):
    """Every query word must appear in hay; earlier/fewer gaps score better (lower). None = no match."""
    hay = hay.lower()
    total = 0
    for w in query.lower().split():
        i = hay.find(w)
        if i < 0:
            return None
        total += i
    return total


class CommandPalette(FadeDialog):
    def __init__(self, host):
        super().__init__(host)
        self.host, self.store = host, host.store
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setObjectName("palette")
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 10)
        lay.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Search tasks, projects and actions…   try  #9 done,  focus #3,  week")
        self.edit.textChanged.connect(self._search)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        self.list.setObjectName("paletteList")
        self.list.setIconSize(QSize(14, 14))
        self.list.setMinimumHeight(300)
        self.list.itemActivated.connect(self._run)
        lay.addWidget(self.list)
        lay.addWidget(set_role(QLabel("↑↓ choose   Enter run   Esc close"), "hint"))
        self._search("")
        self.edit.setFocus()

    def showEvent(self, e):
        super().showEvent(e)
        g = self.host.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 80)

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == e.Type.KeyPress:
            k = e.key()
            if k in (Qt.Key_Down, Qt.Key_Up):
                n = self.list.count()
                if n:
                    i = self.list.currentRow() + (1 if k == Qt.Key_Down else -1)
                    self.list.setCurrentRow(max(0, min(n - 1, i)))
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                it = self.list.currentItem()
                if it:
                    self._run(it)
                return True
        return super().eventFilter(obj, e)

    # ---- entries
    def _add(self, text, fn, icon=None, sub=""):
        it = QListWidgetItem(text + (f"\n{sub}" if sub else ""))
        if icon is not None:
            it.setIcon(icon)
        it.setData(Qt.UserRole, fn)
        self.list.addItem(it)

    def _tasks_numbered(self, n):
        """Tasks with number n, the open project's first."""
        rows = [r for r in self.store.db.execute("SELECT id FROM tasks WHERE number = ?", (n,))]
        tasks = [self.store.find(r[0]) for r in rows]
        cur = self.host.projects_page.current_id if self.host.on_projects() else None
        return sorted(tasks, key=lambda t: (t["project_id"] != cur, t["project_id"]))

    def _task_sub(self, t):
        p = self.store.project(t["project_id"]) if t["project_id"] else None
        return (f"{p['name']} · " if p else "") + STATUS.label(t["status"]) + " · " + \
            TS.span_label(t["start_at"], t["end_at"])

    def _search(self, text):
        self.list.clear()
        q = text.strip()
        h = self.host
        m = STATUS_CMD.match(q)
        if m and m.group(2).strip().lower() in STATUS_WORDS:
            st = STATUS_WORDS[m.group(2).strip().lower()]
            for t in self._tasks_numbered(int(m.group(1))):
                self._add(f"Set {NUM.titled(t)} to {STATUS.label(st)}",
                          lambda t=t, st=st: h.palette_set_status(t["id"], st), status_dot(STATUS.color(st)),
                          self._task_sub(t))
        m = VERB_CMD.match(q)
        if m:
            verb = m.group(1).lower()
            for t in self._tasks_numbered(int(m.group(2))):
                if "focus" in verb:
                    self._add(f"Start focus on {NUM.titled(t)}", lambda t=t: h.palette_focus(t["id"]),
                              h._icon("timer"), self._task_sub(t))
                elif verb == "edit":
                    self._add(f"Edit {NUM.titled(t)}", lambda t=t: h.palette_edit(t["id"]), h._icon("edit"),
                              self._task_sub(t))
                else:
                    self._add(f"Go to {NUM.titled(t)}", lambda t=t: h.reveal_task(t["id"]), h._icon("folder"),
                              self._task_sub(t))
        m = JUMP_CMD.match(q)
        if m:
            for t in self._tasks_numbered(int(m.group(1))):
                self._add(f"Go to {NUM.titled(t)}", lambda t=t: h.reveal_task(t["id"]),
                          status_dot(STATUS.color(t["status"])), self._task_sub(t))

        ranked = []
        for name, keys, icon, fn in h.palette_actions():
            s = score(q, name + " " + keys) if q else 0
            if s is not None:
                ranked.append((s - 5, 0, name + (f"   {keys}" if keys else ""), fn, h._icon(icon) if icon else None, ""))
        if q and not JUMP_CMD.match(q):
            for p in self.store.projects():
                s = score(q, p["name"])
                if s is not None:
                    ranked.append((s, 1, f"Project: {p['name']}", (lambda pid=p["id"]: h.show_projects(pid)),
                                   dot_icon(p["color"]), p["status"].replace("_", " ")))
            like = f"%{q.split()[0]}%" if q.split() else "%"
            rows = self.store.db.execute(
                "SELECT t.id FROM tasks t LEFT JOIN projects p ON p.id = t.project_id "
                "WHERE t.title LIKE ? OR t.tags LIKE ? OR p.name LIKE ? ORDER BY t.status = 'done', t.start_at DESC "
                "LIMIT 120", (like, like, like)).fetchall()
            for r in rows:
                t = self.store.find(r[0])
                p = self.store.project(t["project_id"]) if t["project_id"] else None
                s = score(q, f"{NUM.titled(t)} {t['tags']} {p['name'] if p else ''}")
                if s is not None:
                    ranked.append((s + (20 if t["status"] in STATUS.INACTIVE else 0), 2, NUM.titled(t),
                                   (lambda tid=t["id"]: h.reveal_task(tid)), status_dot(STATUS.color(t["status"])),
                                   self._task_sub(t)))
        ranked.sort(key=lambda x: (x[0], x[1]))
        for _, _, text_, fn, icon, sub in ranked[:60]:
            self._add(text_, fn, icon, sub)
        if self.list.count():
            self.list.setCurrentRow(0)
        elif q:
            self._add(f"New task “{q}”", lambda: h.palette_new_task(q), h._icon("add"),
                      "Quick add with this text (dates, #tags and !high work as usual)")
            self.list.setCurrentRow(0)

    def _run(self, item):
        fn = item.data(Qt.UserRole)
        self.accept()
        if fn:
            fn()
