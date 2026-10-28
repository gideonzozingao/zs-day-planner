"""'Waits for' picker: choose any number of prerequisite tasks from a dropdown.

The dropdown lists the project's other tasks ("#3 Class hierarchy · Open"); type to filter.
Picked tasks appear as rows underneath with their status and a remove (✕) button.
Tasks that would create a loop (they already wait, directly or not, for this one) are shown
greyed out and can't be picked; so are tasks already chosen.
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import numbering as NUM
from .. import status as STATUS
from ..theme.icons import status_dot
from .helpers import set_role

PLACEHOLDER = "Add a task this one waits for…"


class DependencyPicker(QWidget):
    changed = Signal()

    def __init__(self, store, own_id=None):
        super().__init__()
        self.store, self.own_id = store, own_id
        self.tasks = {}           # id -> task, options for the current project
        self.selected = []        # chosen prerequisite ids, in the order picked
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.setIconSize(QSize(12, 12))
        self.combo.lineEdit().setPlaceholderText(PLACEHOLDER)
        self.model = QStandardItemModel(self)
        self.combo.setModel(self.model)
        comp = QCompleter(self.model, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.setCompletionMode(QCompleter.PopupCompletion)
        self.combo.setCompleter(comp)
        self.combo.activated.connect(self._picked)
        comp.activated[str].connect(self._picked_text)
        v.addWidget(self.combo)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        v.addLayout(self.rows)
        self.note = set_role(QLabel(), "hint")
        self.note.setWordWrap(True)
        v.addWidget(self.note)

    # ---- data
    def set_project(self, pid, keep_selected=True):
        """Offer the tasks of project `pid` (none if pid is empty)."""
        tasks = self.store.project_tasks(pid) if pid else []
        self.tasks = {t["id"]: t for t in tasks if t["id"] != self.own_id}
        if keep_selected:
            self.selected = [x for x in self.selected if x in self.tasks]
        else:
            self.selected = []
        self._rebuild()

    def set_selected(self, ids):
        self.selected = [x for x in ids if x in self.tasks]
        self._rebuild()

    def values(self):
        return list(self.selected)

    # ---- ui
    def _label(self, t):
        return f"{NUM.titled(t)}  ·  {STATUS.label(t['status'])}"

    def _rebuild(self):
        self.model.clear()
        head = QStandardItem(PLACEHOLDER)
        head.setEnabled(False)
        self.model.appendRow(head)
        blocked_by_loop = 0
        for t in sorted(self.tasks.values(), key=lambda x: (x["number"] or 10 ** 6, x["title"])):
            it = QStandardItem(status_dot(STATUS.color(t["status"])), self._label(t))
            it.setData(t["id"], Qt.UserRole)
            if t["id"] in self.selected:
                it.setEnabled(False)
                it.setText(self._label(t) + "   (chosen)")
            elif self.own_id and self.store.would_cycle(self.own_id, [t["id"]]):
                it.setEnabled(False)
                it.setText(self._label(t) + "   (waits for this task)")
                blocked_by_loop += 1
            self.model.appendRow(it)
        self.combo.setCurrentIndex(0)
        self.combo.lineEdit().clear()
        # rows of chosen prerequisites
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.hide()                    # gone at once, not just when the event loop gets to it
                w.setParent(None)
                w.deleteLater()
        for tid in self.selected:
            t = self.tasks[tid]
            row = QFrame()
            row.setObjectName("depRow")
            h = QHBoxLayout(row)
            h.setContentsMargins(10, 4, 4, 4)
            h.setSpacing(8)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{STATUS.color(t['status'])};")
            h.addWidget(dot)
            name = QLabel(NUM.titled(t))
            name.setTextFormat(Qt.PlainText)
            h.addWidget(name, 1)
            done = t["status"] in (STATUS.DONE, STATUS.CANCELLED)
            h.addWidget(set_role(QLabel(STATUS.label(t["status"])), "hint" if done else "muted"))
            rm = QPushButton("✕")
            rm.setFlat(True)
            rm.setFixedSize(26, 26)
            rm.setCursor(Qt.PointingHandCursor)
            rm.setToolTip("Remove: this task no longer waits for it")
            rm.clicked.connect(lambda _=False, x=tid: self._remove(x))
            h.addWidget(rm)
            self.rows.addWidget(row)
        waiting = [x for x in self.selected if self.tasks[x]["status"] not in (STATUS.DONE, STATUS.CANCELLED)]
        if not self.tasks:
            self.note.setText("No other tasks in this project yet.")
        elif not self.selected:
            self.note.setText("Optional. Pick as many as you need; the task stays Blocked until all are done.")
        elif waiting:
            self.note.setText(f"Blocked until {len(waiting)} of {len(self.selected)} are done.")
        else:
            self.note.setText("All prerequisites are done.")
        if blocked_by_loop:
            self.note.setText(self.note.text() + " Greyed-out tasks already wait for this one.")

    def _picked(self, index):
        it = self.model.item(index)
        if it is None or not it.isEnabled():
            return
        tid = it.data(Qt.UserRole)
        if tid and tid not in self.selected:
            self.selected.append(tid)
            self._rebuild()
            self.changed.emit()

    def _picked_text(self, text):
        for i in range(self.model.rowCount()):
            if self.model.item(i).text() == text:
                return self._picked(i)

    def _remove(self, tid):
        if tid in self.selected:
            self.selected.remove(tid)
            self._rebuild()
            self.changed.emit()
