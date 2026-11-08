@echo off
setlocal
cd /d "%~dp0"
set "ICOCR_ROOT=%~dp0"
rem An explicit interpreter overrides automatic local-environment selection.
if defined ICOCR_PYTHON goto :check
call :pick .venv-gpu
if not defined ICOCR_PYTHON call :pick .venv
:check
if not defined ICOCR_PYTHON goto :missing
if not exist "%ICOCR_PYTHON%" goto :missing
"%ICOCR_PYTHON%" -m pip install resvg_py==0.5.0
set "ICOCR_EXIT=%ERRORLEVEL%"
if not "%ICOCR_EXIT%"=="0" pause
exit /b %ICOCR_EXIT%
:missing
echo No complete Python environment found. Run setup_windows.bat ^(again^).
echo For NVIDIA CUDA, run: setup_windows.bat cuda
pause
exit /b 1

:pick
rem Use the environment only when setup_windows.bat completed in it (marker file),
rem or, for environments set up before the marker existed, when onnxruntime imports.
if not exist "%ICOCR_ROOT%%~1\Scripts\python.exe" exit /b 0
if exist "%ICOCR_ROOT%%~1\icocr_setup_ok" goto :use
"%ICOCR_ROOT%%~1\Scripts\python.exe" -c "import onnxruntime" >nul 2>&1
if errorlevel 1 exit /b 0
:use
set "ICOCR_PYTHON=%ICOCR_ROOT%%~1\Scripts\python.exe"
exit /b 0
