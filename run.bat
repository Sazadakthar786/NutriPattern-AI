@echo off
title NutriPattern AI
echo Starting NutriPattern AI...

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install requirements
pip install -r requirements.txt

REM Start Flask app
echo NutriPattern AI running at: http://127.0.0.1:5000
python app.py

pause
