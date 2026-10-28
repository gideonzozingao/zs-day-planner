"""Small dialogs: date picker, shortcut cheat-sheet, task history."""
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCalendarWidget, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
)

from .. import numbering as NUM
from ..config import SHORTCUT_HELP
from ..utils import fmt_stamp
from .helpers import set_kind, set_role
from .motion import animate


class FadeDialog(QDialog):
    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_faded", False):
            self._faded = True
            self.setWindowOpacity(0.0)
            animate(self, b"windowOpacity", 0.0, 1.0, 220, "decel")

    def _frame(self, title, spacing=16):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(spacing)
        head = set_role(QLabel(title), "title")
        head.setTextFormat(Qt.PlainText)
        head.setWordWrap(True)
        lay.addWidget(head)
        return lay


class DatePickerDialog(FadeDialog):
    def __init__(self, parent, d: date, title="Move to date"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.cal = QCalendarWidget()
        self.cal.setSelectedDate(QDate(d.year, d.month, d.day))
        self.cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.cal.activated.connect(lambda *_: self.accept())  # double-click / Enter picks
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        set_kind(buttons.button(QDialogButtonBox.Ok), "filled")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = self._frame(title)
        lay.addWidget(self.cal)
        lay.addWidget(buttons)
        self.cal.setFocus()

    def value(self) -> date:
        return self.cal.selectedDate().toPython()


class ShortcutsDialog(FadeDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        lay = self._frame("Keyboard shortcuts")
        cols = QHBoxLayout()
        cols.setSpacing(36)
        left, right = QVBoxLayout(), QVBoxLayout()
        for i, (section, rows) in enumerate(SHORTCUT_HELP):
            col = right if i in (2, 3) else left
            col.addWidget(set_role(QLabel(section), "label"))
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(8)
            for r, (keys, desc) in enumerate(rows):
                grid.addWidget(set_role(QLabel(keys), "kbd"), r, 0, Qt.AlignLeft | Qt.AlignVCenter)
                grid.addWidget(QLabel(desc), r, 1)
            grid.setColumnStretch(1, 1)
            col.addLayout(grid)
            col.addSpacing(12)
        left.addStretch()
        right.addStretch()
        cols.addLayout(left)
        cols.addLayout(right)
        lay.addLayout(cols)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class HistoryDialog(FadeDialog):
    LABELS = {
        "created": "Created", "edited": "Edited", "moved": "Moved",
        "completed": "Marked done", "reopened": "Marked not done",
        "deleted": "Deleted", "restored": "Restored", "imported": "Imported",
        "subtask added": "Subtask added", "subtask removed": "Subtask removed",
        "subtask renamed": "Subtask renamed", "subtask completed": "Subtask done",
        "subtask reopened": "Subtask reopened",
    }

    def __init__(self, parent, task, events):
        super().__init__(parent)
        self.setWindowTitle("Task history")
        self.setMinimumWidth(480)
        lay = self._frame(NUM.titled(task), spacing=10)
        lay.addWidget(set_role(QLabel("ACTIVITY"), "label"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for i, ev in enumerate(events):
            what = QLabel(self.LABELS.get(ev["action"], ev["action"]) +
                          (f"  ·  {ev['detail']}" if ev["detail"] else ""))
            what.setTextFormat(Qt.PlainText)
            what.setWordWrap(True)
            grid.addWidget(set_role(QLabel(fmt_stamp(ev["at"])), "muted"), i, 0, Qt.AlignTop)
            grid.addWidget(what, i, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        if not events:
            lay.addWidget(set_role(QLabel("No recorded activity."), "muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
