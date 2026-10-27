"""Entry point:  python -m planner [--tray | --capture]   (also used by the packaged .exe)

--tray     start hidden in the tray (autostart)
--capture  open quick add (or hand it to the running copy)
"""
import sys
import traceback
from datetime import datetime

from .config import APP_USER_MODEL_ID, DATA_DIR, LOG_FILE, WIN_MUTEX

_mutex = None  # keep the Windows mutex handle alive for the process lifetime


def _install_crash_log():
    """Windowed .exe builds have no console: append uncaught errors to planner.log."""
    def hook(etype, value, tb):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] ")
                traceback.print_exception(etype, value, tb, file=f)
        except OSError:
            pass
        if sys.stderr:
            sys.__excepthook__(etype, value, tb)
    sys.excepthook = hook


def _windows_integration():
    global _mutex
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, WIN_MUTEX)


def main():
    _install_crash_log()
    _windows_integration()
    from .app import PlannerApp
    capture = "--capture" in sys.argv
    PlannerApp(start_hidden=capture or "--tray" in sys.argv, capture=capture).run()


if __name__ == "__main__":
    main()
