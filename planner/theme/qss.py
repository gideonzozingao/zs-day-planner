"""Application stylesheet. Tokens like @primary@ or @onSurface:0.08@ are filled from the scheme."""
import re

from PySide6.QtGui import QColor, QPalette

from ..config import ICON_DIR
from .icons import ARROW_PATH, CHECK_PATH, ICONS

QSS = """
QWidget { color: @onSurface@; font-size: 14px; }
QMainWindow, QWidget#root { background: @surface@; }
QDialog, QMessageBox { background: @surfaceContainerHigh@; }
QLabel { background: transparent; }
QLabel[role="headline"] { font-size: 30px; }
QLabel[role="title"] { font-size: 22px; }
QLabel[role="label"] { color: @onSurfaceVariant@; font-size: 12px; font-weight: 600; }
QLabel[role="muted"] { color: @onSurfaceVariant@; }
QLabel[role="hint"] { color: @onSurfaceVariant@; font-size: 11px; }
QLabel[role="accent"] { color: @primary@; font-size: 12px; font-weight: 600; }
QLabel[role="danger"] { color: @error@; font-size: 12px; font-weight: 600; }
QLabel[role="kbd"] { background: @surfaceContainerHighest@; color: @onSurface@; border: 1px solid @outlineVariant@;
                     border-radius: 6px; padding: 3px 8px; font-family: Consolas, "Cascadia Mono", monospace;
                     font-size: 12px; }
QLabel#iconCircle { background: @primaryContainer@; border-radius: 20px; }
QFrame#rail { background: @surface@; }
QFrame#panel { background: @surfaceContainerLow@; border-radius: 24px; }
QFrame#drawer { background: @surfaceContainer@; border-top-left-radius: 28px; border-bottom-left-radius: 28px; }
QFrame#popupCard { background: @surfaceContainerHigh@; border-radius: 28px; }
QFrame#snackbar { background: @inverseSurface@; border-radius: 8px; }
QFrame#snackbar QLabel { color: @inverseOnSurface@; }
QFrame#subtaskCard { background: @surfaceContainer@; border-radius: 16px; }

QPushButton { min-height: 40px; padding: 0 20px; border-radius: 20px; border: none;
              background: transparent; color: @primary@; font-weight: 600; }
QPushButton:hover { background: @primary:0.08@; }
QPushButton:pressed { background: @primary:0.12@; }
QPushButton::menu-indicator { image: none; width: 0; }
QPushButton#snackAction { color: @inversePrimary@; min-height: 36px; padding: 0 12px; border-radius: 18px; }
QPushButton#snackAction:hover { background: @inversePrimary:0.12@; }
QPushButton[kind="filled"] { background: @primary@; color: @onPrimary@; }
QPushButton[kind="filled"]:hover { background: @primaryHover@; }
QPushButton[kind="filled"]:pressed { background: @primaryPressed@; }
QPushButton[kind="tonal"] { background: @secondaryContainer@; color: @onSecondaryContainer@; }
QPushButton[kind="tonal"]:hover { background: @secondaryHover@; }
QPushButton[kind="tonal"]:pressed { background: @secondaryPressed@; }
QPushButton[kind="icon"] { min-width: 40px; max-width: 40px; padding: 0; color: @onSurfaceVariant@; }
QPushButton[kind="icon"]:hover { background: @onSurface:0.08@; }
QPushButton[kind="icon"]:pressed { background: @onSurface:0.12@; }
QPushButton[kind="iconSmall"] { min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px;
                                padding: 0; border-radius: 16px; }
QPushButton[kind="iconSmall"]:hover { background: @onSurface:0.08@; }
QPushButton[kind="fab"] { min-height: 56px; padding: 0 24px; border-radius: 16px;
                          background: @primaryContainer@; color: @onPrimaryContainer@; }
QPushButton[kind="fab"]:hover { background: @primaryContainerHover@; }
QPushButton[kind="tagchip"] { min-height: 30px; padding: 0 12px; border-radius: 8px; font-weight: 600; }
QPushButton[kind="chip"] { min-height: 32px; padding: 0 14px; border-radius: 8px;
                           border: 1px solid @outline@; color: @onSurfaceVariant@; font-weight: 500; }
QPushButton[kind="chip"]:hover { background: @onSurface:0.08@; }
QPushButton[kind="chip"]:checked { background: @secondaryContainer@; color: @onSecondaryContainer@;
                                   border: 1px solid transparent; }

QToolButton#railBtn { background: transparent; border: none; border-radius: 16px;
                      color: @onSurfaceVariant@; font-size: 12px; font-weight: 600; }
QToolButton#railBtn:hover { background: @onSurface:0.08@; }
QToolButton#railBtn:checked { background: @secondaryContainer@; color: @onSecondaryContainer@; }

QLineEdit, QDateEdit, QDateTimeEdit, QTimeEdit, QPlainTextEdit {
    background: transparent; border: 1px solid @outline@; border-radius: 8px; padding: 10px 14px;
    selection-background-color: @primaryContainer@; selection-color: @onPrimaryContainer@; }
QLineEdit:hover, QDateEdit:hover, QDateTimeEdit:hover, QTimeEdit:hover, QPlainTextEdit:hover { border-color: @onSurface@; }
QLineEdit:focus, QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus, QPlainTextEdit:focus {
    border: 2px solid @primary@; padding: 9px 13px; }
QLineEdit:disabled, QTimeEdit:disabled, QDateEdit:disabled, QDateTimeEdit:disabled, QComboBox:disabled {
    border-color: @outlineVariant@; color: @outline@; }
QCheckBox:disabled { color: @outline@; }
QLineEdit[flat="true"] { border: 1px solid transparent; padding: 6px 8px; }
QLineEdit[flat="true"]:hover { border-color: @outlineVariant@; }
QLineEdit[flat="true"]:focus { border: 2px solid @primary@; padding: 5px 7px; }
QLineEdit[done="true"] { color: @outline@; text-decoration: line-through; }
/* Time fields hide their spin arrows (setButtonSymbols(NoButtons)). With a styled spin box,
   Qt needs explicit zero-width button rules anchored to the border, otherwise it collapses
   the text area to 1 px and the time is invisible and can't be typed. */
QTimeEdit::up-button, QTimeEdit::down-button { subcontrol-origin: border; width: 0px; border: none; }
QTimeEdit::up-arrow, QTimeEdit::down-arrow { image: none; width: 0px; height: 0px; }
QDateEdit::drop-down, QDateTimeEdit::drop-down { border: none; width: 28px; }
QDateEdit::down-arrow, QDateTimeEdit::down-arrow { image: url("@arrow@"); width: 18px; height: 18px; }
QCalendarWidget QWidget { background: @surfaceContainerHigh@; }
QCalendarWidget QToolButton { color: @onSurface@; background: transparent; border-radius: 8px; padding: 6px 10px; }
QCalendarWidget QToolButton:hover { background: @onSurface:0.08@; }
QCalendarWidget QAbstractItemView:enabled { color: @onSurface@; background: @surfaceContainerHigh@;
    selection-background-color: @primary@; selection-color: @onPrimary@; }
QCalendarWidget QAbstractItemView:disabled { color: @outline@; }
QCalendarWidget QSpinBox { padding: 2px 6px; }

QCheckBox { spacing: 12px; }
QCheckBox::indicator, QTableView::indicator, QTreeView::indicator { width: 18px; height: 18px; border: 2px solid @outline@;
    border-radius: 4px; background: transparent; }
QCheckBox::indicator:checked, QTableView::indicator:checked, QTreeView::indicator:checked { background: @primary@;
    border-color: @primary@; image: url("@check@"); }

QTableWidget { background: transparent; border: none; gridline-color: transparent;
    selection-background-color: @secondaryContainer@; selection-color: @onSecondaryContainer@; }
QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid @outlineVariant@; }
QTableWidget::item:selected { background: @secondaryContainer@; color: @onSecondaryContainer@; }
QTreeWidget { background: transparent; border: none; outline: 0;
    selection-background-color: @secondaryContainer@; selection-color: @onSecondaryContainer@; }
QTreeWidget::item { min-height: 40px; padding: 2px 6px; border-bottom: 1px solid @outlineVariant@; }
QTreeWidget::item:selected { background: @secondaryContainer@; color: @onSecondaryContainer@; }
QTreeWidget::item:hover:!selected { background: @onSurface:0.05@; }
QTreeWidget::branch { background: transparent; border-bottom: 1px solid @outlineVariant@; }
QTreeWidget::branch:selected { background: @secondaryContainer@; }
QTreeWidget::branch:has-children:closed { image: url("@chev@"); }
QTreeWidget::branch:has-children:open { image: url("@arrow@"); }
QTreeWidget QLineEdit { padding: 4px 8px; }
QListWidget#projectList { background: transparent; border: none; outline: 0; }
QListWidget#projectList::item { border-radius: 16px; margin: 0 0 6px 0; background: @surfaceContainerLow@; }
QListWidget#projectList::item:hover { background: @surfaceContainer@; }
QListWidget#projectList::item:selected { background: @secondaryContainer@; }
QSplitter::handle { background: transparent; }
QListWidget#taskPool { background: transparent; border: none; outline: 0; }
QListWidget#taskPool::item { background: @surface@; border: 1px solid @outlineVariant@; border-radius: 10px;
    padding: 8px 8px; margin: 0 0 6px 0; color: @onSurface@; }
QListWidget#taskPool::item:hover { border-color: @outline@; }
QListWidget#taskPool::item:selected { border: 2px solid @primary@; background: @surface@; color: @onSurface@; }
QScrollArea#kanban, QWidget#kanbanInner { background: transparent; border: none; }
QFrame#kanbanColumn { background: @surfaceContainer@; border-radius: 16px; border: 2px solid transparent; }
QFrame#kanbanColumn[dropTarget="true"] { border: 2px dashed @primary@; background: @primary:0.08@; }
QFrame#kanbanCard { background: @surface@; border: 1px solid @outlineVariant@; border-radius: 12px; }
QFrame#kanbanCard:hover { border-color: @outline@; }
QFrame#kanbanCard[late="true"] { border-left: 4px solid @error@; }
QFrame#kanbanCard[selected="true"] { border: 2px solid @primary@; }
QFrame#kanbanCard[dragging="true"] { background: @surfaceContainerHigh@; border: 1px dashed @outline@; }
QFrame#kanbanCard QLabel { background: transparent; }
QHeaderView { background: transparent; }
QHeaderView::section { text-align: left; background: transparent; color: @onSurfaceVariant@; border: none;
    border-bottom: 1px solid @outlineVariant@; padding: 10px 8px; font-weight: 600; }
QTableCornerButton::section { background: transparent; border: none; }

QProgressBar { background: @secondaryContainer@; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }
QProgressBar::chunk { background: @primary@; border-radius: 4px; }
QProgressBar[thin="true"] { max-height: 4px; min-height: 4px; border-radius: 2px; }
QProgressBar[thin="true"]::chunk { border-radius: 2px; }

QScrollBar:vertical { background: transparent; width: 12px; margin: 4px 2px; }
QScrollBar::handle:vertical { background: @outlineVariant@; border-radius: 4px; min-height: 36px; }
QScrollBar::handle:vertical:hover { background: @outline@; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QMenu { background: @surfaceContainer@; border: 1px solid @outlineVariant@; border-radius: 4px; padding: 8px 0; }
QMenu::item { padding: 10px 24px 10px 16px; }
QMenu::item:selected { background: @onSurface:0.08@; }
QMenu::item:disabled { color: @outline@; }
QMenu::icon { padding-left: 12px; }
QMenu::indicator { width: 16px; height: 16px; margin-left: 12px; border: 2px solid @outline@; border-radius: 3px; }
QMenu::indicator:checked { background: @primary@; border-color: @primary@; image: url("@check@"); }
QMenu::separator { height: 1px; background: @outlineVariant@; margin: 6px 0; }
QFrame#focusBar { background: @primaryContainer@; border-radius: 16px; }
QFrame#focusBar QLabel { color: @onPrimaryContainer@; }
QFrame#focusBar QLabel#focusState { color: @onPrimaryContainer:0.75@; font-size: 11px; font-weight: 700; }
QLabel#focusClock { font-size: 26px; font-weight: 600; font-family: "Segoe UI Variable Display", "Segoe UI", sans-serif; }
QFrame#focusBar QPushButton:hover { background: @onPrimaryContainer:0.10@; }
QFrame#focusBar QProgressBar { background: @onPrimaryContainer:0.15@; }
QFrame#focusBar QProgressBar::chunk { background: @onPrimaryContainer@; }
QPushButton[kind="chipSmall"] { min-height: 32px; max-height: 32px; padding: 0 12px; border-radius: 16px;
    border: 1px solid @onPrimaryContainer:0.4@; color: @onPrimaryContainer@; }
QFrame#captureCard { background: @surfaceContainerHigh@; border-radius: 22px; }
QFrame#captureSep { background: @outlineVariant@; }
QLineEdit#captureEdit, QLineEdit#captureEdit:focus, QLineEdit#captureEdit:hover {
    font-size: 21px; border: none; padding: 8px 0; background: transparent; }
QFrame#statCard { background: @surfaceContainer@; border-radius: 16px; }
QLabel[role="stat"] { font-size: 26px; font-weight: 600; color: @primary@; }
QComboBox { background: transparent; border: 1px solid @outline@; border-radius: 8px; padding: 8px 12px; min-height: 22px; }
QComboBox:hover { border-color: @onSurface@; }
QComboBox:focus { border: 2px solid @primary@; padding: 7px 11px; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: url("@arrow@"); width: 18px; height: 18px; }
QComboBox QAbstractItemView { background: @surfaceContainer@; border: 1px solid @outlineVariant@; padding: 4px;
    selection-background-color: @secondaryContainer@; selection-color: @onSecondaryContainer@; outline: 0; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: @onSurfaceVariant@; padding: 8px 18px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: @primary@; border-bottom: 2px solid @primary@; }
QTabBar::tab:hover { color: @onSurface@; }
QTextBrowser { background: @surfaceContainer@; border: none; border-radius: 12px; padding: 8px; }
QToolTip { background: @inverseSurface@; color: @inverseOnSurface@; border: none; padding: 6px 8px; }
"""
TOKEN = re.compile(r"@(\w+)(?::([0-9.]+))?@")

