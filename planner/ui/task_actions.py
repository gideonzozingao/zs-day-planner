"""Task operations, undo stack and the right-click menu, mixed into MainWindow.

Expects the host to provide: store, theme, table, quick, current, _undo,
refresh(select=None), snack(...), go_to(date), on_projects(), projects_page, show_projects(...).
On the projects page, "the selected task" is the task selected in the project tree.
"""
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox

from ..focus import PRESETS, default_minutes
from .. import recurrence as R
from .. import status as STATUS
from ..theme.icons import status_dot
from ..quickparse import HIGH, LOW, NORMAL, PRIORITY_NAMES, parse
from ..theme import make_icon
from ..timespan import span_label
from .dialogs import DatePickerDialog, HistoryDialog, ShortcutsDialog
from .project_dialog import ProjectDialog, dot_icon
from .task_dialog import TaskDialog


class TaskActionsMixin:
    # ---- selection
    def selected_id(self):
        if self.on_projects():
            return self.projects_page.selected_task_id()
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _selected_task(self):
        return self.store.find(self.selected_id())

    # ---- undo
    def _push_undo(self, label, fn):
        """fn() reverts the change and may return a task id to re-select."""
        self._undo.append((label, fn))
        del self._undo[:-30]

    def undo(self):
        if not self._undo:
            self.snack("Nothing to undo")
            return
        label, fn = self._undo.pop()
        sel = fn()
        self.refresh(select=sel if isinstance(sel, str) else None)
        self.snack(f"Undone: {label}")

    # ---- create / edit
    def quick_add(self):
        """Natural-language add; with no date given, the task goes on the day being viewed."""
        p = parse(self.quick.text(), date.today())
        if not p.title:
            return
        d = p.date or self.current
        t = self.store.add(d, p.title, p.start, p.end, priority=p.priority, tags=" ".join(p.tags),
                           pinned=p.pinned)
        self.quick.clear()
        if d == self.current:
            self.refresh(select=t["id"])
        else:
            self.refresh()
            self.snack(f"Added to {d:%a %d %b}", "View",
                       lambda: (self.go_to(d), self.refresh(select=t["id"])))

    def _project_choices(self, current=""):
        """Open projects for the Project field, plus the task's own project even if it's done."""
        ps = self.store.projects(include_done=False)
        if current and all(p["id"] != current for p in ps):
            p = self.store.project(current)
            if p:
                ps.append(p)
        return ps

    def _after_save(self, tid, day):
        """Show a just-saved task where it lives: its project page, or its start day."""
        if self.on_projects():
            t = self.store.find(tid)
            if t and t["project_id"] and t["project_id"] != self.projects_page.current_id:
                self.projects_page.show_project(t["project_id"], select_task=tid)
            else:
                self.refresh(select=tid)
            if t and not t["project_id"]:
                self.snack(f"Saved to {day:%a %d %b}", "View", lambda: self.show_day(day, select=tid))
        else:
            visible = any(x["id"] == tid for x in self.store.for_day(self.current))
            if not visible:
                self.go_to(day)
            self.refresh(select=tid)

    def add_task(self, prefill=None):
        """New task. On the projects page it goes into the open project, starting no earlier
        than the project does."""
        in_project = self.projects_page.current_id if self.on_projects() else ""
        if prefill is not None and prefill.date:
            start_day = prefill.date
        else:
            start_day = None if in_project else self.current
        dlg = TaskDialog(self, start_day, self.theme.c, prefill=prefill,
                         projects=self._project_choices(in_project), project_id=in_project,
                         workday=self.store.workday())
        if dlg.exec():
            v = dlg.values()
            t = self.store.add(None, v["title"], note=v["note"], start_at=v["start_at"], end_at=v["end_at"],
                               subtasks=v["subtasks"], priority=v["priority"], tags=v["tags"],
                               pinned=v["pinned"], recurrence=v["recurrence"], project_id=v["project_id"],
                               status=v["status"])
            self._after_save(t["id"], v["date"])

    def edit_task(self):
        task = self._selected_task()
        if not task:
            return
        dlg = TaskDialog(self, None, self.theme.c, task, self.store.subtasks(task["id"]),
                         projects=self._project_choices(task["project_id"]), workday=self.store.workday())
        if dlg.exec():
            v = dlg.values()
            self.store.update(task["id"], start_at=v["start_at"], end_at=v["end_at"], title=v["title"],
                              note=v["note"],
                              priority=v["priority"], tags=v["tags"], pinned=v["pinned"],
                              project_id=v["project_id"], status=v["status"])
            if v["status"] == STATUS.DONE and not task["done"]:
                self.task_done_changed(task["id"])
            self.store.set_subtasks(task["id"], v["subtasks"])
            if v["recurrence"] != task["recurrence"]:
                self.store.set_recurrence(task["id"], v["recurrence"])
            self._after_save(task["id"], v["date"])

    def toggle_selected(self):
        task = self._selected_task()
        if task:
            self.store.update(task["id"], done=not task["done"])
            self.refresh(select=task["id"])
            self.task_done_changed(task["id"])

    def toggle_subtask(self, tid, sid, done):
        """Tick/untick a subtask. Ticking the last open one completes the task (undoable);
        unticking one under a done task reopens it."""
        self.store.set_subtask_done(sid, done)
        task = self.store.find(tid)
        if task and done and not task["done"] and task["sub_total"] and task["sub_done"] == task["sub_total"]:
            self.store.update(tid, done=True)
            self._push_undo("auto-complete", lambda: (self.store.update(tid, done=False), tid)[1])
            self.refresh(select=tid)
            self.snack("All subtasks done, so the task is marked done", "Undo", self.undo)
            self.task_done_changed(tid)
            return
        if task and not done and task["done"]:
            self.store.update(tid, done=False)
            self.refresh(select=tid)
            self.snack(f"Reopened “{task['title']}”: it has an open subtask again")
            return
        self.refresh(select=tid)

    def task_done_changed(self, tid):
        """After a task is completed: if it was the last open task in its project, offer to close it."""
        t = self.store.find(tid)
        if not t or t["status"] not in (STATUS.DONE, STATUS.CANCELLED) or not t["project_id"]:
            return
        p = self.store.project(t["project_id"])
        if not p or p["status"] == "done":
            return
        s = self.store.project_summary(p["id"])
        if s["tasks"] and s["done"] == s["tasks"]:      # cancelled tasks don't count
            def close():
                self.store.update_project(p["id"], status="done")
                self.refresh()
                self.snack(f"Project “{p['name']}” completed")
            self.snack(f"Every task in “{p['name']}” is done", "Complete project", close)

    def toggle_star(self):
        task = self._selected_task()
        if not task:
            return
        self.store.update(task["id"], pinned=not task["pinned"])
        self.refresh(select=task["id"])
        if not task["pinned"]:
            n = sum(t["pinned"] for t in self.store.for_day(date.fromisoformat(task["date"])))
            if n > 3:
                self.snack(f"{n} top tasks on this day. Three or fewer keeps them meaningful")

    def set_priority(self, value):
        task = self._selected_task()
        if task:
            self.store.update(task["id"], priority=value)
            self.refresh(select=task["id"])

    # ---- focus
    def start_focus(self, minutes=None):
        task = self._selected_task()
        if not task:
            self.snack("Select a task to focus on")
            return
        if task["done"]:
            self.store.update(task["id"], done=False)
        minutes = minutes or default_minutes(task, datetime.now(), int(self.store.settings.get("focus_minutes", 25)))
        self.app.focus.start(task, minutes)
        self.refresh(select=task["id"])

    def focus_custom(self):
        n, ok = QInputDialog.getInt(self, "Focus", "Minutes:", int(self.store.settings.get("focus_minutes", 25)), 1, 240, 5)
        if ok:
            self.start_focus(n)

    def toggle_focus(self):
        """Ctrl+F: stop the running session, or start one on the selected task."""
        if self.app.focus.active:
            self.app.focus.stop()
        else:
            self.start_focus()

    def _focus_menu(self, menu, task):
        f = self.app.focus
        sm = menu.addMenu(self._icon("timer"), "Focus")
        if f.is_on(task["id"]):
            self._menu_action(sm, "Resume" if f.paused else "Pause", f.toggle_pause,
                              "play" if f.paused else "pause", "Ctrl+Shift+F")
            self._menu_action(sm, "+5 minutes", lambda: f.extend(5))
            self._menu_action(sm, "Stop and log time", f.stop, "stop", "Ctrl+F")
            return
        auto = default_minutes(task, datetime.now(), int(self.store.settings.get("focus_minutes", 25)))
        if auto not in PRESETS and auto != int(self.store.settings.get("focus_minutes", 25)):
            self._menu_action(sm, f"For this time block ({auto} min)", lambda: self.start_focus(auto),
                              "timer", "Ctrl+F")
        for n in PRESETS:
            keys = "Ctrl+F" if n == auto else ""
            self._menu_action(sm, f"{n} minutes", lambda _=False, n=n: self.start_focus(n), keys=keys)
        self._menu_action(sm, "Custom…", self.focus_custom)

    def set_recurrence_quick(self, rule):
        task = self._selected_task()
        if not task:
            return
        self.store.set_recurrence(task["id"], rule)
        self.refresh(select=task["id"])
        self.snack("Repeat turned off" if not rule
                   else f"Repeats {R.describe(rule, date.fromisoformat(task['date'])).lower()}")

    def _repeat_menu(self, menu, task):
        anchor = date.fromisoformat(task["date"])
        current = task["recurrence"]
        title = f"Repeat: {R.short_label(current)}" if current else "Repeat"
        sm = menu.addMenu(self._icon("event"), title)
        for rule in (R.NONE, R.DAILY, R.WEEKDAYS, R.WEEKLY, R.MONTHLY):
            label = R.describe(rule, anchor) if rule else "Does not repeat"
            a = self._menu_action(sm, label, lambda _=False, r=rule: self.set_recurrence_quick(r))
            a.setCheckable(True)
            a.setChecked(current == rule)

    def set_status(self, status):
        task = self._selected_task()
        if task and task["status"] != status:
            old = task["status"]
            self.store.set_status(task["id"], status)
            self._push_undo("status", lambda tid=task["id"]: (self.store.set_status(tid, old), tid)[1])
            self.refresh(select=task["id"])
            self.task_done_changed(task["id"])

    def cycle_status(self):
        """Ctrl+I steps Open -> In progress -> Done (the common path)."""
        task = self._selected_task()
        if not task:
            return
        nxt = {STATUS.OPEN: STATUS.IN_PROGRESS, STATUS.IN_PROGRESS: STATUS.DONE,
               STATUS.DONE: STATUS.OPEN}.get(task["status"], STATUS.IN_PROGRESS)
        old = task["status"]
        self.store.set_status(task["id"], nxt)
        self._push_undo("status", lambda tid=task["id"]: (self.store.set_status(tid, old), tid)[1])
        self.refresh(select=task["id"])
        self.snack(f"Marked {STATUS.label(nxt).lower()}", "Undo", self.undo)
        self.task_done_changed(task["id"])

    def _status_menu(self, menu, task):
        sm = menu.addMenu(status_dot(STATUS.color(task["status"])), f"Status: {STATUS.label(task['status'])}")
        for st in STATUS.ORDER:
            a = QAction(status_dot(STATUS.color(st)), STATUS.label(st), sm)
            a.setCheckable(True)
            a.setChecked(task["status"] == st)
            a.triggered.connect(lambda _=False, v=st: self.set_status(v))
            sm.addAction(a)
        return sm

    def _priority_menu(self, menu, task):
        sm = menu.addMenu(self._icon("bolt"), f"Priority: {PRIORITY_NAMES[task['priority']]}")
        for value in (HIGH, NORMAL, LOW):
            a = self._menu_action(sm, PRIORITY_NAMES[value], lambda _=False, v=value: self.set_priority(v))
            a.setCheckable(True)
            a.setChecked(task["priority"] == value)

    def duplicate_task(self):
        task = self._selected_task()
        if not task:
            return
        t = self.store.duplicate(task["id"])
        self._push_undo("duplicate", lambda tid=t["id"]: self.store.delete(tid) and None)
        self.refresh(select=t["id"])
        self.snack("Task duplicated", "Undo", self.undo)

    def copy_task(self):
        task = self._selected_task()
        if not task:
            return
        when = span_label(task["start_at"], task["end_at"]) + "  "
        lines = [f"{when}{task['title']}" + (f" — {task['note']}" if task["note"] else "")]
        lines += [f"  [{'x' if s['done'] else ' '}] {s['title']}" for s in self.store.subtasks(task["id"])]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.snack("Copied to clipboard")

    def delete_task(self):
        task = self._selected_task()
        if not task:
            return
        row = self.table.currentRow()
        snapshot = self.store.delete(task["id"])          # includes subtasks for undo
        self._push_undo("delete", lambda t=snapshot: (self.store.restore(t), t["id"])[1])
        self.refresh()
        if self.table.rowCount():
            self.table.setCurrentCell(min(row, self.table.rowCount() - 1), 3)
            self.table.setFocus()
        if task["recurrence"]:
            self.snack(f"Deleted this occurrence of \u201c{task['title']}\u201d",
                       "Delete whole series", lambda t=task: self._delete_series(t))
        else:
            self.snack(f"Deleted \u201c{task['title']}\u201d", "Undo", self.undo)

    def _delete_series(self, task):
        n = self.store.delete_series(task["id"])
        self.refresh()
        self.snack(f"Deleted all {n} occurrence(s) of \u201c{task['title']}\u201d")

    # ---- move
    def move_task(self, target: date):
        task = self._selected_task()
        if not task or task["date"] == target.isoformat():
            return
        old = task["date"]
        self.store.update(task["id"], date=target)
        self._push_undo("move", lambda tid=task["id"], d=old: (self.store.update(tid, date=d), tid)[1])
        self.refresh()
        self.snack(f"Moved to {target:%a %d %b}", "Undo", self.undo)

    def move_by(self, days):
        task = self._selected_task()
        if task:
            self.move_task(date.fromisoformat(task["date"]) + timedelta(days=days))

    def move_to_picked(self):
        task = self._selected_task()
        if not task:
            return
        dlg = DatePickerDialog(self, date.fromisoformat(task["date"]))
        if dlg.exec():
            self.move_task(dlg.value())

    # ---- info
    def show_history(self):
        task = self._selected_task()
        if task:
            HistoryDialog(self, task, self.store.history(task["id"])).exec()

    def show_shortcuts(self):
        ShortcutsDialog(self).exec()

    # ---- day-level
    def load_routine(self):
        n = self.store.load_routine(self.current)
        self.refresh()
        self.snack(f"Added {n} routine block(s)" if n else "Routine already loaded for this day")

    def save_routine(self):
        if QMessageBox.question(self, "Save routine",
                                "Replace your saved routine with this day's timed tasks?") == QMessageBox.Yes:
            self.store.save_as_routine(self.current)
            self.snack("Routine saved")

    def carry_over(self):
        nxt = self.current + timedelta(days=1)
        n = self.store.carry_over(self.current, nxt)
        self.refresh()
        self.snack(f"Copied {n} unfinished task(s) to {nxt:%a %d %b}", "View", lambda: self.go_to(nxt))

    def plan_tomorrow(self):
        tomorrow = date.today() + timedelta(days=1)
        self.go_to(tomorrow)
        if not self.store.for_day(tomorrow):
            ans = QMessageBox.question(
                self, "Plan tomorrow",
                "Tomorrow is empty.\n\nLoad your routine and carry over today's unfinished tasks?")
            if ans == QMessageBox.Yes:
                self.store.load_routine(tomorrow)
                self.store.carry_over(date.today(), tomorrow)
                self.refresh()
        self.quick.setFocus()

    # ---- context menu
    def _icon(self, name):
        return make_icon(name, self.theme.c["onSurfaceVariant"])

    def _menu_action(self, menu, text, slot, icon=None, keys=""):
        a = QAction(self._icon(icon) if icon else QIcon(), f"{text}\t{keys}" if keys else text, menu)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _subtask_menu(self, menu, task):
        subs = self.store.subtasks(task["id"])
        title = f"Subtasks ({task['sub_done']}/{task['sub_total']})" if subs else "Subtasks"
        sm = menu.addMenu(self._icon("checklist"), title)
        for s in subs:
            a = QAction(s["title"].replace("&", "&&"), sm)
            a.setCheckable(True)
            a.setChecked(s["done"])
            a.toggled.connect(lambda checked, tid=task["id"], sid=s["id"]: self.toggle_subtask(tid, sid, checked))
            sm.addAction(a)
        if subs:
            sm.addSeparator()
        self._menu_action(sm, "Add / edit subtasks…", self.edit_task, "edit", "F2")

    def assign_project(self, pid):
        task = self._selected_task()
        if not task or task["project_id"] == pid:
            return
        old = task["project_id"]
        self.store.update(task["id"], project_id=pid)
        self._push_undo("project", lambda tid=task["id"]: (self.store.update(tid, project_id=old), tid)[1])
        self.refresh(select=task["id"])
        p = self.store.project(pid)
        self.snack(f"Added to “{p['name']}”" if p else "Removed from project", "Undo", self.undo)

    def assign_new_project(self):
        task = self._selected_task()
        if not task:
            return
        dlg = ProjectDialog(self, used_colors=[x["color"] for x in self.store.projects(include_done=False)],
                            workday=self.store.workday())
        if dlg.exec():
            p = self.store.add_project(**dlg.values())
            self.assign_project(p["id"])

    def _project_menu(self, menu, task):
        current = self.store.project(task["project_id"]) if task["project_id"] else None
        sm = menu.addMenu(self._icon("folder"), f"Project: {current['name']}" if current else "Add to project")
        for p in self._project_choices(task["project_id"]):
            a = self._menu_action(sm, p["name"].replace("&", "&&"),
                                  lambda _=False, pid=p["id"]: self.assign_project(pid))
            a.setIcon(dot_icon(p["color"]))
            a.setCheckable(True)
            a.setChecked(p["id"] == task["project_id"])
        if sm.actions():
            sm.addSeparator()
        self._menu_action(sm, "New project…", self.assign_new_project, "add")
        if current:
            self._menu_action(sm, "Remove from project", lambda: self.assign_project(""))
            sm.addSeparator()
            self._menu_action(sm, f"Open “{current['name']}”".replace("&", "&&"),
                              lambda: self.show_projects(current["id"], select=task["id"]), "folder")

    def _show_menu(self, global_pos, row):
        menu = QMenu(self)
        add = lambda *a, **k: self._menu_action(menu, *a, **k)
        task = None
        if row >= 0:
            self.table.setCurrentCell(row, 3)
            task = self._selected_task()
        if task:
            add("Mark as not done" if task["done"] else "Mark as done", self.toggle_selected, "check", "Space")
            self._status_menu(menu, task)
            add("Edit…", self.edit_task, "edit", "F2")
            self._focus_menu(menu, task)
            add("Unstar" if task["pinned"] else "Star as top task", self.toggle_star,
                "star_outline" if task["pinned"] else "star", "Ctrl+B")
            self._priority_menu(menu, task)
            self._repeat_menu(menu, task)
            self._subtask_menu(menu, task)
            self._project_menu(menu, task)
            add("Duplicate", self.duplicate_task, "add", "Ctrl+D")
            add("Copy text", self.copy_task, "copy", "Ctrl+C")
            move = menu.addMenu(self._icon("event"), "Move to")
            today = date.today()
            tdate = date.fromisoformat(task["date"])
            for label, d, keys in (("Today", today, ""), ("Tomorrow", today + timedelta(days=1), ""),
                                   ("Previous day", tdate - timedelta(days=1), "Ctrl+Shift+←"),
                                   ("Next day", tdate + timedelta(days=1), "Ctrl+Shift+→")):
                a = self._menu_action(move, label, lambda _=False, d=d: self.move_task(d), keys=keys)
                a.setEnabled(d != tdate)
            move.addSeparator()
            self._menu_action(move, "Pick a date…", self.move_to_picked)
            add("History…", self.show_history, "history", "Ctrl+H")
            menu.addSeparator()
            add("Delete", self.delete_task, "delete", "Del")
        else:
            add("New task…", lambda: self.add_task(), "add", "Ctrl+N")
            add("Load routine", self.load_routine, "event")
            add("Carry unfinished to next day", self.carry_over)
            if self._undo:
                menu.addSeparator()
                add(f"Undo {self._undo[-1][0]}", self.undo, "undo", "Ctrl+Z")
        menu.exec(global_pos)
