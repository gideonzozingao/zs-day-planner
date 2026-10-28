"""Small dialogs for project templates, task checklists and calendar (.ics) export."""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QSize, Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QRadioButton,
    QVBoxLayout,
)

from .. import timespan as TS
from ..ics import build_ics
from .dialogs import FadeDialog
from .helpers import set_kind, set_role
from .project_dialog import dot_icon


def _buttons(dlg, ok_text):
    b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok = set_kind(b.button(QDialogButtonBox.Ok), "filled")
    ok.setText(ok_text)
    b.accepted.connect(dlg.accept)
    b.rejected.connect(dlg.reject)
    return b


def _qdt(dt):
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute))


class SaveTemplateDialog(FadeDialog):
    def __init__(self, parent, project):
        super().__init__(parent)
        self.setWindowTitle("Save as template")
        self.setMinimumWidth(460)
        lay = self._frame("Save as template")
        lay.addWidget(set_role(QLabel(
            f"Saves the tasks, subtasks, dependencies and checklist of “{project['name']}” so new "
            f"projects can start from it."), "muted"))
        lay.itemAt(lay.count() - 1).widget().setWordWrap(True)
        form = QFormLayout()
        self.name = QLineEdit(project["name"])
        self.name.selectAll()
        self.desc = QLineEdit()
        self.desc.setPlaceholderText("Optional, e.g. one video: outline → record → edit → publish")
        self.dates = QCheckBox("Keep each task's timing relative to the project start")
        self.dates.setChecked(True)
        self.dates.setToolTip("Off: tasks are laid out one working day each, in order")
        form.addRow("Template name", self.name)
        form.addRow("Description", self.desc)
        form.addRow("", self.dates)
        lay.addLayout(form)
        lay.addWidget(_buttons(self, "Save template"))

    def values(self):
        return self.name.text().strip(), self.desc.text().strip(), self.dates.isChecked()


class TemplatePickerDialog(FadeDialog):
    """Pick a template, name the new project and choose when it starts."""

    def __init__(self, parent, store):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("New project from template")
        self.setMinimumSize(560, 520)
        lay = self._frame("New project from template", spacing=12)
        self.list = QListWidget()
        self.list.setObjectName("taskPool")
        self.list.currentItemChanged.connect(self._picked)
        lay.addWidget(self.list, 1)
        self.detail = set_role(QLabel(), "muted")
        self.detail.setWordWrap(True)
        lay.addWidget(self.detail)
        form = QFormLayout()
        self.name = QLineEdit()
        self.start = QDateTimeEdit()
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("ddd dd MMM yyyy   HH:mm")
        ws = store.workday()[0]
        d = date.today()
        self.start.setDateTime(_qdt(TS.at(d, ws)))
        form.addRow("Project name", self.name)
        form.addRow("Starts", self.start)
        lay.addLayout(form)
        row = QHBoxLayout()
        self.delete_btn = set_kind(QPushButton("Delete template"), "text")
        self.delete_btn.clicked.connect(self._delete)
        row.addWidget(self.delete_btn)
        row.addStretch()
        self.buttons = _buttons(self, "Create project")
        row.addWidget(self.buttons)
        lay.addLayout(row)
        self._fill()

    def _fill(self):
        self.list.clear()
        for t in self.store.templates():
            n = len(t["data"].get("tasks", []))
            it = QListWidgetItem(dot_icon(t["data"].get("color") or "#888888"),
                                 f"{t['name']}\n{n} task(s)" + (f" · {t['description']}" if t["description"] else ""))
            it.setData(Qt.UserRole, t["id"])
            self.list.addItem(it)
        empty = self.list.count() == 0
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(not empty)
        self.delete_btn.setEnabled(not empty)
        if empty:
            self.detail.setText("No templates yet. Open a project and choose ⋮ → Save as template…")
        else:
            self.list.setCurrentRow(0)

    def _tpl(self):
        it = self.list.currentItem()
        tid = it.data(Qt.UserRole) if it else None
        return next((t for t in self.store.templates() if t["id"] == tid), None)

    def _picked(self, *_):
        t = self._tpl()
        if not t:
            return
        data = t["data"]
        self.name.setText(t["name"])
        tasks = data.get("tasks", [])
        lines = [f"{len(tasks)} task(s), runs {TS.fmt_length((data.get('length_min') or 0) * 60)}"]
        if data.get("checklist"):
            lines.append("Checklist for new tasks: " + " → ".join(data["checklist"]))
        lines.append("Tasks: " + ", ".join(x["title"] for x in tasks[:8]) + ("…" if len(tasks) > 8 else ""))
        self.detail.setText("\n".join(lines))

    def _delete(self):
        t = self._tpl()
        if t and QMessageBox.question(self, "Delete template", f"Delete the template “{t['name']}”?\n"
                                      "Projects made from it aren't affected.") == QMessageBox.Yes:
            self.store.delete_template(t["id"])
            self._fill()

    def values(self):
        t = self._tpl()
        start = self.start.dateTime().toPython().replace(second=0, microsecond=0)
        return (t["id"] if t else None), (self.name.text().strip() or (t["name"] if t else "Project")), start


