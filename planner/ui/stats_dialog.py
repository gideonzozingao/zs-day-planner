"""Statistics: a Today overview and an Overall (all-time) view.

Both show a status breakdown (the coloured stacked bar + a legend with counts), headline
numbers (completion, focus time, totals), and a tag breakdown. Overall adds a 14-day
completion trend. All drawing uses the status colours so it matches the task list.
"""
from datetime import date, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from .. import status as STATUS
from ..utils import fmt_duration
from .dialogs import FadeDialog
from .helpers import set_role


class StatusBar(QWidget):
    """A single horizontal stacked bar of status counts."""

    def __init__(self, counts, height=22):
        super().__init__()
        self.counts = counts
        self.setFixedHeight(height)
        self.setMinimumWidth(240)

    def set_counts(self, counts):
        self.counts = counts
        self.update()

    def paintEvent(self, e):
        total = sum(self.counts.values())
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = 6
        w, h = self.width(), self.height()
        if not total:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#00000020"))
            p.drawRoundedRect(QRectF(0, 0, w, h), r, r)
            return
        x = 0.0
        p.setPen(Qt.NoPen)
        for st in STATUS.ORDER:
            n = self.counts.get(st, 0)
            if not n:
                continue
            seg = w * n / total
            p.setBrush(QColor(STATUS.color(st)))
            p.drawRoundedRect(QRectF(x, 0, seg + (r if x + seg < w else 0), h), r, r)
            x += seg


class TrendChart(QWidget):
    """14-day completion-rate bars; empty days greyed."""

    def __init__(self, trend, color):
        super().__init__()
        self.trend = trend
        self.color = color
        self.setFixedHeight(130)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.trend)
        if not n:
            return
        pad_b = 18
        w, h = self.width(), self.height() - pad_b
        gap = 5
        bw = (w - gap * (n - 1)) / n
        base = QColor(self.color)
        muted = QColor("#88888830")
        p.setFont(QFont(self.font().family(), 7))
        for i, d in enumerate(self.trend):
            x = i * (bw + gap)
            rate = d["rate"]
            p.setPen(Qt.NoPen)
            p.setBrush(muted)
            p.drawRoundedRect(QRectF(x, 0, bw, h), 3, 3)
            if rate is not None and d["planned"]:
                bh = max(2, h * rate)
                p.setBrush(base)
                p.drawRoundedRect(QRectF(x, h - bh, bw, bh), 3, 3)
            p.setPen(QColor("#999999"))
            if i == 0 or i == n - 1 or d["date"].weekday() == 0:
                p.drawText(QRectF(x - 6, h + 2, bw + 12, pad_b), Qt.AlignHCenter | Qt.AlignTop,
                           d["date"].strftime("%d/%m"))


