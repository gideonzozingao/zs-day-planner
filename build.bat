@echo off
rem  build.bat                 PyInstaller + installer
rem  build.bat -Compiler nuitka  native compile + installer
rem Double-clickable wrapper around build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
if errorlevel 1 pause
