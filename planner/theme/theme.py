"""Live theme object: holds settings, rebuilds the colour scheme, emits `changed`."""
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication

from .colors import make_scheme


def system_dark():
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


class Theme(QObject):
    changed = Signal()

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings          # shared with Store.settings
        self.c = {}
        self.rebuild()

    @property
    def seed(self):
        return self.settings["seed"]

    @property
    def mode(self):
        return self.settings["mode"]

    @property
    def variant(self):
        return self.settings["variant"]

    @property
    def dark(self):
        return self.mode == "dark" or (self.mode == "system" and system_dark())

    def rebuild(self):
        self.c = make_scheme(self.seed, self.variant, self.dark)

    def set(self, **kw):
        self.settings.update(kw)
        self.rebuild()
        self.changed.emit()
