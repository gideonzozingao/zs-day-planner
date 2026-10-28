"""Inline checklist editor used inside the task dialog.

Keyboard: Enter in the add field appends a subtask; Up/Down move between rows;
Alt+Up/Down reorder; Backspace in an empty row removes it.
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ..theme.icons import make_icon
from .helpers import repolish, set_kind, set_role

MAX_LIST_HEIGHT = 232


class SubtaskLineEdit(QLineEdit):
    backspaceOnEmpty = Signal()
    moveRequested = Signal(int)   # Alt+Up/Down: reorder
    focusStep = Signal(int)       # Up/Down: move focus

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key_Backspace and not self.text():
            self.backspaceOnEmpty.emit()
            return
        if key in (Qt.Key_Up, Qt.Key_Down):
            step = -1 if key == Qt.Key_Up else 1
            if e.modifiers() & Qt.AltModifier:
                self.moveRequested.emit(step)
            else:
                self.focusStep.emit(step)
            return
        super().keyPressEvent(e)


class SubtaskRow(QWidget):
    def __init__(self, item, remove_icon, label=""):
        """label: the subtask's number as shown (e.g. '9.2'); empty for a row not saved yet."""
        super().__init__()
        self.sid = item.get("id")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(8)
        self.num = set_role(QLabel(label), "hint")
        self.num.setMinimumWidth(30)
        self.num.setToolTip("Subtask number (given automatically)" if label else "Numbered when you save")
        self.check = QCheckBox()
        self.check.setToolTip("Mark subtask done")
        self.check.setChecked(bool(item.get("done")))
        self.edit = SubtaskLineEdit(item.get("title", ""))
        self.edit.setProperty("flat", True)
        self.edit.setPlaceholderText("Subtask")
        self.edit.setCursorPosition(0)              # show long titles from the start, not the end
        self.edit.setToolTip(self.edit.text())
        self.edit.textChanged.connect(self.edit.setToolTip)
        self.edit.editingFinished.connect(lambda: self.edit.setCursorPosition(0))
        self.remove = set_kind(QPushButton(), "iconSmall")
        self.remove.setIcon(remove_icon)
        self.remove.setIconSize(QSize(18, 18))
        self.remove.setToolTip("Remove subtask")
        self.remove.setCursor(Qt.PointingHandCursor)
        self.remove.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.num)
        lay.addWidget(self.check)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.remove)
        self.check.toggled.connect(self._restyle)
        self._restyle()

    def _restyle(self):
        self.edit.setProperty("done", self.check.isChecked())
        repolish(self.edit)

    def value(self):
        return {"id": self.sid, "title": self.edit.text().strip(), "done": self.check.isChecked()}


