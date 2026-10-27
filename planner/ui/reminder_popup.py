"""Frameless reminder card that slides/fades in at the bottom-right of the screen."""
from datetime import datetime

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ..data import reminder_sections
from ..theme import make_icon
from .helpers import set_kind, set_role
from .motion import animate

SNOOZE_CHOICES = ((5, "5 min"), (15, "15 min"), (60, "1 hr"))


def _label(t):
    when = f"{t['start']}-{t['end']}  " if t["start"] else ""
    subs = f"  ({t['sub_done']}/{t['sub_total']})" if t.get("sub_total") else ""
    star = "★ " if t.get("pinned") else ""
    repeat = " ⟳" if t.get("recurrence") else ""
    return f"{when}{star}{t['title']}{repeat}{subs}"


class ReminderPopup(QWidget):
    def __init__(self, store, theme, now: datetime, on_change, on_open, on_snooze=None, on_focus=None,
                 snoozed=None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.store, self.on_change = store, on_change
        self.on_snooze, self.on_focus, self.theme = on_snooze, on_focus, theme
        self._entered = self._leaving = self._done = False

        current, overdue, upcoming, anytime = reminder_sections(store, now, snoozed)
        self.has_content = bool(current or overdue or upcoming or anytime)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 32)
        card = QFrame()
        card.setObjectName("popupCard")
        card.setAttribute(Qt.WA_StyledBackground)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(44)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 110))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 22, 24, 16)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(14)
        circle = QLabel()
        circle.setObjectName("iconCircle")
        circle.setFixedSize(40, 40)
        circle.setAlignment(Qt.AlignCenter)
        circle.setPixmap(make_icon("bell", theme.c["onPrimaryContainer"]).pixmap(22, 22))
        head.addWidget(circle)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(set_role(QLabel("DAILY PLANNER"), "label"))
        col.addWidget(set_role(QLabel(f"{now:%A %d %b} · {now:%H:%M}"), "title"))
        head.addLayout(col)
        head.addStretch()
        lay.addLayout(head)
        lay.addSpacing(8)

        # the single most relevant task gets per-task actions (snooze / start now)
        self.featured = (current[0] if current else (overdue[-1] if overdue else
                         (upcoming[0] if upcoming else None)))
        self._section(lay, "NOW", current, True, "accent")
        self._section(lay, f"OVERDUE ({len(overdue)})" if len(overdue) > 3 else "OVERDUE",
                      overdue[-3:], True, "danger")
        self._section(lay, "NEXT 3 HOURS", upcoming, False, "accent")
        self._section(lay, "ANYTIME TODAY", anytime[:5], True, "accent")
        if not self.has_content:
            lay.addWidget(set_role(QLabel("Nothing scheduled right now."), "muted"))

        if self.featured and (self.on_snooze or self.on_focus):
            lay.addSpacing(6)
            lay.addWidget(set_role(QLabel("REMIND ME IN"), "label"))
            snooze_row = QHBoxLayout()
            snooze_row.setSpacing(6)
            for mins_, label in SNOOZE_CHOICES:
                b = set_kind(QPushButton(label), "chip")
                b.setMinimumWidth(66)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, m=mins_: self._snooze(m))
                snooze_row.addWidget(b)
            snooze_row.addStretch()
            if self.on_focus and not self.featured["done"]:
                start = set_kind(QPushButton("  Start now"), "tonal")
                start.setIcon(make_icon("timer", theme.c["onSecondaryContainer"]))
                start.setCursor(Qt.PointingHandCursor)
                start.clicked.connect(self._start_now)
                snooze_row.addWidget(start)
            lay.addLayout(snooze_row)

        lay.addSpacing(10)
        row = QHBoxLayout()
        open_btn = QPushButton("Open planner")
        open_btn.clicked.connect(lambda: (on_open(), self.close()))
        ok = set_kind(QPushButton("Got it"), "filled")
        ok.clicked.connect(self.close)
        row.addStretch()
        row.addWidget(open_btn)
        row.addWidget(ok)
        lay.addLayout(row)

        QShortcut(QKeySequence("Escape"), self).activated.connect(self.close)

        self.setFixedWidth(480)
        self.adjustSize()
        geo = QApplication.primaryScreen().availableGeometry()
        self._target = QPoint(geo.right() - self.width() - 8, geo.bottom() - self.height() - 8)
        self.move(self._target)

    def _section(self, lay, title, items, checkable, role):
        if not items:
            return
        label = set_role(QLabel(title), role)
        label.setContentsMargins(0, 8, 0, 2)
        lay.addWidget(label)
        for t in items:
            if checkable:
                box = QCheckBox(_label(t).replace("&", "&&"))
                box.setChecked(t["done"])
                box.toggled.connect(lambda c, tid=t["id"]: self._toggle(tid, c))
                lay.addWidget(box)
                if t["note"]:
                    note = set_role(QLabel(t["note"]), "muted")
                    note.setTextFormat(Qt.PlainText)
                    note.setContentsMargins(30, 0, 0, 0)
                    lay.addWidget(note)
            else:
                lbl = QLabel(_label(t))
                lbl.setTextFormat(Qt.PlainText)
                lbl.setContentsMargins(30, 0, 0, 0)
                lay.addWidget(lbl)

    def _toggle(self, tid, checked):
        self.store.update(tid, done=checked)
        self.on_change()

    def _snooze(self, minutes):
        if self.featured and self.on_snooze:
            self.on_snooze(self.featured, minutes)
        self.close()

    def _start_now(self):
        if self.featured and self.on_focus:
            self.on_focus(self.featured)
        self.close()

    def showEvent(self, e):
        super().showEvent(e)
        if self._entered:
            return
        self._entered = True
        self.setWindowOpacity(0.0)
        self.move(self._target + QPoint(0, 36))
        animate(self, b"pos", self._target + QPoint(0, 36), self._target, 420, "decel")
        animate(self, b"windowOpacity", 0.0, 1.0, 240, "std")

    def closeEvent(self, e):
        if self._done:
            e.accept()
            return
        e.ignore()
        if self._leaving:
            return
        self._leaving = True
        animate(self, b"pos", self.pos(), self._target + QPoint(0, 28), 200, "accel")
        animate(self, b"windowOpacity", 1.0, 0.0, 180, "std", finished=self._finish)

    def _finish(self):
        self._done = True
        self.close()
