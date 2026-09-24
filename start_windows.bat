@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install_windows.bat in this folder first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m metawipe gui %*
if errorlevel 1 pause
