"""Spotlight-style quick add, opened from any app with the global hotkey.

Enter adds and closes · Shift+Enter adds and stays open · Ctrl+Enter opens the full editor
Esc or clicking away hides it (unsent text is kept for next time).
"""
from datetime import date

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ..quickparse import describe, parse
from ..theme.icons import render_logo
from .helpers import set_role
from .motion import animate


class QuickCapture(QWidget):
    def __init__(self, store, on_added, on_details, hotkey_label=""):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.store, self.on_added, self.on_details = store, on_added, on_details

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 36)
        card = QFrame()
        card.setObjectName("captureCard")
        card.setAttribute(Qt.WA_StyledBackground)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 120))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 16, 22, 14)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(render_logo(20))
        head.addWidget(logo)
        head.addWidget(set_role(QLabel("QUICK ADD"), "label"))
        head.addStretch()
        if hotkey_label:
            head.addWidget(set_role(QLabel(hotkey_label), "kbd"))
        lay.addLayout(head)

        self.edit = QLineEdit()
        self.edit.setObjectName("captureEdit")
        self.edit.setPlaceholderText("e.g.  Review PR tomorrow 2pm #dpp !high")
        self.edit.textChanged.connect(self._preview)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.preview = set_role(QLabel(), "muted")
        self.preview.setTextFormat(Qt.PlainText)
        lay.addWidget(self.preview)
        sep = QFrame()
        sep.setObjectName("captureSep")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        lay.addWidget(set_role(QLabel("Enter add  ·  Shift+Enter add another  ·  Ctrl+Enter details  ·  Esc close"), "hint"))
        self.setFixedWidth(640)
        self._preview()

    # ---- behaviour
    def open(self):
        self.adjustSize()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        self.move(QPoint(g.center().x() - self.width() // 2, g.top() + g.height() // 4))
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
        self.edit.selectAll()
        animate(self, b"windowOpacity", 0.0, 1.0, 160, "decel")

    def close_capture(self):
        animate(self, b"windowOpacity", self.windowOpacity(), 0.0, 120, "accel", finished=self.hide)

    def changeEvent(self, e):
        if e.type() == QEvent.ActivationChange and not self.isActiveWindow() and self.isVisible():
            QTimer.singleShot(0, self.close_capture)      # clicked away: hide, keep the text
        super().changeEvent(e)

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == QEvent.KeyPress:
            key, mods = e.key(), e.modifiers()
            if key == Qt.Key_Escape:
                self.close_capture()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if mods & Qt.ControlModifier:
                    self._details()
                else:
                    self._add(keep_open=bool(mods & Qt.ShiftModifier))
                return True
        return super().eventFilter(obj, e)

    def _parsed(self):
        return parse(self.edit.text(), date.today())

    def _preview(self, *_):
        today = date.today()
        p = self._parsed()
        if not self.edit.text().strip():
            self.preview.setText("Dates, times, #tags, !high and * (top task) are understood")
        elif not p.title:
            self.preview.setText("Add a title")
        else:
            self.preview.setText("→  " + describe(p, today, today, self.store.workday()))

    def _add(self, keep_open):
        p = self._parsed()
        if not p.title:
            self.preview.setText("Add a title first")
            return
        t = self.store.add(p.date or date.today(), p.title, p.start, p.end,
                           priority=p.priority, tags=" ".join(p.tags), pinned=p.pinned)
        self.on_added(t)
        self.edit.clear()
        if keep_open:
            self.preview.setText(f"✓ Added “{t['title']}”. Add another")
        else:
            self.close_capture()

    def _details(self):
        p = self._parsed()
        self.edit.clear()
        self.hide()
        self.on_details(p)