class StatsDialog(FadeDialog):
    def __init__(self, parent, store, colors, today=None):
        super().__init__(parent)
        self.store, self.c = store, colors
        self.today = today or date.today()
        self.setWindowTitle("Statistics")
        self.setMinimumSize(560, 560)
        lay = self._frame("Statistics", spacing=10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._scroll(self._today_tab()), "Today")
        self.tabs.addTab(self._scroll(self._overall_tab()), "Overall")
        lay.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    @staticmethod
    def _scroll(inner):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                         "QScrollArea>QWidget>QWidget{background:transparent;}")
        sa.setWidget(inner)
        return sa

    # ---- shared pieces
    def _stat_card(self, value, caption, color=None):
        f = QFrame()
        f.setObjectName("statCard")
        f.setAttribute(Qt.WA_StyledBackground)
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(0)
        val = set_role(QLabel(value), "stat")
        if color:
            val.setStyleSheet(f"color: {color}; font-size: 26px; font-weight: 600;")
        v.addWidget(val)
        v.addWidget(set_role(QLabel(caption), "muted"))
        return f

    def _legend(self, counts):
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        shown = [st for st in STATUS.ORDER if counts.get(st)]
        for i, st in enumerate(shown or STATUS.ORDER[:1]):
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {STATUS.color(st)}; font-size: 15px;")
            row, col = divmod(i, 2)
            cell = QHBoxLayout()
            cell.setSpacing(8)
            cell.addWidget(dot)
            cell.addWidget(QLabel(f"{STATUS.label(st)}"))
            cell.addStretch()
            cell.addWidget(set_role(QLabel(str(counts.get(st, 0))), "muted"))
            wrap = QWidget()
            wrap.setLayout(cell)
            grid.addWidget(wrap, row, col)
        return grid

    def _tag_rows(self, tags, limit=8):
        box = QVBoxLayout()
        box.setSpacing(6)
        if not tags:
            box.addWidget(set_role(QLabel("No tags yet."), "muted"))
            return box
        for tag, b in list(tags.items())[:limit]:
            row = QHBoxLayout()
            name = QLabel(f"#{tag}" if tag != "(untagged)" else tag)
            col = self.store.tag_colors().get(tag)
            if col:
                name.setStyleSheet(f"color: {col}; font-weight: 600;")
            bar = StatusBar({STATUS.DONE: b["done"], STATUS.OPEN: b["total"] - b["done"]}, height=10)
            row.addWidget(name, 2)
            row.addWidget(bar, 5)
            row.addWidget(set_role(QLabel(f"{b['done']}/{b['total']}"), "muted"), 0)
            box.addLayout(row)
        return box

    # ---- Today
    def _today_tab(self):
        ov = self.store.overview(self.today)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 10, 4, 4)
        v.setSpacing(12)
        v.addWidget(set_role(QLabel(self.today.strftime("%A %d %B %Y")), "muted"))
        cards = QHBoxLayout()
        cards.setSpacing(10)
        cards.addWidget(self._stat_card(f"{ov['completion']*100:.0f}%", "completed",
                                        STATUS.color(STATUS.DONE)))
        cards.addWidget(self._stat_card(f"{ov['done']}/{ov['planned']}", "tasks done"))
        cards.addWidget(self._stat_card(fmt_duration(ov["focus_seconds"]) if ov["focus_seconds"] else "0m",
                                        "focused"))
        v.addLayout(cards)
        if ov["total"]:
            v.addWidget(set_role(QLabel("STATUS BREAKDOWN"), "label"))
            v.addWidget(StatusBar(ov["counts"]))
            v.addLayout(self._legend(ov["counts"]))
            v.addWidget(set_role(QLabel("BY TAG"), "label"))
            v.addLayout(self._tag_rows(ov["tags"]))
        else:
            v.addWidget(set_role(QLabel("No tasks for today yet."), "muted"))
        v.addStretch()
        return w

    # ---- Overall
    def _overall_tab(self):
        gs = self.store.global_stats(self.today)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 10, 4, 4)
        v.setSpacing(12)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        cards.addWidget(self._stat_card(str(gs["active"]), "active tasks"))
        cards.addWidget(self._stat_card(f"{gs['completion']*100:.0f}%", "completion",
                                        STATUS.color(STATUS.DONE)))
        cards.addWidget(self._stat_card(str(gs["overdue"]), "overdue",
                                        STATUS.color(STATUS.BLOCKED) if gs["overdue"] else None))
        cards.addWidget(self._stat_card(fmt_duration(gs["focus_seconds"]) if gs["focus_seconds"] else "0m",
                                        "focused (all time)"))
        v.addLayout(cards)
        v.addWidget(set_role(QLabel(f"ALL TASKS ({gs['total']})"), "label"))
        bar = StatusBar(gs["counts"]); bar.setFixedHeight(22)
        v.addWidget(bar)
        v.addSpacing(2)
        v.addLayout(self._legend(gs["counts"]))
        v.addWidget(set_role(QLabel("COMPLETION, LAST 14 DAYS"), "label"))
        v.addWidget(TrendChart(gs["trend"], STATUS.color(STATUS.DONE)))
        v.addWidget(set_role(QLabel("BY TAG"), "label"))
        v.addLayout(self._tag_rows(gs["tags"]))
        v.addStretch()
        return w
