"""End-of-day review: 1) how today went  2) move unfinished tasks  3) plan the next day.

Unfinished routine blocks (Lunch, Stand-up…) are unticked by default since the routine
recreates them; everything else is ticked to move to the next working day.
"""
from datetime import date, timedelta

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..quickparse import describe, parse
from ..theme.icons import make_icon
from ..timespan import span_label
from .. import status as STATUS
from ..utils import fmt_duration
from .dialogs import FadeDialog
from .helpers import set_kind, set_role

MAX_STARS = 3


def next_workday(d: date) -> date:
    n = d + timedelta(days=1)
    while n.weekday() >= 5:
        n += timedelta(days=1)
    return n


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


def _scroll(inner_layout, max_h=None):
    body = QWidget()
    body.setLayout(inner_layout)
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                     "QScrollArea>QWidget>QWidget{background:transparent;}")
    sa.setWidget(body)
    if max_h:
        sa.setMaximumHeight(max_h)
    sa.setMinimumHeight(120)
    return sa


class ReviewDialog(FadeDialog):
    STEPS = ("How today went", "Unfinished tasks", "Plan ahead")

    def __init__(self, parent, store, colors, today=None):
        super().__init__(parent)
        self.store, self.c = store, colors
        self.today = today or date.today()
        self.target = next_workday(self.today)
        self.moved = {}               # task id -> date moved to
        self.setWindowTitle("Wrap up your day")
        self.setMinimumWidth(560)
        lay = self._frame("Wrap up your day", spacing=8)
        self.step_lbl = set_role(QLabel(), "hint")
        lay.addWidget(self.step_lbl)
        lay.addSpacing(6)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_today())
        self.stack.addWidget(self._page_unfinished())
        self.stack.addWidget(self._page_plan())
        lay.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(lambda: self._go(self.stack.currentIndex() - 1))
        self.skip_btn = QPushButton("Not today")
        self.skip_btn.clicked.connect(self.reject)
        self.next_btn = set_kind(QPushButton("Next"), "filled")
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.skip_btn)
        nav.addStretch()
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)
        # Enter belongs to the text boxes here; it must never "click" a dialog button
        # (it used to trigger "Add my routine" while adding a task in step 3).
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)
            b.setDefault(False)
        self._go(0)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            return            # line edits already handled returnPressed
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ navigation
    def _go(self, i):
        i = max(0, min(i, self.stack.count() - 1))
        if i == 1:
            self._fill_unfinished()
        if i == 2:
            self._fill_plan()
        self.stack.setCurrentIndex(i)
        self.step_lbl.setText(f"STEP {i + 1} OF 3  ·  {self.STEPS[i].upper()}")
        self.back_btn.setVisible(i > 0)
        self.skip_btn.setVisible(i == 0)
        self.next_btn.setText("Finish" if i == 2 else "Next")

    def _next(self):
        i = self.stack.currentIndex()
        if i == 1:
            self._apply_moves()
        if i == 2:
            self._finish()
            return
        self._go(i + 1)

    # ------------------------------------------------------------------ page 1
    def _stat(self, value, caption):
        f = QFrame()
        f.setObjectName("statCard")
        f.setAttribute(Qt.WA_StyledBackground)
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(0)
        v.addWidget(set_role(QLabel(value), "stat"))
        v.addWidget(set_role(QLabel(caption), "muted"))
        return f

    def _page_today(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        tasks = self.store.for_day(self.today)
        done = [t for t in tasks if t["done"]]
        focused = self.store.focus_seconds_on(self.today)
        v.addWidget(set_role(QLabel(f"{self.today:%A %d %B}"), "muted"))
        stats = QHBoxLayout()
        stats.setSpacing(10)
        stats.addWidget(self._stat(f"{len(done)}/{len(tasks)}", "tasks done"))
        stats.addWidget(self._stat(fmt_duration(focused) if focused else "0m", "focused"))
        subs = sum(t["sub_done"] for t in tasks)
        stats.addWidget(self._stat(str(subs), "subtasks ticked"))
        v.addLayout(stats)
        if done:
            v.addWidget(set_role(QLabel("COMPLETED"), "label"))
            box = QVBoxLayout()
            box.setSpacing(4)
            for t in done:
                extra = f"   ·  {fmt_duration(t['focus_seconds'])} focused" if t["focus_seconds"] >= 60 else ""
                lbl = QLabel(f"✓  {t['title']}{extra}")
                lbl.setTextFormat(Qt.PlainText)
                box.addWidget(lbl)
            box.addStretch()
            v.addWidget(_scroll(box), 1)
        else:
            msg = "Nothing was planned today." if not tasks else "Nothing ticked off today. Tomorrow's a fresh start."
            v.addWidget(set_role(QLabel(msg), "muted"))
            v.addStretch()
        return w

    # ------------------------------------------------------------------ page 2
    def _page_unfinished(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(set_role(QLabel("Ticked tasks move to"), "muted"))
        self.target_combo = QComboBox()
        options = []
        tomorrow = self.today + timedelta(days=1)
        for d in (tomorrow, next_workday(self.today), self.today + timedelta(days=7 - self.today.weekday())):
            if d not in options:
                options.append(d)
        for d in options:
            label = "Tomorrow" if d == tomorrow else f"{d:%A}"
            self.target_combo.addItem(f"{label}  ({d:%a %d %b})", d)
        self.target_combo.setCurrentIndex(options.index(self.target))
        self.target_combo.currentIndexChanged.connect(
            lambda i: setattr(self, "target", self.target_combo.itemData(i)))
        row.addWidget(self.target_combo)
        row.addStretch()
        v.addLayout(row)
        self.unfinished_rows = QVBoxLayout()
        self.unfinished_rows.setSpacing(2)
        v.addWidget(_scroll(self.unfinished_rows), 1)
        self.unfinished_hint = set_role(QLabel(), "hint")
        self.unfinished_hint.setWordWrap(True)
        v.addWidget(self.unfinished_hint)
        return w

    def _routine_keys(self):
        return {(r["title"], r["start"]) for r in self.store.routine}

    def _fill_unfinished(self):
        _clear(self.unfinished_rows)
        self.carry = {}
        routine = self._routine_keys()
        # unfinished tasks that end today (ones still running into later days aren't "left over")
        end_of_day = (self.today + timedelta(days=1)).isoformat() + "T00:00"
        open_tasks = [t for t in self.store.for_day(self.today) if t["status"] not in (STATUS.DONE, STATUS.CANCELLED)
                      and t["end_at"] <= end_of_day]
        for t in open_tasks:
            is_routine = (t["title"], t["start"]) in routine
            r = QHBoxLayout()
            when = span_label(t["start_at"], t["end_at"], self.today) + "  "
            cb = QCheckBox(f"{when}{t['title']}".replace("&", "&&") + ("   · routine" if is_routine else ""))
            cb.setChecked(not is_routine)
            self.carry[t["id"]] = cb
            done_btn = QPushButton("Mark done")
            done_btn.setAutoDefault(False)
            done_btn.setCursor(Qt.PointingHandCursor)
            done_btn.clicked.connect(lambda _=False, tid=t["id"], c=cb, b=done_btn: self._mark_done(tid, c, b))
            r.addWidget(cb, 1)
            r.addWidget(done_btn)
            self.unfinished_rows.addLayout(r)
        self.unfinished_rows.addStretch()
        if not open_tasks:
            self.unfinished_rows.insertWidget(0, set_role(QLabel("Nothing left over. Nice work!"), "muted"))
            self.unfinished_hint.setText("")
        else:
            self.unfinished_hint.setText("Routine blocks are unticked: your routine adds them again. "
                                         "Moved tasks keep their subtasks and history.")

    def _mark_done(self, tid, cb, btn):
        self.store.update(tid, done=True)
        cb.setChecked(False)
        cb.setEnabled(False)
        btn.setText("Done ✓")
        btn.setEnabled(False)
        self.carry.pop(tid, None)

    def _apply_moves(self):
        for tid, cb in list(self.carry.items()):
            if cb.isChecked() and tid not in self.moved:
                self.store.update(tid, date=self.target)
                self.moved[tid] = self.target

    # ------------------------------------------------------------------ page 3
    def _page_plan(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.plan_title = set_role(QLabel(), "title")
        v.addWidget(self.plan_title)
        v.addWidget(set_role(QLabel(f"Star up to {MAX_STARS} top tasks. They get a ★ and stand out in the list."), "muted"))
        self.plan_add = QLineEdit()
        self.plan_add.returnPressed.connect(self._plan_quick_add)
        self.plan_add.textChanged.connect(self._plan_preview)
        v.addWidget(self.plan_add)
        self.plan_preview = set_role(QLabel(), "hint")
        v.addWidget(self.plan_preview)
        self.plan_rows = QVBoxLayout()
        self.plan_rows.setSpacing(2)
        v.addWidget(_scroll(self.plan_rows), 1)
        self.routine_btn = set_kind(QPushButton("Add my routine"), "tonal")
        self.routine_btn.clicked.connect(self._add_routine)
        row = QHBoxLayout()
        row.addWidget(self.routine_btn)
        row.addStretch()
        v.addLayout(row)
        return w

    def _fill_plan(self):
        d = self.target
        self.plan_title.setText(f"Plan {d:%A %d %b}")
        self.plan_add.setPlaceholderText(f"Add a task for {d:%A}, e.g. Deploy staging 9am #dpp !high")
        _clear(self.plan_rows)
        self.stars = {}
        tasks = [t for t in self.store.for_day(d) if not t["done"]]
        for t in tasks:
            r = QHBoxLayout()
            star = set_kind(QPushButton(), "iconSmall")
            star.setCheckable(True)
            star.setChecked(t["pinned"])
            star.setIconSize(QSize(20, 20))
            star.setCursor(Qt.PointingHandCursor)
            star.setToolTip("Top task")
            star.setAutoDefault(False)
            star.toggled.connect(self._stars_changed)
            self.stars[t["id"]] = star
            when = span_label(t["start_at"], t["end_at"], d)
            title = QLabel(t["title"])
            title.setTextFormat(Qt.PlainText)
            r.addWidget(star)
            r.addWidget(title, 1)
            r.addWidget(set_role(QLabel(when), "muted"))
            self.plan_rows.addLayout(r)
        self.plan_rows.addStretch()
        if not tasks:
            self.plan_rows.insertWidget(0, set_role(QLabel("Nothing planned yet. Add a task above."), "muted"))
        routine = self._routine_keys()
        has_routine = any((t["title"], t["start"]) in routine for t in self.store.for_day(d))
        self.routine_btn.setVisible(bool(routine) and not has_routine)
        self._stars_changed()
        self._plan_preview()

    def _stars_changed(self, *_):
        n = sum(b.isChecked() for b in self.stars.values())
        for b in self.stars.values():
            b.setIcon(make_icon("star" if b.isChecked() else "star_outline",
                                self.c["primary"] if b.isChecked() else self.c["onSurfaceVariant"]))
            b.setEnabled(b.isChecked() or n < MAX_STARS)

    def _plan_preview(self, *_):
        text = self.plan_add.text()
        if text.strip():
            p = parse(text, self.today)
            self.plan_preview.setText("→  " + describe(p, self.target, self.today, self.store.workday()))
        else:
            self.plan_preview.setText("Enter adds it  ·  dates, times, #tags, !high are understood")

    def _plan_quick_add(self):
        p = parse(self.plan_add.text(), self.today)
        if not p.title:
            return
        self._save_stars()
        self.store.add(p.date or self.target, p.title, p.start, p.end, priority=p.priority,
                       tags=" ".join(p.tags), pinned=p.pinned)
        self.plan_add.clear()
        self._fill_plan()

    def _add_routine(self):
        self._save_stars()
        self.store.load_routine(self.target)
        self._fill_plan()

    def _save_stars(self):
        for tid, b in self.stars.items():
            self.store.update(tid, pinned=b.isChecked())

    def _finish(self):
        self._save_stars()
        self.store.settings["review_last"] = self.today.isoformat()
        self.store.save_settings()
        self.accept()

    def summary(self):
        n = len(self.moved)
        moved = f"{n} task{'s' if n != 1 else ''} moved to {self.target:%a %d %b}. " if n else ""
        return f"{moved}All set for {self.target:%A}."
