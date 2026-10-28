"""Appearance settings: mode, seed colour, scheme variant, preview (a Settings section)."""
import re

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QColorDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from ..config import SEEDS, VARIANTS
from ..theme import on_color
from .helpers import set_kind, set_role


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


class ThemePanel(QWidget):
    """Appearance controls, shown as a section of the Settings page:
    mode (light / dark / auto), seed colour (swatches, hex, picker), scheme style, preview."""
    themeRequested = Signal(dict)   # e.g. {"seed": "#00796B"}

    def __init__(self, theme):
        super().__init__()
        self.theme = theme
        bl = QVBoxLayout(self)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(28)
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self._lbl("MODE", first=True))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.mode_chips = {}
        grp = QButtonGroup(self)
        for key, text in (("light", "Light"), ("dark", "Dark"), ("system", "Auto (follow Windows)")):
            b = set_kind(QPushButton(text), "chip")
            b.setCheckable(True)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._request(mode=k))
            row.addWidget(b)
            self.mode_chips[key] = b
        row.addStretch()
        left.addLayout(row)

        left.addWidget(self._lbl("COLOUR"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.swatches = {}
        for i, (name, hx) in enumerate(SEEDS):
            b = QPushButton()
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, x=hx: self._request(seed=x))
            grid.addWidget(b, i // 8, i % 8, Qt.AlignLeft)
            self.swatches[hx] = b
        grid.setColumnStretch(8, 1)
        left.addLayout(grid)

        hexrow = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("#RRGGBB")
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setFixedWidth(140)
        self.hex_edit.editingFinished.connect(self._hex_entered)
        pick = set_kind(QPushButton("Pick a colour…"), "tonal")
        pick.clicked.connect(self._pick_color)
        hexrow.addWidget(self.hex_edit)
        hexrow.addWidget(pick)
        hexrow.addStretch()
        left.addLayout(hexrow)

        left.addWidget(self._lbl("STYLE"))
        vg = QGridLayout()
        vg.setSpacing(8)
        self.variant_chips = {}
        vgrp = QButtonGroup(self)
        for i, name in enumerate(VARIANTS):
            b = set_kind(QPushButton(name), "chip")
            b.setCheckable(True)
            vgrp.addButton(b)
            b.clicked.connect(lambda _=False, n=name: self._request(variant=n))
            vg.addWidget(b, i // 4, i % 4)
            self.variant_chips[name] = b
        vg.setColumnStretch(4, 1)
        left.addLayout(vg)
        top.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(self._lbl("PREVIEW", first=True))
        self.preview = PreviewStrip(theme)
        self.preview.setMinimumWidth(260)
        right.addWidget(self.preview)
        right.addStretch()
        top.addLayout(right, 2)
        bl.addLayout(top)

    @staticmethod
    def _lbl(text, first=False):
        l = set_role(QLabel(text), "hint")
        l.setContentsMargins(0, 0 if first else 8, 0, 0)
        return l

    def _request(self, **kw):
        self.themeRequested.emit(kw)

    def sync(self):
        """Refresh controls to reflect the current theme."""
        c = self.theme.c
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
