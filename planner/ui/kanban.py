"""Kanban board for a project's tasks: one column per status, drag a card to change its
status or its place in the project's order.

The board only displays and reports; ProjectsPage does the store writes (with undo).
Signals:
    moved(task_id, status, before_id)  dropped into `status` column, above `before_id`
                                       ('' = at the end of that column)
    selected(task_id)                  a card was clicked / focused
    activated(task_id)                 a card was double-clicked (edit)
    menuRequested(task_id, QPoint)     right-click on a card (global position)

Keyboard (handled by ProjectsPage shortcuts): Ctrl+Shift+←/→ moves the selected card to the
previous / next column, so drag and drop isn't the only way.
"""
from datetime import datetime

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QProgressBar, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS
from ..quickparse import HIGH, LOW
from ..utils import fmt_duration, rgba
from .helpers import set_role

MIME = "application/x-zuqongtech-task"
COLUMN_W = 248


class Card(QFrame):
    def __init__(self, board, task, now_s, colors, waits=None):
        super().__init__()
        self.board, self.task = board, task
        self.tid = task["id"]
        self.setObjectName("kanbanCard")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.OpenHandCursor)
        self._press = None
        st = task["status"]
        inactive = st in STATUS.INACTIVE
        late = task["end_at"] <= now_s and not inactive

        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        no = NUM.task_no(task)
        if no:
            top.addWidget(set_role(QLabel(no), "hint"))
        marks = ("★ " if task["pinned"] else "") + ("⚑ " if task["priority"] == HIGH else "") \
            + ("⟳" if task["recurrence"] else "")
        if marks.strip():
            m = QLabel(marks.strip())
            m.setStyleSheet(f"color:{colors['primary']};")
            top.addWidget(m)
        top.addStretch()
        if board.app_focus(self.tid):
            top.addWidget(set_role(QLabel("◉ focus"), "accent"))
        v.addLayout(top)

        title = QLabel(task["title"])
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        f = title.font()
        f.setStrikeOut(st in (STATUS.DONE, STATUS.CANCELLED))
        f.setWeight(f.Weight.DemiBold if task["priority"] == HIGH else f.Weight.Normal)
        title.setFont(f)
        if inactive or task["priority"] == LOW:
            title.setStyleSheet(f"color:{colors['onSurfaceVariant']};")
        v.addWidget(title)

        if waits:
            open_w = [w for w in waits if w["status"] not in (STATUS.DONE, STATUS.CANCELLED)]
            txt = ("⛓ waits for " if open_w else "✓ was waiting for ") + " ".join(
                NUM.task_no(w) or w["title"][:12] for w in waits)
            wl = set_role(QLabel(txt), "danger" if open_w else "hint")
            wl.setWordWrap(True)
            v.addWidget(wl)
        when = QLabel(TS.span_label(task["start_at"], task["end_at"]))
        set_role(when, "danger" if late else "hint")
        v.addWidget(when)

        if task["sub_total"]:
            row = QHBoxLayout()
            row.setSpacing(8)
            bar = QProgressBar()
            bar.setProperty("thin", True)
            bar.setTextVisible(False)
            bar.setMaximum(task["sub_total"])
            bar.setValue(task["sub_done"])
            row.addWidget(bar, 1)
            row.addWidget(set_role(QLabel(f"✓ {task['sub_done']}/{task['sub_total']}"), "hint"))
            v.addLayout(row)
        extras = []
        if task["tags"]:
            extras.append(" ".join("#" + t for t in task["tags"].split()))
        if task["focus_seconds"] >= 60:
            extras.append(f"⏱ {fmt_duration(task['focus_seconds'])}")
        if extras:
            e = set_role(QLabel("   ".join(extras)), "hint")
            e.setWordWrap(True)
            v.addWidget(e)
        tip = TS.span_label(task["start_at"], task["end_at"])
        if task["note"]:
            tip += "\n\n" + task["note"]
        self.setToolTip(tip + "\n\nDrag to another column to change its status.\n"
                              "Ctrl+Shift+←/→ moves it from the keyboard.")
        self.setProperty("late", late)

    def set_selected(self, on):
        self.setProperty("selected", bool(on))
        self.style().unpolish(self)
        self.style().polish(self)

    # ---- mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
            self.board.select(self.tid)
            self.setFocus()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() < QApplication.startDragDistance():
            return
        self._press = None
        mime = QMimeData()
        mime.setData(MIME, self.tid.encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        pm = self.grab()
        drag.setPixmap(pm)
        drag.setHotSpot(e.position().toPoint())
        self.setProperty("dragging", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.board.drag_started()
        drag.exec(Qt.MoveAction)
        # the board may have been rebuilt by the drop; only touch self if still alive
        try:
            self.setProperty("dragging", False)
            self.style().unpolish(self)
            self.style().polish(self)
        except RuntimeError:
            pass
        self.board.drag_finished()

    def mouseReleaseEvent(self, e):
        self._press = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.board.activated.emit(self.tid)

    def contextMenuEvent(self, e):
        self.board.select(self.tid)
        self.board.menuRequested.emit(self.tid, e.globalPos())

    def focusInEvent(self, e):
        self.board.select(self.tid, emit=True)
        super().focusInEvent(e)


class Column(QFrame):
    """One status column. Accepts drops and draws where the card will land."""

    def __init__(self, board, status, color):
        super().__init__()
        self.board, self.status, self.color = board, status, color
        self.setObjectName("kanbanColumn")
        self.setAcceptDrops(True)
        self.setFixedWidth(COLUMN_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.cards = []
        self._drop_index = None
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 12)
        v.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{color};font-size:14px;")
        head.addWidget(dot)
        self.title = QLabel(STATUS.label(status))
        self.title.setStyleSheet("font-weight:600;")
        head.addWidget(self.title)
        head.addStretch()
        self.count = set_role(QLabel("0"), "hint")
        head.addWidget(self.count)
        v.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        v.addLayout(self.body)
        self.empty = set_role(QLabel("Drop tasks here"), "hint")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumHeight(64)
        v.addWidget(self.empty)
        v.addStretch()

    def set_cards(self, cards):
        self.cards = cards
        for c in cards:
            self.body.addWidget(c)
        self.count.setText(str(len(cards)))
        self.empty.setVisible(not cards)

    def set_highlight(self, on):
        self.setProperty("dropTarget", bool(on))
        self.style().unpolish(self)
        self.style().polish(self)

    # ---- drop target
    def _index_at(self, y):
        for i, c in enumerate(self.cards):
            g = c.geometry()
            if y < g.center().y():
                return i
        return len(self.cards)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME):
            e.acceptProposedAction()
            self.set_highlight(True)

    def dragMoveEvent(self, e):
        if not e.mimeData().hasFormat(MIME):
            return
        e.acceptProposedAction()
        idx = self._index_at(e.position().toPoint().y())
        if idx != self._drop_index:
            self._drop_index = idx
            self.update()
        self.board.autoscroll(self.mapTo(self.board.inner, e.position().toPoint()))

    def dragLeaveEvent(self, e):
        self._drop_index = None
        self.set_highlight(False)
        self.update()

    def dropEvent(self, e):
        tid = bytes(e.mimeData().data(MIME)).decode()
        idx = self._index_at(e.position().toPoint().y())
        self._drop_index = None
        self.set_highlight(False)
        # neighbours, skipping the dragged card itself
        ids = [c.tid for c in self.cards if c.tid != tid]
        own = [c.tid for c in self.cards]
        if tid in own and own.index(tid) < idx:
            idx -= 1
        before = ids[idx] if idx < len(ids) else ""
        e.acceptProposedAction()
        # let the drag finish before the board is rebuilt under it
        QTimer.singleShot(0, lambda: self.board.moved.emit(tid, self.status, before))

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._drop_index is None:
            return
        if self.cards:
            if self._drop_index < len(self.cards):
                y = self.cards[self._drop_index].geometry().top() - 5
            else:
                y = self.cards[-1].geometry().bottom() + 4
        else:
            y = self.empty.geometry().center().y()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(self.color), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(14, y, self.width() - 14, y)


class KanbanBoard(QScrollArea):
    moved = Signal(str, str, str)
    selected = Signal(str)
    activated = Signal(str)
    menuRequested = Signal(str, QPoint)

    def __init__(self, focus_check=None):
        """focus_check(task_id) -> bool: whether a focus session is running on the task."""
        super().__init__()
        self._focus_check = focus_check or (lambda tid: False)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("kanban")
        self.inner = QWidget()
        self.inner.setObjectName("kanbanInner")
        self.row = QHBoxLayout(self.inner)
        self.row.setContentsMargins(0, 4, 0, 4)
        self.row.setSpacing(12)
        self.setWidget(self.inner)
        self.columns = {}
        self.cards = {}
        self.selected_id = None
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(30)
        self._scroll_timer.timeout.connect(self._do_scroll)
        self._scroll_v = (0, 0)

    def app_focus(self, tid):
        return self._focus_check(tid)

    def set_tasks(self, tasks, colors, hide_done=False, select=None, deps=None):
        """Rebuild the board. Order within a column follows the project order."""
        keep_scroll = (self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        while self.row.count():
            it = self.row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.columns, self.cards = {}, {}
        now_s = TS.to_str(datetime.now())
        statuses = [s for s in STATUS.ORDER
                    if not (hide_done and s in (STATUS.DONE, STATUS.CANCELLED))]
        by_status = {s: [] for s in STATUS.ORDER}
        for t in tasks:
            by_status[t["status"]].append(t)
        for st in statuses:
            col = Column(self, st, STATUS.color(st))
            by_id = {t["id"]: t for t in tasks}
            cards = [Card(self, t, now_s, colors, [by_id[x] for x in (deps or {}).get(t["id"], []) if x in by_id])
                     for t in by_status[st]]
            for c in cards:
                self.cards[c.tid] = c
            col.set_cards(cards)
            self.columns[st] = col
            self.row.addWidget(col)
        self.row.addStretch()
        sel = select or self.selected_id
        self.selected_id = None
        if sel in self.cards:
            self.select(sel)
        QTimer.singleShot(0, lambda: (self.horizontalScrollBar().setValue(keep_scroll[0]),
                                      self.verticalScrollBar().setValue(keep_scroll[1])))

    def select(self, tid, emit=True):
        if self.selected_id == tid:
            return
        old = self.cards.get(self.selected_id)
        if old is not None:
            old.set_selected(False)
        self.selected_id = tid
        card = self.cards.get(tid)
        if card is not None:
            card.set_selected(True)
            self.ensureWidgetVisible(card, 20, 20)
        if emit:
            self.selected.emit(tid or "")

    def focus_selected(self):
        card = self.cards.get(self.selected_id)
        if card is None and self.cards:
            card = next(iter(self.cards.values()))
        if card is not None:
            card.setFocus()
        else:
            self.setFocus()

    def neighbour_status(self, tid, delta):
        """Status of the column `delta` steps left/right of the task's column, or None."""
        card = self.cards.get(tid)
        if card is None:
            return None
        order = list(self.columns)
        i = order.index(card.task["status"]) + delta
        return order[i] if 0 <= i < len(order) else None

    # ---- drag helpers
    def drag_started(self):
        for col in self.columns.values():
            col.set_highlight(False)

    def drag_finished(self):
        self._scroll_timer.stop()
        for col in self.columns.values():
            col.set_highlight(False)

    def autoscroll(self, pos_in_inner):
        """Scroll when a drag nears the board's edges."""
        p = self.inner.mapTo(self.viewport(), pos_in_inner)
        vw, vh = self.viewport().width(), self.viewport().height()
        edge = 48
        dx = -12 if p.x() < edge else 12 if p.x() > vw - edge else 0
        dy = -12 if p.y() < edge else 12 if p.y() > vh - edge else 0
        self._scroll_v = (dx, dy)
        if dx or dy:
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        else:
            self._scroll_timer.stop()

    def _do_scroll(self):
        dx, dy = self._scroll_v
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + dx)
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + dy)
