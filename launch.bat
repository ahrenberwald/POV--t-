@echo off
echo ============================================
echo   Player POV - Starting...
echo ============================================
echo.
echo The app will open in your browser automatically.
echo Keep this window open while using the app.
echo Close this window to stop the app.
echo.

:: Create folders if they don't exist
if not exist "uploads" mkdir uploads
if not exist "outputs" mkdir outputs
if not exist "static" mkdir static

:: Open browser after short delay
start "" /b timeout /t 2 >nul
start "" "http://localhost:8000"

:: Start the server
uvicorn main:app --host 0.0.0.0 --port 8000
pause
