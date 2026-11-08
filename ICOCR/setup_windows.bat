@echo off
setlocal
cd /d "%~dp0"
set "ICOCR_ENV=.venv"
if "%~1"=="" goto :setup
if /i "%~1"=="cpu" goto :setup
if /i not "%~1"=="cuda" goto :usage
set "ICOCR_ENV=.venv-gpu"
:setup
py -3.11 --version >nul 2>&1
if errorlevel 1 (
 echo Install Python 3.11 64-bit with the Python Launcher enabled.
 pause
 exit /b 1
)
rem The marker is written only after a complete setup; run_windows.bat checks it.
if exist "%ICOCR_ENV%\icocr_setup_ok" del "%ICOCR_ENV%\icocr_setup_ok"
if exist "%ICOCR_ENV%\icocr_setup_ok" goto :failed
if not exist "%ICOCR_ENV%\Scripts\python.exe" py -3.11 -m venv "%ICOCR_ENV%"
if errorlevel 1 goto :failed
rem CPU and GPU ONNX distributions share a module: remove both before installing one.
"%ICOCR_ENV%\Scripts\python.exe" -m pip uninstall -y onnxruntime onnxruntime-gpu
if errorlevel 1 goto :failed
"%ICOCR_ENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
if /i "%~1"=="cuda" (
 rem RapidOCR explicitly depends on CPU onnxruntime. Replace it after dependency resolution.
 "%ICOCR_ENV%\Scripts\python.exe" -m pip uninstall -y onnxruntime onnxruntime-gpu
 if errorlevel 1 goto :failed
 "%ICOCR_ENV%\Scripts\python.exe" -m pip install "onnxruntime-gpu[cuda,cudnn]==1.22.0"
 if errorlevel 1 goto :failed
 "%ICOCR_ENV%\Scripts\python.exe" -c "import onnxruntime as o, sys; p=o.get_available_providers(); print('ONNX Runtime providers:', p); sys.exit(0 if 'CUDAExecutionProvider' in p else 1)"
 if errorlevel 1 goto :failed
)
>"%ICOCR_ENV%\icocr_setup_ok" echo ICOCR setup completed || goto :failed
echo Setup complete. Run run_windows.bat.
pause
exit /b 0
:usage
echo Usage: setup_windows.bat [cpu^|cuda]
pause
exit /b 1
:failed
echo Setup failed. See the error above and docs\TROUBLESHOOTING.md.
pause
exit /b 1
