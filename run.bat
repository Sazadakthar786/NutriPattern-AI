@echo off
title NutriPattern AI
echo Starting NutriPattern AI...

REM Run from project directory (where run.bat lives)
cd /d "%~dp0"

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Optional: set Flask app (default is app.py in current dir)
set FLASK_APP=app.py
set FLASK_ENV=development

REM Start Flask app
echo.
echo NutriPattern AI running at: http://127.0.0.1:5000
echo Press Ctrl+C to stop.
echo.
python app.py

pause
