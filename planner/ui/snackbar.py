"""Material snackbar overlay with an optional action button (e.g. Undo)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton

from .motion import animate


class Snackbar(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("snackbar")
        self.setAttribute(Qt.WA_StyledBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 8, 6)
        lay.setSpacing(8)
        self.text = QLabel()
        self.text.setTextFormat(Qt.PlainText)
        self.btn = QPushButton()
        self.btn.setObjectName("snackAction")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._act)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.btn)
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.dismiss)
        self._action = None
        self._gen = 0
        self.hide()

    def show_message(self, text, action_text="", action=None, ms=4500):
        self._gen += 1
        self._action = action
        self.text.setText(text)
        self.btn.setText(action_text)
        self.btn.setVisible(bool(action))
        was_visible = self.isVisible()
        self.reposition()
        self.show()
        self.raise_()
        if not was_visible:
            self.eff.setOpacity(0.0)
        animate(self.eff, b"opacity", self.eff.opacity(), 1.0, 180, "decel")
        self.timer.start(ms)

    def dismiss(self):
        self.timer.stop()
        if not self.isVisible():
            return
        gen = self._gen
        animate(self.eff, b"opacity", self.eff.opacity(), 0.0, 160, "accel",
                finished=lambda: gen == self._gen and self.hide())

    def reposition(self):
        p = self.parentWidget()
        self.adjustSize()
        w = max(320, min(self.sizeHint().width() + 24, p.width() - 48))
        h = self.sizeHint().height()
        self.setGeometry((p.width() - w) // 2, p.height() - h - 92, w, h)

    def _act(self):
        fn = self._action
        self.dismiss()
        if fn:
            fn()
