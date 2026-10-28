"""Settings page: working hours, planning defaults, reminders, startup, backups.

Every change is saved and applied immediately (no Save button). Things with their own
screens (updates, theme, shortcuts) are linked from the bottom.
"""
import os
from datetime import datetime

from PySide6.QtCore import QTime, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractSpinBox, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from .. import autostart
from ..config import DATA_DIR
from ..data import backup as B
from .helpers import set_kind, set_role
from .theme_panel import ThemePanel

BLOCKS = (15, 30, 45, 60, 90, 120)
LEADS = ((0, "When it starts"), (5, "5 minutes before"), (10, "10 minutes before"), (15, "15 minutes before"),
         (30, "30 minutes before"))
STYLES = (("popup", "Reminder card", "The planner's own card with Now / Overdue / Next and snooze"),
          ("toast", "Windows notification", "A system notification; quieter, goes to the notification centre"),
          ("both", "Both", ""),
          ("off", "Off", "No reminders (the end-of-day review prompt has its own switch)"))
HOTKEYS = ("Ctrl+Alt+Space", "Ctrl+Alt+N", "Ctrl+Shift+Space")


def _qt(hhmm):
    h, m = (hhmm or "08:00").split(":")
    return QTime(int(h), int(m))


class SettingsPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host, self.store = host, host.store
        self.s = self.store.settings
        self._loading = True

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 20, 16)
        outer.setSpacing(10)
        outer.addWidget(set_role(QLabel("Settings"), "headline"))
        outer.addWidget(set_role(QLabel("Changes are saved and applied straight away."), "muted"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("kanban")                  # transparent background
        body = QWidget()
        body.setObjectName("kanbanInner")
        self.v = QVBoxLayout(body)
        self.v.setContentsMargins(0, 6, 12, 12)
        self.v.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self._scroll = scroll

        self._sections = {}
        self._appearance()
        self._hours()
        self._planning()
        self._reminders()
        self._startup()
        self._backups()
        self._more()
        self.v.addStretch()
        self._loading = False

    # ---- helpers
    def _card(self, title, hint=""):
        card = QFrame()
        card.setObjectName("panel")
        card.setMaximumWidth(820)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(set_role(QLabel(title.upper()), "label"))
        if hint:
            h = set_role(QLabel(hint), "hint")
            h.setWordWrap(True)
            lay.addWidget(h)
        self.v.addWidget(card)
        return lay

    def _form(self, lay):
        f = QFormLayout()
        f.setHorizontalSpacing(18)
        f.setVerticalSpacing(10)
        f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.addLayout(f)
        return f

    def _set(self, key, value, after=None):
        if self._loading:
            return
        self.s[key] = value
        self.store.save_settings()
        if after:
            after()
        self.host.refresh()

    def scroll_to(self, section):
        card = self._sections.get(section)
        if card is not None:
            self._scroll.ensureWidgetVisible(card, 0, 0)
            self._scroll.verticalScrollBar().setValue(card.y())

    # ---- sections
    def _appearance(self):
        lay = self._card("Appearance", "Light or dark, the colour everything is built from, and the "
                                       "colour style. Ctrl+, opens this section.")
        self._sections["appearance"] = lay.parentWidget()
        self.theme_panel = ThemePanel(self.host.theme)
        self.theme_panel.themeRequested.connect(lambda kw: self.host.change_theme(**kw))
        lay.addWidget(self.theme_panel)

    def _hours(self):
        lay = self._card("Working hours", "Tasks added without a time get this working day. It's also the "
                                          "week planner's shaded hours and the “Work day” button.")
        f = self._form(lay)
        row = QHBoxLayout()
        self.ws, self.we = QTimeEdit(), QTimeEdit()
        for w in (self.ws, self.we):
            w.setDisplayFormat("HH:mm")
            w.setFixedWidth(110)
            w.setButtonSymbols(QAbstractSpinBox.NoButtons)
        start, end = self.store.workday()
        self.ws.setTime(_qt(start))
        self.we.setTime(_qt(end))
        row.addWidget(self.ws)
        row.addWidget(QLabel("to"))
        row.addWidget(self.we)
        row.addStretch()
        f.addRow("Working day", row)
        self.hours_src = set_role(QLabel(), "hint")
        reset = set_kind(QPushButton("Use my routine"), "text")
        reset.setToolTip("Go back to taking the working day from your routine's first and last block")
        reset.clicked.connect(self._hours_from_routine)
        r2 = QHBoxLayout()
        r2.addWidget(self.hours_src, 1)
        r2.addWidget(reset)
        lay.addLayout(r2)
        self.ws.timeChanged.connect(self._hours_changed)
        self.we.timeChanged.connect(self._hours_changed)
        self._hours_label()

    def _hours_label(self):
        explicit = bool(self.s.get("workday_start") and self.s.get("workday_end"))
        self.hours_src.setText("Set here." if explicit else "Currently taken from your routine.")

    def _hours_changed(self, *_):
        if self._loading:
            return
        a, b = self.ws.time().toString("HH:mm"), self.we.time().toString("HH:mm")
        if b <= a:
            self.hours_src.setText("The end must be after the start.")
            return
        self.s["workday_start"], self.s["workday_end"] = a, b
        self.store.save_settings()
        self._hours_label()
        self.host.refresh()

    def _hours_from_routine(self):
        self.s["workday_start"] = self.s["workday_end"] = ""
        self.store.save_settings()
        self._loading = True
        start, end = self.store.workday()
        self.ws.setTime(_qt(start))
        self.we.setTime(_qt(end))
        self._loading = False
        self._hours_label()
        self.host.refresh()

    def _planning(self):
        lay = self._card("Planning")
        f = self._form(lay)
        self.block = QComboBox()
        for m in BLOCKS:
            self.block.addItem(f"{m} minutes" if m < 60 else (f"{m // 60} hour" + ("s" if m > 60 else "")
                                                               if m % 60 == 0 else f"{m / 60:g} hours"), m)
        self.block.setCurrentIndex(max(0, self.block.findData(int(self.s.get("block_minutes", 60)))))
        self.block.currentIndexChanged.connect(lambda *_: self._set("block_minutes", self.block.currentData()))
        f.addRow("New time block length", self.block)
        self.week_start = QComboBox()
        self.week_start.addItem("Monday", 0)
        self.week_start.addItem("Sunday", 6)
        self.week_start.setCurrentIndex(max(0, self.week_start.findData(int(self.s.get("week_start", 0)))))
        self.week_start.currentIndexChanged.connect(lambda *_: self._set("week_start", self.week_start.currentData(),
                                                                       self._reset_week))
        f.addRow("Week starts on", self.week_start)
        self.focus_len = QSpinBox()
        self.focus_len.setRange(5, 240)
        self.focus_len.setSingleStep(5)
        self.focus_len.setSuffix(" minutes")
        self.focus_len.setValue(int(self.s.get("focus_minutes", 25)))
        self.focus_len.setFixedWidth(160)
        self.focus_len.valueChanged.connect(lambda v: self._set("focus_minutes", v))
        f.addRow("Default focus session", self.focus_len)

    def _reset_week(self):
        wp = self.host.week_page
        wp.week_start = self.store.week_start_of(datetime.now().date())

    def _reminders(self):
        lay = self._card("Reminders & notifications")
        self.style_group = QButtonGroup(self)
        for key, label, hint in STYLES:
            rb = QRadioButton(label)
            rb.setProperty("key", key)
            rb.setChecked(self.s.get("notify_style", "popup") == key)
            if hint:
                rb.setToolTip(hint)
            self.style_group.addButton(rb)
            lay.addWidget(rb)
        self.style_group.buttonToggled.connect(
            lambda b, on: on and self._set("notify_style", b.property("key"), self._style_changed))
        f = self._form(lay)
        self.lead = QComboBox()
        for m, label in LEADS:
            self.lead.addItem(label, m)
        self.lead.setCurrentIndex(max(0, self.lead.findData(int(self.s.get("notify_lead_min", 0)))))
        self.lead.currentIndexChanged.connect(lambda *_: self._set("notify_lead_min", self.lead.currentData()))
        f.addRow("Remind me", self.lead)
        self.hourly = QCheckBox("Hourly check-in (skipped while a focus session runs)")
        self.hourly.setChecked(bool(self.s.get("notify_hourly", True)))
        self.hourly.toggled.connect(lambda on: self._set("notify_hourly", on))
        lay.addWidget(self.hourly)
        row = QHBoxLayout()
        self.review = QCheckBox("End-of-day review prompt at")
        self.review.setChecked(bool(self.s.get("review_enabled", True)))
        self.review.toggled.connect(lambda on: self._set("review_enabled", on))
        self.review_at = QTimeEdit()
        self.review_at.setDisplayFormat("HH:mm")
        self.review_at.setFixedWidth(110)
        self.review_at.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.review_at.setTime(_qt(self.host.app.review_time()))
        self.review_at.timeChanged.connect(lambda t: self._set("review_time", t.toString("HH:mm")))
        row.addWidget(self.review)
        row.addWidget(self.review_at)
        row.addStretch()
        test = set_kind(QPushButton("Test"), "chip")
        test.setToolTip("Show a reminder now in the chosen style")
        test.clicked.connect(lambda: self.host.app.notify())
        row.addWidget(test)
        lay.addLayout(row)
        self._style_changed()

    def _style_changed(self):
        off = self.s.get("notify_style", "popup") == "off"
        self.lead.setEnabled(not off)
        self.hourly.setEnabled(not off)

    def _startup(self):
        lay = self._card("Startup")
        self.auto = QCheckBox("Start automatically when I sign in to Windows (quietly, in the tray)")
        self.auto_hint = set_role(QLabel(), "hint")
        self.auto_hint.setWordWrap(True)
        st = autostart.state()
        self.auto.setChecked(bool(st))
        if not autostart.supported():
            self.auto.setEnabled(False)
            self.auto_hint.setText("Available in the installed Windows app.")
        elif st == "machine":
            self.auto.setEnabled(False)
            self.auto_hint.setText("Turned on for all users by the installer; change it by reinstalling "
                                   "and unticking “Start automatically”.")
        self.auto.toggled.connect(self._autostart_toggled)
        lay.addWidget(self.auto)
        lay.addWidget(self.auto_hint)
        f = self._form(lay)
        self.hotkey = QComboBox()
        for k in HOTKEYS:
            self.hotkey.addItem(k, k)
        self.hotkey.setCurrentIndex(max(0, self.hotkey.findData(self.s.get("capture_hotkey") or HOTKEYS[0])))
        self.hotkey.currentIndexChanged.connect(self._hotkey_changed)
        f.addRow("Quick add from any app", self.hotkey)
        self.hotkey_hint = set_role(QLabel(), "hint")
        lay.addWidget(self.hotkey_hint)

    def _autostart_toggled(self, on):
        if self._loading:
            return
        try:
            autostart.set_enabled(on)
            self.auto_hint.setText("")
            self.host.snack("Starts with Windows" if on else "Won't start with Windows")
        except OSError as e:
            self.auto_hint.setText(f"Couldn't change it: {e}")

    def _hotkey_changed(self, *_):
        if self._loading:
            return
        key = self.hotkey.currentData()
        self.s["capture_hotkey"] = key
        self.store.save_settings()
        got = self.host.app.set_capture_hotkey(key)
        self.hotkey_hint.setText("" if got == key else
                                 f"{key} is taken by another app; using {got}." if got else
                                 "No shortcut could be registered; another app may be using them.")

    def _backups(self):
        lay = self._card("Backups", "A copy of your planner database. One is also made automatically "
                                    "before every app upgrade changes the data format.")
        self.backup_auto = QCheckBox("Back up automatically once a day")
        self.backup_auto.setChecked(bool(self.s.get("backup_auto", True)))
        self.backup_auto.toggled.connect(lambda on: self._set("backup_auto", on))
        lay.addWidget(self.backup_auto)
        f = self._form(lay)
        row = QHBoxLayout()
        self.folder = QLineEdit(str(self.store.backup_folder()))
        self.folder.setReadOnly(True)
        change = set_kind(QPushButton("Change…"), "chip")
        change.clicked.connect(self._change_folder)
        opn = set_kind(QPushButton("Open"), "chip")
        opn.clicked.connect(lambda: self._open_folder(self.store.backup_folder()))
        row.addWidget(self.folder, 1)
        row.addWidget(change)
        row.addWidget(opn)
        f.addRow("Folder", row)
        self.keep = QSpinBox()
        self.keep.setRange(0, 365)
        self.keep.setSpecialValueText("All")
        self.keep.setSuffix(" backups")
        self.keep.setValue(int(self.s.get("backup_keep", 14)))
        self.keep.setFixedWidth(160)
        self.keep.valueChanged.connect(lambda v: self._set("backup_keep", v))
        f.addRow("Keep the newest", self.keep)
        tip = set_role(QLabel("Tip: choose a OneDrive folder to keep a copy off this PC."), "hint")
        lay.addWidget(tip)
        row = QHBoxLayout()
        self.last = set_role(QLabel(), "muted")
        row.addWidget(self.last, 1)
        now_btn = set_kind(QPushButton("Back up now"), "tonal")
        now_btn.clicked.connect(self._backup_now)
        restore = set_kind(QPushButton("Restore…"), "chip")
        restore.clicked.connect(self._restore)
        row.addWidget(now_btn)
        row.addWidget(restore)
        lay.addLayout(row)
        self._backup_label()

    def _backup_label(self):
        items = B.list_backups(self.store.backup_folder())
        if items:
            p, stamp, size = items[0]
            self.last.setText(f"Last backup {stamp:%a %d %b %Y %H:%M} ({size / 1024:.0f} KB) · {len(items)} kept")
        else:
            self.last.setText("No backups yet.")

    def _change_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Backup folder", str(self.store.backup_folder()))
        if d:
            self.s["backup_dir"] = d
            self.store.save_settings()
            self.folder.setText(d)
            self._backup_label()

    def _backup_now(self):
        try:
            p = self.store.backup_now()
            self._backup_label()
            self.host.snack(f"Backed up to {p.name}")
        except Exception as e:                       # disk full, folder gone, no permission…
            QMessageBox.warning(self, "Backup failed", str(e))

    def _restore(self):
        folder = str(self.store.backup_folder())
        path, _ = QFileDialog.getOpenFileName(self, "Restore from backup", folder, "Planner backup (*.db)")
        if not path:
            return
        ans = QMessageBox.question(
            self, "Restore backup",
            f"Replace all your planner data with this backup?\n\n{os.path.basename(path)}\n\n"
            "Your current data is backed up first. The planner needs to restart to finish; "
            "it will close now.")
        if ans != QMessageBox.Yes:
            return
        try:
            B.stage_restore(path)
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Can't restore", str(e))
            return
        self.host.app.restart()

    def _open_folder(self, path):
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _more(self):
        lay = self._card("More")
        row = QHBoxLayout()
        for label, fn in (("Updates…", lambda: self.host.app.show_updates()),
                          ("Keyboard shortcuts", self.host.show_shortcuts),
                          ("Open data folder", lambda: self._open_folder(DATA_DIR))):
            b = set_kind(QPushButton(label), "chip")
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

    def refresh(self, select=None):
        self._backup_label()
