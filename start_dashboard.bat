@echo off
REM ============================================================
REM  Polymarket Whale Alerts - one-click dashboard starter (Windows)
REM  Double-click this file. First run installs dependencies.
REM ============================================================
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Install it from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add python.exe to PATH" during install.
    pause
    exit /b 1
)

echo Installing dependencies (first run only, may take a minute)...
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Check your network and try again.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Dashboard starting... open this in your browser:
echo  http://127.0.0.1:5000
echo  Press Ctrl+C in this window to stop.
echo ============================================================
python -m src.webapp
pause
