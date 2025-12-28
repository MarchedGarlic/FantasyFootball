@echo off
REM Fantasy Football Analysis Startup Script for Windows

echo 🏈 Starting Fantasy Football Analysis Server...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.8 or higher.
    pause
    exit /b 1
)

REM Install Python dependencies
echo 📦 Installing Python dependencies...
pip install -r requirements.txt

REM Install Node.js dependencies
npm --version >nul 2>&1
if errorlevel 1 (
    echo ⚠️  npm not found. Some build features may not work.
) else (
    echo 📦 Installing Node.js dependencies...
    npm install
)

echo.
echo 🚀 Starting Fantasy Football Analysis Server...
echo    Open your browser to: http://localhost:5000
echo.
echo    Press Ctrl+C to stop the server
echo.

REM Start the Flask server
python server.py

pause