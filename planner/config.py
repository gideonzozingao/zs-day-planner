"""App-wide constants, paths and defaults."""
from pathlib import Path

APP_NAME = "Zuqongtech Daily Planner"
LOOKAHEAD_MIN = 180              # reminder popup looks this far ahead
REMINDER_TICK_MS = 15_000        # how often the reminder timer checks

DATA_DIR = Path.home() / ".zuqongtech_planner"
DB_FILE = DATA_DIR / "planner.db"
LEGACY_JSON = DATA_DIR / "planner.json"
ICON_DIR = DATA_DIR / "icons"

DEFAULT_SETTINGS = {
    "seed": "#6750A4", "mode": "system", "variant": "Tonal",
    "update_channel": "stable",      # "stable" | "beta"
    "update_auto": True,             # check in the background
    "update_skip": "",               # version the user chose to skip
    "focus_minutes": 25,             # default focus length for tasks without a time block
    "review_enabled": True,          # end-of-day review prompt
    "review_time": "",               # "HH:MM"; empty = start of the routine's Wrap-up block
    "review_last": "",               # date of the last completed review
    "capture_hotkey": "Ctrl+Alt+Space",
}

DEFAULT_ROUTINE = [
    ("08:00", "08:30", "Triage & planning", "Email/Teams, alerts, set priorities"),
    ("08:30", "08:50", "Team stand-up", "Blockers first"),
    ("08:50", "10:50", "Deep work #1", "Architecture / coding, notifications off"),
    ("10:50", "11:05", "Break", ""),
    ("11:05", "12:05", "Code review & PR queue", "Merge/release decisions"),
    ("12:05", "13:00", "Stakeholder window", "Requirements, UAT feedback"),
    ("13:00", "14:00", "Lunch", ""),
    ("14:00", "15:00", "Deep work #2", "Continue or R&D"),
    ("15:00", "15:45", "Team support & 1:1s", "Pairing, sprint board"),
    ("15:45", "16:15", "Reporting & admin", "Status, KPI tracking"),
    ("16:15", "16:30", "Wrap-up", "Set tomorrow's top 3"),
]

SEEDS = [
    ("Violet", "#6750A4"), ("Indigo", "#3F51B5"), ("Blue", "#1A73E8"), ("Sky", "#0288D1"),
    ("Cyan", "#00838F"), ("Teal", "#00796B"), ("Green", "#2E7D32"), ("Lime", "#7A9A01"),
    ("Amber", "#F9A825"), ("Orange", "#EF6C00"), ("Coral", "#FF6F61"), ("Red", "#C62828"),
    ("Rose", "#D81B60"), ("Purple", "#8E24AA"), ("Brown", "#795548"), ("Slate", "#546E7A"),
]
VARIANTS = ["Tonal", "Vibrant", "Faithful", "Neutral", "Mono"]

SHORTCUT_HELP = [
    ("ANYWHERE", [
        ("Ctrl+Alt+Space", "Quick add from any app"),
    ]),
    ("TASKS", [
        ("Ctrl+N", "New task"),
        ("Enter / F2", "Edit task (and its subtasks)"),
        ("Space", "Toggle done"),
        ("Delete", "Delete task (undoable)"),
        ("Ctrl+D", "Duplicate task with subtasks"),
        ("Ctrl+C", "Copy task text"),
        ("Ctrl+Shift+← / →", "Move to previous / next day"),
        ("Ctrl+H", "Task history"),
        ("Ctrl+F", "Start / stop focus on task"),
        ("Ctrl+Shift+F", "Pause / resume focus"),
        ("Ctrl+B", "Star as top task"),
        ("Ctrl+I", "Cycle status (open/in progress/done)"),
        ("Ctrl+Z", "Undo"),
        ("Right-click", "Task actions, repeat, subtasks"),
    ]),
    ("NAVIGATION", [
        ("Alt+← / →", "Previous / next day"),
        ("Ctrl+T", "Jump to today"),
        ("Ctrl+P", "Plan tomorrow"),
        ("Ctrl+E", "End-of-day review"),
        ("Ctrl+Shift+S", "Statistics"),
        ("Ctrl+L", "Focus quick add"),
        ("Ctrl+,", "Theme drawer"),
        ("Ctrl+R", "Show reminder now"),
        ("Esc", "Close drawer / clear"),
        ("Ctrl+W / Ctrl+Q", "Hide to tray / quit"),
        ("F1 / Ctrl+/", "This list"),
    ]),
    ("TASK DIALOG", [
        ("Quick add", "tomorrow 2pm-3pm #tag !high *"),
        ("Enter", "Add subtask (in the add field)"),
        ("↑ / ↓", "Move between subtasks"),
        ("Alt+↑ / ↓", "Reorder subtask"),
        ("Backspace", "Remove an empty subtask"),
        ("Ctrl+Enter", "Save"),
    ]),
]

# --- packaging / OS integration
EXE_NAME = "ZuqongtechPlanner"
APP_USER_MODEL_ID = "Zuqongtech.DailyPlanner"     # taskbar grouping / pinning (must match installer)
WIN_MUTEX = "ZuqongtechDailyPlannerMutex"         # lets the installer detect a running copy
INSTANCE_KEY = "zuqongtech-daily-planner"         # single-instance local socket name
LOG_FILE = DATA_DIR / "planner.log"

# --- updates (GitHub Releases is the update channel)
UPDATE_REPO = "gideonzozingao/zuqongtech-daily-planner"   # owner/repo that publishes releases
UPDATE_ASSET_PATTERN = r"ZuqongtechPlanner-Setup-.+\.exe"
UPDATE_FIRST_CHECK_MS = 20_000                             # after start-up
UPDATE_CHECK_EVERY_MS = 6 * 60 * 60 * 1000                 # then every 6 hours
