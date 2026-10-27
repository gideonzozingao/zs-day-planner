"""Compile the app to native code with Nuitka, producing the same output folder the
PyInstaller spec does:  dist/ZuqongtechPlanner/ZuqongtechPlanner.exe (+ its files).

The installer (packaging/installer.iss) then packs that folder unchanged, so switching
compilers doesn't touch the installer, update feed, shortcuts or data location.

Usual entry point is build.ps1 -Compiler nuitka. Run directly with:
    python packaging/build_nuitka.py
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planner import __version__                 # noqa: E402
from planner.config import APP_NAME, EXE_NAME   # noqa: E402

ICON = ROOT / "packaging" / "assets" / "planner.ico"
DIST = ROOT / "dist"
OUT = DIST / EXE_NAME                            # final folder, matches PyInstaller's
BUILD = ROOT / "build" / "nuitka"

# Qt modules the app imports (everything else is left out, like the PyInstaller excludes).
QT_PLUGINS = "platforms,styles,iconengines,imageformats,tls,generic,platforminputcontexts"

# Numeric Windows file version, e.g. 1.1.0-beta.2 -> 1.1.0.2
NUMS = ".".join((re.findall(r"\d+", __version__) + ["0"] * 4)[:4])


def main():
    if sys.platform != "win32":
        sys.exit("Nuitka release builds are Windows-only (run this on Windows or in CI).")
    if BUILD.exists():
        shutil.rmtree(BUILD)
    if OUT.exists():
        shutil.rmtree(OUT)
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)

    args = [
        sys.executable, "-m", "nuitka",
        "--standalone",                       # self-contained folder (not --onefile: see notes)
        "--assume-yes-for-downloads",         # fetch the C toolchain headlessly in CI
        "--enable-plugin=pyside6",
        f"--include-qt-plugins={QT_PLUGINS}",
        "--noinclude-qt-translations",        # English-only app; drops ~20 MB like the spec
        "--windows-console-mode=disable",     # tray app: no console window
        f"--windows-icon-from-ico={ICON}",
        "--company-name=Zuqongtech",
        f"--product-name={APP_NAME}",
        f"--file-version={NUMS}",
        f"--product-version={NUMS}",
        f"--file-description={APP_NAME}",
        "--copyright=\u00a9 Zuqongtech",
        f"--output-filename={EXE_NAME}.exe",
        f"--output-dir={BUILD}",
        "--remove-output",                    # discard C intermediates when done
        # Python modules Nuitka can't see through the dynamic UI imports:
        "--include-module=planner.hotkey",
        "--include-module=planner.single_instance",
        str(ROOT / "daily_planner.py"),
    ]
    print("==> Nuitka\n    " + " ".join(args))
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode != 0:
        sys.exit(result.returncode)

    produced = BUILD / "daily_planner.dist"   # Nuitka names it after the main script
    if not produced.exists():
        sys.exit(f"Nuitka output folder not found: {produced}")
    shutil.move(str(produced), str(OUT))
    exe = OUT / f"{EXE_NAME}.exe"
    if not exe.exists():
        sys.exit(f"Expected {exe} was not produced")
    print(f"==> Native build ready: {exe}")


if __name__ == "__main__":
    main()
