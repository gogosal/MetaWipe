@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install_windows.bat in this folder first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.15,<7"
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name MetaWipe gui_entry.py
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console --name metawipe-cli cli_entry.py
if errorlevel 1 goto failure
echo.
echo Executables created: dist\MetaWipe.exe and dist\metawipe-cli.exe
pause
exit /b 0
:failure
echo.
echo Could not build the executables. Review the error above.
pause
exit /b 1
