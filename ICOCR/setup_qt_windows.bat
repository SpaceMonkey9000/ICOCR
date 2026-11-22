@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ICOCR Setup

set "ICOCR_ENV=.venv-qt"
if /i "%~1"=="cuda" set "ICOCR_ENV=.venv-qt-gpu"
if not "%~1"=="" if /i not "%~1"=="cpu" if /i not "%~1"=="cuda" goto usage

where py >nul 2>&1
if errorlevel 1 goto no_python
py -3.11 -c "import sys,struct; sys.exit(0 if struct.calcsize('P')*8==64 else 1)" >nul 2>&1
if errorlevel 1 goto no_python

if not exist "%ICOCR_ENV%\Scripts\python.exe" (
    echo Creating %ICOCR_ENV%...
    py -3.11 -m venv "%ICOCR_ENV%"
    if errorlevel 1 goto failed
)
set "PYTHON=%ICOCR_ENV%\Scripts\python.exe"
if exist "%ICOCR_ENV%\icocr_qt_setup_ok" del "%ICOCR_ENV%\icocr_qt_setup_ok"

echo Updating pip...
"%PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto failed

echo Installing ICOCR requirements...
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto failed

if /i "%~1"=="cuda" (
    echo Installing CUDA ONNX Runtime...
    "%PYTHON%" -m pip uninstall -y onnxruntime onnxruntime-gpu
    if errorlevel 1 goto failed
    "%PYTHON%" -m pip install "onnxruntime-gpu[cuda,cudnn]==1.22.0"
    if errorlevel 1 goto failed
    "%PYTHON%" -c "import onnxruntime as ort,sys; print(ort.get_available_providers()); sys.exit(0 if 'CUDAExecutionProvider' in ort.get_available_providers() else 1)"
    if errorlevel 1 goto failed
)

echo Checking imports...
"%PYTHON%" -c "import PySide6,cv2,numpy,onnxruntime,rapidocr_onnxruntime; print('Qt and OCR dependencies OK')"
if errorlevel 1 goto failed
>"%ICOCR_ENV%\icocr_qt_setup_ok" echo Setup completed

echo.
echo Setup complete. Run run_qt_windows.bat to launch the CPU version.
if /i "%~1"=="cuda" echo To launch CUDA version: run_qt_windows.bat cuda
pause
exit /b 0

:no_python
echo Python 3.11 64-bit with the Windows py launcher is required.
pause
exit /b 1
:usage
echo Usage: setup_qt_windows.bat [cpu^|cuda]
pause
exit /b 1
:failed
echo.
echo Setup failed. Review the error above. The Qt installation marker was not created.
pause
exit /b 1
