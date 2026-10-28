"""Start with Windows: the HKCU ...\\CurrentVersion\\Run value the installer also uses.

The installer writes the value under HKCU for a per-user install and HKLM for an all-users
install; this module manages the per-user one and reports a machine-wide one it can't change.
"""
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "ZuqongtechDailyPlanner"


def supported() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def _command():
    return f'"{sys.executable}" --tray'


def state():
    """-> 'user', 'machine' or '' (off). '' on other platforms."""
    if sys.platform != "win32":
        return ""
    import winreg
    for hive, name in ((winreg.HKEY_CURRENT_USER, "user"), (winreg.HKEY_LOCAL_MACHINE, "machine")):
        try:
            with winreg.OpenKey(hive, RUN_KEY) as k:
                winreg.QueryValueEx(k, VALUE)
                return name
        except OSError:
            continue
    return ""


def set_enabled(on: bool):
    """Turn the per-user autostart on/off. Raises OSError if it can't."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, VALUE, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, VALUE)
            except FileNotFoundError:
                pass
