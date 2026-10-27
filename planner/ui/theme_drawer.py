"""Slide-out theme picker: mode, seed colour, scheme variant, preview."""
import re

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..config import SEEDS, VARIANTS
from ..theme import make_icon, on_color
from .helpers import set_kind, set_role
from .motion import animate


class PreviewStrip(QWidget):
    ROWS = [[("Primary", "primary", "onPrimary"), ("Secondary", "secondary", "onSecondary"),
             ("Tertiary", "tertiary", "onTertiary")],
            [("Container", "primaryContainer", "onPrimaryContainer"),
             ("Container", "secondaryContainer", "onSecondaryContainer"),
             ("Container", "tertiaryContainer", "onTertiaryContainer")]]

    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self.setFixedHeight(108)

    def paintEvent(self, e):
        c = self.theme.c
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        gap = 8
        w, h = (self.width() - 2 * gap) / 3, (self.height() - gap) / 2
        for r, row in enumerate(self.ROWS):
            for i, (name, bg, fg) in enumerate(row):
                rect = QRectF(i * (w + gap), r * (h + gap), w, h)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(c[bg]))
                p.drawRoundedRect(rect, 14, 14)
                p.setPen(QColor(c[fg]))
                p.drawText(rect, Qt.AlignCenter, name)


class ThemeDrawer(QFrame):
    themeRequested = Signal(dict)   # e.g. {"seed": "#00796B"}
    closeRequested = Signal()
    WIDTH = 340

    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        self._open = False
        self.setObjectName("drawer")
        self.setMinimumWidth(0)
        self.setMaximumWidth(0)

        dl = QVBoxLayout(self)
        dl.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollArea>QWidget>QWidget{background:transparent;}")
        body = QWidget()
        body.setFixedWidth(self.WIDTH)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 24, 24, 24)
        bl.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(set_role(QLabel("Theme"), "title"))
        head.addStretch()
        self.close_btn = set_kind(QPushButton(), "icon")
        self.close_btn.setToolTip("Close (Esc)")
        self.close_btn.setIconSize(QSize(24, 24))
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.closeRequested)
        head.addWidget(self.close_btn)
        bl.addLayout(head)

        bl.addWidget(self._lbl("MODE"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.mode_chips = {}
        grp = QButtonGroup(self)
        for key, text in (("light", "Light"), ("dark", "Dark"), ("system", "Auto")):
            b = set_kind(QPushButton(text), "chip")
            b.setCheckable(True)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._request(mode=k))
            row.addWidget(b)
            self.mode_chips[key] = b
        row.addStretch()
        bl.addLayout(row)

        bl.addWidget(self._lbl("COLOUR"))
        grid = QGridLayout()
        grid.setSpacing(10)
        self.swatches = {}
        for i, (name, hx) in enumerate(SEEDS):
            b = QPushButton()
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=hx: self._request(seed=x))
            grid.addWidget(b, i // 4, i % 4, Qt.AlignCenter)
            self.swatches[hx] = b
        bl.addLayout(grid)

        hexrow = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("#RRGGBB")
        self.hex_edit.setMaxLength(7)
        self.hex_edit.editingFinished.connect(self._hex_entered)
        pick = set_kind(QPushButton("Pick…"), "tonal")
        pick.clicked.connect(self._pick_color)
        hexrow.addWidget(self.hex_edit, 1)
        hexrow.addWidget(pick)
        bl.addLayout(hexrow)

        bl.addWidget(self._lbl("STYLE"))
        vg = QGridLayout()
        vg.setSpacing(8)
        self.variant_chips = {}
        vgrp = QButtonGroup(self)
        for i, name in enumerate(VARIANTS):
            b = set_kind(QPushButton(name), "chip")
            b.setCheckable(True)
            vgrp.addButton(b)
            b.clicked.connect(lambda _=False, n=name: self._request(variant=n))
            vg.addWidget(b, i // 3, i % 3)
            self.variant_chips[name] = b
        bl.addLayout(vg)

        bl.addWidget(self._lbl("PREVIEW"))
        self.preview = PreviewStrip(theme)
        bl.addWidget(self.preview)
        bl.addStretch()
        scroll.setWidget(body)
        dl.addWidget(scroll)

    @staticmethod
    def _lbl(text):
        l = set_role(QLabel(text), "label")
        l.setContentsMargins(0, 10, 0, 0)
        return l

    def _request(self, **kw):
        self.themeRequested.emit(kw)

    @property
    def is_open(self):
        return self._open

    def set_open(self, opening: bool):
        self._open = opening
        animate(self, b"maximumWidth", self.maximumWidth(), self.WIDTH if opening else 0,
                340, "decel" if opening else "accel")

    def sync(self):
        """Refresh controls to reflect the current theme."""
        c = self.theme.c
        self.close_btn.setIcon(make_icon("close", c["onSurfaceVariant"]))
        ring = c["onSurface"]
        for hx, b in self.swatches.items():
            sel = hx.lower() == self.theme.seed.lower()
            b.setText("✓" if sel else "")
            b.setStyleSheet(
                f"QPushButton{{background:{hx};border:3px solid {ring if sel else 'transparent'};"
                f"border-radius:20px;min-width:34px;max-width:34px;min-height:34px;max-height:34px;"
                f"padding:0;color:{on_color(hx)};font-size:16px;}}"
                f"QPushButton:hover{{border:3px solid {ring if sel else c['outline']};}}")
        self.mode_chips[self.theme.mode].setChecked(True)
        self.variant_chips[self.theme.variant].setChecked(True)
        self.hex_edit.setText(self.theme.seed.upper())
        self.preview.update()

    def _hex_entered(self):
        t = self.hex_edit.text().strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", t) and t.lower() != self.theme.seed.lower():
            self._request(seed=t)
        else:
            self.hex_edit.setText(self.theme.seed.upper())

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self.theme.seed), self, "Pick a seed colour")
        if col.isValid():
            self._request(seed=col.name())
