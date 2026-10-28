# Zuqongtech Daily Planner

Material 3 tray planner: projects, tasks with subtasks, reminders, routine, SQLite storage.

Material 3 tray planner: projects, tasks with subtasks, reminders, routine, SQLite storage.

## Features

- **Quick add from anywhere**: press `Ctrl+Alt+Space` in any app (or use the Start Menu
  _Quick add_ shortcut) and type naturally:
  `Deploy staging tomorrow 2pm-3pm #dpp !high *`. Dates (`fri`, `next fri`, `31/10`, `in 3 days`),
  times (`2pm`, `14:00-15:30`, `at 3`, `for 45m`), `#tags`, `!high` / `!low` and `*`
  (top task) are understood. Put text in "quotes" to keep it literal. The main window's
  quick-add box uses the same parser.

- **Focus timer**: `Ctrl+F` on a task (or right-click → Focus). It defaults to the rest of the
  task's time block, otherwise 25 min. The tray icon shows a countdown ring, hourly reminders
  are held back while you focus, and time spent is logged per task (`⏱ 45m`).

- **End-of-day review**: prompted at your routine's _Wrap-up_ time (or `Ctrl+E`). It has three
  steps: see what got done; move unfinished tasks to the next working day (routine blocks
  excluded); plan that day and star up to 3 top tasks.

- **Snooze reminders**: the reminder popup has _Remind me in 5 / 15 / 60 min_ and _Start now_
  (which begins a focus session) alongside _Got it_.

