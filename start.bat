@echo off
echo ========================================
echo   Music Taste Analyzer - Startup
echo ========================================
echo.

:: Install dependencies
echo [1/3] Installing Python dependencies...
pip install -r requirements.txt -q

:: Check if install succeeded
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    echo Try running: pip install -r requirements.txt
    pause
    exit /b 1
)

echo [2/3] Starting server...
echo.
echo The app will open in your browser shortly.
echo Press Ctrl+C in this window to stop the server.
echo.

:: Start the server
python run.py

pause
