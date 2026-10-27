"""System-wide hotkey (Windows) that works while another app has focus.

Uses Win32 RegisterHotKey on a hidden native window; WM_HOTKEY arrives through Qt's
native event filter. On other platforms register() returns None (use the tray menu).
"""
import ctypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QWidget

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
NAMED_KEYS = {"space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "insert": 0x2D,
              "home": 0x24, "end": 0x23, "pause": 0x13}
HOTKEY_ID = 0xB0B1


def parse_hotkey(text):
    """'Ctrl+Alt+Space' -> (modifier flags, virtual key) or None."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if len(parts) < 2:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in MODIFIERS:
            return None
        mods |= MODIFIERS[p]
    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in NAMED_KEYS:
        vk = NAMED_KEYS[key]
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        return None
    return mods, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        # PySide6: return (handled, result). Only WM_HOTKEY for our id is consumed.
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.owner.activated.emit()
                    return True, 0
        except Exception:   # never let a filter error break the event loop
            pass
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.registered = None
        self._filter = None
        self._window = None
        self._hwnd = None

    @property
    def supported(self):
        return sys.platform == "win32"

    def register(self, candidates):
        """Try each 'Ctrl+Alt+Space'-style combo in turn; return the one registered (or None)."""
        if not self.supported:
            return None
        self.unregister()
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        if self._filter is None:
            self._filter = _Filter(self)
            self.app.installNativeEventFilter(self._filter)
            self._window = QWidget()            # hidden; only its native handle is used
            self._hwnd = wintypes.HWND(int(self._window.winId()))
        for combo in candidates:
            parsed = parse_hotkey(combo)
            if parsed and user32.RegisterHotKey(self._hwnd, HOTKEY_ID, parsed[0] | MOD_NOREPEAT, parsed[1]):
                self.registered = combo
                return combo
        return None

    def unregister(self):
        if self.registered and self.supported:
            ctypes.windll.user32.UnregisterHotKey(self._hwnd, HOTKEY_ID)
        self.registered = None
