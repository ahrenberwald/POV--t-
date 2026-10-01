@echo off
echo ============================================
echo   Player POV - First Time Setup
echo ============================================
echo.
echo This will install everything needed to run Player POV.
echo Please wait, this may take a few minutes...
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed on this computer.
    echo.
    echo Please download and install Python from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation!
    echo Then run this setup again.
    pause
    exit /b 1
)

:: Check if FFmpeg is installed
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo FFmpeg not found. Installing via winget...
    winget install ffmpeg
    if errorlevel 1 (
        echo.
        echo Could not install FFmpeg automatically.
        echo Please download it manually from https://ffmpeg.org/download.html
        echo and add it to your PATH, then run setup again.
        pause
        exit /b 1
    )
)

:: Install Python packages
echo Installing Python packages...
python -m pip install -r requirements.txt

echo.
echo ============================================
echo   Setup complete! 
echo   Double-click launch.bat to start the app.
echo ============================================
pause
