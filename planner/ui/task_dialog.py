"""New / edit task dialog with an inline subtask checklist."""
from datetime import date, datetime

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDateEdit, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLineEdit,
    QMessageBox, QPlainTextEdit, QTimeEdit,
)

from .. import recurrence as R
from .. import status as STATUS
from ..quickparse import PRIORITY_NAMES, normalize_tags
from .dialogs import FadeDialog
from .helpers import set_kind
from ..theme.icons import status_dot
from .subtasks import SubtaskEditor


class TaskDialog(FadeDialog):
    def __init__(self, parent, d: date, colors, task=None, subtasks=(), prefill=None):
        """prefill: a quickparse.Parsed to start a new task from (quick capture's Ctrl+Enter)."""
        super().__init__(parent)
        title = "Edit task" if task else "New task"
        self.setWindowTitle(title)
        self.setMinimumWidth(520)

        self.title = QLineEdit()
        self.title.setPlaceholderText("What needs doing?")
        self.date = QDateEdit(QDate(d.year, d.month, d.day))
        self.date.setCalendarPopup(True)
        self.has_time = QCheckBox("Scheduled time (enables popup reminders)")
        self.start, self.end = QTimeEdit(), QTimeEdit()
        for w in (self.start, self.end):
            w.setDisplayFormat("HH:mm")
            w.setButtonSymbols(QAbstractSpinBox.NoButtons)
            w.findChild(QLineEdit).setTextMargins(13, 0, 0, 0)   # align with the other fields' padding
        self.note = QPlainTextEdit()
        self.note.setFixedHeight(64)
        self.note.setPlaceholderText("Optional note")
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("#dpp #aws")
        self.priority = QComboBox()
        for value in (2, 1, 0):
            self.priority.addItem(PRIORITY_NAMES[value], value)
        self.priority.setCurrentIndex(1)
        self.status = QComboBox()
        for st in STATUS.ORDER:
            self.status.addItem(status_dot(STATUS.color(st)), STATUS.label(st), st)
        self.status.setCurrentIndex(STATUS.ORDER.index(STATUS.OPEN))
        self.pinned = QCheckBox("★  Top task")
        self.pinned.setToolTip("One of the day's top tasks (Ctrl+B in the list)")
        self.repeat = QComboBox()
        for rule in (R.NONE, R.DAILY, R.WEEKDAYS, R.WEEKLY, R.MONTHLY):
            self.repeat.addItem(R.LABELS[rule], rule)
        self._repeat_locked = ""   # set when editing a single occurrence of an existing series

        now = datetime.now()
        s = QTime(now.hour, (now.minute // 5) * 5)
        self.start.setTime(s)
        self.end.setTime(s.addSecs(30 * 60) if s.hour() < 23 else QTime(23, 59))
        self.has_time.setChecked(True)
        if task:
            self.title.setText(task["title"])
            self.note.setPlainText(task["note"])
            if task["start"]:
                self.start.setTime(QTime.fromString(task["start"], "HH:mm"))
                self.end.setTime(QTime.fromString(task["end"], "HH:mm"))
            self.has_time.setChecked(bool(task["start"]))
            self._set_meta(task.get("priority", 1), task.get("tags", ""), task.get("pinned", False))
            self._set_repeat(task.get("recurrence", ""))
            self.status.setCurrentIndex(max(0, self.status.findData(task.get("status", "open"))))
        elif prefill is not None:
            self.title.setText(prefill.title)
            if prefill.date:
                self.date.setDate(QDate(prefill.date.year, prefill.date.month, prefill.date.day))
            if prefill.start:
                self.start.setTime(QTime.fromString(prefill.start, "HH:mm"))
                self.end.setTime(QTime.fromString(prefill.end, "HH:mm"))
            self.has_time.setChecked(bool(prefill.start))
            self._set_meta(prefill.priority if prefill.priority is not None else 1,
                           " ".join(prefill.tags), prefill.pinned)
        self.title.setCursorPosition(0)
        self.has_time.toggled.connect(self._toggle)
        self._toggle(self.has_time.isChecked())

        self.subtasks = SubtaskEditor(colors, subtasks)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Task", self.title)
        form.addRow("Date", self.date)
        form.addRow("", self.has_time)
        form.addRow("Start", self.start)
        form.addRow("End", self.end)
        form.addRow("Note", self.note)
        form.addRow("Tags", self.tags)
        meta = QHBoxLayout()
        meta.addWidget(self.priority)
        meta.addSpacing(16)
        meta.addWidget(self.pinned)
        meta.addStretch()
        form.addRow("Priority", meta)
        form.addRow("Status", self.status)
        form.addRow("Repeat", self.repeat)
        self.date.dateChanged.connect(self._update_repeat_labels)
        self._update_repeat_labels()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save = set_kind(buttons.button(QDialogButtonBox.Save), "filled")
        save.setToolTip("Save (Ctrl+Enter)")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self).activated.connect(self._accept)

        lay = self._frame(title, spacing=14)
        lay.addLayout(form)
        lay.addWidget(self.subtasks)
        lay.addWidget(buttons)
        self.title.setFocus()

    def keyPressEvent(self, e):
        # Enter inside the subtask editor adds/moves rows; it must not trigger Save.
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ControlModifier):
            fw = self.focusWidget()
            if fw is not None and self.subtasks.isAncestorOf(fw):
                return
        super().keyPressEvent(e)

    def _set_meta(self, priority, tags, pinned):
        self.priority.setCurrentIndex(max(0, self.priority.findData(int(priority))))
        self.tags.setText(" ".join("#" + t for t in (tags or "").split()))
        self.pinned.setChecked(bool(pinned))

    def _set_repeat(self, rule):
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(rule if R.is_valid(rule) else R.NONE)))

    def _update_repeat_labels(self, *_):
        d = self.date.date().toPython()
        self.repeat.setItemText(self.repeat.findData(R.WEEKLY), f"Every {d:%A}")
        self.repeat.setItemText(self.repeat.findData(R.MONTHLY), f"Monthly on the {R._ordinal(d.day)}")

    def _toggle(self, on):
        self.start.setEnabled(on)
        self.end.setEnabled(on)

    def _accept(self):
        if not self.title.text().strip():
            QMessageBox.warning(self, "Missing title", "Please enter a task title.")
            self.title.setFocus()
            return
        if self.has_time.isChecked() and self.end.time() <= self.start.time():
            QMessageBox.warning(self, "Invalid time", "End time must be after start time.")
            return
        self.accept()

    def values(self):
        timed = self.has_time.isChecked()
        return {
            "date": self.date.date().toPython(),
            "title": self.title.text().strip(),
            "start": self.start.time().toString("HH:mm") if timed else "",
            "end": self.end.time().toString("HH:mm") if timed else "",
            "note": self.note.toPlainText().strip(),
            "subtasks": self.subtasks.values(),
            "priority": self.priority.currentData(),
            "tags": normalize_tags(self.tags.text()),
            "pinned": self.pinned.isChecked(),
            "recurrence": self.repeat.currentData(),
            "status": self.status.currentData(),
        }
