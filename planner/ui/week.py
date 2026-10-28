"""Week planner: the week as day columns with hours down the side (like Outlook's calendar),
and a list of open tasks on the left to drag onto a time slot.

Long tasks (a whole working day or more, or spanning days) sit in the all-day band at the top
of each day, like all-day events in Outlook; shorter ones are time blocks in the grid.

Mouse:
  drag a task from the list onto a slot   -> time-blocks it there (30-min snap; 1 h by default,
                                             or its own length if it's already a short block)
  drag a block                            -> move it (to another time or day; length kept)
  drag a block's bottom edge              -> change its end
  drag a block or task onto the all-day band -> back to the whole working day
  double-click an empty slot              -> new task at that time
  double-click a block / right-click      -> edit / task menu
"""
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QMimeData, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSplitter, QToolTip, QVBoxLayout, QWidget,
)

from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS
from .helpers import set_kind, set_role
from .kanban import MIME
from .project_dialog import dot_icon

GUTTER = 58          # hour labels
HEAD_H = 44          # day names
HOUR_H = 48          # one hour
SNAP_MIN = 15
ALLDAY_MIN = 6 * 60  # blocks this long (or multi-day) go in the all-day band
CHIP_H = 22
DEFAULT_BLOCK = 60   # minutes, for a task dropped from the list that isn't already a short block


def is_allday(t) -> bool:
    sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
    return (ea - sa) >= timedelta(minutes=ALLDAY_MIN) or (ea - timedelta(minutes=1)).date() != sa.date()


