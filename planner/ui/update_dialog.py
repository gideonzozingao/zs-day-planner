"""Updates dialog: version info, channel, auto-check, release notes, download & install."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialogButtonBox, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QTextBrowser,
)

from .. import __version__
from .dialogs import FadeDialog
from .helpers import set_kind, set_role


class UpdateDialog(FadeDialog):
    def __init__(self, parent, updater, store):
        super().__init__(parent)
        self.updater, self.store, self.s = updater, store, store.settings
        self.info = None
        self.setWindowTitle("Updates")
        self.setMinimumWidth(520)
        lay = self._frame("Updates", spacing=10)
        lay.addWidget(set_role(QLabel(f"Installed version {__version__}"), "muted"))

        lay.addWidget(set_role(QLabel("CHANNEL"), "label"))
        row = QHBoxLayout()
        row.setSpacing(8)
        grp = QButtonGroup(self)
        for key, text in (("stable", "Stable"), ("beta", "Beta")):
            b = set_kind(QPushButton(text), "chip")
            b.setCheckable(True)
            b.setChecked(self.s.get("update_channel", "stable") == key)
            grp.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._set_channel(k))
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(set_role(QLabel("Beta gets new features first; it may be less polished."), "hint"))

        self.auto = QCheckBox("Check for updates automatically")
        self.auto.setChecked(bool(self.s.get("update_auto", True)))
        self.auto.toggled.connect(self._set_auto)
        lay.addWidget(self.auto)
        lay.addSpacing(6)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        lay.addWidget(self.status)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(140)
        self.notes.setMaximumHeight(240)
        self.notes.hide()
        lay.addWidget(self.notes)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)

        actions = QHBoxLayout()
        self.skip_btn = QPushButton("Skip this version")
        self.skip_btn.clicked.connect(self._skip)
        self.check_btn = set_kind(QPushButton("Check now"), "tonal")
        self.check_btn.clicked.connect(self.check)
        self.install_btn = set_kind(QPushButton("Download && install"), "filled")
        self.install_btn.clicked.connect(self._install)
        actions.addWidget(self.skip_btn)
        actions.addStretch()
        actions.addWidget(self.check_btn)
        actions.addWidget(self.install_btn)
        lay.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        lay.addWidget(close)

        self._links = [(updater.checked, self._on_checked), (updater.checkFailed, self._on_failed),
                       (updater.progress, self._on_progress), (updater.downloaded, self._on_downloaded),
                       (updater.downloadFailed, self._on_download_failed)]
        for sig, slot in self._links:
            sig.connect(slot)

        self._show(None)
        if updater.available:
            self._show(updater.available)
        else:
            self.check()

    def done(self, r):
        if self.updater.downloading:          # don't strand a running download
            return
        for sig, slot in self._links:
            try:
                sig.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        super().done(r)

    # ---- settings
    def _save(self):
        self.store.save_settings()

    def _set_channel(self, key):
        if self.s.get("update_channel") != key:
            self.s["update_channel"] = key
            self._save()
            self.updater.available = None
            self.check()

    def _set_auto(self, on):
        self.s["update_auto"] = bool(on)
        self._save()

    # ---- states
    def check(self):
        self._show(None)
        self.status.setText("Checking for updates…")
        self.check_btn.setEnabled(False)
        self.updater.check(manual=True)

    def _show(self, info):
        self.info = info
        has = bool(info)
        self.notes.setVisible(has)
        self.skip_btn.setVisible(has)
        self.install_btn.setVisible(has)
        self.install_btn.setEnabled(has and self.updater.can_install)
        self.bar.hide()
        if not has:
            return
        tag = " (beta)" if info["prerelease"] else ""
        size = f" · {info['size'] / 1_048_576:.0f} MB" if info.get("size") else ""
        text = f"Version {info['version']}{tag} is available{size}."
        if info["version"] == self.s.get("update_skip"):
            text += " You chose to skip this version."
        if not self.updater.can_install:
            text += "\nAutomatic install works in the installed app; you're running from source."
        self.status.setText(text)
        notes = info["notes"].strip() or "_No release notes._"
        if info.get("page"):
            notes += f"\n\n[View on GitHub]({info['page']})"
        self.notes.setMarkdown(notes)

    def _on_checked(self, info, manual):
        self.check_btn.setEnabled(True)
        if info:
            self._show(info)
        else:
            self._show(None)
            channel = self.s.get("update_channel", "stable")
            self.status.setText(f"You're up to date ({__version__}, {channel} channel).")

    def _on_failed(self, msg, manual):
        self.check_btn.setEnabled(True)
        self.status.setText(f"Couldn't check for updates: {msg}")

    def _skip(self):
        if self.info:
            self.s["update_skip"] = self.info["version"]
            self._save()
            self.status.setText(f"Skipped {self.info['version']}. You'll be told about newer versions.")
            self.install_btn.hide()
            self.skip_btn.hide()

    def _install(self):
        if not self.info:
            return
        for b in (self.install_btn, self.check_btn, self.skip_btn):
            b.setEnabled(False)
        self.bar.setRange(0, 0)
        self.bar.show()
        self.status.setText("Downloading…")
        self.updater.download(self.info)

    def _on_progress(self, got, total):
        if total and total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(got * 1000 / total))
            self.status.setText(f"Downloading… {got / 1_048_576:.1f} of {total / 1_048_576:.1f} MB")

    def _on_downloaded(self, path):
        self.bar.setRange(0, 0)
        self.status.setText("Verified. Installing: the planner will close and reopen in a moment.")
        QTimer.singleShot(900, lambda: self.updater.install(path))

    def _on_download_failed(self, msg):
        self.bar.hide()
        self.status.setText(msg)
        for b in (self.install_btn, self.check_btn, self.skip_btn):
            b.setEnabled(True)
