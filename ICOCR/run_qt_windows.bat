@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "ICOCR_ENV=.venv-qt"
if /i "%~1"=="cuda" set "ICOCR_ENV=.venv-qt-gpu"
if not "%~1"=="" if /i not "%~1"=="cpu" if /i not "%~1"=="cuda" goto usage
if not exist "%ICOCR_ENV%\Scripts\python.exe" goto not_installed
if not exist "%ICOCR_ENV%\icocr_qt_setup_ok" goto not_installed
"%ICOCR_ENV%\Scripts\python.exe" qt_full.py
if errorlevel 1 (
    echo.
    echo ICOCR exited with an error.
    pause
    exit /b 1
)
exit /b 0
:not_installed
echo Qt environment not installed. Run setup_qt_windows.bat first.
pause
exit /b 1
:usage
echo Usage: run_qt_windows.bat [cpu^|cuda]
pause
exit /b 1
