@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m pip install -e ".[gui]"
if errorlevel 1 goto failure
echo.
echo Installation complete. Open start_windows.bat to use MetaWipe.
pause
exit /b 0
:failure
echo.
echo Installation failed. Check that Python 3.10 to 3.14 and Internet access are available.
echo The error details appear above.
pause
exit /b 1