PALETTE_ROLES = (
    (QPalette.Window, "surface"), (QPalette.WindowText, "onSurface"),
    (QPalette.Base, "surfaceContainerLow"), (QPalette.Text, "onSurface"),
    (QPalette.Button, "secondaryContainer"), (QPalette.ButtonText, "onSecondaryContainer"),
    (QPalette.Highlight, "primary"), (QPalette.HighlightedText, "onPrimary"),
    (QPalette.ToolTipBase, "inverseSurface"), (QPalette.ToolTipText, "inverseOnSurface"),
    (QPalette.PlaceholderText, "onSurfaceVariant"),
)


def _write_svg_assets(c):
    """QSS image: urls need files on disk; regenerate them in the current colours."""
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    check, arrow = ICON_DIR / "check.svg", ICON_DIR / "arrow.svg"
    check.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                     f'<path fill="{c["onPrimary"]}" d="{CHECK_PATH}"/></svg>', encoding="utf-8")
    arrow.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                     f'<path fill="{c["onSurfaceVariant"]}" d="{ARROW_PATH}"/></svg>', encoding="utf-8")
    chev = ICON_DIR / "chevron.svg"
    chev.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                    f'<path fill="{c["onSurfaceVariant"]}" d="{ICONS["chevron_right"]}"/></svg>', encoding="utf-8")
    return check.as_posix(), arrow.as_posix(), chev.as_posix()


def apply_theme(app, theme):
    c = dict(theme.c)
    c["check"], c["arrow"], c["chev"] = _write_svg_assets(c)

    def sub(m):
        val = c[m.group(1)]
        if m.group(2):
            q = QColor(val)
            return f"rgba({q.red()},{q.green()},{q.blue()},{int(float(m.group(2)) * 255)})"
        return val

    app.setStyleSheet(TOKEN.sub(sub, QSS))
    pal = QPalette()
    for role, key in PALETTE_ROLES:
        pal.setColor(role, QColor(c[key]))
    app.setPalette(pal)
