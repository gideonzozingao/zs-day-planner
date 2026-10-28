"""Projects page: a list of projects on the left, the selected project on the right.

Hierarchy shown: project -> tasks -> subtasks (a tree). Projects and tasks each have a start
and end date-time; project tasks also show in the day view of each day they cover.

Keyboard (tree focused): Space toggle · Enter/F2 edit · Insert add subtask · Delete delete ·
Alt+Up/Down reorder tasks · Ctrl+D duplicate · Ctrl+H history.
"""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar, QPushButton,
    QSizePolicy, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..data.schema import PROJECT_STATUS_NAMES, PROJECT_STATUSES
from ..quickparse import HIGH, LOW, describe, parse
from .. import numbering as NUM
from .. import status as STATUS
from .. import timespan as TS
from ..theme.icons import status_dot
from .gantt import GanttView
from .kanban import KanbanBoard
from .stats_dialog import StatusBar
from ..utils import fmt_duration, rgba
from .dialogs import DatePickerDialog
from .helpers import set_kind, set_role
from .motion import crossfade
from .project_dialog import ProjectDialog, dot_icon

TASK, SUB = "task", "sub"
FILTERS = (("open", "Open"), ("done", "Done"), ("all", "All"))


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def _left(delta: timedelta) -> str:
    secs = delta.total_seconds()
    if secs >= 86400:
        return _plural(int(secs // 86400), "day")
    if secs >= 3600:
        return _plural(int(secs // 3600), "hour")
    return _plural(max(1, int(secs // 60)), "minute")


def timing(p, now: datetime):
    """-> (text, role) describing where the project is against its start and finish."""
    start, end = TS.to_dt(p["start_at"]), TS.to_dt(p["end_at"])
    if p["status"] == "done":
        when = (p["completed_at"] or "")[:10]
        return (f"Completed {date.fromisoformat(when):%d %b %Y}" if when else "Completed"), "muted"
    if p["status"] == "on_hold":
        return "On hold", "muted"
    if now < start:
        return f"Starts in {_left(start - now)}", "muted"
    if now >= end:
        return f"Overdue by {_left(now - end)}", "danger"
    left = end - now
    return f"{_left(left)} left", "danger" if left <= timedelta(days=3) else "accent"


def time_used(p, now: datetime):
    """Fraction of the start→finish window that has passed."""
    start, end = TS.to_dt(p["start_at"]), TS.to_dt(p["end_at"])
    span = max(60.0, (end - start).total_seconds())
    return min(1.0, max(0.0, (now - start).total_seconds() / span))


def date_range(p):
    start, end = TS.to_dt(p["start_at"]), TS.to_dt(p["end_at"])
    return f"{start:%a %d %b %Y %H:%M}  →  {end:%a %d %b %Y %H:%M}"


def tint_bar(bar, color, thin=True):
    """Progress bar chunk in the project's colour."""
    if color:
        r = 2 if thin else 4
        bar.setStyleSheet(f"QProgressBar::chunk{{background:{color};border-radius:{r}px;}}"
                          f"QProgressBar{{background:{rgba(color, 0.2)};}}")


class ProjectCard(QWidget):
    """One row in the project list."""

    def __init__(self, p, summary, now):
        super().__init__()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 10, 10, 10)
        row.setSpacing(12)
        strip = QFrame()
        strip.setFixedWidth(5)
        strip.setStyleSheet(f"background:{p['color'] or '#888'};border-radius:2px;")
        row.addWidget(strip)
        col = QVBoxLayout()
        col.setSpacing(4)
        name = QLabel(p["name"])
        name.setTextFormat(Qt.PlainText)
        name.setStyleSheet("font-weight:600;font-size:15px;")
        col.addWidget(name)
        text, role = timing(p, now)
        line = set_role(QLabel(text if p["status"] != "planned" else f"Planned · {text}"),
                        role if role != "accent" else "muted")
        col.addWidget(line)
        bar = QProgressBar()
        bar.setProperty("thin", True)
        bar.setTextVisible(False)
        bar.setMaximum(1000)
        bar.setValue(int(summary["progress"] * 1000))
        tint_bar(bar, p["color"])
        col.addWidget(bar)
        count = set_role(QLabel(f"{summary['done']}/{summary['tasks']} tasks  ·  "
                                f"{round(summary['progress'] * 100)}%"), "hint")
        col.addWidget(count)
        row.addLayout(col, 1)


class ProjectsPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host                      # MainWindow
        self.store = host.store
        self.current_id = None
        self.filter = "open"
        self._building = False

        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 20, 16)
        v.setSpacing(14)

        # ---- header
        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(set_role(QLabel("Projects"), "headline"))
        self.sub_lbl = set_role(QLabel(), "muted")
        titles.addWidget(self.sub_lbl)
        top.addLayout(titles)
        top.addStretch()
        self.filter_btns = {}
        for key, label in FILTERS:
            b = set_kind(QPushButton(label), "chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_filter(k))
            self.filter_btns[key] = b
            top.addWidget(b)
        top.addSpacing(8)
        new = set_kind(QPushButton("  New project"), "tonal")
        new.setToolTip("New project (Ctrl+Shift+N)")
        new.setCursor(Qt.PointingHandCursor)
        new.clicked.connect(self.new_project)
        host._icons.append((new, "add", "onSecondaryContainer", None))
        top.addWidget(new)
        v.addLayout(top)

        # ---- body
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)

        self.list = QListWidget()
        self.list.setObjectName("projectList")
        self.list.setMinimumWidth(240)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.currentItemChanged.connect(self._list_changed)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit_project())
        split.addWidget(self.list)

        self.panel = QFrame()
        self.panel.setObjectName("panel")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(20, 16, 16, 12)
        pl.setSpacing(10)
        self.detail = QWidget()
        self._build_detail(QVBoxLayout(self.detail))
        self.empty = set_role(QLabel(), "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        pl.addWidget(self.detail, 1)
        pl.addWidget(self.empty, 1)
        split.addWidget(self.panel)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([290, 700])
        v.addWidget(split, 1)

    # ------------------------------------------------------------------ builders
    def _build_detail(self, lay):
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.dot = QLabel()
        head.addWidget(self.dot)
        self.name_lbl = set_role(QLabel(), "title")
        self.name_lbl.setTextFormat(Qt.PlainText)
        self.name_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.addWidget(self.name_lbl, 1)
        self.status_btn = set_kind(QPushButton(), "chip")
        self.status_btn.setCursor(Qt.PointingHandCursor)
        self.status_btn.setToolTip("Project status")
        head.addWidget(self.status_btn)
        h = self.host
        head.addWidget(h._icon_btn("chart", "Project statistics (Ctrl+Shift+S)", self.show_stats))
        head.addWidget(h._icon_btn("edit", "Edit project (dates, colour, status)", self.edit_project))
        head.addWidget(h._icon_btn("delete", "Delete project", self.delete_project))
        lay.addLayout(head)

        self.range_lbl = set_role(QLabel(), "muted")
        self.timing_lbl = QLabel()
        dates = QHBoxLayout()
        dates.addWidget(self.range_lbl)
        dates.addSpacing(10)
        dates.addWidget(self.timing_lbl)
        dates.addStretch()
        lay.addLayout(dates)
        self.desc_lbl = set_role(QLabel(), "muted")
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setTextFormat(Qt.PlainText)
        lay.addWidget(self.desc_lbl)

        bars = QHBoxLayout()
        bars.setSpacing(18)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.progress_lbl = set_role(QLabel(), "label")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximum(1000)
        col.addWidget(self.progress_lbl)
        col.addWidget(self.progress)
        bars.addLayout(col, 3)
        col2 = QVBoxLayout()
        col2.setSpacing(4)
        self.time_lbl = set_role(QLabel(), "label")
        self.time_bar = QProgressBar()
        self.time_bar.setProperty("thin", True)
        self.time_bar.setTextVisible(False)
        self.time_bar.setMaximum(1000)
        self.time_bar.setToolTip("How much of the start → finish window has passed.\n"
                                 "If this runs ahead of progress, the project is behind.")
        col2.addWidget(self.time_lbl)
        col2.addWidget(self.time_bar)
        self.time_box = QWidget()
        self.time_box.setLayout(col2)
        bars.addWidget(self.time_box, 2)
        lay.addLayout(bars)
        self.stats_lbl = set_role(QLabel(), "hint")
        lay.addWidget(self.stats_lbl)
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self.status_bar = StatusBar({}, height=8)
        self.status_bar.setMinimumWidth(120)
        self.status_bar.setToolTip("Tasks by status")
        self.status_legend = QLabel()
        self.status_legend.setTextFormat(Qt.RichText)
        status_row.addWidget(self.status_bar, 2)
        status_row.addWidget(self.status_legend, 3)
        lay.addLayout(status_row)

        add_row = QHBoxLayout()
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Add a task to this project, e.g.  Write API spec fri #api !high   (Enter)")
        self.quick.returnPressed.connect(self.quick_add)
        self.quick.textChanged.connect(self._quick_preview)
        add_row.addWidget(self.quick, 1)
        self.hide_done = QCheckBox("Hide completed")
        self.hide_done.toggled.connect(lambda *_: self.refresh())
        add_row.addSpacing(8)
        add_row.addWidget(self.hide_done)
        add_row.addSpacing(12)
        self.view_btns = {}
        for key, label, tip in (("list", "List", "Tasks and subtasks as a tree (Ctrl+Shift+L)"),
                                ("board", "Board", "Kanban board: drag tasks between statuses (Ctrl+Shift+K)"),
                                ("timeline", "Timeline", "Gantt timeline: drag bars to reschedule (Ctrl+Shift+T)")):
            b = set_kind(QPushButton(label), "chip")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.set_view(k))
            self.view_btns[key] = b
            add_row.addWidget(b)
        self.view = self.store.settings.get("project_view", "list")
        if self.view not in self.view_btns:
            self.view = "list"
        lay.addLayout(add_row)
        self.quick_hint = set_role(QLabel(), "hint")
        self.quick_hint.setContentsMargins(14, 0, 0, 0)
        self.quick_hint.hide()
        lay.addWidget(self.quick_hint)

        t = QTreeWidget()
        t.setColumnCount(4)
        t.setHeaderLabels(["Task", "Status", "When", "Progress"])
        hh = t.header()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        t.setFrameShape(QFrame.NoFrame)
        t.setUniformRowHeights(False)
        t.setIndentation(28)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.itemChanged.connect(self._item_changed)
        t.itemDoubleClicked.connect(self._double_clicked)
        t.itemExpanded.connect(lambda it: self._remember_expanded(it, True))
        t.itemCollapsed.connect(lambda it: self._remember_expanded(it, False))
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(lambda pos: self._tree_menu(t.viewport().mapToGlobal(pos),
                                                                         t.itemAt(pos)))
        t.itemDelegate().closeEditor.connect(lambda *_: QTimer.singleShot(0, self.refresh))
        self.tree = t
        self._collapsed = set()
        lay.addWidget(t, 1)
        self.board = KanbanBoard(focus_check=lambda tid: self.host.app.focus.is_on(tid))
        self.board.moved.connect(self._board_moved)
        self.board.activated.connect(lambda tid: self.host.edit_task())
        self.board.menuRequested.connect(lambda tid, pos: self._tree_menu(pos, None))
        lay.addWidget(self.board, 1)
        # timeline (Gantt): zoom toolbar + chart
        self.gantt_bar = QWidget()
        gb = QHBoxLayout(self.gantt_bar)
        gb.setContentsMargins(0, 0, 0, 0)
        gb.setSpacing(6)
        self.gantt_hint = set_role(QLabel("Drag a bar to move a task, drag its ends to change start or end. "
                                          "Ctrl+wheel zooms."), "hint")
        gb.addWidget(self.gantt_hint, 1)
        for label, tip, fn in (("−", "Zoom out (−)", lambda: self.gantt.set_zoom(self.gantt.zoom - 1)),
                               ("+", "Zoom in (+)", lambda: self.gantt.set_zoom(self.gantt.zoom + 1)),
                               ("Fit", "Fit the project's start → finish", lambda: self.gantt.fit()),
                               ("Today", "Scroll to today", lambda: self.gantt.scroll_to(datetime.now()))):
            b = set_kind(QPushButton(label), "chip")
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            gb.addWidget(b)
        lay.addWidget(self.gantt_bar)
        self.gantt = GanttView()
        self.gantt.spanChanged.connect(self._span_changed)
        self.gantt.activated.connect(lambda tid: self.host.edit_task())
        self.gantt.menuRequested.connect(lambda tid, pos: self._tree_menu(pos, None))
        lay.addWidget(self.gantt, 1)
        self._gantt_fitted = set()
        self.tree_empty = set_role(QLabel("No tasks yet. Type one above and press Enter,\n"
                                          "or press Ctrl+N to set its start and end."), "muted")
        self.tree_empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.tree_empty, 1)

    # ------------------------------------------------------------------ public
    def project(self):
        return self.store.project(self.current_id)

    def show_project(self, pid, select_task=None):
        p = self.store.project(pid)
        if p is None:
            return
        if p["status"] == "done" and self.filter == "open":
            self.filter = "all"
        self.current_id = pid
        self.refresh(select=select_task)

    def selected(self):
        """-> (kind, task_id, subtask_id) for the selected tree row or board card,
        or (None, None, None)."""
        if self.view in ("board", "timeline"):
            tid = self.board.selected_id if self.view == "board" else self.gantt.selected_id
            return (TASK, tid, None) if tid else (None, None, None)
        it = self.tree.currentItem()
        data = it.data(0, Qt.UserRole) if it else None
        if not data:
            return None, None, None
        return data[0], data[1], (data[2] if len(data) > 2 else None)

    def selected_task_id(self):
        return self.selected()[1]

    def show_stats(self):
        self.host.app.show_stats(project_id=self.current_id)

    def set_view(self, key):
        """Switch the project's tasks between the tree (list) and the Kanban board."""
        if key not in self.view_btns:
            return
        sel = self.selected_task_id()
        self.view = key
        self.store.settings["project_view"] = key
        self.store.save_settings()
        self.refresh(select=sel)
        self.focus_tasks()

    def focus_tasks(self):
        if self.view == "board":
            self.board.focus_selected()
        elif self.view == "timeline":
            self.gantt.setFocus()
        else:
            self.tree.setFocus()

    def set_filter(self, key):
        self.filter = key
        self.refresh()

    # ------------------------------------------------------------------ refresh
    def refresh(self, select=None):
        today = datetime.now()
        all_projects = self.store.projects()
        n_open = sum(1 for p in all_projects if p["status"] != "done")
        n_done = len(all_projects) - n_open
        self.sub_lbl.setText(f"{n_open} open · {n_done} done" if all_projects else "Group tasks into projects")
        for key, b in self.filter_btns.items():
            b.setChecked(key == self.filter)
        for key, b in self.view_btns.items():
            b.setChecked(key == self.view)
        shown = [p for p in all_projects
                 if self.filter == "all" or (p["status"] == "done") == (self.filter == "done")]

        ids = [p["id"] for p in shown]
        if self.current_id not in ids:
            self.current_id = ids[0] if ids else None

        self._building = True
        self.list.clear()
        for p in shown:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, p["id"])
            card = ProjectCard(p, self.store.project_summary(p["id"]), today)
            item.setSizeHint(QSize(200, card.sizeHint().height() + 4))
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
            if p["id"] == self.current_id:
                self.list.setCurrentItem(item)
        self._building = False

        p = self.project()
        self.detail.setVisible(p is not None)
        self.empty.setVisible(p is None)
        if p is None:
            self.empty.setText("No projects yet.\nCreate one with New project (Ctrl+Shift+N)."
                               if not all_projects else "No projects in this view.")
            return
        self._fill_header(p, today)
        self._fill_tree(p, today, select)

    def _fill_header(self, p, now):
        self.dot.setPixmap(dot_icon(p["color"], 18).pixmap(18, 18))
        self.name_lbl.setText(p["name"])
        self.status_btn.setText(PROJECT_STATUS_NAMES[p["status"]] + "  ▾")
        menu = QMenu(self.status_btn)
        for s in PROJECT_STATUSES:
            a = QAction(PROJECT_STATUS_NAMES[s], menu)
            a.setCheckable(True)
            a.setChecked(s == p["status"])
            a.triggered.connect(lambda _=False, s=s: self.set_status(s))
            menu.addAction(a)
        self.status_btn.setMenu(menu)
        self.range_lbl.setText(date_range(p))
        text, role = timing(p, now)
        set_role(self.timing_lbl, role)
        self.timing_lbl.setText(text)
        self.timing_lbl.style().unpolish(self.timing_lbl)
        self.timing_lbl.style().polish(self.timing_lbl)
        self.desc_lbl.setText(p["description"])
        self.desc_lbl.setVisible(bool(p["description"]))

        s = self.store.project_summary(p["id"])
        pct = round(s["progress"] * 100)
        self.progress.setValue(int(s["progress"] * 1000))
        tint_bar(self.progress, p["color"], thin=False)
        self.progress_lbl.setText(f"PROGRESS  {pct}%")
        used = time_used(p, now)
        self.time_box.setVisible(p["status"] != "done")
        if True:
            self.time_bar.setValue(int(used * 1000))
            behind = used - s["progress"] > 0.15 and s["tasks"]
            self.time_lbl.setText(f"TIME USED  {round(used * 100)}%" + ("  ·  BEHIND" if behind else ""))
            set_role(self.time_lbl, "danger" if behind else "label")
            self.time_lbl.style().unpolish(self.time_lbl)
            self.time_lbl.style().polish(self.time_lbl)
        bits = [f"{s['done']} of {_plural(s['tasks'], 'task')} done"]
        if s["sub_total"]:
            bits.append(f"{s['sub_done']}/{s['sub_total']} subtasks")
        if s["overdue"]:
            bits.append(f"{s['overdue']} overdue")
        if s["focus_seconds"] >= 60:
            bits.append(f"{fmt_duration(s['focus_seconds'])} focused")
        self.stats_lbl.setText("   ·   ".join(bits))
        counts = s["counts"]
        self.status_bar.set_counts(counts)
        self.status_legend.setText("&nbsp;&nbsp;&nbsp;".join(
            f"<span style='color:{STATUS.color(st)}'>●</span> {counts[st]} {STATUS.label(st).lower()}"
            for st in STATUS.ORDER if counts[st]) or "No tasks yet")

    def _fill_gantt(self, p, select):
        tasks = self.store.project_tasks(p["id"])
        if self.hide_done.isChecked():
            tasks = [t for t in tasks if t["status"] not in (STATUS.DONE, STATUS.CANCELLED)]
        self.tree.hide()
        self.board.hide()
        self.tree_empty.hide()
        self.gantt_bar.show()
        self.gantt.show()
        self.gantt.set_tasks(p, tasks, self.host.theme.c, select=select)
        if p["id"] not in self._gantt_fitted:          # first time this project is shown: fit it
            self._gantt_fitted.add(p["id"])
            QTimer.singleShot(0, self.gantt.fit)

    def _span_changed(self, tid, sa, ea):
        t = self.store.find(tid)
        if not t:
            return
        old = (t["start_at"], t["end_at"])
        self.store.update(tid, start_at=sa, end_at=ea)

        def undo():
            self.store.update(tid, start_at=old[0], end_at=old[1])
            return tid
        self.host._push_undo("reschedule", undo)
        self.refresh(select=tid)
        p = self.project()
        warn = ""
        if p and TS.to_str(ea) > p["end_at"]:
            warn = "  ·  past the project's finish"
        self.host.snack(f"{NUM.titled(t)[:32]}: {TS.span_label(sa, ea)}{warn}", "Undo", self.host.undo)

    def shift_days(self, days):
        """Timeline keyboard move: shift the selected task by whole days."""
        tid = self.gantt.selected_id
        t = self.store.find(tid) if tid else None
        if t:
            delta = timedelta(days=days)
            self._span_changed(tid, TS.to_dt(t["start_at"]) + delta, TS.to_dt(t["end_at"]) + delta)

    def _fill_board(self, p, select):
        tasks = self.store.project_tasks(p["id"])
        self.board.set_tasks(tasks, self.host.theme.c, hide_done=self.hide_done.isChecked(),
                             select=select or self.board.selected_id)
        self.tree.hide()
        self.board.setVisible(bool(tasks))
        self.tree_empty.setVisible(not tasks)
        self.tree_empty.setText("No tasks yet. Type one above and press Enter,\n"
                                "or press Ctrl+N to set its start and end.")

    def _board_moved(self, tid, status, before):
        """A card was dropped: change its status and/or its place in the project order."""
        task = self.store.find(tid)
        if not task:
            return
        old_status = task["status"]
        old_order = self.store.project_order(task["project_id"])
        col = self.board.columns.get(status)
        others = [c.tid for c in col.cards if c.tid != tid] if col else []
        if before:
            self.store.place_in_project(tid, before_id=before)
        elif others:
            self.store.place_in_project(tid, after_id=others[-1])
        if status != old_status:
            self.store.set_status(tid, status)
        new_order = self.store.project_order(task["project_id"])
        if status == old_status and new_order == old_order:
            return

        def undo(pid=task["project_id"]):
            self.store.set_status(tid, old_status)
            self.store.set_project_order(pid, old_order)
            return tid
        self.host._push_undo("move", undo)
        self.refresh(select=tid)
        self.board.focus_selected()
        if status != old_status:
            self.host.snack(f"{NUM.titled(task)[:40]} → {STATUS.label(status)}", "Undo", self.host.undo)
            self.host.task_done_changed(tid)

    def move_card(self, delta):
        """Keyboard alternative to dragging: on the board, move the selected card one column
        left/right; on the timeline, move the selected task a day earlier/later."""
        if self.view == "timeline":
            return self.shift_days(delta)
        if self.view != "board" or not self.board.selected_id:
            return
        st = self.board.neighbour_status(self.board.selected_id, delta)
        if st:
            self._board_moved(self.board.selected_id, st, "")

    def _fill_tree(self, p, now, select):
        if self.view == "timeline":
            return self._fill_gantt(p, select)
        self.gantt_bar.hide()
        self.gantt.hide()
        if self.view == "board":
            return self._fill_board(p, select)
        self.board.hide()
        c = self.host.theme.c
        keep = select or self.selected_task_id()
        keep_sub = None if select else self.selected()[2]
        tasks = self.store.project_tasks(p["id"])
        subs = self.store.subtasks_for_project(p["id"])
        if self.hide_done.isChecked():
            tasks = [t for t in tasks if not t["done"]]
        pstart, pend = p["start_at"], p["end_at"]
        now_s = TS.to_str(now)
        t = self.tree
        t.blockSignals(True)
        t.clear()
        current = None
        for task in tasks:
            it = QTreeWidgetItem()
            it.setData(0, Qt.UserRole, (TASK, task["id"]))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if task["done"] else Qt.Unchecked)
            prefix = ("◉ " if self.host.app.focus.is_on(task["id"]) else "") + ("★ " if task["pinned"] else "") \
                + ("⚑ " if task["priority"] == HIGH else "") + ("⟳ " if task["recurrence"] else "")
            no = NUM.task_no(task)
            it.setText(0, (f"{no}   " if no else "") + prefix + task["title"])
            st = task["status"]
            it.setText(1, STATUS.label(st))
            it.setIcon(1, status_dot(STATUS.color(st)))
            it.setText(2, TS.span_label(task["start_at"], task["end_at"], today=now.date()))
            prog = []
            if task["sub_total"]:
                prog.append(f"✓ {task['sub_done']}/{task['sub_total']}")
            if task["focus_seconds"] >= 60:
                prog.append(f"⏱ {fmt_duration(task['focus_seconds'])}")
            it.setText(3, "   ".join(prog))
            length = (TS.to_dt(task["end_at"]) - TS.to_dt(task["start_at"])).total_seconds()
            tip = f"{TS.span_label(task['start_at'], task['end_at'])}   ({TS.fmt_length(length)})"
            if task["note"]:
                tip += "\n\n" + task["note"]
            inactive = st in STATUS.INACTIVE
            outside = not inactive and (task["start_at"] < pstart or task["end_at"] > pend)
            if outside:
                tip += "\n\nOutside the project's start → finish"
            for col in range(4):
                it.setToolTip(col, tip)
            colour = None
            if inactive:
                colour = c["outline"]
            elif task["end_at"] <= now_s:
                colour = c["error"]
            elif task["priority"] == LOW:
                colour = c["onSurfaceVariant"]
            font = it.font(0)
            font.setStrikeOut(st in (STATUS.DONE, STATUS.CANCELLED))
            for col in range(4):
                if col != 1:                      # the status cell keeps its colour, unstruck
                    it.setFont(col, font)
                    if colour:
                        it.setForeground(col, QBrush(QColor(colour)))
            it.setForeground(1, QBrush(QColor(STATUS.color(st))))
            if outside:
                it.setForeground(2, QBrush(QColor(c["error"])))
            t.addTopLevelItem(it)
            for s in subs.get(task["id"], []):
                ch = QTreeWidgetItem(it)
                ch.setData(0, Qt.UserRole, (SUB, task["id"], s["id"]))
                ch.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
                ch.setCheckState(0, Qt.Checked if s["done"] else Qt.Unchecked)
                ch.setText(0, NUM.sub_titled(task, s))
                ch.setData(0, Qt.UserRole + 1, s["title"])        # plain title, for in-place rename
                f = ch.font(0)
                f.setStrikeOut(s["done"])
                ch.setFont(0, f)
                if s["done"] or task["done"]:
                    ch.setForeground(0, QBrush(QColor(c["outline"])))
                if keep_sub and s["id"] == keep_sub:
                    current = ch
            it.setExpanded(task["id"] not in self._collapsed)
            if task["id"] == keep and current is None:
                current = it
        if current is not None:
            t.setCurrentItem(current)
        t.blockSignals(False)
        t.setVisible(bool(tasks))
        self.tree_empty.setVisible(not tasks)

        if not tasks and self.hide_done.isChecked() and self.store.project_tasks(p["id"]):
            self.tree_empty.setText("Every task in this project is done.")
        else:
            self.tree_empty.setText("No tasks yet. Type one above and press Enter,\n"
                                    "or press Ctrl+N for the full task dialog.")

    def _remember_expanded(self, item, expanded):
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != TASK:
            return
        if expanded:
            self._collapsed.discard(data[1])
        else:
            self._collapsed.add(data[1])

    # ------------------------------------------------------------------ list
    def _list_changed(self, cur, _prev):
        if self._building or cur is None:
            return
        pid = cur.data(Qt.UserRole)
        if pid != self.current_id:
            def apply():
                self.current_id = pid
                self.refresh()
            crossfade(self.panel, apply, 180)

    def _list_menu(self, pos):
        item = self.list.itemAt(pos)
        menu = QMenu(self)
        act = self.host._menu_action
        if item:
            self.list.setCurrentItem(item)
            act(menu, "Edit project…", self.edit_project, "edit")
            act(menu, "Renumber tasks…", self.renumber, "checklist")
            sm = menu.addMenu("Status")
            p = self.project()
            for s in PROJECT_STATUSES:
                a = act(sm, PROJECT_STATUS_NAMES[s], lambda _=False, s=s: self.set_status(s))
                a.setCheckable(True)
                a.setChecked(p is not None and p["status"] == s)
            menu.addSeparator()
            act(menu, "Delete project…", self.delete_project, "delete")
            menu.addSeparator()
        act(menu, "New project…", self.new_project, "add", "Ctrl+Shift+N")
        menu.exec(self.list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ project actions
    def new_project(self):
        used = [p["color"] for p in self.store.projects(include_done=False)]
        dlg = ProjectDialog(self.host, used_colors=used, workday=self.store.workday())
        if dlg.exec():
            v = dlg.values()
            p = self.store.add_project(**v)
            self.filter = "done" if p["status"] == "done" else ("open" if self.filter == "done" else self.filter)
            self.current_id = p["id"]
            self.refresh()
            self.quick.setFocus()
            self.host.snack(f"Project “{p['name']}” created. Add its tasks below")
            return p
        return None

    def edit_project(self):
        p = self.project()
        if not p:
            return
        dlg = ProjectDialog(self.host, p, workday=self.store.workday())
        if dlg.exec():
            before = dict(p)
            self.store.update_project(p["id"], **dlg.values())
            self.host._push_undo("project edit", lambda b=before: self._restore_fields(b))
            self.refresh()

    def _restore_fields(self, before):
        self.store.update_project(before["id"], **{k: before[k] for k in
                                                   ("name", "description", "color", "start_at",
                                                    "end_at", "status")})
        self.current_id = before["id"]

    def set_status(self, status):
        p = self.project()
        if not p or p["status"] == status:
            return
        old = p["status"]
        self.store.update_project(p["id"], status=status)
        self.host._push_undo("status change", lambda pid=p["id"], s=old: self.store.update_project(pid, status=s))
        if status == "done" and self.filter == "open":
            self.filter = "all"
        self.refresh()
        s = self.store.project_summary(p["id"])
        if status == "done" and s["done"] < s["tasks"]:
            self.host.snack(f"Marked done with {s['tasks'] - s['done']} open task(s) left", "Undo", self.host.undo)
        else:
            self.host.snack(f"“{p['name']}” is now {PROJECT_STATUS_NAMES[status].lower()}", "Undo", self.host.undo)

    def delete_project(self):
        p = self.project()
        if not p:
            return
        n = len(self.store.project_tasks(p["id"]))
        box = QMessageBox(self.host)
        box.setWindowTitle("Delete project")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"Delete the project “{p['name']}”?")
        keep = delete_all = None
        if n:
            box.setInformativeText(f"It has {_plural(n, 'task')}. Keep them as ordinary tasks "
                                   f"(on their own dates), or delete them too?")
            keep = box.addButton("Keep tasks", QMessageBox.AcceptRole)
            delete_all = box.addButton("Delete tasks too", QMessageBox.DestructiveRole)
        else:
            keep = box.addButton("Delete", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (keep, delete_all) or clicked is None:
            return
        with_tasks = clicked is delete_all
        snap = self.store.delete_project(p["id"], with_tasks=with_tasks)

        def undo(s=snap):
            self.store.restore_project(s)
            self.current_id = s["project"]["id"]
        self.host._push_undo("delete project", undo)
        self.current_id = None
        self.refresh()
        self.host.snack(f"Deleted project “{p['name']}”", "Undo", self.host.undo)

    # ------------------------------------------------------------------ task actions
    def _quick_preview(self, text):
        if not text.strip():
            self.quick_hint.hide()
            return
        pr = parse(text, date.today())
        if not pr.title:
            self.quick_hint.setText("→  add a title")
        else:
            day = pr.date or self._default_day()
            self.quick_hint.setText("→  " + describe(pr, day, date.today(), self.store.workday()))
        self.quick_hint.show()

    def _default_day(self):
        """Quick-added project tasks with no date go on today, or the project's first day."""
        p = self.project()
        start = TS.to_dt(p["start_at"]).date() if p else date.today()
        return max(date.today(), start)

    def quick_add(self):
        p = self.project()
        pr = parse(self.quick.text(), date.today())
        if not p or not pr.title:
            return
        day = pr.date or self._default_day()
        t = self.store.add(day, pr.title, pr.start, pr.end, priority=pr.priority, tags=" ".join(pr.tags),
                           pinned=pr.pinned, project_id=p["id"])
        self.quick.clear()
        self.refresh(select=t["id"])

    def _double_clicked(self, item, column):
        kind, tid, sid = self.selected()
        if kind == SUB:
            self._edit_sub(item)
        elif kind == TASK:
            self.host.edit_task()

    def _edit_sub(self, item):
        """Rename a subtask in place: the editor shows just its title, not the 9.2 label."""
        self.tree.blockSignals(True)
        item.setText(0, item.data(0, Qt.UserRole + 1) or item.text(0))
        self.tree.blockSignals(False)
        self.tree.editItem(item, 0)

    def _item_changed(self, item, column):
        data = item.data(0, Qt.UserRole)
        if not data or column != 0:
            return
        done = item.checkState(0) == Qt.Checked
        if data[0] == TASK:
            task = self.store.find(data[1])
            if task and task["done"] != done:
                self.store.update(data[1], done=done)
                QTimer.singleShot(0, lambda: (self.refresh(select=data[1]), self.host.task_done_changed(data[1])))
        else:
            tid, sid = data[1], data[2]
            subs = {s["id"]: s for s in self.store.subtasks(tid)}
            s = subs.get(sid)
            if s is None:
                return
            if s["done"] != done:
                QTimer.singleShot(0, lambda: self.host.toggle_subtask(tid, sid, done))
            elif item.text(0).strip() != s["title"]:
                if item.text(0).strip():
                    self.store.rename_subtask(sid, item.text(0))
                QTimer.singleShot(0, lambda: self.refresh())

    def toggle_current(self):
        kind, tid, sid = self.selected()
        if kind == SUB:
            s = next((x for x in self.store.subtasks(tid) if x["id"] == sid), None)
            if s:
                self.host.toggle_subtask(tid, sid, not s["done"])
        elif kind == TASK:
            self.host.toggle_selected()

    def edit_current(self):
        kind, tid, sid = self.selected()
        if kind == SUB:
            self._edit_sub(self.tree.currentItem())
        elif kind == TASK:
            self.host.edit_task()

    def renumber(self):
        p = self.project()
        if not p:
            return
        ans = QMessageBox.question(
            self.host, "Renumber tasks",
            f"Number the tasks in “{p['name']}” #1, #2, … in their current order, and each task's "
            f"subtasks 1, 2, … in checklist order?\n\nNumbers you've shared elsewhere will change. "
            f"Ctrl+Z undoes this.")
        if ans != QMessageBox.Yes:
            return
        snap = self.store.renumber_project(p["id"])
        self.host._push_undo("renumber", lambda s=snap: self.store.restore_numbers(s))
        self.refresh()
        self.host.snack(f"Renumbered {len(snap['tasks'])} task(s)", "Undo", self.host.undo)

    def add_subtask(self):
        kind, tid, _ = self.selected()
        if not tid:
            self.host.snack("Select a task to add a subtask to")
            return
        task = self.store.find(tid)
        title, ok = QInputDialog.getText(self.host, "Add subtask", f"Subtask of “{task['title']}”:")
        if ok and title.strip():
            sid = self.store.add_subtask(tid, title)
            self._collapsed.discard(tid)
            if task["done"]:
                self.store.update(tid, done=False)          # new open work reopens the task
            self.host._push_undo("add subtask", lambda s=sid: (self.store.delete_subtask(s), tid)[1])
            self.refresh(select=tid)

    def delete_current(self):
        kind, tid, sid = self.selected()
        if kind == SUB:
            snap = self.store.delete_subtask(sid)
            self.host._push_undo("delete subtask", lambda s=snap: (self.store.restore_subtask(s), s["task_id"])[1])
            self.refresh(select=tid)
            self.host.snack(f"Deleted subtask “{snap['title']}”", "Undo", self.host.undo)
        elif kind == TASK:
            item = self.tree.currentItem()
            row = self.tree.indexOfTopLevelItem(item)
            task = self.store.find(tid)
            snapshot = self.store.delete(tid)
            self.host._push_undo("delete", lambda t=snapshot: (self.store.restore(t), t["id"])[1])
            if self.view == "board":
                self.board.selected_id = None
            elif self.view == "timeline":
                self.gantt.selected_id = None
            self.refresh()
            n = self.tree.topLevelItemCount()
            if n and self.view == "list":
                self.tree.setCurrentItem(self.tree.topLevelItem(min(max(row, 0), n - 1)))
            self.host.snack(f"Deleted “{task['title']}”", "Undo", self.host.undo)

    def move_current(self, delta):
        kind, tid, _ = self.selected()
        if kind == TASK and self.store.move_in_project(tid, delta):
            self.refresh(select=tid)
            self.tree.setFocus()

    def schedule(self, day):
        """Move the task to start on `day` (same times, same length)."""
        kind, tid, _ = self.selected()
        task = self.store.find(tid)
        if not task or task["date"] == day.isoformat():
            return
        old = task["date"]
        self.store.update(tid, date=day)
        self.host._push_undo("move", lambda: (self.store.update(tid, date=old), tid)[1])
        self.refresh(select=tid)
        self.host.snack(f"Now starts {day:%a %d %b}", "Undo", self.host.undo)

    def schedule_picked(self):
        task = self.store.find(self.selected_task_id())
        if not task:
            return
        dlg = DatePickerDialog(self.host, date.fromisoformat(task["date"]), "Start on")
        if dlg.exec():
            self.schedule(dlg.value())

    def open_day(self):
        task = self.store.find(self.selected_task_id())
        if task:
            self.host.show_day(date.fromisoformat(task["date"]), select=task["id"])

    def move_to_project(self, pid):
        task = self.store.find(self.selected_task_id())
        if not task or task["project_id"] == pid:
            return
        old = task["project_id"]
        self.store.update(task["id"], project_id=pid)

        def undo(tid=task["id"]):
            self.store.update(tid, project_id=old)
            self.current_id = old
            return tid
        self.host._push_undo("move", undo)
        target = self.store.project(pid)
        self.refresh()
        self.host.snack(f"Moved to {target['name']}" if target else "Removed from project",
                        "Undo", self.host.undo)

    def _tree_menu(self, pos, item):
        menu = QMenu(self)
        h = self.host
        add = lambda *a, **k: h._menu_action(menu, *a, **k)
        if item is not None:
            self.tree.setCurrentItem(item)
        kind, tid, sid = self.selected()
        task = self.store.find(tid) if tid else None
        if kind == SUB:
            s = next((x for x in self.store.subtasks(tid) if x["id"] == sid), None)
            if s:
                add("Mark as not done" if s["done"] else "Mark as done", self.toggle_current, "check", "Space")
                add("Rename", self.edit_current, "edit", "F2")
                add("Add another subtask…", self.add_subtask, "subdirectory", "Ins")
                menu.addSeparator()
                add("Delete subtask", self.delete_current, "delete", "Del")
        elif task:
            add("Mark as not done" if task["done"] else "Mark as done", self.toggle_current, "check", "Space")
            h._status_menu(menu, task)
            add("Edit…", h.edit_task, "edit", "F2")
            add("Add subtask…", self.add_subtask, "subdirectory", "Ins")
            h._focus_menu(menu, task)
            h._priority_menu(menu, task)
            sched = menu.addMenu(h._icon("event"), "Move start to")
            today = date.today()
            h._menu_action(sched, "Today", lambda: self.schedule(today))
            h._menu_action(sched, "Tomorrow", lambda: self.schedule(today + timedelta(days=1)))
            h._menu_action(sched, "Pick a date…", self.schedule_picked)
            add(f"Open {date.fromisoformat(task['date']):%a %d %b} in day view", self.open_day, "today")
            mv = menu.addMenu(h._icon("folder"), "Move to project")
            for p in self.store.projects(include_done=False):
                if p["id"] != task["project_id"]:
                    h._menu_action(mv, p["name"].replace("&", "&&"),
                                   lambda _=False, pid=p["id"]: self.move_to_project(pid)).setIcon(dot_icon(p["color"]))
            mv.addSeparator()
            h._menu_action(mv, "Remove from project", lambda: self.move_to_project(""))
            up = add("Move up", lambda: self.move_current(-1), "arrow_up", "Alt+↑")
            down = add("Move down", lambda: self.move_current(1), "arrow_down", "Alt+↓")
            order = self.store.project_order(task["project_id"])
            idx = order.index(task["id"]) if task["id"] in order else -1
            up.setEnabled(idx > 0)
            down.setEnabled(0 <= idx < len(order) - 1)
            if self.view == "timeline":
                add("Move a day earlier", lambda: self.shift_days(-1), None, "Ctrl+Shift+←")
                add("Move a day later", lambda: self.shift_days(1), None, "Ctrl+Shift+→")
            if self.view == "board":
                left = self.board.neighbour_status(task["id"], -1)
                right = self.board.neighbour_status(task["id"], 1)
                a = add(f"Move to {STATUS.label(left)}" if left else "Move left", lambda: self.move_card(-1),
                        None, "Ctrl+Shift+←")
                a.setEnabled(bool(left))
                a = add(f"Move to {STATUS.label(right)}" if right else "Move right", lambda: self.move_card(1),
                        None, "Ctrl+Shift+→")
                a.setEnabled(bool(right))
            add("Duplicate", h.duplicate_task, "add", "Ctrl+D")
            add("Copy text", h.copy_task, "copy", "Ctrl+C")
            add("History…", h.show_history, "history", "Ctrl+H")
            menu.addSeparator()
            add("Delete", self.delete_current, "delete", "Del")
        else:
            add("New task…", lambda: h.add_task(), "add", "Ctrl+N")
            add("Edit project…", self.edit_project, "edit")
            add("Renumber tasks…", self.renumber, "checklist")
        if h._undo:
            menu.addSeparator()
            add(f"Undo {h._undo[-1][0]}", h.undo, "undo", "Ctrl+Z")
        menu.exec(pos)
