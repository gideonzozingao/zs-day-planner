"""Statistics: Today, Overall (all-time) and Projects.

Today / Overall show a status breakdown (the coloured stacked bar + a legend with counts),
headline numbers (completion, focus time, totals), and breakdowns by project and by tag.
Overall adds a 14-day completion trend.
Projects shows every project side by side (status bar, completion, progress against time
used, overdue) and, for one project, its full task and progress stats: completion and
weighted progress, timing against start/finish, pace, status breakdown, next due tasks,
tags and the last 14 days of completions.
All drawing uses the status colours so it matches the task list.
"""
from datetime import date, datetime, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QTabWidget, QVBoxLayout, QWidget,
)

from .. import status as STATUS
from .. import timespan as TS
from ..utils import fmt_duration, rgba
from .dialogs import FadeDialog
from .helpers import set_kind, set_role


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
            p.setBrush(QColor(0, 0, 0, 32))
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
        muted = QColor(136, 136, 136, 48)
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


class CountChart(QWidget):
    """Bars of a daily count (e.g. tasks completed per day)."""

    def __init__(self, days, color):
        super().__init__()
        self.days = days
        self.color = color
        self.setFixedHeight(110)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.days)
        if not n:
            return
        pad_b, pad_t = 18, 14
        w, h = self.width(), self.height() - pad_b - pad_t
        gap = 5
        bw = (w - gap * (n - 1)) / n
        top = max(1, max(d["done"] for d in self.days))
        p.setFont(QFont(self.font().family(), 7))
        for i, d in enumerate(self.days):
            x = i * (bw + gap)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(136, 136, 136, 48))
            p.drawRoundedRect(QRectF(x, pad_t, bw, h), 3, 3)
            if d["done"]:
                bh = max(3, h * d["done"] / top)
                p.setBrush(QColor(self.color))
                p.drawRoundedRect(QRectF(x, pad_t + h - bh, bw, bh), 3, 3)
                p.setPen(QColor("#999999"))
                p.drawText(QRectF(x - 4, pad_t + h - bh - 13, bw + 8, 12), Qt.AlignHCenter, str(d["done"]))
            p.setPen(QColor("#999999"))
            if i == 0 or i == n - 1 or d["date"].weekday() == 0:
                p.drawText(QRectF(x - 6, pad_t + h + 2, bw + 12, pad_b), Qt.AlignHCenter | Qt.AlignTop,
                           d["date"].strftime("%d/%m"))


