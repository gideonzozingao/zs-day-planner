# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Zuqongtech Daily Planner.

Build from the project root:
    pyinstaller packaging/planner.spec --noconfirm --clean
Output: dist/ZuqongtechPlanner/ZuqongtechPlanner.exe  (one-folder build; the installer packs it)
"""
import re
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT))
from planner import __version__              # noqa: E402
from planner.config import APP_NAME, EXE_NAME  # noqa: E402

ICON = ROOT / "packaging" / "assets" / "planner.ico"

# Qt modules the app never imports: keeps the build lean if full PySide6 is installed.
EXCLUDES = [
    "tkinter", "unittest", "pydoc", "test",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtTest", "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio",
    "PySide6.QtTextToSpeech", "PySide6.QtNfc", "PySide6.QtHttpServer",
]


def version_file():
    """Windows file properties (Details tab) generated from planner.__version__."""
    if sys.platform != "win32":
        return None
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct,
        VSVersionInfo,
    )
    nums = tuple((list(map(int, re.findall(r"\d+", __version__))) + [0] * 4)[:4])  # 1.2.0-beta.3 -> 1,2,0,3
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Zuqongtech"),
                StringStruct("FileDescription", APP_NAME),
                StringStruct("FileVersion", __version__),
                StringStruct("InternalName", EXE_NAME),
                StringStruct("OriginalFilename", f"{EXE_NAME}.exe"),
                StringStruct("ProductName", APP_NAME),
                StringStruct("ProductVersion", __version__),
                StringStruct("LegalCopyright", "© Zuqongtech"),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    path = Path(workpath) / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(info), encoding="utf-8")
    return str(path)


a = Analysis(
    [str(ROOT / "daily_planner.py")],
    pathex=[str(ROOT)],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtNetwork"],
    excludes=EXCLUDES,
    noarchive=False,
)


def _norm(path):
    return path.replace("\\", "/").lower()


# Qt's UI translations aren't used (the app is English-only).
a.datas = [d for d in a.datas if "/translations/" not in "/" + _norm(d[0])]

# Libraries dragged in only through plugins this Widgets app never uses
# (PDF image plugin -> Qt6Pdf, QML/Quick, virtual keyboard).
UNUSED_LIBS = ("qt6pdf", "qt6qml", "qt6quick", "qt6virtualkeyboard", "/imageformats/qpdf")
a.binaries = [b for b in a.binaries if not any(x in _norm(b[0]) for x in UNUSED_LIBS)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=EXE_NAME,
    icon=str(ICON),
    version=version_file(),
    console=False,          # tray app: no console window
    upx=False,              # UPX triggers antivirus false positives
)

coll = COLLECT(exe, a.binaries, a.datas, name=EXE_NAME, upx=False)
