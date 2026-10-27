"""New / edit project dialog: name, colour, start and finish date-time (both required), status."""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QSize, Qt, QTime
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDateTimeEdit, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit,
)

from ..data.schema import PROJECT_STATUS_NAMES, PROJECT_STATUSES
from .. import timespan as TS
from ..quickparse import TAG_PALETTE
from .dialogs import FadeDialog
from .helpers import set_kind, set_role


def dot_icon(color, size=14):
    """A filled circle in the project's colour, for lists, menus and combo boxes."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color or "#888888"))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def _qdt(dt: datetime) -> QDateTime:
    return QDateTime(QDate(dt.year, dt.month, dt.day), QTime(dt.hour, dt.minute))


class ProjectDialog(FadeDialog):
    def __init__(self, parent, project=None, used_colors=(), workday=TS.DEFAULT_WORKDAY):
        super().__init__(parent)
        title = "Edit project" if project else "New project"
        self.setWindowTitle(title)
        self.setMinimumWidth(480)

        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. DPP member portal revamp")
        self.desc = QPlainTextEdit()
        self.desc.setFixedHeight(72)
        self.desc.setPlaceholderText("Optional: goal, scope, links")

        self.color = QComboBox()
        self.color.setIconSize(QSize(14, 14))
        for name, col in TAG_PALETTE:
            self.color.addItem(dot_icon(col), name, col)
        self.color.addItem("Custom…", "")
        self.color.activated.connect(self._color_picked)
        self._custom = ""

        today = date.today()
        self.start = QDateTimeEdit(_qdt(TS.at(today, workday[0])))
        self.end = QDateTimeEdit(_qdt(TS.at(today + timedelta(days=30), workday[1])))
        for w in (self.start, self.end):
            w.setCalendarPopup(True)
            w.setDisplayFormat("ddd dd MMM yyyy   HH:mm")
        self.length = set_role(QLabel(), "hint")
        self.start.dateTimeChanged.connect(self._update_length)
        self.end.dateTimeChanged.connect(self._update_length)

        self.status = QComboBox()
        for s in PROJECT_STATUSES:
            self.status.addItem(PROJECT_STATUS_NAMES[s], s)

        if project:
            self.name.setText(project["name"])
            self.desc.setPlainText(project["description"])
            self._set_color(project["color"])
            self.start.setDateTime(_qdt(TS.to_dt(project["start_at"])))
            self.end.setDateTime(_qdt(TS.to_dt(project["end_at"])))
            self.status.setCurrentIndex(max(0, self.status.findData(project["status"])))
        else:
            free = [c for _, c in TAG_PALETTE if c.lower() not in {u.lower() for u in used_colors}]
            self._set_color(free[0] if free else TAG_PALETTE[0][1])
            self.status.setCurrentIndex(self.status.findData("active"))
            self.start.dateTimeChanged.connect(self._auto_status)

        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.addRow("Project", self.name)
        form.addRow("Description", self.desc)
        form.addRow("Colour", self.color)
        form.addRow("Starts", self.start)
        form.addRow("Finishes", self.end)
        form.addRow("", self.length)
        form.addRow("Status", self.status)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        set_kind(buttons.button(QDialogButtonBox.Save), "filled").setToolTip("Save (Ctrl+Enter)")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self).activated.connect(self._accept)

        lay = self._frame(title, spacing=14)
        lay.addLayout(form)
        lay.addWidget(buttons)
        self._update_length()
        self.name.setFocus()

    def _set_color(self, col):
        i = self.color.findData(col) if col else -1
        if i < 0 and col:
            self._custom = col
            last = self.color.count() - 1
            self.color.setItemIcon(last, dot_icon(col))
            self.color.setItemText(last, f"Custom {col}")
            self.color.setItemData(last, col)
            i = last
        self.color.setCurrentIndex(max(0, i))

    def _color_picked(self, index):
        if index != self.color.count() - 1:
            return
        start = QColor(self._custom or self.color.itemData(0))
        col = QColorDialog.getColor(start, self, "Project colour")
        if col.isValid():
            self._set_color(col.name())
        elif not self._custom:
            self.color.setCurrentIndex(0)

    def _sa(self):
        return self.start.dateTime().toPython().replace(second=0, microsecond=0)

    def _ea(self):
        return self.end.dateTime().toPython().replace(second=0, microsecond=0)

    def _update_length(self, *_):
        sa, ea = self._sa(), self._ea()
        self.length.setText("Finishes before it starts" if ea <= sa
                            else "Runs " + TS.fmt_length((ea - sa).total_seconds()))

    def _auto_status(self, qdt):
        """New project starting in the future defaults to Planned; now or earlier, Active."""
        if self.status.currentData() in ("planned", "active"):
            planned = qdt.toPython() > datetime.now()
            self.status.setCurrentIndex(self.status.findData("planned" if planned else "active"))

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Missing name", "Please give the project a name.")
            self.name.setFocus()
            return
        if self._ea() <= self._sa():
            QMessageBox.warning(self, "Invalid dates", "The finish must be after the start.")
            self.end.setFocus()
            return
        self.accept()

    def values(self):
        return {
            "name": self.name.text().strip(),
            "description": self.desc.toPlainText().strip(),
            "color": self.color.currentData() or TAG_PALETTE[0][1],
            "start_at": self._sa(),
            "end_at": self._ea(),
            "status": self.status.currentData(),
        }