class StatsDialog(FadeDialog):
    def __init__(self, parent, store, colors, today=None, project_id=None, on_open_project=None):
        """project_id: open on the Projects tab with that project selected.
        on_open_project(pid): called by "Open project" (the dialog closes first)."""
        super().__init__(parent)
        self.store, self.c = store, colors
        self.today = today or date.today()
        self.on_open_project = on_open_project
        self.setWindowTitle("Statistics")
        self.setMinimumSize(640, 600)
        lay = self._frame("Statistics", spacing=10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._scroll(self._today_tab()), "Today")
        self.tabs.addTab(self._scroll(self._overall_tab()), "Overall")
        self.tabs.addTab(self._projects_tab(project_id), "Projects")
        if project_id:
            self.tabs.setCurrentIndex(2)
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
            if any(pid for pid in ov["projects"]):
                v.addWidget(set_role(QLabel("BY PROJECT"), "label"))
                v.addLayout(self._project_rows(ov["projects"]))
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
        projects = {ps["project"]["id"]: {"total": ps["tasks"], "done": ps["done"]}
                    for ps in self.store.all_project_stats(include_done=False)}
        if projects:
            v.addWidget(set_role(QLabel("OPEN PROJECTS"), "label"))
            v.addLayout(self._project_rows(projects))
        v.addWidget(set_role(QLabel("BY TAG"), "label"))
        v.addLayout(self._tag_rows(gs["tags"]))
        v.addStretch()
        return w

    # ---- shared: project rows
    def _project_rows(self, breakdown):
        """breakdown: {project_id: {total, done}} ('' = tasks outside any project)."""
        box = QVBoxLayout()
        box.setSpacing(6)
        for pid, b in sorted(breakdown.items(), key=lambda kv: (kv[0] == "", -kv[1]["total"])):
            p = self.store.project(pid) if pid else None
            row = QHBoxLayout()
            name = QLabel(p["name"] if p else "(no project)")
            name.setTextFormat(Qt.PlainText)
            if p:
                name.setStyleSheet(f"color: {p['color'] or '#888'}; font-weight: 600;")
            bar = StatusBar({STATUS.DONE: b["done"], STATUS.OPEN: b["total"] - b["done"]}, height=10)
            row.addWidget(name, 2)
            row.addWidget(bar, 5)
            row.addWidget(set_role(QLabel(f"{b['done']}/{b['total']}"), "muted"), 0)
            box.addLayout(row)
        return box

    # ---- Projects
    def _projects_tab(self, project_id):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 10, 4, 4)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(set_role(QLabel("Show"), "muted"))
        self.project_pick = QComboBox()
        self.project_pick.addItem("All projects", "")
        from .project_dialog import dot_icon
        for p in self.store.projects():
            label = p["name"] + ("  (done)" if p["status"] == "done" else "")
            self.project_pick.addItem(dot_icon(p["color"]), label, p["id"])
        top.addWidget(self.project_pick, 1)
        v.addLayout(top)
        self.project_body = QScrollArea()
        self.project_body.setWidgetResizable(True)
        self.project_body.setFrameShape(QFrame.NoFrame)
        self.project_body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.project_body.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                                        "QScrollArea>QWidget>QWidget{background:transparent;}")
        v.addWidget(self.project_body, 1)
        self.project_pick.currentIndexChanged.connect(lambda *_: self._show_project_stats())
        self.project_pick.setCurrentIndex(max(0, self.project_pick.findData(project_id or "")))
        self._show_project_stats()
        return w

    def _show_project_stats(self):
        pid = self.project_pick.currentData()
        self.project_body.setWidget(self._one_project(pid) if pid else self._all_projects())

    def _all_projects(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)
        stats = self.store.all_project_stats()
        if not stats:
            v.addWidget(set_role(QLabel("No projects yet. Create one on the Projects page (Ctrl+J)."), "muted"))
            v.addStretch()
            return w
        open_ = [s for s in stats if s["project"]["status"] != "done"]
        cards = QHBoxLayout()
        cards.setSpacing(10)
        cards.addWidget(self._stat_card(str(len(open_)), "open"))
        cards.addWidget(self._stat_card(str(sum(1 for s in open_ if s["behind"])), "behind",
                                        STATUS.color(STATUS.CANCELLED) if any(s["behind"] for s in open_) else None))
        late = sum(1 for s in open_ if datetime.now() > TS.to_dt(s["project"]["end_at"]))
        cards.addWidget(self._stat_card(str(late), "past finish",
                                        STATUS.color(STATUS.CANCELLED) if late else None))
        cards.addWidget(self._stat_card(str(sum(s["overdue"] for s in open_)), "overdue tasks"))
        v.addLayout(cards)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        for c, head in enumerate(("PROJECT", "TASKS BY STATUS", "DONE", "PROGRESS / TIME")):
            grid.addWidget(set_role(QLabel(head), "label"), 0, c)
        for r, s in enumerate(stats, start=1):
            p = s["project"]
            name = QPushButton(p["name"].replace("&", "&&"))
            name.setCursor(Qt.PointingHandCursor)
            name.setStyleSheet(f"QPushButton{{color:{p['color'] or '#888'};font-weight:600;text-align:left;"
                               f"padding:0 6px;min-height:28px;border-radius:8px;}}"
                               f"QPushButton:hover{{background:{rgba(p['color'] or '#888888', 0.12)};}}")
            name.setToolTip(f"{TS.span_label(p['start_at'], p['end_at'])}\n"
                            f"Status: {p['status'].replace('_', ' ')}\nClick for this project's details")
            name.clicked.connect(lambda _=False, pid=p["id"]: self.project_pick.setCurrentIndex(
                self.project_pick.findData(pid)))
            grid.addWidget(name, r, 0)
            bar = StatusBar(s["counts"], height=12)
            bar.setMinimumWidth(140)
            bar.setToolTip("\n".join(f"{STATUS.label(st)}: {n}" for st, n in s["counts"].items() if n)
                           or "No tasks")
            grid.addWidget(bar, r, 1)
            grid.addWidget(QLabel(f"{s['done']}/{s['tasks']}  ({s['completion'] * 100:.0f}%)"), r, 2)
            flag = ""
            if p["status"] == "done":
                flag = "complete"
            elif s["behind"]:
                flag = "BEHIND"
            prog = set_role(QLabel(f"{s['progress'] * 100:.0f}% / {s['time_used'] * 100:.0f}%"
                                   + (f"  {flag}" if flag else "")),
                            "danger" if flag == "BEHIND" else "muted")
            grid.addWidget(prog, r, 3)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        v.addWidget(set_role(QLabel("Progress counts subtasks toward each task; time used is how much of "
                                    "the project's start → finish has passed. A project is behind when "
                                    "time used runs more than 15 points ahead of progress."), "hint"))
        v.addStretch()
        for lbl in w.findChildren(QLabel):
            if lbl.property("role") == "hint":
                lbl.setWordWrap(True)
        return w

    def _one_project(self, pid):
        s = self.store.project_stats(pid)
        p = s["project"]
        now = datetime.now()
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel(p["name"])
        title.setTextFormat(Qt.PlainText)
        title.setStyleSheet(f"color: {p['color'] or '#888'}; font-size: 18px; font-weight: 600;")
        head.addWidget(title, 1)
        if self.on_open_project:
            go = set_kind(QPushButton("Open project"), "tonal")
            go.setCursor(Qt.PointingHandCursor)
            go.clicked.connect(lambda: (self.accept(), self.on_open_project(pid)))
            head.addWidget(go)
        v.addLayout(head)
        start, end = TS.to_dt(p["start_at"]), TS.to_dt(p["end_at"])
        if p["status"] == "done":
            when = "completed"
        elif now < start:
            when = f"starts in {TS.fmt_length((start - now).total_seconds())}"
        elif now >= end:
            when = f"finish passed {TS.fmt_length((now - end).total_seconds())} ago"
        else:
            when = f"{TS.fmt_length((end - now).total_seconds())} left"
        v.addWidget(set_role(QLabel(f"{start:%a %d %b %Y %H:%M}  →  {end:%a %d %b %Y %H:%M}   ·   {when}"), "muted"))

        cards = QHBoxLayout()
        cards.setSpacing(10)
        cards.addWidget(self._stat_card(f"{s['completion'] * 100:.0f}%", "tasks completed", STATUS.color(STATUS.DONE)))
        cards.addWidget(self._stat_card(f"{s['progress'] * 100:.0f}%", "progress (with subtasks)", p["color"] or None))
        cards.addWidget(self._stat_card(f"{s['done']}/{s['tasks']}", "tasks done"))
        cards.addWidget(self._stat_card(str(s["overdue"]), "overdue",
                                        STATUS.color(STATUS.CANCELLED) if s["overdue"] else None))
        cards.addWidget(self._stat_card(fmt_duration(s["focus_seconds"]) if s["focus_seconds"] else "0m", "focused"))
        v.addLayout(cards)

        # progress against time
        v.addWidget(set_role(QLabel("PROGRESS AGAINST TIME"), "label"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for r, (label, frac, col) in enumerate((("Progress", s["progress"], p["color"] or "#1A73E8"),
                                                ("Time used", s["time_used"], "#888888"))):
            grid.addWidget(QLabel(label), r, 0)
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setMaximum(1000)
            bar.setValue(int(frac * 1000))
            bar.setStyleSheet(f"QProgressBar::chunk{{background:{col};border-radius:4px;}}"
                              f"QProgressBar{{background:{rgba(col, 0.2)};}}")
            grid.addWidget(bar, r, 1)
            grid.addWidget(set_role(QLabel(f"{frac * 100:.0f}%"), "muted"), r, 2)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        pace_bits = []
        if s["pace"] is not None:
            pace_bits.append(f"Pace so far: {s['pace']:.1f} tasks/week")
        if s["remaining"] and s["needed_pace"] is not None:
            pace_bits.append(f"needed to finish on time: {s['needed_pace']:.1f} tasks/week")
        elif s["remaining"] and p["status"] != "done":
            pace_bits.append(f"{s['remaining']} task(s) left after the finish date")
        if s["last_done"]:
            pace_bits.append(f"last completion {s['last_done']:%a %d %b %H:%M}")
        verdict = ("Behind schedule" if s["behind"] else "On track") if p["status"] != "done" and s["tasks"] else ""
        if verdict:
            pace_bits.insert(0, verdict)
        line = set_role(QLabel("   ·   ".join(pace_bits)), "danger" if s["behind"] else "muted")
        line.setWordWrap(True)
        v.addWidget(line)

        # statuses
        v.addWidget(set_role(QLabel(f"TASKS BY STATUS ({s['all']})"), "label"))
        v.addWidget(StatusBar(s["counts"]))
        v.addLayout(self._legend(s["counts"]))
        if s["sub_total"]:
            v.addWidget(set_role(QLabel(f"Subtasks: {s['sub_done']} of {s['sub_total']} done"), "muted"))

        # next due
        v.addWidget(set_role(QLabel("NEXT DUE"), "label"))
        if s["next_due"]:
            for t in s["next_due"]:
                row = QHBoxLayout()
                dot = QLabel("●")
                dot.setStyleSheet(f"color: {STATUS.color(t['status'])};")
                row.addWidget(dot)
                name = QLabel(t["title"])
                name.setTextFormat(Qt.PlainText)
                row.addWidget(name, 1)
                row.addWidget(set_role(QLabel(f"ends {TS.to_dt(t['end_at']):%a %d %b %H:%M}"), "muted"))
                v.addLayout(row)
        else:
            v.addWidget(set_role(QLabel("Nothing open with a future end."), "muted"))

        v.addWidget(set_role(QLabel("COMPLETED PER DAY, LAST 14 DAYS"), "label"))
        v.addWidget(CountChart(s["history"], p["color"] or STATUS.color(STATUS.DONE)))
        if s["tags"]:
            v.addWidget(set_role(QLabel("BY TAG"), "label"))
            v.addLayout(self._tag_rows(s["tags"]))
        v.addStretch()
        return w