class ChecklistDialog(FadeDialog):
    """The subtasks every new task in a project starts with."""

    def __init__(self, parent, project, titles, n_tasks):
        super().__init__(parent)
        self.setWindowTitle("Task checklist")
        self.setMinimumWidth(460)
        lay = self._frame("Checklist for new tasks", spacing=12)
        msg = set_role(QLabel(f"Every new task in “{project['name']}” starts with these subtasks. "
                              f"One per line."), "muted")
        msg.setWordWrap(True)
        lay.addWidget(msg)
        self.text = QPlainTextEdit("\n".join(titles))
        self.text.setPlaceholderText("Outline\nRecord\nEdit\nPublish")
        self.text.setMinimumHeight(150)
        lay.addWidget(self.text)
        self.apply_all = QCheckBox(f"Also add any missing ones to the {n_tasks} existing task(s)")
        self.apply_all.setVisible(n_tasks > 0)
        lay.addWidget(self.apply_all)
        lay.addWidget(_buttons(self, "Save"))

    def values(self):
        return [x.strip() for x in self.text.toPlainText().splitlines() if x.strip()], self.apply_all.isChecked()


class ExportCalendarDialog(FadeDialog):
    """Export tasks as an .ics file for Outlook / Google Calendar."""

    def __init__(self, parent, store, project_id=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Export to calendar")
        self.setMinimumWidth(500)
        lay = self._frame("Export to calendar (.ics)", spacing=12)
        form = QFormLayout()
        self.range = QComboBox()
        for label, days in (("This week", 7), ("Next 2 weeks", 14), ("Next 4 weeks", 28), ("Next 3 months", 91)):
            self.range.addItem(label, days)
        self.range.setCurrentIndex(1)
        self.scope = QComboBox()
        self.scope.setIconSize(QSize(12, 12))
        self.scope.addItem("All tasks", "*")
        for p in store.projects(include_done=False):
            self.scope.addItem(dot_icon(p["color"]), p["name"], p["id"])
        if project_id:
            self.scope.setCurrentIndex(max(0, self.scope.findData(project_id)))
        self.blocks_only = QRadioButton("Time blocks only (shorter than a working day)")
        self.everything = QRadioButton("Everything, including whole-day and multi-day tasks")
        self.blocks_only.setChecked(True)
        self.include_done = QCheckBox("Include done and cancelled tasks")
        form.addRow("Range", self.range)
        form.addRow("Tasks", self.scope)
        lay.addLayout(form)
        lay.addWidget(self.blocks_only)
        lay.addWidget(self.everything)
        lay.addWidget(self.include_done)
        self.count = set_role(QLabel(), "hint")
        lay.addWidget(self.count)
        how = set_role(QLabel(
            "Outlook (classic): File → Open & Export → Open Calendar, pick the file; it opens as its "
            "own calendar you can overlay on yours. New Outlook / Outlook on the web: Calendar → Add "
            "calendar → Upload from file. Export again after changes; events keep the same IDs."), "hint")
        how.setWordWrap(True)
        lay.addWidget(how)
        for w in (self.range, self.scope):
            w.currentIndexChanged.connect(self._update)
        for w in (self.blocks_only, self.everything, self.include_done):
            w.toggled.connect(self._update)
        lay.addWidget(_buttons(self, "Save .ics…"))
        self._update()

    def tasks(self):
        week0 = date.today() - timedelta(days=date.today().weekday())
        d0 = week0 if self.range.currentData() == 7 else date.today()
        d1 = d0 + timedelta(days=self.range.currentData() - 1)
        rows = self.store.for_range(d0, d1)
        pid = self.scope.currentData()
        if pid != "*":
            rows = [t for t in rows if t["project_id"] == pid]
        if self.blocks_only.isChecked():
            rows = [t for t in rows
                    if TS.to_dt(t["end_at"]) - TS.to_dt(t["start_at"]) < timedelta(hours=6)]
        if not self.include_done.isChecked():
            rows = [t for t in rows if t["status"] not in ("done", "cancelled")]
        return rows

    def _update(self, *_):
        self.count.setText(f"{len(self.tasks())} event(s) will be exported.")

    def save(self, parent):
        """Ask for a file name and write it. Returns the path or None."""
        tasks = self.tasks()
        default = f"daily-planner-{date.today():%Y-%m-%d}.ics"
        path, _ = QFileDialog.getSaveFileName(parent, "Save calendar", default, "iCalendar (*.ics)")
        if not path:
            return None
        if not path.lower().endswith(".ics"):
            path += ".ics"
        projects = {p["id"]: p for p in self.store.projects()}
        name = "Daily Planner" if self.scope.currentData() == "*" else self.scope.currentText()
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(build_ics(tasks, projects, name))
        return path
