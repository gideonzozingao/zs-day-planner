"""Keyboard shortcuts for the main window. The full list lives in config.SHORTCUT_HELP."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut


def bind(owner, keys, slot, widget=None, children=False):
    """Window-wide shortcut, or one that only fires while `widget` (or, with children=True,
    any widget inside it, e.g. a focused Kanban card) has focus."""
    for k in (keys if isinstance(keys, (list, tuple)) else [keys]):
        s = QShortcut(QKeySequence(k), widget or owner)
        if widget:
            s.setContext(Qt.WidgetWithChildrenShortcut if children else Qt.WidgetShortcut)
        else:
            s.setContext(Qt.WindowShortcut)
        s.activated.connect(slot)


def install_shortcuts(win):
    t = win.table
    # task-level: only while the task list has focus, so typing elsewhere is unaffected
    bind(win, "Delete", win.delete_task, t)
    bind(win, ["F2", "Return", "Enter"], win.edit_task, t)
    bind(win, "Space", win.toggle_selected, t)
    bind(win, "Ctrl+D", win.duplicate_task, t)
    bind(win, "Ctrl+C", win.copy_task, t)
    bind(win, "Ctrl+H", win.show_history, t)
    bind(win, "Ctrl+B", win.toggle_star, t)
    bind(win, "Ctrl+I", win.cycle_status, t)
    bind(win, "Ctrl+Shift+Left", lambda: win.move_by(-1), t)
    bind(win, "Ctrl+Shift+Right", lambda: win.move_by(1), t)
    # project tree: same keys, project-aware actions
    pp = win.projects_page
    tr = pp.tree
    bind(win, "Delete", pp.delete_current, tr)
    bind(win, ["F2", "Return", "Enter"], pp.edit_current, tr)
    bind(win, "Space", pp.toggle_current, tr)
    bind(win, "Insert", pp.add_subtask, tr)
    bind(win, "Alt+Up", lambda: pp.move_current(-1), tr)
    bind(win, "Alt+Down", lambda: pp.move_current(1), tr)
    bind(win, "Ctrl+D", win.duplicate_task, tr)
    bind(win, "Ctrl+C", win.copy_task, tr)
    bind(win, "Ctrl+H", win.show_history, tr)
    bind(win, "Ctrl+B", win.toggle_star, tr)
    bind(win, "Ctrl+I", win.cycle_status, tr)
    # Kanban board: the same task keys while a card has focus, plus moving between columns
    bd = pp.board
    bind(win, "Delete", pp.delete_current, bd, True)
    bind(win, ["F2", "Return", "Enter"], pp.edit_current, bd, True)
    bind(win, "Space", pp.toggle_current, bd, True)
    bind(win, "Insert", pp.add_subtask, bd, True)
    bind(win, "Ctrl+Shift+Left", lambda: pp.move_card(-1), bd, True)
    bind(win, "Ctrl+Shift+Right", lambda: pp.move_card(1), bd, True)
    bind(win, "Ctrl+D", win.duplicate_task, bd, True)
    bind(win, "Ctrl+C", win.copy_task, bd, True)
    bind(win, "Ctrl+H", win.show_history, bd, True)
    bind(win, "Ctrl+B", win.toggle_star, bd, True)
    bind(win, "Ctrl+I", win.cycle_status, bd, True)
    # window-level
    bind(win, "Ctrl+Shift+K", lambda: (win.show_projects(), pp.set_view("board")))
    bind(win, "Ctrl+Shift+L", lambda: (win.show_projects(), pp.set_view("list")))
    bind(win, "Ctrl+N", lambda: win.add_task())
    bind(win, "Ctrl+Shift+N", win.new_project)
    bind(win, "Ctrl+J", lambda: win.show_projects())
    bind(win, "Ctrl+F", win.toggle_focus)
    bind(win, "Ctrl+Shift+F", win.app.focus.toggle_pause)
    bind(win, "Ctrl+E", lambda: win.app.show_review())
    bind(win, "Ctrl+Shift+S", win.show_stats)
    bind(win, "Ctrl+L", win.focus_quick)
    bind(win, "Ctrl+Z", win.undo)
    bind(win, "Alt+Left", lambda: win.show_day() if win.on_projects() else win.shift_day(-1))
    bind(win, "Alt+Right", lambda: win.show_day() if win.on_projects() else win.shift_day(1))
    bind(win, "Ctrl+T", win.go_today)
    bind(win, "Ctrl+P", win.plan_tomorrow)
    bind(win, "Ctrl+,", win.toggle_drawer)
    bind(win, "Ctrl+R", lambda: win.app.show_popup(force=True))
    bind(win, "Escape", win.on_escape)
    bind(win, "Ctrl+W", win.close)
    bind(win, "Ctrl+Q", win.app.quit)
    bind(win, ["F1", "Ctrl+/"], win.show_shortcuts)
