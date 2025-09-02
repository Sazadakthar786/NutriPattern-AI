@echo off
title NutriPattern AI
echo ===============================
echo   Starting NutriPattern AI...
echo ===============================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b
    )
    echo Virtual environment created.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b
)

REM Fix numpy/pandas compatibility issue
echo Fixing package compatibility issues...
pip uninstall numpy pandas -y
pip install numpy>=2.3.2
pip install pandas>=2.2.0

REM Install requirements if needed
echo Installing requirements...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install requirements.
    pause
    exit /b
)

REM Start Flask app
echo Starting Flask application...
echo NutriPattern AI will be available at: http://127.0.0.1:5000
echo Press Ctrl+C to stop the server.
echo.

python app.py

pause