- **Coloured tags with a filter**: tags get colours (auto, or right-click a filter chip to pick).
  The filter bar above the list narrows to one project at a time (#dpp, #autolense, #nastel…).

- **Repeating tasks**: set a task to repeat daily, on weekdays, weekly or monthly in the task
  dialog's _Repeat_ field, or the right-click _Repeat_ menu. Occurrences are created ahead
  automatically; editing or deleting one occurrence leaves the rest alone, and _Delete whole
  series_ removes them all. This is separate from the routine.

- **Start and end date-time on everything**: every task has a start and an end date-time, and
  a task can run over several days (it then shows on each day it covers, e.g.
  `14:00 → Thu 10:00`, `All day (Tue → Thu)`). The task dialog has _Starts_ / _Ends_ pickers,
  moving the start keeps the length, and quick buttons set 30 min / 1 h / 2 h / _Work day_ /
  _+1 day_. A task typed without a time (quick add, quick capture) spans the working day,
  which is taken from your routine (first block's start to last block's end; 08:00–16:30 by
  default).

- **Projects** (`Ctrl+J`): group work as _project → tasks → subtasks_. Each project has a
  colour, a start and finish date-time (both required) and a status (Planned / Active /
  On hold / Done). The project page shows progress (subtasks count toward it), time left or
  overdue, and a _Time used_ bar that flags **Behind** when the clock runs ahead of the work.
  Project tasks show in the day view (with the project's colour) and in reminders. Tasks
  outside the project's start → finish are flagged in red, and the task dialog warns about it.
  Ticking the last subtask completes its task; finishing the last task offers to complete the
  project. In the day view, right-click a task → _Add to project_, filter by project from the
  chip bar, or right-click a tag chip → _Convert #tag to a project_.
  Keys in the project tree: `Insert` add subtask, `Space` toggle, `Enter` edit/rename,
  `Alt+↑/↓` reorder, `Delete` delete (undoable), `Ctrl+Shift+N` new project.

- **Timeline (Gantt)** per project (`Ctrl+Shift+T`, or _Timeline_ next to List/Board): one row
  per task, bars from start to end (filled in by subtask progress, coloured by status), the
  project's start and finish as dashed lines, a red today line, weekends shaded, and a
  _tasks per day_ strip that shows overlaps and gaps. Bars running past the finish are
  hatched red. Drag a bar to move the task, drag its ends to change start or end (snaps to
  days zoomed out, hours zoomed in); `Ctrl+Shift+←/→` moves the selected task a day.
  Zoom with `Ctrl+wheel`, `+`/`−`, _Fit_ and _Today_. Every change is undoable.

- **Week planner** (_Week_ on the rail, `Ctrl+Shift+W`): the week as day columns with hours
  down the side, like Outlook. Whole-day and multi-day tasks sit in the _all day_ band; time
  blocks sit in the grid (overlaps side by side), with working hours, today and the current
  time marked. Drag a task from **To schedule** (open tasks still set to a whole working day,
  filterable by project) onto a slot to time-block it (1 h, 15-min snap); drag blocks to move
  them, drag a block's bottom edge to change its end, drag onto the all-day band to make it a
  whole working day again. Double-click an empty slot for a new task at that time.
  `Alt+←/→` changes week; _Work week_ / _7 days_.

- **Kanban board** for project tasks: switch a project between **List** and **Board**
  (`Ctrl+Shift+L` / `Ctrl+Shift+K`; the choice is remembered). The board has one column per
  status; drag a card to another column to change its status, or up/down to change its
  place in the project order (a line shows where it will land; the board scrolls at the
  edges). Every move is undoable (`Ctrl+Z`). Cards show the task number, title, dates (red
  when overdue), subtask progress, tags and focus time. Keyboard: `Ctrl+Shift+←/→` moves the
  selected card to the previous/next column; Space, Enter, Delete, Insert, `Ctrl+I` work as
  in the list. _Hide completed_ hides the Done and Cancelled columns.

- **Automatic numbering**: tasks in a project are numbered `#1`, `#2`, … as they're created
  (shown before the title everywhere: project tree, day view, reminders, copy text), and every
  task's subtasks are numbered as they're added, shown as `9.1`, `9.2` under task `#9`.
  Numbers are stable labels, like issue numbers: reordering doesn't change them and deleted
  numbers aren't reused. A task moved into another project gets that project's next number.
  Right-click a project → _Renumber tasks…_ makes them sequential again in the current order
  (undoable). The task dialog shows the number, or _will be #n_ for a new task.
  On upgrade, project tasks whose title already started with a typed `#12 ` keep 12 as their
  number and the typed prefix is removed from the title.

- **Task status**: every task has a status with its own colour, shown as a pill in the list:
  Open, In progress, Done, Postponed, Cancelled, Blocked. Set it from the task dialog, the
  right-click _Status_ menu, or cycle Open → In progress → Done with **Ctrl+I**. The Done
  checkbox and status stay in sync.
- **Statistics** (_Stats_ on the rail, tray, or **Ctrl+Shift+S**): a **Today** overview
  (completion %, tasks done, focus time, a status breakdown bar and per-tag progress) and an
  **Overall** view (active tasks, all-time completion, overdue count, focus time, the full
  status breakdown, a 14-day completion trend, open projects and top tags) and a **Projects**
  view: every project side by side (tasks by status, done/planned, progress against time used,
  _Behind_ flag) and per-project details (completion, progress with subtasks, overdue, focus
  time, pace vs. the pace needed to finish on time, status breakdown, next due tasks, tags and
  completions per day). The chart button on a project opens its stats directly.
- Subtasks, tags, priorities, reminders, routine, undo, history, themes, auto-updates.

## Run from source

```
pip install -r requirements.txt
python daily_planner.py            # or: python -m planner [--tray]
```

## Build the Windows installer

Requirements: Windows 10/11 x64, Python 3.10+ on PATH, Inno Setup 6.3+
(`winget install JRSoftware.InnoSetup`).

```
build.bat                          # or: .\build.ps1
```

Output:

- `dist\ZuqongtechPlanner\ZuqongtechPlanner.exe`: the app (runnable as-is)
- `dist\installer\ZuqongtechPlanner-Setup-<version>.exe`: the installer to share

### Native (harder to reverse-engineer) builds with Nuitka

PyInstaller bundles your `.py`/`.pyc` files, which decompile easily. Nuitka instead
compiles the app to C and then to a native binary, so there's no bytecode to pull out.

```
build.bat -Compiler nuitka          # or:  .\build.ps1 -Compiler nuitka
```

Needs a C compiler. On Windows, Nuitka offers to download a bundled MinGW the first
time (the build script accepts this automatically). First build is slow (a few minutes);
later builds are cached. Output is the same `dist\ZuqongtechPlanner` folder and the same
installer, so nothing else changes. In GitHub Actions, the _Release_ workflow has a
**Build with** choice (defaults to `nuitka`); tag pushes use Nuitka too.

Caveat: this raises the bar, it is not DRM. A determined attacker can still inspect a
running process. It stops casual `.pyc` decompilation, which is the common case.

Release a new version: bump `__version__` in `planner/__init__.py` and rebuild.
The installer upgrades in place (fixed AppId) and closes a running copy first.

## Releasing updates (rolling releases)

GitHub Releases is the update feed. Installed apps check it 20 s after start-up and
then every 6 hours. They offer the update through a tray notification and a message
bar, and install it silently, then restart.

**Publish**: GitHub → Actions → _Release_ → _Run workflow_. Pick:

- **bump**: `patch` (fixes), `minor` (features), `major` (breaking)
- **channel**: `stable` (everyone) or `beta` (users who opted into Beta)

The workflow bumps `planner/__init__.py`, commits, tags `vX.Y.Z`, builds on Windows and
publishes the installer and its `.sha256`. Beta versions (`1.2.0-beta.1`) are GitHub
pre-releases. Releasing `stable` after betas finalises the version (`1.2.0-beta.3` → `1.2.0`).

Fully rolling beta: uncomment `branches: [main]` in `.github/workflows/release.yml`.
Every push to main then ships the next beta.

**Local version bump**: `python scripts/bump_version.py minor beta`

**How the app finds updates**: CI keeps `stable.json` / `beta.json` on a permanent
pre-release called `update-feed`. Don't delete it. The app downloads
`releases/download/update-feed/<channel>.json`. That file is not subject to GitHub's
60-requests/hour API limit, which matters when many PCs share one office IP. Each
manifest carries the installer's SHA-256, and a download that doesn't match is discarded.

**Requirements for the feed**

- `UPDATE_REPO` in `planner/config.py` must be the repository that publishes releases.
- The repository (or at least its releases) must be public. The app reads releases
  without a token.
- Keep the asset name `ZuqongtechPlanner-Setup-<version>.exe`. The app matches it.

**Users** choose the channel, turn auto-check on or off, skip a version, or check
manually under ⋮ → _Check for updates…_ (also in the tray menu).

## What the installer does

- Installs per-user to `%LOCALAPPDATA%\Programs\Zuqongtech\Daily Planner` (no admin
  prompt); it can instead install for all users.
- Creates a Start Menu shortcut, and optionally a desktop shortcut.
- Optionally starts the app in the tray at sign-in. This is a checkbox on the setup page.
- Uninstall asks whether to also delete your data. The default is to keep it.

## Data & logs

`%USERPROFILE%\.zuqongtech_planner\`: `planner.db` (SQLite) and `planner.log`
(crash log; the .exe has no console).

## Icon

`packaging/assets/planner.ico` is generated from the theme colours:
`pip install pillow && python packaging/make_icon.py`.