class SubtaskEditor(QFrame):
    changed = Signal()

    def __init__(self, colors, items=(), task=None):
        """task: the task being edited (for '9.2'-style labels); None for a new task."""
        super().__init__()
        self._task = task
        self.setObjectName("subtaskCard")
        self.setAttribute(Qt.WA_StyledBackground)
        self._remove_icon = make_icon("close", colors["onSurfaceVariant"])

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(set_role(QLabel("SUBTASKS"), "label"))
        head.addStretch()
        self.count = set_role(QLabel(), "muted")
        head.addWidget(self.count)
        lay.addLayout(head)

        self.progress = QProgressBar()
        self.progress.setProperty("thin", True)
        self.progress.setTextVisible(False)
        lay.addWidget(self.progress)

        self.body = QWidget()
        self.body.setAttribute(Qt.WA_StyledBackground, False)
        self.rows = QVBoxLayout(self.body)
        self.rows.setContentsMargins(0, 0, 4, 0)
        self.rows.setSpacing(2)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                                  "QScrollArea>QWidget>QWidget{background:transparent;}")
        self.scroll.setWidget(self.body)
        lay.addWidget(self.scroll)

        self.add_edit = SubtaskLineEdit()
        self.add_edit.setPlaceholderText("Add a subtask and press Enter")
        self.add_edit.returnPressed.connect(self._add_from_field)
        self.add_edit.focusStep.connect(self._from_add_field)
        lay.addWidget(self.add_edit)
        lay.addWidget(set_role(QLabel("↑/↓ move  ·  Alt+↑/↓ reorder  ·  Backspace on empty removes"), "hint"))

        for it in items:
            self._append(it, update=False)
        self._update()

    # ---- rows
    def _rows(self):
        return [self.rows.itemAt(i).widget() for i in range(self.rows.count())]

    def _append(self, item, index=-1, focus=False, update=True):
        from ..numbering import sub_no
        row = SubtaskRow(item, self._remove_icon, sub_no(self._task, item) if item.get("id") else "")
        row.check.toggled.connect(self._update)
        row.edit.textChanged.connect(self.changed)
        row.edit.returnPressed.connect(self.add_edit.setFocus)
        row.edit.backspaceOnEmpty.connect(lambda r=row: self.remove_row(r))
        row.edit.moveRequested.connect(lambda d, r=row: self.move_row(r, d))
        row.edit.focusStep.connect(lambda d, r=row: self.focus_step(r, d))
        row.remove.clicked.connect(lambda _=False, r=row: self.remove_row(r, refocus=False))
        self.rows.insertWidget(index if index >= 0 else self.rows.count(), row)
        if update:
            self._update()
        if focus:
            row.edit.setFocus()
        return row

    def remove_row(self, row, refocus=True):
        rows = self._rows()
        i = rows.index(row)
        self.rows.removeWidget(row)
        row.hide()
        row.deleteLater()
        self._update()
        if refocus:
            rest = self._rows()
            target = rest[i - 1].edit if i > 0 else (rest[0].edit if rest else self.add_edit)
            target.setFocus()
            if isinstance(target, QLineEdit):
                target.end(False)

    def move_row(self, row, delta):
        rows = self._rows()
        i = rows.index(row)
        j = i + delta
        if 0 <= j < len(rows):
            self.rows.removeWidget(row)
            self.rows.insertWidget(j, row)
            row.edit.setFocus()
            self.changed.emit()

    def focus_step(self, row, delta):
        rows = self._rows()
        j = rows.index(row) + delta
        if j < 0:
            return
        (rows[j].edit if j < len(rows) else self.add_edit).setFocus()

    def _from_add_field(self, delta):
        rows = self._rows()
        if delta < 0 and rows:
            rows[-1].edit.setFocus()

    def _add_from_field(self):
        text = self.add_edit.text().strip()
        if not text:
            return
        self._append({"title": text})
        self.add_edit.clear()
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _update(self, *_):
        rows = self._rows()
        done = sum(r.check.isChecked() for r in rows)
        self.count.setText(f"{done} of {len(rows)} done" if rows else "None yet")
        self.progress.setVisible(bool(rows))
        self.progress.setMaximum(max(len(rows), 1))
        self.progress.setValue(done)
        self.scroll.setVisible(bool(rows))
        self.rows.activate()
        self.scroll.setFixedHeight(min(self.body.sizeHint().height(), MAX_LIST_HEIGHT) + 2)
        self.changed.emit()

    # ---- public
    def set_checklist(self, titles):
        """Fill a new task's list from its project's checklist. Replaces a previous checklist
        fill only if the user hasn't changed it, and never touches rows they typed."""
        current = [r.value()["title"] for r in self._rows()]
        auto = getattr(self, "_auto", [])
        if current and current != auto:
            return
        for r in self._rows():
            self.rows.removeWidget(r)
            r.deleteLater()
        for t in titles:
            self._append({"title": t, "done": False}, update=False)
        self._auto = list(titles)
        self._update()

    def values(self):
        """[{id|None, title, done}] in display order, empty titles dropped."""
        out = [r.value() for r in self._rows()]
        pending = self.add_edit.text().strip()   # typed but Enter not pressed: keep it
        if pending:
            out.append({"id": None, "title": pending, "done": False})
        return [v for v in out if v["title"]]