class TaskPool(QListWidget):
    """The 'to schedule' list. Items drag out with the task id."""

    def __init__(self):
        super().__init__()
        self.setObjectName("taskPool")
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setIconSize(QSize(12, 12))
        self.setWordWrap(True)
        self.setFrameShape(QFrame.NoFrame)

    def startDrag(self, actions):
        it = self.currentItem()
        if it is None:
            return
        mime = QMimeData()
        mime.setData(MIME, it.data(Qt.UserRole).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        label = QLabel(it.text().split("\n")[0])
        label.setStyleSheet("background:#333;color:white;padding:6px 10px;border-radius:8px;")
        label.adjustSize()
        drag.setPixmap(label.grab())
        drag.exec(Qt.MoveAction)


class WeekGrid(QAbstractScrollArea):
    placed = Signal(str, object, object)        # task id, start, end (a drop or a drag)
    selected = Signal(str)
    activated = Signal(str)
    createAt = Signal(object)                   # datetime of the double-clicked slot
    menuRequested = Signal(str, QPoint)

    def __init__(self):
        super().__init__()
        self.setObjectName("weekGrid")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().setMouseTracking(True)
        self.days = []
        self.tasks = []
        self.projects = {}
        self.c = {}
        self.workday = TS.DEFAULT_WORKDAY
        self.selected_id = None
        self._drag = None            # dict(tid, mode, offset_min, sa, ea, allday)
        self._ghost = None           # (sa, ea, allday) preview while dragging/dropping
        self._layout = {}            # tid -> list of (QRectF, kind) hit regions
        self.band_h = 30
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    # ---- data
    def set_week(self, days, tasks, projects, colors, workday, select=None):
        self.days, self.tasks, self.projects, self.c, self.workday = days, tasks, projects, colors, workday
        if select:
            self.selected_id = select
        per_day = {d: 0 for d in days}
        for t in tasks:
            if is_allday(t):
                for d in self._days_of(t):
                    per_day[d] += 1
        self.band_h = max(30, max(per_day.values(), default=0) * (CHIP_H + 3) + 8)
        self._update_ranges()
        self.viewport().update()

    def _days_of(self, t):
        sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
        last = (ea - timedelta(minutes=1)).date()
        return [d for d in self.days if sa.date() <= d <= last]

    def _update_ranges(self):
        content = 24 * HOUR_H
        vis = self.viewport().height() - self.top_h
        self.verticalScrollBar().setRange(0, max(0, content - vis))
        self.verticalScrollBar().setPageStep(max(1, vis))
        self.verticalScrollBar().setSingleStep(HOUR_H // 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_ranges()

    def scroll_to_hour(self, h):
        self.verticalScrollBar().setValue(int(h * HOUR_H))

    @property
    def top_h(self):
        return HEAD_H + self.band_h

    # ---- geometry
    @property
    def col_w(self):
        return (self.viewport().width() - GUTTER) / max(1, len(self.days))

    def x_of_day(self, i):
        return GUTTER + i * self.col_w

    def y_of(self, minutes):
        return self.top_h + minutes / 60 * HOUR_H - self.verticalScrollBar().value()

    def slot_at(self, pos):
        """-> (date, minutes-from-midnight snapped) for a point in the grid, or None."""
        if pos.x() < GUTTER or pos.y() < self.top_h or not self.days:
            return None
        i = int((pos.x() - GUTTER) // self.col_w)
        if not 0 <= i < len(self.days):
            return None
        m = (pos.y() - self.top_h + self.verticalScrollBar().value()) / HOUR_H * 60
        m = max(0, min(24 * 60 - SNAP_MIN, int(m // SNAP_MIN) * SNAP_MIN))
        return self.days[i], m

    def band_day_at(self, pos):
        if pos.x() < GUTTER or not (HEAD_H <= pos.y() < self.top_h) or not self.days:
            return None
        i = int((pos.x() - GUTTER) // self.col_w)
        return self.days[i] if 0 <= i < len(self.days) else None

    def _blocks_for_day(self, d):
        """Timed blocks on day d, laid out side by side where they overlap:
        -> list of (task, start_min, end_min, col, ncols)."""
        items = []
        for t in self.tasks:
            if is_allday(t):
                continue
            sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
            if sa.date() != d:
                continue
            s = sa.hour * 60 + sa.minute
            e = s + int((ea - sa).total_seconds() // 60)
            items.append([t, s, min(e, 24 * 60), 0, 1])
        items.sort(key=lambda x: (x[1], -x[2]))
        clusters, cur, cur_end = [], [], -1
        for it in items:
            if cur and it[1] >= cur_end:
                clusters.append(cur)
                cur, cur_end = [], -1
            cur.append(it)
            cur_end = max(cur_end, it[2])
        if cur:
            clusters.append(cur)
        for cl in clusters:
            cols_end = []
            for it in cl:
                for ci, end in enumerate(cols_end):
                    if it[1] >= end:
                        it[3] = ci
                        cols_end[ci] = it[2]
                        break
                else:
                    it[3] = len(cols_end)
                    cols_end.append(it[2])
            for it in cl:
                it[4] = len(cols_end)
        return items

    # ---- paint
    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        c = self.c
        W, H = self.viewport().width(), self.viewport().height()
        p.fillRect(0, 0, W, H, QColor(c.get("surfaceContainerLow", "#f6f6f6")))
        if not self.days:
            return
        grid = QColor(c.get("outlineVariant", "#cccccc"))
        muted = QColor(c.get("onSurfaceVariant", "#666666"))
        text = QColor(c.get("onSurface", "#111111"))
        primary = QColor(c.get("primary", "#6750A4"))
        error = QColor(c.get("error", "#B3261E"))
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, self.font().pointSizeF() - 1.5))
        bold = QFont(self.font())
        bold.setBold(True)
        now = datetime.now()
        cw = self.col_w
        top = self.top_h
        self._compute_layout()

        # outside-working-hours shading
        ws, we = self.workday
        ws_m = int(ws[:2]) * 60 + int(ws[3:])
        we_m = int(we[:2]) * 60 + int(we[3:])
        off = QColor(c.get("onSurface", "#000000"))
        off.setAlpha(10)
        for i, d in enumerate(self.days):
            x = self.x_of_day(i)
            p.fillRect(QRectF(x, self.y_of(0), cw, self.y_of(ws_m) - self.y_of(0)), off)
            p.fillRect(QRectF(x, self.y_of(we_m), cw, self.y_of(24 * 60) - self.y_of(we_m)), off)
            if d == now.date():
                tint = QColor(primary)
                tint.setAlpha(14)
                p.fillRect(QRectF(x, top, cw, H - top), tint)

        # hour lines + labels
        p.setFont(small)
        for h in range(25):
            y = self.y_of(h * 60)
            if y < top - 1 or y > H + 1:
                continue
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(GUTTER, y), QPointF(W, y))
            if h < 24:
                p.setPen(muted)
                p.drawText(QRectF(0, y - 8, GUTTER - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{h:02d}:00")
            yh = self.y_of(h * 60 + 30)
            if top <= yh <= H:
                p.setPen(QPen(grid, 1, Qt.DotLine))
                p.drawLine(QPointF(GUTTER, yh), QPointF(W, yh))
        for i in range(len(self.days) + 1):
            x = self.x_of_day(i)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(x, 0), QPointF(x, H))

        # timed blocks
        fm = QFontMetrics(small)
        by_id = {t["id"]: t for t in self.tasks}
        p.save()
        p.setClipRect(QRectF(GUTTER, top, W - GUTTER, H - top))
        for tid, regions in self._layout.items():
            for r, kind in regions:
                if kind == "block" and r.bottom() >= top and r.top() <= H:
                    self._paint_block(p, by_id[tid], r, small, bold, fm, text, muted, primary, error, now)
        p.restore()

        # now line
        if now.date() in self.days:
            i = self.days.index(now.date())
            y = self.y_of(now.hour * 60 + now.minute)
            if y >= top:
                p.setPen(QPen(error, 2))
                p.drawLine(QPointF(self.x_of_day(i), y), QPointF(self.x_of_day(i) + cw, y))
                p.setBrush(error)
                p.drawEllipse(QPointF(self.x_of_day(i), y), 4, 4)

        # ghost (drop / drag preview)
        if self._ghost:
            sa, ea, allday = self._ghost
            gcol = QColor(primary)
            gcol.setAlpha(60)
            p.setPen(QPen(primary, 2, Qt.DashLine))
            p.setBrush(gcol)
            if allday:
                for i, d in enumerate(self.days):
                    if sa.date() <= d <= (ea - timedelta(minutes=1)).date():
                        p.drawRoundedRect(QRectF(self.x_of_day(i) + 3, HEAD_H + 3, cw - 6, CHIP_H), 6, 6)
            elif sa.date() in self.days:
                i = self.days.index(sa.date())
                s = sa.hour * 60 + sa.minute
                e_ = s + (ea - sa).total_seconds() / 60
                r = QRectF(self.x_of_day(i) + 3, self.y_of(s), cw - 6, self.y_of(min(e_, 1440)) - self.y_of(s))
                p.drawRoundedRect(r, 6, 6)
                p.setPen(text)
                p.setFont(small)
                p.drawText(r.adjusted(6, 2, -4, 0), Qt.AlignLeft | Qt.AlignTop,
                           f"{sa:%H:%M}–{ea:%H:%M}")

        # sticky header + all-day band
        hdr = QColor(c.get("surfaceContainer", "#eeeeee"))
        p.fillRect(QRectF(0, 0, W, top), hdr)
        for i, d in enumerate(self.days):
            x = self.x_of_day(i)
            is_today = d == now.date()
            p.setFont(bold if is_today else self.font())
            p.setPen(primary if is_today else text)
            p.drawText(QRectF(x, 0, cw, HEAD_H), Qt.AlignCenter,
                       f"{d:%a} {d.day}" + (" · Today" if is_today and cw > 120 else ""))
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(x, 0), QPointF(x, top))
        p.setPen(muted)
        p.setFont(small)
        p.drawText(QRectF(0, HEAD_H, GUTTER - 6, self.band_h), Qt.AlignRight | Qt.AlignVCenter, "all day")
        # all-day chips
        fm = QFontMetrics(small)
        by_id = {t["id"]: t for t in self.tasks}
        for tid, regions in self._layout.items():
            for r, kind in regions:
                if kind == "chip":
                    self._paint_chip(p, by_id[tid], r, small, fm, text, muted, primary)
        p.setPen(QPen(grid, 1))
        p.drawLine(QPointF(0, top), QPointF(W, top))
        p.drawLine(QPointF(0, HEAD_H), QPointF(W, HEAD_H))

    def _compute_layout(self):
        """Hit regions for every block and all-day chip at the current size and scroll."""
        self._layout = {}
        cw = self.col_w
        for i, d in enumerate(self.days):
            for t, s, e_, col, ncols in self._blocks_for_day(d):
                x = self.x_of_day(i) + 2 + col * (cw - 4) / ncols
                w = (cw - 4) / ncols - 2
                y1, y2 = self.y_of(s), self.y_of(e_)
                self._layout.setdefault(t["id"], []).append((QRectF(x, y1 + 1, w, max(14.0, y2 - y1 - 2)), "block"))
        rows = {d: 0 for d in self.days}
        for t in self.tasks:
            if not is_allday(t):
                continue
            for d in self._days_of(t):
                i = self.days.index(d)
                k = rows[d]
                rows[d] += 1
                r = QRectF(self.x_of_day(i) + 3, HEAD_H + 3 + k * (CHIP_H + 3), cw - 6, CHIP_H)
                self._layout.setdefault(t["id"], []).append((r, "chip"))

    def _color(self, t):
        proj = self.projects.get(t["project_id"])
        return QColor((proj or {}).get("color") or self.c.get("primary", "#6750A4"))

    def _paint_block(self, p, t, r, small, bold, fm, text, muted, primary, error, now):
        col = self._color(t)
        st = t["status"]
        inactive = st in STATUS.INACTIVE
        fill = QColor(col)
        fill.setAlpha(55 if not inactive else 25)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.fillPath(path, fill)
        p.fillRect(QRectF(r.left(), r.top() + 2, 4, r.height() - 4), col)
        late = TS.to_dt(t["end_at"]) <= now and not inactive
        pen = QPen(primary, 2.5) if t["id"] == self.selected_id else QPen(error, 1.5) if late else QPen(col, 1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setFont(small)
        p.setPen(text if not inactive else muted)
        sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
        inner = r.adjusted(9, 2, -4, -2)
        title = NUM.titled(t)
        if r.height() < 34:
            p.drawText(inner, Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(f"{sa:%H:%M} {title}", Qt.ElideRight, int(inner.width())))
        else:
            f = QFont(small)
            f.setStrikeOut(st in (STATUS.DONE, STATUS.CANCELLED))
            p.setFont(f)
            p.drawText(inner, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, title)
            p.setFont(small)
            p.setPen(muted)
            p.drawText(inner, Qt.AlignLeft | Qt.AlignBottom, f"{sa:%H:%M}–{ea:%H:%M}")
        dot = QColor(STATUS.color(st))
        p.setPen(Qt.NoPen)
        p.setBrush(dot)
        p.drawEllipse(QPointF(r.right() - 7, r.top() + 7), 3.5, 3.5)

    def _paint_chip(self, p, t, r, small, fm, text, muted, primary):
        col = self._color(t)
        inactive = t["status"] in STATUS.INACTIVE
        fill = QColor(col)
        fill.setAlpha(70 if not inactive else 30)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.fillPath(path, fill)
        if t["id"] == self.selected_id:
            p.setPen(QPen(primary, 2))
            p.drawPath(path)
        p.setFont(small)
        p.setPen(text if not inactive else muted)
        p.drawText(r.adjusted(6, 0, -4, 0), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(NUM.titled(t), Qt.ElideRight, int(r.width() - 10)))

    # ---- hit testing
    def hit(self, pos):
        """-> (task, kind) with kind 'block', 'resize' (bottom edge) or 'chip'; else (None, None)."""
        self._compute_layout()
        by_id = {t["id"]: t for t in self.tasks}
        for tid, regions in self._layout.items():
            for r, kind in regions:
                if r.contains(pos):
                    if kind == "chip" and pos.y() >= self.top_h:
                        continue
                    if kind == "block" and pos.y() < self.top_h:
                        continue
                    if kind == "block" and pos.y() >= r.bottom() - 6:
                        return by_id.get(tid), "resize"
                    return by_id.get(tid), kind
        return None, None

    def _target(self, pos, length, offset_min=0):
        """Where a drag would land: (sa, ea, allday) or None."""
        d = self.band_day_at(pos)
        if d is not None:
            return (*TS.make_span(d, *self.workday), True)
        slot = self.slot_at(pos)
        if slot is None:
            return None
        d, m = slot
        m = max(0, m - offset_min)
        sa = datetime.combine(d, time()) + timedelta(minutes=m)
        return sa, sa + length, False

    # ---- mouse
    def mousePressEvent(self, e):
        pos = e.position()
        t, kind = self.hit(pos)
        if t:
            self.select(t["id"])
        if e.button() == Qt.LeftButton and t:
            sa, ea = TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"])
            offset = 0
            if kind == "block":
                slot = self.slot_at(pos)
                if slot:
                    offset = max(0, slot[1] - (sa.hour * 60 + sa.minute)) if slot[0] == sa.date() else 0
                    offset = int(offset // SNAP_MIN) * SNAP_MIN
            self._drag = {"tid": t["id"], "mode": kind, "offset": offset, "sa": sa, "ea": ea,
                          "start": pos, "active": False}
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position()
        d = self._drag
        if d is None:
            t, kind = self.hit(pos)
            self.viewport().setCursor(Qt.SizeVerCursor if kind == "resize"
                                      else Qt.OpenHandCursor if kind else Qt.ArrowCursor)
            return
        if not d["active"]:
            if (pos - d["start"]).manhattanLength() < 6:
                return
            d["active"] = True
        if d["mode"] == "resize":
            slot = self.slot_at(pos)
            if slot is None:
                return
            day, m = slot
            ea = datetime.combine(day, time()) + timedelta(minutes=m + SNAP_MIN)
            ea = max(d["sa"] + timedelta(minutes=SNAP_MIN), ea)
            self._ghost = (d["sa"], ea, False)
        else:
            length = d["ea"] - d["sa"]
            if d["mode"] == "chip":       # an all-day task pulled into the grid becomes a block
                length = timedelta(minutes=self.block_min)
            self._ghost = self._target(pos, length, d["offset"] if d["mode"] == "block" else 0)
        if self._ghost:
            sa, ea, allday = self._ghost
            QToolTip.showText(e.globalPosition().toPoint(),
                              "All day" if allday else f"{sa:%a %d %b}  {sa:%H:%M}–{ea:%H:%M}", self.viewport())
        self.viewport().setCursor(Qt.SizeVerCursor if d["mode"] == "resize" else Qt.ClosedHandCursor)
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        d, self._drag = self._drag, None
        ghost, self._ghost = self._ghost, None
        QToolTip.hideText()
        self.viewport().setCursor(Qt.ArrowCursor)
        if d and d["active"] and ghost:
            sa, ea, _ = ghost
            if (sa, ea) != (d["sa"], d["ea"]):
                self.placed.emit(d["tid"], sa, ea)
        self.viewport().update()
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        t, _ = self.hit(e.position())
        if t:
            self.activated.emit(t["id"])
            return
        slot = self.slot_at(e.position())
        if slot:
            self.createAt.emit(datetime.combine(slot[0], time()) + timedelta(minutes=slot[1]))

    def contextMenuEvent(self, e):
        t, _ = self.hit(QPointF(e.pos()))
        if t:
            self.select(t["id"])
            self.menuRequested.emit(t["id"], e.globalPos())

    def select(self, tid):
        if tid != self.selected_id:
            self.selected_id = tid
            self.viewport().update()
            self.selected.emit(tid or "")

    # ---- drops from the task list
    block_min = DEFAULT_BLOCK

    def _drop_length(self, tid):
        t = self.find_task(tid)
        if t and not is_allday(t):
            return TS.to_dt(t["end_at"]) - TS.to_dt(t["start_at"])
        return timedelta(minutes=self.block_min)

    def find_task(self, tid):
        return self._lookup(tid) if self._lookup else None

    _lookup = None

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if not e.mimeData().hasFormat(MIME):
            return
        tid = bytes(e.mimeData().data(MIME)).decode()
        self._ghost = self._target(e.position(), self._drop_length(tid))
        if self._ghost:
            e.acceptProposedAction()
        else:
            e.ignore()
        self.viewport().update()

    def dragLeaveEvent(self, e):
        self._ghost = None
        self.viewport().update()

    def dropEvent(self, e):
        tid = bytes(e.mimeData().data(MIME)).decode()
        target = self._target(e.position(), self._drop_length(tid))
        self._ghost = None
        self.viewport().update()
        if target:
            e.acceptProposedAction()
            self.placed.emit(tid, target[0], target[1])


class WeekPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host, self.store = host, host.store
        self.week_start = self.store.week_start_of(date.today())
        self.seven = self.store.settings.get("week_days", 7) != 5

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 20, 16)
        v.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(4)
        top.addWidget(host._icon_btn("chevron_left", "Previous week", lambda: self.shift(-7)))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = set_role(QLabel("Week planner"), "headline")
        self.sub = set_role(QLabel(), "muted")
        titles.addWidget(self.title)
        titles.addWidget(self.sub)
        top.addSpacing(6)
        top.addLayout(titles)
        top.addSpacing(6)
        top.addWidget(host._icon_btn("chevron_right", "Next week", lambda: self.shift(7)))
        top.addStretch()
        export = set_kind(QPushButton("Export…"), "chip")
        export.setToolTip("Save these time blocks as an .ics file for Outlook / Google Calendar")
        export.clicked.connect(lambda: host.export_calendar())
        top.addWidget(export)
        top.addSpacing(8)
        this = set_kind(QPushButton("This week"), "chip")
        this.clicked.connect(self.this_week)
        top.addWidget(this)
        top.addSpacing(8)
        self.days_btns = {}
        for n, label in ((5, "Work week"), (7, "7 days")):
            b = set_kind(QPushButton(label), "chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, n=n: self.set_days(n))
            self.days_btns[n] = b
            top.addWidget(b)
        v.addLayout(top)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        side = QFrame()
        side.setObjectName("panel")
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 14, 14, 12)
        sl.setSpacing(8)
        sl.addWidget(set_role(QLabel("TO SCHEDULE"), "label"))
        sl.addWidget(set_role(QLabel("Drag a task onto a time slot"), "hint"))
        self.project_pick = QComboBox()
        self.project_pick.setIconSize(QSize(12, 12))
        self.project_pick.currentIndexChanged.connect(lambda *_: self.fill_pool())
        sl.addWidget(self.project_pick)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.textChanged.connect(lambda *_: self.fill_pool())
        sl.addWidget(self.search)
        self.only_unblocked = QCheckBox("Only tasks without a time block")
        self.only_unblocked.setChecked(True)
        self.only_unblocked.setToolTip("Tasks set to a whole working day or several days")
        self.only_unblocked.toggled.connect(lambda *_: self.fill_pool())
        sl.addWidget(self.only_unblocked)
        self.pool = TaskPool()
        self.pool.itemDoubleClicked.connect(lambda it: self._edit(it.data(Qt.UserRole)))
        self.pool.currentItemChanged.connect(
            lambda it, _p: setattr(self, "_pool_sel", it.data(Qt.UserRole) if it else None))
        sl.addWidget(self.pool, 1)
        self.pool_count = set_role(QLabel(), "hint")
        sl.addWidget(self.pool_count)
        side.setMinimumWidth(240)
        split.addWidget(side)

        self.grid = WeekGrid()
        self.grid._lookup = self.store.find
        self.grid.placed.connect(self._placed)
        self.grid.activated.connect(lambda tid: self._edit(tid))
        self.grid.createAt.connect(self._create_at)
        self.grid.menuRequested.connect(self._menu)
        self.grid.selected.connect(lambda tid: setattr(self, "_pool_sel", None))
        panel = QFrame()
        panel.setObjectName("panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(8, 8, 8, 8)
        pl.addWidget(self.grid)
        split.addWidget(panel)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 900])
        v.addWidget(split, 1)
        self._pool_sel = None
        self._first_show = True

    # ---- navigation
    @property
    def days(self):
        if self.seven:
            return [self.week_start + timedelta(days=i) for i in range(7)]
        monday = self.week_start + timedelta(days=(7 - self.week_start.weekday()) % 7)
        return [monday + timedelta(days=i) for i in range(5)]       # work week: Mon–Fri

    def shift(self, n):
        self.week_start += timedelta(days=n)
        self.refresh()

    def this_week(self):
        self.week_start = self.store.week_start_of(date.today())
        self.refresh()
        self.grid.scroll_to_hour(max(0, datetime.now().hour - 2))

    def set_days(self, n):
        self.seven = n == 7
        self.store.settings["week_days"] = n
        self.store.save_settings()
        self.refresh()

    def selected_task_id(self):
        return self._pool_sel or self.grid.selected_id

    def focus_grid(self):
        self.grid.setFocus()

    # ---- refresh
    def refresh(self, select=None):
        days = self.days
        d0, d1 = days[0], days[-1]
        iso = d0.isocalendar()[1]
        self.sub.setText(f"{d0:%d %b} – {d1:%d %b %Y}   ·   Week {iso}")
        for n, b in self.days_btns.items():
            b.setChecked((n == 7) == self.seven)
        projects = {p["id"]: p for p in self.store.projects()}
        tasks = self.store.for_range(d0, d1)
        self.grid.block_min = int(self.store.settings.get("block_minutes", DEFAULT_BLOCK) or DEFAULT_BLOCK)
        self.grid.set_week(days, tasks, projects, self.host.theme.c, self.store.workday(),
                           select=select)
        self._fill_projects(projects)
        self.fill_pool()
        if self._first_show:
            self._first_show = False
            ws = int(self.store.workday()[0][:2])
            self.grid.scroll_to_hour(max(0, ws - 1))

    def _fill_projects(self, projects):
        keep = self.project_pick.currentData()
        self.project_pick.blockSignals(True)
        self.project_pick.clear()
        self.project_pick.addItem("All open tasks", "*")
        self.project_pick.addItem("Tasks outside projects", "")
        for p in self.store.projects(include_done=False):
            self.project_pick.addItem(dot_icon(p["color"]), p["name"], p["id"])
        i = self.project_pick.findData(keep if keep is not None else "*")
        self.project_pick.setCurrentIndex(max(0, i))
        self.project_pick.blockSignals(False)

    def fill_pool(self):
        pid = self.project_pick.currentData()
        q = self.search.text().strip().lower()
        rows = self.store.open_tasks(None if pid in (None, "*") else pid)
        if self.only_unblocked.isChecked():
            rows = [t for t in rows if is_allday(t)]
        if q:
            rows = [t for t in rows if q in NUM.titled(t).lower() or q in t["tags"].lower()]
        projects = {p["id"]: p for p in self.store.projects()}
        keep = self._pool_sel
        self.pool.clear()
        now_s = TS.to_str(datetime.now())
        for t in rows:
            p = projects.get(t["project_id"])
            when = TS.span_label(t["start_at"], t["end_at"])
            late = t["end_at"] <= now_s
            it = QListWidgetItem(f"{NUM.titled(t)}\n{(p['name'] + ' · ') if p else ''}{when}"
                                 + ("   (overdue)" if late else ""))
            it.setData(Qt.UserRole, t["id"])
            it.setIcon(dot_icon(p["color"] if p else self.host.theme.c["primary"]))
            it.setToolTip("Drag onto the week to give it a time block")
            self.pool.addItem(it)
            if t["id"] == keep:
                self.pool.setCurrentItem(it)
        self.pool_count.setText(f"{len(rows)} task(s)")

    # ---- actions
    def _placed(self, tid, sa, ea):
        t = self.store.find(tid)
        if not t:
            return
        old = (t["start_at"], t["end_at"])
        self.store.update(tid, start_at=sa, end_at=ea)

        def undo():
            self.store.update(tid, start_at=old[0], end_at=old[1])
            return tid
        self.host._push_undo("time block", undo)
        self._pool_sel = None
        self.refresh(select=tid)
        self.grid.setFocus()
        self.host.snack(f"{NUM.titled(t)[:36]}: {TS.span_label(sa, ea)}", "Undo", self.host.undo)

    def _edit(self, tid):
        self.grid.selected_id = tid if self._pool_sel != tid else self.grid.selected_id
        if self._pool_sel != tid:
            self._pool_sel = None
            self.grid.select(tid)
        self.host.edit_task()

    def _create_at(self, sa):
        self.host.add_task(span=(sa, sa + timedelta(minutes=self.grid.block_min)))

    def _menu(self, tid, pos):
        self._pool_sel = None
        self.host._show_menu(pos, 0, task_id=tid)
