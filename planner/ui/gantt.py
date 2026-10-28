"""Project timeline (Gantt): one row per task, bars from start to end on a date axis.

Shows the project's start and finish (dashed lines), a "today" line, weekends, and a load
strip under the header (how many tasks run on each day, so overlaps and gaps stand out).
The part of a bar past the project's finish is hatched red.

Mouse: drag a bar to move the task (length kept), drag its left/right edge to change the
start/end. Moves snap to whole days when zoomed out, to hours/30 min when zoomed in.
Ctrl+wheel zooms around the cursor, Shift+wheel scrolls sideways.

Signals:
    spanChanged(task_id, start_dt, end_dt)   a drag finished (ProjectsPage writes + undo)
    selected(task_id), activated(task_id), menuRequested(task_id, QPoint)
"""
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractScrollArea, QToolTip

from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS

ZOOMS = (6, 10, 16, 24, 36, 56, 90, 140, 220)    # pixels per day
LABEL_W = 250
HEADER_H = 46
LOAD_H = 16
ROW_H = 34
EDGE = 7                                          # px either side of a bar end that grabs it


def _floor_day(dt):
    return datetime.combine(dt.date(), time())


class GanttView(QAbstractScrollArea):
    spanChanged = Signal(str, object, object)
    selected = Signal(str)
    activated = Signal(str)
    menuRequested = Signal(str, QPoint)

    def __init__(self):
        super().__init__()
        self.setObjectName("gantt")
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setMouseTracking(True)
        self.zoom = 3
        self.tasks, self.project, self.c = [], None, {}
        self.deps = {}
        self.t0 = self.t1 = datetime.now()
        self.selected_id = None
        self._drag = None          # dict(tid, mode, x0, sa, ea)
        self._preview = {}         # tid -> (sa, ea) while dragging
        self.horizontalScrollBar().valueChanged.connect(self.viewport().update)
        self.verticalScrollBar().valueChanged.connect(self.viewport().update)

    # ------------------------------------------------------------------ data
    @property
    def ppd(self):
        return ZOOMS[self.zoom]

    def set_tasks(self, project, tasks, colors, select=None, deps=None):
        self.project, self.tasks, self.c = project, tasks, colors
        self.deps = deps or {}
        starts = [TS.to_dt(t["start_at"]) for t in tasks] + [TS.to_dt(project["start_at"]), datetime.now()]
        ends = [TS.to_dt(t["end_at"]) for t in tasks] + [TS.to_dt(project["end_at"]), datetime.now()]
        self.t0 = _floor_day(min(starts)) - timedelta(days=3)
        self.t1 = _floor_day(max(ends)) + timedelta(days=5)
        if select:
            self.selected_id = select
        if self.selected_id not in {t["id"] for t in tasks}:
            self.selected_id = None
        self._update_ranges()
        self.viewport().update()

    def _update_ranges(self):
        days = (self.t1 - self.t0).total_seconds() / 86400
        content_w = int(days * self.ppd)
        vw = max(1, self.viewport().width() - LABEL_W)
        self.horizontalScrollBar().setRange(0, max(0, content_w - vw))
        self.horizontalScrollBar().setPageStep(vw)
        self.horizontalScrollBar().setSingleStep(max(8, self.ppd // 2))
        content_h = HEADER_H + LOAD_H + len(self.tasks) * ROW_H + 8
        vh = self.viewport().height()
        self.verticalScrollBar().setRange(0, max(0, content_h - vh))
        self.verticalScrollBar().setPageStep(vh)
        self.verticalScrollBar().setSingleStep(ROW_H)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_ranges()

    # ------------------------------------------------------------------ geometry
    def x_of(self, dt):
        return LABEL_W + (dt - self.t0).total_seconds() / 86400 * self.ppd - self.horizontalScrollBar().value()

    def dt_of(self, x):
        return self.t0 + timedelta(days=(x - LABEL_W + self.horizontalScrollBar().value()) / self.ppd)

    def row_y(self, i):
        return HEADER_H + LOAD_H + i * ROW_H - self.verticalScrollBar().value()

    def span(self, t):
        return self._preview.get(t["id"]) or (TS.to_dt(t["start_at"]), TS.to_dt(t["end_at"]))

    def bar_rect(self, i, t):
        sa, ea = self.span(t)
        x1, x2 = self.x_of(sa), self.x_of(ea)
        return QRectF(x1, self.row_y(i) + 7, max(4.0, x2 - x1), ROW_H - 14)

    def snap_minutes(self):
        return 1440 if self.ppd < 40 else 60 if self.ppd < 120 else 30

    def scroll_to(self, dt, align=0.3):
        """Scroll so `dt` sits at `align` (0..1) of the visible timeline."""
        vw = self.viewport().width() - LABEL_W
        x = (dt - self.t0).total_seconds() / 86400 * self.ppd - vw * align
        self.horizontalScrollBar().setValue(int(x))

    def set_zoom(self, z, anchor_x=None):
        z = max(0, min(len(ZOOMS) - 1, z))
        if z == self.zoom:
            return
        anchor_x = anchor_x if anchor_x is not None else LABEL_W + (self.viewport().width() - LABEL_W) / 2
        anchor_dt = self.dt_of(anchor_x)
        self.zoom = z
        self._update_ranges()
        x = (anchor_dt - self.t0).total_seconds() / 86400 * self.ppd - (anchor_x - LABEL_W)
        self.horizontalScrollBar().setValue(int(x))
        self.viewport().update()

    def fit(self):
        """Zoom so the project's start..finish fills the view."""
        p = self.project
        if not p:
            return
        span_days = max(1.0, (TS.to_dt(p["end_at"]) - TS.to_dt(p["start_at"])).total_seconds() / 86400 + 2)
        vw = self.viewport().width() - LABEL_W
        best = 0
        for i, z in enumerate(ZOOMS):
            if span_days * z <= vw:
                best = i
        self.zoom = best
        self._update_ranges()
        self.scroll_to(TS.to_dt(p["start_at"]) - timedelta(days=1), 0)
        self.viewport().update()

    def hit(self, pos):
        """-> (task, mode) under pos; mode is 'move', 'start' or 'end'; (None, None) if none."""
        if pos.x() < LABEL_W or pos.y() < HEADER_H + LOAD_H:
            return None, None
        i = int((pos.y() - HEADER_H - LOAD_H + self.verticalScrollBar().value()) // ROW_H)
        if not 0 <= i < len(self.tasks):
            return None, None
        t = self.tasks[i]
        r = self.bar_rect(i, t)
        x = pos.x()
        if r.top() - 4 <= pos.y() <= r.bottom() + 4:
            if r.width() >= 4 * EDGE:
                # wide bar: the inner few pixels at each end resize it
                if abs(x - r.right()) <= EDGE:
                    return t, "end"
                if abs(x - r.left()) <= EDGE:
                    return t, "start"
                if r.left() <= x <= r.right():
                    return t, "move"
            else:
                # narrow bar (zoomed out): the bar itself moves; just outside its ends resizes
                if r.right() < x <= r.right() + EDGE:
                    return t, "end"
                if r.left() - EDGE <= x < r.left():
                    return t, "start"
                if r.left() - 1 <= x <= r.right() + 1:
                    return t, "move"
        return t, None

    def row_task(self, pos):
        if pos.y() < HEADER_H + LOAD_H:
            return None
        i = int((pos.y() - HEADER_H - LOAD_H + self.verticalScrollBar().value()) // ROW_H)
        return self.tasks[i] if 0 <= i < len(self.tasks) else None

    # ------------------------------------------------------------------ paint
    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        c = self.c
        W, H = self.viewport().width(), self.viewport().height()
        bg = QColor(c.get("surfaceContainerLow", "#f4f4f4"))
        p.fillRect(0, 0, W, H, bg)
        if not self.project:
            return
        grid = QColor(c.get("outlineVariant", "#cccccc"))
        muted = QColor(c.get("onSurfaceVariant", "#666666"))
        text = QColor(c.get("onSurface", "#111111"))
        primary = QColor(c.get("primary", "#6750A4"))
        error = QColor(c.get("error", "#B3261E"))
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, self.font().pointSizeF() - 1.5))
        p.setFont(small)

        # visible day range
        d_first = self.dt_of(LABEL_W).date() - timedelta(days=1)
        d_last = self.dt_of(W).date() + timedelta(days=1)
        top_rows = HEADER_H + LOAD_H

        # weekends + day grid
        d = d_first
        while d <= d_last:
            x = self.x_of(datetime.combine(d, time()))
            if d.weekday() >= 5:
                shade = QColor(c.get("onSurface", "#000000"))
                shade.setAlpha(12)
                p.fillRect(QRectF(x, top_rows, self.ppd, H), shade)
            if self.ppd >= 14 or d.weekday() == 0:
                pen = QPen(grid, 1)
                pen.setCosmetic(True)
                p.setPen(pen)
                p.drawLine(QPointF(x, top_rows), QPointF(x, H))
            d += timedelta(days=1)

        # hour grid when zoomed far in
        if self.ppd >= 140:
            pen = QPen(grid, 1, Qt.DotLine)
            p.setPen(pen)
            d = d_first
            while d <= d_last:
                for h in (6, 12, 18):
                    x = self.x_of(datetime.combine(d, time(h)))
                    p.drawLine(QPointF(x, top_rows), QPointF(x, H))
                d += timedelta(days=1)

        # row separators
        p.setPen(QPen(grid, 1))
        for i in range(len(self.tasks) + 1):
            y = self.row_y(i)
            if top_rows <= y <= H:
                p.drawLine(QPointF(LABEL_W, y), QPointF(W, y))

        # project start / finish
        pcol = QColor(self.project["color"] or c.get("primary", "#6750A4"))
        ps, pe = TS.to_dt(self.project["start_at"]), TS.to_dt(self.project["end_at"])
        for dt, label in ((ps, "Start"), (pe, "Finish")):
            x = self.x_of(dt)
            pen = QPen(pcol, 2, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(QPointF(x, top_rows), QPointF(x, H))
            p.setPen(pcol)
            p.drawText(QRectF(x + 4, top_rows + 1, 80, 14), Qt.AlignLeft | Qt.AlignVCenter, label)
        # after-finish tint
        xf = self.x_of(pe)
        if xf < W:
            tint = QColor(error)
            tint.setAlpha(14)
            p.fillRect(QRectF(max(xf, LABEL_W), top_rows, W - max(xf, LABEL_W), H), tint)

        # bars
        now = datetime.now()
        now_s = TS.to_str(now)
        fm = QFontMetrics(self.font())
        p.setFont(self.font())
        for i, t in enumerate(self.tasks):
            y = self.row_y(i)
            if y + ROW_H < top_rows or y > H:
                continue
            r = self.bar_rect(i, t)
            if r.right() < LABEL_W or r.left() > W:
                continue
            st = t["status"]
            col = QColor(STATUS.color(st))
            inactive = st in STATUS.INACTIVE
            sa, ea = self.span(t)
            late = TS.to_str(ea) <= now_s and not inactive
            base = QColor(col)
            base.setAlpha(70 if not inactive else 40)
            path = QPainterPath()
            path.addRoundedRect(r, 6, 6)
            p.fillPath(path, base)
            frac = 1.0 if st == STATUS.DONE else (t["sub_done"] / t["sub_total"] if t["sub_total"] else 0.0)
            if frac > 0:
                pr = QRectF(r.left(), r.top(), r.width() * frac, r.height())
                pp = QPainterPath()
                pp.addRoundedRect(pr, 6, 6)
                solid = QColor(col)
                solid.setAlpha(200 if not inactive else 90)
                p.fillPath(pp, solid)
            # past the project's finish
            if r.right() > xf and not inactive:
                over = QRectF(max(r.left(), xf), r.top(), r.right() - max(r.left(), xf), r.height())
                p.save()
                p.setClipPath(path)
                p.fillRect(over, QBrush(error, Qt.BDiagPattern))
                p.restore()
            pen = QPen(col.darker(130), 1)
            if late:
                pen = QPen(error, 2)
            if t["id"] == self.selected_id:
                pen = QPen(primary, 2.5)
            p.setPen(pen)
            p.drawPath(path)
            # label: inside if it fits, else to the right
            label = NUM.titled(t)
            avail = r.width() - 12
            p.setPen(text if not inactive else muted)
            if fm.horizontalAdvance(label) <= avail:
                p.drawText(r.adjusted(6, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft, label)
            else:
                p.drawText(QRectF(r.right() + 6, r.top(), 360, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                           fm.elidedText(label, Qt.ElideRight, 360))

        # dependency arrows: from the end of a prerequisite to the start of the task waiting for it
        row_of = {t["id"]: i for i, t in enumerate(self.tasks)}
        for tid, pres in self.deps.items():
            if tid not in row_of:
                continue
            j = row_of[tid]
            rj = self.bar_rect(j, self.tasks[j])
            for pid in pres:
                if pid not in row_of:
                    continue
                i = row_of[pid]
                ri = self.bar_rect(i, self.tasks[i])
                pre_open = self.tasks[i]["status"] not in (STATUS.DONE, STATUS.CANCELLED)
                late = TS.to_str(self.span(self.tasks[i])[1]) > TS.to_str(self.span(self.tasks[j])[0])
                col = QColor(error if (late and pre_open) else muted)
                p.setPen(QPen(col, 1.4))
                p.setBrush(Qt.NoBrush)
                x1, y1 = ri.right(), ri.center().y()
                x2, y2 = rj.left(), rj.center().y()
                mid = max(x1 + 8, min(x2 - 8, x1 + 12))
                path = QPainterPath(QPointF(x1, y1))
                path.lineTo(mid, y1)
                path.lineTo(mid, y2)
                path.lineTo(x2 - 1, y2)
                p.drawPath(path)
                p.setBrush(col)
                p.drawPolygon([QPointF(x2, y2), QPointF(x2 - 6, y2 - 3.5), QPointF(x2 - 6, y2 + 3.5)])

        # today line
        xt = self.x_of(now)
        if LABEL_W <= xt <= W:
            p.setPen(QPen(error, 2))
            p.drawLine(QPointF(xt, HEADER_H), QPointF(xt, H))

        # ---- sticky header (date axis + load strip)
        hdr = QColor(c.get("surfaceContainer", "#eeeeee"))
        p.fillRect(QRectF(LABEL_W, 0, W - LABEL_W, top_rows), hdr)
        p.setFont(small)
        d = d_first
        last_month = None
        while d <= d_last:
            x = self.x_of(datetime.combine(d, time()))
            if (d.year, d.month) != last_month and (d.day == 1 or last_month is None):
                p.setPen(text)
                p.drawText(QRectF(max(x, LABEL_W) + 4, 2, 160, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           d.strftime("%B %Y"))
                last_month = (d.year, d.month)
            if self.ppd >= 24:
                lab = f"{d:%a}"[0] + f" {d.day}" if self.ppd < 56 else f"{d:%a %d}"
                p.setPen(error if d == now.date() else muted)
                p.drawText(QRectF(x, 22, self.ppd, 20), Qt.AlignCenter, lab)
            elif d.weekday() == 0:
                p.setPen(muted)
                p.drawText(QRectF(x + 2, 22, 7 * self.ppd, 20), Qt.AlignLeft | Qt.AlignVCenter,
                           f"W{d.isocalendar()[1]} · {d:%d %b}")
            d += timedelta(days=1)
        # load strip: active tasks per day
        loads = self._loads(d_first, d_last)
        top = max(loads.values(), default=0)
        d = d_first
        while d <= d_last:
            n = loads.get(d, 0)
            if n:
                x = self.x_of(datetime.combine(d, time()))
                lc = QColor(primary)
                lc.setAlpha(min(230, 50 + int(180 * n / max(top, 1))))
                p.fillRect(QRectF(x + 1, HEADER_H + 2, self.ppd - 2, LOAD_H - 4), lc)
                if self.ppd >= 24:
                    p.setPen(QColor(c.get("onPrimary", "#ffffff")))
                    p.drawText(QRectF(x, HEADER_H, self.ppd, LOAD_H), Qt.AlignCenter, str(n))
            d += timedelta(days=1)
        p.setPen(QPen(grid, 1))
        p.drawLine(QPointF(LABEL_W, top_rows), QPointF(W, top_rows))

        # ---- sticky label column
        p.fillRect(QRectF(0, 0, LABEL_W, H), hdr)
        p.setPen(muted)
        p.drawText(QRectF(12, 0, LABEL_W - 16, HEADER_H), Qt.AlignVCenter | Qt.AlignLeft, "TASK")
        p.drawText(QRectF(12, HEADER_H, LABEL_W - 16, LOAD_H), Qt.AlignVCenter | Qt.AlignLeft, "tasks per day")
        p.setFont(self.font())
        for i, t in enumerate(self.tasks):
            y = self.row_y(i)
            if y + ROW_H < top_rows or y > H:
                continue
            rr = QRectF(0, y, LABEL_W, ROW_H)
            if t["id"] == self.selected_id:
                sel = QColor(c.get("secondaryContainer", "#e8def8"))
                p.fillRect(rr, sel)
            p.setPen(QColor(STATUS.color(t["status"])))
            p.setBrush(QColor(STATUS.color(t["status"])))
            p.drawEllipse(QPointF(16, y + ROW_H / 2), 4, 4)
            p.setPen(text if t["status"] not in STATUS.INACTIVE else muted)
            p.drawText(rr.adjusted(28, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(NUM.titled(t), Qt.ElideRight, LABEL_W - 40))
        p.setPen(QPen(grid, 1))
        p.drawLine(QPointF(LABEL_W, 0), QPointF(LABEL_W, H))
        if not self.tasks:
            p.setPen(muted)
            p.drawText(QRectF(LABEL_W, top_rows, W - LABEL_W, 80), Qt.AlignCenter,
                       "No tasks yet. Add one above; it appears here as a bar.")

    def _loads(self, d0, d1):
        out = {}
        for t in self.tasks:
            if t["status"] in (STATUS.CANCELLED,):
                continue
            sa, ea = self.span(t)
            d = max(sa.date(), d0)
            last = (ea - timedelta(minutes=1)).date()
            while d <= min(last, d1):
                out[d] = out.get(d, 0) + 1
                d += timedelta(days=1)
        return out

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, e):
        pos = e.position()
        t, mode = self.hit(pos)
        if e.button() == Qt.LeftButton:
            rt = t or self.row_task(pos)
            if rt:
                self.select(rt["id"])
            if t and mode:
                sa, ea = self.span(t)
                self._drag = {"tid": t["id"], "mode": mode, "x0": pos.x(), "sa": sa, "ea": ea, "moved": False}
                self.viewport().setCursor(Qt.ClosedHandCursor if mode == "move" else Qt.SizeHorCursor)
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        pos = e.position()
        d = self._drag
        if d is None:
            t, mode = self.hit(pos)
            self.viewport().setCursor(Qt.SizeHorCursor if mode in ("start", "end")
                                      else Qt.OpenHandCursor if mode == "move" else Qt.ArrowCursor)
            return
        snap = self.snap_minutes()
        minutes = (pos.x() - d["x0"]) / self.ppd * 1440
        minutes = round(minutes / snap) * snap
        delta = timedelta(minutes=minutes)
        sa, ea = d["sa"], d["ea"]
        min_len = timedelta(minutes=min(30, snap))
        if d["mode"] == "move":
            sa, ea = sa + delta, ea + delta
        elif d["mode"] == "end":
            ea = max(sa + min_len, ea + delta)
        else:
            sa = min(ea - min_len, sa + delta)
        if (sa, ea) != (d["sa"], d["ea"]):
            d["moved"] = True
        self._preview = {d["tid"]: (sa, ea)}
        QToolTip.showText(e.globalPosition().toPoint(),
                          f"{TS.span_label(sa, ea)}\n{TS.fmt_length((ea - sa).total_seconds())}", self.viewport())
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        d, self._drag = self._drag, None
        if d is not None:
            span = self._preview.get(d["tid"])
            self._preview = {}
            QToolTip.hideText()
            self.viewport().setCursor(Qt.ArrowCursor)
            if d["moved"] and span and span != (d["sa"], d["ea"]):
                self.spanChanged.emit(d["tid"], span[0], span[1])
            self.viewport().update()
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        t = self.row_task(e.position())
        if t:
            self.select(t["id"])
            self.activated.emit(t["id"])

    def contextMenuEvent(self, e):
        t = self.row_task(QPointF(e.pos()))
        if t:
            self.select(t["id"])
            self.menuRequested.emit(t["id"], e.globalPos())

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            step = 1 if e.angleDelta().y() > 0 else -1
            self.set_zoom(self.zoom + step, e.position().x())
            return
        if e.modifiers() & Qt.ShiftModifier:
            hb = self.horizontalScrollBar()
            hb.setValue(hb.value() - e.angleDelta().y())
            return
        super().wheelEvent(e)

    def select(self, tid):
        if tid != self.selected_id:
            self.selected_id = tid
            self.viewport().update()
            self.selected.emit(tid or "")
        self.ensure_visible(tid)

    def ensure_visible(self, tid):
        ids = [t["id"] for t in self.tasks]
        if tid not in ids:
            return
        i = ids.index(tid)
        vb = self.verticalScrollBar()
        top = HEADER_H + LOAD_H + i * ROW_H
        vis_top = vb.value() + HEADER_H + LOAD_H
        vis_bot = vb.value() + self.viewport().height()
        if top < vis_top:
            vb.setValue(top - HEADER_H - LOAD_H)
        elif top + ROW_H > vis_bot:
            vb.setValue(top + ROW_H - self.viewport().height())

    def keyPressEvent(self, e):
        ids = [t["id"] for t in self.tasks]
        if e.key() in (Qt.Key_Up, Qt.Key_Down) and ids and not e.modifiers():
            i = ids.index(self.selected_id) if self.selected_id in ids else -1
            i = max(0, min(len(ids) - 1, i + (1 if e.key() == Qt.Key_Down else -1)))
            self.select(ids[i])
            return
        if e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.set_zoom(self.zoom + 1)
            return
        if e.key() == Qt.Key_Minus:
            self.set_zoom(self.zoom - 1)
            return
        super().keyPressEvent(e)
