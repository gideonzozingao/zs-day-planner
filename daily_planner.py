"""Launcher kept for existing shortcuts/autostart entries.

Run:        python daily_planner.py
Autostart:  pythonw daily_planner.py --tray
Same as:    python -m planner [--tray]
"""
from planner.__main__ import main

if __name__ == "__main__":
    main()
