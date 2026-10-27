"""Banner shown in the main window while a focus session runs."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from ..theme.icons import make_icon
from ..utils import fmt_clock
from .helpers import set_kind, set_role


class FocusBar(QFrame):
    def __init__(self, focus):
        super().__init__()
        self.focus = focus
        self.setObjectName("focusBar")
        self.setAttribute(Qt.WA_StyledBackground)
        self._fg = "#000000"
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 10, 12, 10)
        v.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.icon = QLabel()
        row.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.state = set_role(QLabel("FOCUSING"), "label")
        self.state.setObjectName("focusState")
        self.title = QLabel()
        self.title.setTextFormat(Qt.PlainText)
        col.addWidget(self.state)
        col.addWidget(self.title)
        row.addLayout(col, 1)
        self.clock = QLabel()
        self.clock.setObjectName("focusClock")
        row.addWidget(self.clock)
        row.addSpacing(6)
        self.pause_btn = self._btn("Pause / resume (Ctrl+Shift+F)", focus.toggle_pause)
        self.plus = set_kind(QPushButton("+5"), "chipSmall")
        self.plus.setToolTip("Add 5 minutes")
        self.plus.setCursor(Qt.PointingHandCursor)
        self.plus.clicked.connect(lambda: focus.extend(5))
        self.stop_btn = self._btn("Stop and log time (Ctrl+F)", focus.stop)
        for w in (self.pause_btn, self.plus, self.stop_btn):
            row.addWidget(w)
        v.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setProperty("thin", True)
        self.progress.setTextVisible(False)
        v.addWidget(self.progress)
        focus.changed.connect(self.sync)
        focus.tick.connect(self._on_tick)
        self.sync()

    def _btn(self, tip, slot):
        b = set_kind(QPushButton(), "iconSmall")
        b.setToolTip(tip)
        b.setIconSize(QSize(20, 20))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def retheme(self, c):
        self._fg = c["onPrimaryContainer"]
        self.icon.setPixmap(make_icon("timer", self._fg).pixmap(24, 24))
        self.stop_btn.setIcon(make_icon("stop", self._fg))
        self.sync()

    def sync(self):
        f = self.focus
        self.setVisible(f.active)
        if not f.active:
            return
        self.state.setText("PAUSED" if f.paused else "FOCUSING")
        self.pause_btn.setIcon(make_icon("play" if f.paused else "pause", self._fg))
        self._elide()
        self._on_tick(f.remaining(), f.total_s)

    def _elide(self):
        if self.focus.active:
            fm = QFontMetrics(self.title.font())
            self.title.setText(fm.elidedText(self.focus.task["title"], Qt.ElideRight, max(80, self.title.width())))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _on_tick(self, remaining, total):
        self.clock.setText(fmt_clock(remaining))
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(max(0, total - remaining))
