"""Application controller: Qt app, tray icon, reminder timer, main window."""
import math
import re
import sys
from datetime import date, datetime

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__
from .config import (
    INSTANCE_KEY, REMINDER_TICK_MS, UPDATE_CHECK_EVERY_MS, UPDATE_FIRST_CHECK_MS,
)
from .data import Store
from .single_instance import SingleInstance
from .focus import FocusTimer
from .hotkey import GlobalHotkey
from .theme import Theme, app_icon, apply_theme
from .theme.icons import focus_icon
from .utils import fmt_clock, fmt_duration
from .data import reminder_sections
from .ui import MainWindow, ReminderPopup
from .ui.quick_capture import QuickCapture
from .ui.review_dialog import ReviewDialog
from .ui.stats_dialog import StatsDialog
from .ui.update_dialog import UpdateDialog
from .updater import UpdateManager


class PlannerApp:
    def __init__(self, start_hidden=False, capture=False):
        self.qt = QApplication.instance() or QApplication(sys.argv)
        self.qt.setStyle("Fusion")
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName("Daily Planner")
        self.qt.setOrganizationName("Zuqongtech")
        self.qt.setApplicationVersion(__version__)
        self.quitting = False

        self.instance = SingleInstance(INSTANCE_KEY)
        self.already_running = self.instance.notify_running(
            "capture" if capture else ("tray" if start_hidden else "show"))
        if self.already_running:
            return                      # the running copy shows itself; run() exits
        self.instance.listen()
        self.instance.messageReceived.connect(self._on_instance_message)
        self.store = Store()
        self.qt.aboutToQuit.connect(self.store.close)
        self.theme = Theme(self.store.settings)
        apply_theme(self.qt, self.theme)
        self.theme.changed.connect(self._theme_changed)
        self.popup = None
        self.capture = None
        self.last_fired = ""
        self.snoozed = {}        # task id -> datetime until which it's hidden from reminders
        self._last_recur_day = None
        self._review_prompted = ""
        self._focus_icon_key = None

        self.focus = FocusTimer(self.store)
        self.focus.changed.connect(self._on_focus_changed)
        self.focus.tick.connect(lambda *_: self._update_focus_tray())
        self.focus.finished.connect(self._on_focus_finished)
        self.focus.stopped.connect(self._on_focus_stopped)

        self.tray = QSystemTrayIcon(app_icon(self.theme.c))
        self.menu = QMenu()

        def item(text, fn):
            act = QAction(text, self.menu)
            act.triggered.connect(lambda *_: fn())
            self.menu.addAction(act)
            return act
        item("Open planner", self.open_window)
        self.act_capture = item("Quick add…", self.show_capture)
        item("New task…", self.new_task_from_tray)
        self.menu.addSeparator()
        self.act_focus_pause = item("Pause focus", self.focus.toggle_pause)
        self.act_focus_stop = item("Stop focus", self.focus.stop)
        self.act_focus_pause.setVisible(False)
        self.act_focus_stop.setVisible(False)
        item("Review my day…", self.show_review)
        item("Statistics…", self.show_stats)
        item("Show reminder now", lambda: self.show_popup(force=True))
        item("Check for updates…", self.show_updates)
        self.menu.addSeparator()
        item("Quit", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.setToolTip(f"Daily Planner {__version__}")
        self.tray.activated.connect(
            lambda r: self.open_window() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.messageClicked.connect(self._tray_message_clicked)
        self._tray_msg = ""
        self.tray.show()

        self.window = MainWindow(self.store, self)
        if not start_hidden:
            self.window.show()

        # ---- quick capture from any app
        self.hotkey = GlobalHotkey(self.qt)
        self.hotkey.activated.connect(self.show_capture)
        wanted = self.store.settings.get("capture_hotkey") or "Ctrl+Alt+Space"
        got = self.hotkey.register([wanted, "Ctrl+Alt+N", "Ctrl+Shift+Space"])
        if got:
            self.act_capture.setText(f"Quick add…\t{got}")
        if capture:
            QTimer.singleShot(300, self.show_capture)

        try:
            self.qt.styleHints().colorSchemeChanged.connect(self._scheme_changed)
        except AttributeError:
            pass
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(REMINDER_TICK_MS)

        # ---- updates
        self.updater = UpdateManager(self.store.settings)
        self.updater.checked.connect(self._on_update_checked)
        self.updater.installStarted.connect(self.quit)
        self._update_dialog = None
        self._notified_version = ""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._auto_update_check)
        if self.updater.can_install:
            QTimer.singleShot(UPDATE_FIRST_CHECK_MS, self._auto_update_check)
            self.update_timer.start(UPDATE_CHECK_EVERY_MS)

    def _theme_changed(self):
        apply_theme(self.qt, self.theme)
        self.tray.setIcon(app_icon(self.theme.c))

    def _scheme_changed(self, *_):
        if self.theme.mode == "system":
            self.window.change_theme()

    # ---- updates
    def _auto_update_check(self):
        if self.store.settings.get("update_auto", True) and not self.updater.downloading:
            self.updater.check(manual=False)

    def _on_update_checked(self, info, manual):
        if manual or not info:
            return                                    # the dialog shows manual results
        if info["version"] in (self.store.settings.get("update_skip"), self._notified_version):
            return
        self._notified_version = info["version"]
        self._tray_msg = "update"
        self.tray.showMessage("Update available",
                              f"Daily Planner {info['version']} is ready to install. Click to see what's new.",
                              QSystemTrayIcon.Information, 10_000)
        if self.window.isVisible():
            self.window.snack(f"Version {info['version']} is available", "View", self.show_updates)

    def _tray_message_clicked(self):
        if self._tray_msg == "update":
            self.show_updates()
        elif self._tray_msg == "review":
            self.show_review()
        elif self._tray_msg in ("focus", "added"):
            self.open_window()

    def show_updates(self):
        self.open_window()
        if self._update_dialog is not None and self._update_dialog.isVisible():
            self._update_dialog.raise_()
            return
        self._update_dialog = UpdateDialog(self.window, self.updater, self.store)
        self._update_dialog.exec()
        self._update_dialog = None

    def _on_instance_message(self, msg):
        msg = msg.strip()
        if msg == "show":
            self.open_window()
        elif msg == "capture":
            self.show_capture()

    # ---- quick capture
    def show_capture(self):
        if self.capture is None:
            self.capture = QuickCapture(self.store, self._captured, self._capture_details,
                                        self.hotkey.registered or "")
        self.capture.open()

    def _captured(self, t):
        self.window.refresh()
        d = date.fromisoformat(t["date"])
        when = "today" if d == date.today() else f"{d:%a %d %b}"
        if self.window.isVisible():
            self.window.snack(f"Added “{t['title']}” to {when}", "View",
                              lambda: (self.window.go_to(d), self.window.refresh(select=t["id"])))
        else:
            self._tray_msg = "added"
            self.tray.showMessage("Task added", f"“{t['title']}”: {when}", QSystemTrayIcon.Information, 3000)

    def _capture_details(self, parsed):
        self.open_window()
        self.window.add_task(prefill=parsed)

    # ---- focus
    def _on_focus_changed(self):
        f = self.focus
        self.act_focus_pause.setVisible(f.active)
        self.act_focus_stop.setVisible(f.active)
        self._focus_icon_key = None
        if f.active:
            self.act_focus_pause.setText("Resume focus" if f.paused else "Pause focus")
            self._update_focus_tray()
        else:
            self.tray.setIcon(app_icon())
            self.tray.setToolTip(f"Daily Planner {__version__}")
        if hasattr(self, "window"):
            self.window.refresh()

    def _update_focus_tray(self):
        f = self.focus
        if not f.active:
            return
        rem = f.remaining()
        frac = rem / max(1, f.total_s)
        key = (round(frac * 48), math.ceil(rem / 60), f.paused)
        if key != self._focus_icon_key:            # redraw only when the ring/minute changes
            self._focus_icon_key = key
            self.tray.setIcon(focus_icon(frac, key[1], f.paused))
        self.tray.setToolTip(f"{'Paused' if f.paused else 'Focusing'}: {f.task['title']}  ({fmt_clock(rem)} left)")

    def _on_focus_finished(self, task, secs):
        QApplication.beep()
        self._tray_msg = "focus"
        self.tray.showMessage("Focus block complete",
                              f"{fmt_duration(secs)} on “{task['title']}”. Take a short break.",
                              QSystemTrayIcon.Information, 10_000)
        if self.window.isVisible():
            def mark_done():
                self.store.update(task["id"], done=True)
                self.window.refresh(select=task["id"])
            self.window.snack(f"Focus block complete: {fmt_duration(secs)} on “{task['title']}”",
                              "Mark done", mark_done)

    def _on_focus_stopped(self, task, secs):
        if secs >= 30 and self.window.isVisible():
            self.window.snack(f"Logged {fmt_duration(secs)} on “{task['title']}”")

    # ---- end-of-day review
    def review_time(self):
        t = self.store.settings.get("review_time") or ""
        if re.fullmatch(r"\d{2}:\d{2}", t):
            return t
        for r in self.store.routine:                 # default: the routine's wrap-up block
            if "wrap" in r["title"].lower():
                return r["start"]
        return "16:30"

    def _check_review(self, now):
        s, today = self.store.settings, now.date().isoformat()
        if not s.get("review_enabled", True) or today in (s.get("review_last"), self._review_prompted):
            return
        if now.strftime("%H:%M") < self.review_time() or not self.store.for_day(now.date()):
            return
        self._review_prompted = today
        self._tray_msg = "review"
        self.tray.showMessage("Time to wrap up", "Review today and plan tomorrow. Takes about a minute.",
                              QSystemTrayIcon.Information, 15_000)
        if self.window.isVisible():
            self.window.snack("Time to wrap up your day", "Start review", self.show_review)

    def show_stats(self):
        self.open_window()
        StatsDialog(self.window, self.store, self.theme.c).exec()

    def show_review(self):
        self.open_window()
        dlg = ReviewDialog(self.window, self.store, self.theme.c)
        if dlg.exec():
            self.window.go_to(dlg.target)
            self.window.refresh()
            self.window.snack(dlg.summary())
        else:
            self.window.refresh()

    def open_window(self):
        self.window.refresh()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def new_task_from_tray(self):
        self.open_window()
        self.window.add_task()

    def tick(self):
        now = datetime.now()
        if self._last_recur_day != now.date():       # new day (or first tick): extend series
            self._last_recur_day = now.date()
            if self.store.ensure_recurrences(today=now.date()):
                self.window.refresh()
        self._check_review(now)
        key = now.strftime("%Y-%m-%d %H:%M")
        if key == self.last_fired:
            return
        starts = {t["start"] for t in self.store.for_day(now.date())
                  if t["start"] and not t["done"]
                  and not (t["id"] in self.snoozed and now < self.snoozed[t["id"]])}
        focusing = self.focus.active and not self.focus.paused   # hold back hourly nudges
        if (now.minute == 0 and not focusing) or now.strftime("%H:%M") in starts:
            self.last_fired = key
            self.show_popup(force=False)

    def _snooze_task(self, task, minutes):
        from datetime import timedelta
        self.snoozed[task["id"]] = datetime.now() + timedelta(minutes=minutes)
        if self.window.isVisible():
            self.window.snack(f"Reminder for “{task['title']}” in {minutes} min")

    def _focus_task(self, task):
        self.open_window()
        self.window.table.setFocus()
        self.window.refresh(select=task["id"])
        self.window.start_focus()

    def show_popup(self, force=False):
        popup = ReminderPopup(self.store, self.theme, datetime.now(), self.window.refresh,
                              self.open_window, on_snooze=self._snooze_task, on_focus=self._focus_task,
                              snoozed=self.snoozed)
        if not popup.has_content and not force:
            return
        if self.popup is not None:
            self.popup.close()
        self.popup = popup
        popup.show()
        popup.raise_()

    def quit(self):
        self.quitting = True
        if self.focus.active:
            self.focus.stop()             # log the time before exiting
        self.hotkey.unregister()
        self.qt.quit()

    def run(self):
        if self.already_running:
            sys.exit(0)
        sys.exit(self.qt.exec())
