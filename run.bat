@echo off
REM Runs the bot with the Python launcher (py). Usage: double-click or "run.bat"
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python launcher "py" not found. Install Python 3.9+ from https://python.org and check "Add to PATH".
    pause
    exit /b 1
)

if not exist ".env" (
    echo No .env file found. Copy .env.example to .env and fill it in:
    echo     copy .env.example .env
    pause
    exit /b 1
)

echo Installing dependencies...
py -m pip install -q -r requirements.txt

echo Starting bot...
py bot.py
pause
