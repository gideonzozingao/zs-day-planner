"""New / edit task dialog: title, project, start and end date-time, note, tags, priority,
repeat, and an inline subtask checklist.

Every task has a start and an end date-time; the end may be on a later day.
Moving the start keeps the length (the end moves with it); the end can't be before the start.
"""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QSize, Qt, QTime
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton,
)

from .. import recurrence as R
from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS
from ..quickparse import PRIORITY_NAMES, normalize_tags
from .dialogs import FadeDialog
from .helpers import set_kind, set_role
from .project_dialog import dot_icon
from ..theme.icons import status_dot
from .subtasks import SubtaskEditor

DT_FORMAT = "ddd dd MMM yyyy   HH:mm"


def qdt(dt: datetime) -> QDateTime:
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute))


class TaskDialog(FadeDialog):
    def __init__(self, parent, d, colors, task=None, subtasks=(), prefill=None, projects=(), project_id="",
                 workday=TS.DEFAULT_WORKDAY, span=None):
        """d: the day a new task starts on (None: today).
        prefill: a quickparse.Parsed to start a new task from (quick capture's Ctrl+Enter).
        projects: project dicts offered in the Project field; project_id preselects one.
        workday: (HH:MM, HH:MM) used by the "Work day" button and for prefill without times."""
        super().__init__(parent)
        title = (f"Edit task {NUM.task_no(task)}".strip()) if task else "New task"
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self.workday = workday
        self._projects = {p["id"]: p for p in projects}

        self.title = QLineEdit()
        self.title.setPlaceholderText("What needs doing?")
        self.project = QComboBox()
        self.project.setIconSize(QSize(14, 14))
        self.project.addItem("No project", "")
        for p in projects:
            self.project.addItem(dot_icon(p["color"]), p["name"], p["id"])

        self.start = QDateTimeEdit()
        self.end = QDateTimeEdit()
        for w in (self.start, self.end):
            w.setCalendarPopup(True)
            w.setDisplayFormat(DT_FORMAT)
        self.length = set_role(QLabel(), "hint")
        self.warn = set_role(QLabel(), "danger")
        self.warn.setWordWrap(True)
        self.warn.hide()
        presets = QHBoxLayout()
        presets.setSpacing(6)
        for label, fn in (("30 min", lambda: self._set_length(30)), ("1 h", lambda: self._set_length(60)),
                          ("2 h", lambda: self._set_length(120)), ("Work day", self._work_day),
                          ("+1 day", self._plus_day)):
            b = set_kind(QPushButton(label), "chip")
            b.setStyleSheet("QPushButton{padding:0 10px;min-height:30px;}")
            b.setAutoDefault(False)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            presets.addWidget(b)
        presets.addStretch()

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
        self.status.setIconSize(QSize(12, 12))
        for st in STATUS.ORDER:
            self.status.addItem(status_dot(STATUS.color(st)), STATUS.label(st), st)
        self.status.setCurrentIndex(STATUS.ORDER.index(STATUS.OPEN))
        self.pinned = QCheckBox("★  Top task")
        self.pinned.setToolTip("One of the day's top tasks (Ctrl+B in the list)")
        self.repeat = QComboBox()
        for rule in (R.NONE, R.DAILY, R.WEEKDAYS, R.WEEKLY, R.MONTHLY):
            self.repeat.addItem(R.LABELS[rule], rule)

        # ---- initial values
        if task:
            project_id = task.get("project_id", "")
            sa, ea = TS.to_dt(task["start_at"]), TS.to_dt(task["end_at"])
            self.title.setText(task["title"])
            self.note.setPlainText(task["note"])
            self._set_meta(task.get("priority", 1), task.get("tags", ""), task.get("pinned", False))
            self._set_repeat(task.get("recurrence", ""))
            self.status.setCurrentIndex(max(0, self.status.findData(task.get("status", STATUS.OPEN))))
        else:
            day = d or date.today()
            p = self._projects.get(project_id)
            if p and prefill is None and d is None:
                day = max(day, TS.to_dt(p["start_at"]).date())    # don't start before the project
            sa = TS.default_start(day)
            if p and sa < TS.to_dt(p["start_at"]):
                sa = TS.to_dt(p["start_at"])
            ea = sa + timedelta(minutes=30)
            if span:                                    # e.g. a slot double-clicked in the week planner
                sa, ea = span
            if prefill is not None:
                self.title.setText(prefill.title)
                pday = prefill.date or day
                if prefill.start:
                    sa, ea = TS.make_span(pday, prefill.start, prefill.end, workday)
                elif prefill.date:
                    sa, ea = TS.make_span(pday, "", "", workday)
                self._set_meta(prefill.priority if prefill.priority is not None else 1,
                               " ".join(prefill.tags), prefill.pinned)
        self.project.setCurrentIndex(max(0, self.project.findData(project_id or "")))
        self.start.setDateTime(qdt(sa))
        self.end.setDateTime(qdt(ea))
        self._length = ea - sa
        self.title.setCursorPosition(0)

        self.start.dateTimeChanged.connect(self._start_changed)
        self.end.dateTimeChanged.connect(self._end_changed)
        self.project.currentIndexChanged.connect(self._update_info)

        self.subtasks = SubtaskEditor(colors, subtasks, task)
        self._task = task
        self.number_hint = set_role(QLabel(), "hint")
        self.project.currentIndexChanged.connect(self._update_number_hint)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Task", self.title)
        if len(projects) or self.project.currentData():
            prow = QHBoxLayout()
            prow.addWidget(self.project, 1)
            prow.addSpacing(8)
            prow.addWidget(self.number_hint)
            form.addRow("Project", prow)
        else:
            self.project.hide()
        form.addRow("Starts", self.start)
        form.addRow("Ends", self.end)
        form.addRow("", presets)
        form.addRow("Length", self.length)
        form.addRow("", self.warn)
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
        self._update_info()
        self._update_number_hint()
        self.title.setFocus()

    def keyPressEvent(self, e):
        # Enter inside the subtask editor adds/moves rows; it must not trigger Save.
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ControlModifier):
            fw = self.focusWidget()
            if fw is not None and self.subtasks.isAncestorOf(fw):
                return
        super().keyPressEvent(e)

    # ---- span
    def _sa(self) -> datetime:
        return self.start.dateTime().toPython().replace(second=0, microsecond=0)

    def _ea(self) -> datetime:
        return self.end.dateTime().toPython().replace(second=0, microsecond=0)

    def _start_changed(self, *_):
        """Moving the start keeps the task's length: the end follows."""
        self.end.blockSignals(True)
        self.end.setDateTime(qdt(self._sa() + self._length))
        self.end.blockSignals(False)
        self._update_info()

    def _end_changed(self, *_):
        if self._ea() > self._sa():
            self._length = self._ea() - self._sa()
        self._update_info()

    def _set_length(self, minutes):
        self._length = timedelta(minutes=minutes)
        self._start_changed()

    def _work_day(self):
        sa, ea = TS.make_span(self._sa().date(), *self.workday)
        self._length = ea - sa
        self.start.setDateTime(qdt(sa))       # triggers _start_changed with the new length

    def _plus_day(self):
        self.end.setDateTime(qdt(self._ea() + timedelta(days=1)))

    def _update_info(self, *_):
        sa, ea = self._sa(), self._ea()
        if ea <= sa:
            self.length.setText("Ends before it starts")
        else:
            self.length.setText(TS.fmt_length((ea - sa).total_seconds())
                                + (f"  ·  ends {ea:%a %d %b}" if ea.date() != sa.date() else ""))
        warn = ""
        p = self._projects.get(self.project.currentData() or "")
        if p and ea > sa:
            ps, pe = TS.to_dt(p["start_at"]), TS.to_dt(p["end_at"])
            if sa < ps:
                warn = f"Starts before the project does ({ps:%a %d %b %H:%M})."
            elif ea > pe:
                warn = f"Ends after the project's finish ({pe:%a %d %b %H:%M})."
        self.warn.setText(warn)
        self.warn.setVisible(bool(warn))
        d = sa.date()
        self.repeat.setItemText(self.repeat.findData(R.WEEKLY), f"Every {d:%A}")
        self.repeat.setItemText(self.repeat.findData(R.MONTHLY), f"Monthly on the {R._ordinal(d.day)}")

    # ---- meta
    def _update_number_hint(self, *_):
        """Show the task's number in the chosen project: its own, or the one it will get."""
        pid = self.project.currentData() or ""
        t = self._task
        if not pid:
            text = ""
        elif t and t.get("project_id") == pid and t.get("number"):
            text = f"#{t['number']}"
        else:
            p = self._projects.get(pid)
            text = f"will be #{(p.get('task_seq') or 0) + 1}" if p else ""
        self.number_hint.setText(text)
        self.number_hint.setVisible(bool(text))

    def _set_meta(self, priority, tags, pinned):
        self.priority.setCurrentIndex(max(0, self.priority.findData(int(priority))))
        self.tags.setText(" ".join("#" + t for t in (tags or "").split()))
        self.pinned.setChecked(bool(pinned))

    def _set_repeat(self, rule):
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(rule if R.is_valid(rule) else R.NONE)))

    def _accept(self):
        if not self.title.text().strip():
            QMessageBox.warning(self, "Missing title", "Please enter a task title.")
            self.title.setFocus()
            return
        if self._ea() <= self._sa():
            QMessageBox.warning(self, "Invalid time", "The end must be after the start.")
            self.end.setFocus()
            return
        self.accept()

    def values(self):
        sa, ea = self._sa(), self._ea()
        return {
            "start_at": sa,
            "end_at": ea,
            "date": sa.date(),
            "project_id": self.project.currentData() or "",
            "title": self.title.text().strip(),
            "note": self.note.toPlainText().strip(),
            "subtasks": self.subtasks.values(),
            "priority": self.priority.currentData(),
            "tags": normalize_tags(self.tags.text()),
            "pinned": self.pinned.isChecked(),
            "recurrence": self.repeat.currentData(),
            "status": self.status.currentData(),
        }
