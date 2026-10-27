"""Main window: navigation rail, day view (task table), bottom bar, theme drawer."""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QDateEdit, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMenu, QProgressBar, QPushButton, QSizePolicy, QSystemTrayIcon, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from ..config import APP_NAME
from .. import recurrence as R
from .. import status as STATUS
from ..theme import app_icon, make_icon, on_color
from ..theme.icons import status_dot
from ..quickparse import HIGH, LOW, PRIORITY_NAMES, TAG_PALETTE, describe, parse, tag_color
from ..utils import fmt_duration, fmt_stamp, mins
from .focus_bar import FocusBar
from .helpers import set_kind, set_role
from .motion import animate, crossfade
from .shortcuts import install_shortcuts
from .snackbar import Snackbar
from .task_actions import TaskActionsMixin
from .theme_drawer import ThemeDrawer


class MainWindow(QMainWindow, TaskActionsMixin):
    def __init__(self, store, app):
        super().__init__()
        self.store, self.app, self.theme = store, app, app.theme
        self.current = date.today()
        self._icons = []        # (widget, icon name, off colour role, on colour role)
        self._compact = False
        self._undo = []         # stack of (label, callable)
        self._tag_filter = None  # None = all; otherwise a tag string
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(620, 540)

        self.root = QWidget()
        self.root.setObjectName("root")
        h = QHBoxLayout(self.root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_rail())
        h.addWidget(self._build_content(), 1)
        self.drawer = ThemeDrawer(self.theme)
        self.drawer.themeRequested.connect(lambda kw: self.change_theme(**kw))
        self.drawer.closeRequested.connect(self.toggle_drawer)
        h.addWidget(self.drawer)
        self.setCentralWidget(self.root)
        self.snackbar = Snackbar(self.root)
        install_shortcuts(self)
        self.on_theme()
        self.resize(1080, 740)

    # ------------------------------------------------------------------ builders
    def _icon_btn(self, icon, tip, slot, kind="icon"):
        b = set_kind(QPushButton(), kind)
        b.setToolTip(tip)
        b.setIconSize(QSize(24, 24))
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(slot)
        self._icons.append((b, icon, "onSurfaceVariant", None))
        return b

    def _build_rail(self):
        self.rail = QFrame()
        self.rail.setObjectName("rail")
        self.rail.setMaximumWidth(88)
        lay = QVBoxLayout(self.rail)
        lay.setContentsMargins(8, 28, 8, 16)
        lay.setSpacing(12)

        def rb(text, icon, slot, keys):
            b = QToolButton()
            b.setObjectName("railBtn")
            b.setText(text)
            b.setCheckable(True)
            b.setToolTip(f"{text} ({keys})")
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(24, 24))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setFixedHeight(64)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            self._icons.append((b, icon, "onSurfaceVariant", "onSecondaryContainer"))
            lay.addWidget(b)
            return b

        self.btn_today = rb("Today", "today", self.go_today, "Ctrl+T")
        self.btn_plan = rb("Plan", "event", self.plan_tomorrow, "Ctrl+P")
        self.btn_review = rb("Review", "done_all", lambda: self.app.show_review(), "Ctrl+E")
        self.btn_review.setCheckable(False)
        self.btn_stats = rb("Stats", "chart", lambda: self.app.show_stats(), "Ctrl+Shift+S")
        self.btn_stats.setCheckable(False)
        self.btn_theme = rb("Theme", "palette", self.toggle_drawer, "Ctrl+,")
        self.rail_buttons = [self.btn_today, self.btn_plan, self.btn_review, self.btn_stats, self.btn_theme]
        lay.addStretch()
        return self.rail

    def _build_header(self):
        top = QHBoxLayout()
        top.setSpacing(4)
        top.addWidget(self._icon_btn("chevron_left", "Previous day (Alt+←)", lambda: self.shift_day(-1)))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.day_lbl = set_role(QLabel(), "headline")
        self.sub_lbl = set_role(QLabel(), "muted")
        titles.addWidget(self.day_lbl)
        titles.addWidget(self.sub_lbl)
        top.addSpacing(6)
        top.addLayout(titles)
        top.addSpacing(6)
        top.addWidget(self._icon_btn("chevron_right", "Next day (Alt+→)", lambda: self.shift_day(1)))
        top.addStretch()
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setFixedWidth(150)
        self.date_edit.dateChanged.connect(lambda qd: self.go_to(qd.toPython()))
        top.addWidget(self.date_edit)
        return top

    def _build_table(self):
        t = QTableWidget(0, 5)
        t.setHorizontalHeaderLabels(["", "Status", "Time", "Task", "Note"])
        hh = t.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        t.setColumnWidth(0, 52)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        t.setColumnWidth(1, 138)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(52)
        t.setShowGrid(False)
        t.setFrameShape(QFrame.NoFrame)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        t.itemChanged.connect(self._item_changed)
        t.cellDoubleClicked.connect(lambda *_: self.edit_task())
        t.setContextMenuPolicy(Qt.CustomContextMenu)
        t.customContextMenuRequested.connect(
            lambda p: self._show_menu(t.viewport().mapToGlobal(p), t.indexAt(p).row()))
        return t

    def _build_bottom(self):
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        prog = QVBoxLayout()
        prog.setSpacing(6)
        self.count_lbl = set_role(QLabel(), "muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        prog.addWidget(self.count_lbl)
        prog.addWidget(self.progress)
        bottom.addLayout(prog, 1)
        bottom.addSpacing(16)
        bottom.addWidget(self._icon_btn("edit", "Edit selected task (F2)", self.edit_task))
        bottom.addWidget(self._icon_btn("delete", "Delete selected task (Del)", self.delete_task))

        more = self._icon_btn("more", "More", lambda: None)
        more.clicked.disconnect()
        menu = QMenu(more)
        for text, fn in (("Load routine", self.load_routine),
                         ("Save day as routine", self.save_routine),
                         ("Carry unfinished to next day", self.carry_over),
                         (None, None),
                         ("Undo\tCtrl+Z", self.undo),
                         ("Keyboard shortcuts\tF1", self.show_shortcuts),
                         ("Check for updates…", lambda: self.app.show_updates())):
            if text is None:
                menu.addSeparator()
                continue
            act = QAction(text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        more.setMenu(menu)
        bottom.addWidget(more)
        bottom.addSpacing(8)

        self.fab = set_kind(QPushButton("  New task"), "fab")
        self.fab.setToolTip("New task (Ctrl+N)")
        self.fab.setIconSize(QSize(24, 24))
        self.fab.setCursor(Qt.PointingHandCursor)
        self.fab.clicked.connect(lambda: self.add_task())
        self._icons.append((self.fab, "add", "onPrimaryContainer", None))
        bottom.addWidget(self.fab)
        return bottom

    def _build_content(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 24, 20, 16)
        v.setSpacing(14)
        v.addLayout(self._build_header())

        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Quick add, e.g.  Review PR tomorrow 2pm #dpp !high   (Ctrl+L)")
        self.quick.returnPressed.connect(self.quick_add)
        self.quick.textChanged.connect(self._quick_preview)
        quick_box = QVBoxLayout()
        quick_box.setSpacing(4)
        quick_box.addWidget(self.quick)
        self.quick_hint = set_role(QLabel(), "hint")
        self.quick_hint.setTextFormat(Qt.PlainText)
        self.quick_hint.setContentsMargins(14, 0, 0, 0)
        self.quick_hint.hide()
        quick_box.addWidget(self.quick_hint)
        v.addLayout(quick_box)

        self.focus_bar = FocusBar(self.app.focus)
        v.addWidget(self.focus_bar)

        self.filter_bar = QWidget()
        self.filter_row = QHBoxLayout(self.filter_bar)
        self.filter_row.setContentsMargins(2, 0, 2, 0)
        self.filter_row.setSpacing(6)
        v.addWidget(self.filter_bar)

        self.panel = QFrame()
        self.panel.setObjectName("panel")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(12, 8, 12, 8)
        self.table = self._build_table()
        self.empty = set_role(QLabel("No tasks for this day.\nAdd one below (Ctrl+N), "
                                     "or right-click to load your routine."), "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setContextMenuPolicy(Qt.CustomContextMenu)
        self.empty.customContextMenuRequested.connect(
            lambda p: self._show_menu(self.empty.mapToGlobal(p), -1))
        pl.addWidget(self.table)
        pl.addWidget(self.empty, 1)
        v.addWidget(self.panel, 1)
        v.addLayout(self._build_bottom())
        return w

    # ------------------------------------------------------------------ theme
    def change_theme(self, **kw):
        def apply():
            self.theme.set(**kw)
            self.store.save_settings()
            self.on_theme()
        crossfade(self.root, apply, 300)

    def on_theme(self):
        c = self.theme.c
        for w, name, off, on in self._icons:
            w.setIcon(make_icon(name, c[off], c[on] if on else None))
        self.drawer.sync()
        self.focus_bar.retheme(c)
        self.setWindowIcon(app_icon(c))
        self.refresh()

    def toggle_drawer(self):
        opening = not self.drawer.is_open
        self.drawer.set_open(opening)
        self.btn_theme.setChecked(opening)

    # ------------------------------------------------------------------ window events
    def _set_compact(self, compact):
        if compact == self._compact:
            return
        self._compact = compact
        style = Qt.ToolButtonIconOnly if compact else Qt.ToolButtonTextUnderIcon
        if compact:
            for b in self.rail_buttons:
                b.setToolButtonStyle(style)
        animate(self.rail, b"maximumWidth", self.rail.width(), 64 if compact else 88, 280, "std",
                finished=None if compact else (lambda: [b.setToolButtonStyle(style) for b in self.rail_buttons]))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._set_compact(e.size().width() < 780)
        if self.snackbar.isVisible():
            self.snackbar.reposition()

    def closeEvent(self, event):
        if self.app.quitting:
            event.accept()
        else:
            event.ignore()
            self.hide()
            self.app.tray.showMessage("Daily Planner", "Still running in the tray.",
                                      QSystemTrayIcon.Information, 2000)

    def on_escape(self):
        if self.drawer.is_open:
            self.toggle_drawer()
        elif self.snackbar.isVisible():
            self.snackbar.dismiss()
        elif self.quick.hasFocus() and self.quick.text():
            self.quick.clear()
        else:
            self.table.clearSelection()
            self.table.setFocus()

    def focus_quick(self):
        self.quick.setFocus()
        self.quick.selectAll()

    def snack(self, text, action_text="", action=None):
        self.snackbar.show_message(text, action_text, action)

    # ------------------------------------------------------------------ navigation
    def go_today(self):
        self.go_to(date.today())

    def shift_day(self, days):
        self.go_to(self.current + timedelta(days=days))

    def go_to(self, d: date):
        def apply():
            self.current = d
            self.date_edit.blockSignals(True)
            self.date_edit.setDate(QDate(d.year, d.month, d.day))
            self.date_edit.blockSignals(False)
            self.refresh()
        if d == self.current:
            self.refresh()
        else:
            crossfade(self.panel, apply, 200)

    # ------------------------------------------------------------------ day view
    def tag_color(self, tag):
        return self.store.tag_colors().get(tag.lower()) or tag_color(tag)

    def _rebuild_filter_bar(self):
        while self.filter_row.count():
            it = self.filter_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        tags = self.store.all_tags()
        self.filter_bar.setVisible(bool(tags))
        if not tags:
            self._tag_filter = None
            return
        allb = set_kind(QPushButton("All"), "chip")
        allb.setCheckable(True)
        allb.setChecked(self._tag_filter is None)
        allb.setCursor(Qt.PointingHandCursor)
        allb.clicked.connect(lambda: self._set_filter(None))
        self.filter_row.addWidget(allb)
        for tag, count in tags:
            col = self.tag_color(tag)
            chip = set_kind(QPushButton(f"#{tag}  {count}"), "tagchip")
            chip.setCheckable(True)
            chip.setChecked(self._tag_filter == tag)
            chip.setCursor(Qt.PointingHandCursor)
            sel = self._tag_filter == tag
            fg = on_color(col) if sel else col
            bg = col if sel else "transparent"
            chip.setStyleSheet(
                f"QPushButton{{background:{bg};color:{fg};border:1px solid {col};"
                f"border-radius:8px;min-height:30px;padding:0 12px;font-weight:600;}}"
                f"QPushButton:hover{{background:{col}2a;}}")
            chip.clicked.connect(lambda _=False, t=tag: self._set_filter(t))
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.customContextMenuRequested.connect(
                lambda pos, t=tag, c=chip: self._tag_color_menu(c.mapToGlobal(pos), t))
            self.filter_row.addWidget(chip)
        self.filter_row.addStretch()

    def _set_filter(self, tag):
        self._tag_filter = tag
        self._rebuild_filter_bar()
        self.refresh()

    def _tag_color_menu(self, pos, tag):
        menu = QMenu(self)
        for name, col in TAG_PALETTE:
            a = QAction(name, menu)
            a.triggered.connect(lambda _=False, c=col: self._apply_tag_color(tag, c))
            menu.addAction(a)
        menu.addSeparator()
        pick = QAction("Custom…", menu)
        pick.triggered.connect(lambda: self._pick_tag_color(tag))
        menu.addAction(pick)
        reset = QAction("Reset to automatic", menu)
        reset.triggered.connect(lambda: self._apply_tag_color(tag, ""))
        menu.addAction(reset)
        menu.exec(pos)

    def _apply_tag_color(self, tag, color):
        self.store.set_tag_color(tag, color)
        self._rebuild_filter_bar()
        self.refresh()

    def _pick_tag_color(self, tag):
        col = QColorDialog.getColor(QColor(self.tag_color(tag)), self, f"Colour for #{tag}")
        if col.isValid():
            self._apply_tag_color(tag, col.name())

    def _quick_preview(self, text):
        if not text.strip():
            self.quick_hint.hide()
            return
        p = parse(text, date.today())
        self.quick_hint.setText("→  " + (describe(p, self.current, date.today()) if p.title else "add a title"))
        self.quick_hint.show()

    def _title_text(self, t):
        prefix = ("◉ " if self.app.focus.is_on(t["id"]) else "") + ("★ " if t["pinned"] else "") \
            + ("⚑ " if t["priority"] == HIGH else "") + ("⟳ " if t["recurrence"] else "")
        extras = []
        if t["tags"] and t["note"]:   # if there's a note, keep tags inline in the title
            extras.append(" ".join("#" + x for x in t["tags"].split()))
        if t["sub_total"]:
            extras.append(f"✓ {t['sub_done']}/{t['sub_total']}")
        if t["focus_seconds"] >= 60:
            extras.append(f"⏱ {fmt_duration(t['focus_seconds'])}")
        return prefix + t["title"] + ("   " + "   ".join(extras) if extras else "")

    @staticmethod
    def _tooltip(t, subs):
        tip = f"Created {fmt_stamp(t['created_at'])}"
        if t["completed_at"]:
            tip += f"\nCompleted {fmt_stamp(t['completed_at'])}"
        if t["priority"] != 1:
            tip += f"\nPriority: {PRIORITY_NAMES[t['priority']]}"
        if t["focus_seconds"]:
            tip += f"\nFocused: {fmt_duration(t['focus_seconds'])}"
        if subs:
            tip += "\n\nSubtasks:\n" + "\n".join(("☑ " if s["done"] else "☐ ") + s["title"] for s in subs)
        return tip

    def refresh(self, select=None):
        c = self.theme.c
        keep = select or self.selected_id()
        self._rebuild_filter_bar()
        all_today = self.store.for_day(self.current)
        if self._tag_filter:
            tasks = [t for t in all_today if self._tag_filter in t["tags"].split()]
        else:
            tasks = all_today
        subs_by_task = self.store.subtasks_for_day(self.current)
        now = datetime.now()
        nm = now.hour * 60 + now.minute
        today = now.date()
        is_today = self.current == today
        tomorrow = today + timedelta(days=1)
        tag = " · Today" if is_today else (" · Tomorrow" if self.current == tomorrow else "")
        self.day_lbl.setText(self.current.strftime("%A"))
        self.sub_lbl.setText(self.current.strftime("%d %B %Y") + tag)
        self.btn_today.setChecked(is_today)
        self.btn_plan.setChecked(self.current == tomorrow)

        self.table.blockSignals(True)
        self.table.setCurrentCell(-1, -1)
        self.table.setRowCount(len(tasks))
        keep_row = -1
        for r, t in enumerate(tasks):
            if t["id"] == keep:
                keep_row = r
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if t["done"] else Qt.Unchecked)
            chk.setData(Qt.UserRole, t["id"])
            self.table.setItem(r, 0, chk)
            when = f"{t['start']}-{t['end']}" if t["start"] else "Anytime"
            title = self._title_text(t)
            tip = self._tooltip(t, subs_by_task.get(t["id"], []))
            items = [chk]
            # status pill cell (col 1): coloured dot + label, never struck through
            st = t["status"]
            scol = STATUS.color(st)
            pill = QTableWidgetItem("  " + STATUS.label(st))
            pill.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            pill.setIcon(status_dot(scol))
            pill.setForeground(QBrush(QColor(scol)))
            pill.setToolTip(tip)
            self.table.setItem(r, 1, pill)
            for col, text in ((2, when), (3, title), (4, t["note"])):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                it.setToolTip(tip)
                self.table.setItem(r, col, it)
                items.append(it)
            tag_items = []    # tags get their own colour, not the row's done/priority colour
            if t["tags"]:
                first = t["tags"].split()[0]
                tag_it = items[3]   # the Note column cell carries the tag colour accent
                if not t["note"]:
                    tag_it.setText(" ".join("#" + x for x in t["tags"].split()))
                    tag_it.setForeground(QBrush(QColor(self.tag_color(first))))
                    tag_items.append(tag_it)
            live = is_today and t["start"] and mins(t["start"]) <= nm < mins(t["end"]) and not t["done"]
            late = is_today and t["start"] and mins(t["end"]) <= nm and not t["done"]
            for it in items:
                f = it.font()
                f.setStrikeOut(t["status"] in (STATUS.DONE, STATUS.CANCELLED))
                it.setFont(f)
                if it in tag_items and not t["done"]:
                    continue
                if t["status"] in (STATUS.DONE, STATUS.CANCELLED, STATUS.POSTPONED):
                    it.setForeground(QBrush(QColor(c["outline"])))
                elif t["priority"] == LOW and not live:
                    it.setForeground(QBrush(QColor(c["onSurfaceVariant"])))
                elif late:
                    it.setForeground(QBrush(QColor(c["error"])))
                if live:
                    it.setBackground(QBrush(QColor(c["primaryContainer"])))
                    it.setForeground(QBrush(QColor(c["onPrimaryContainer"])))
                if self.app.focus.is_on(t["id"]):
                    it.setBackground(QBrush(QColor(c["tertiaryContainer"])))
                    it.setForeground(QBrush(QColor(c["onTertiaryContainer"])))
        if keep_row >= 0:
            self.table.setCurrentCell(keep_row, 3)
        self.table.blockSignals(False)
        self.table.setVisible(bool(tasks))
        self.empty.setVisible(not tasks)
        if not tasks and self._tag_filter and all_today:
            self.empty.setText(f"No #{self._tag_filter} tasks today.")
        elif not tasks:
            self.empty.setText("No tasks for this day.\nAdd one below (Ctrl+N), "
                               "or right-click to load your routine.")

        done = sum(1 for t in tasks if t["done"])
        self.progress.setMaximum(max(len(tasks), 1))
        self.progress.setValue(done)
        wk_done, wk_total = self.store.stats(self.current - timedelta(days=6), self.current)
        focused = self.store.focus_seconds_on(self.current)
        self.count_lbl.setText(f"{done} of {len(tasks)} done   ·   "
                               + (f"{fmt_duration(focused)} focused   ·   " if focused >= 60 else "")
                               + f"last 7 days: {wk_done}/{wk_total}")

    def _item_changed(self, item):
        if item.column() == 0:
            self.store.update(item.data(Qt.UserRole), done=item.checkState() == Qt.Checked)
            QTimer.singleShot(0, self.refresh)
