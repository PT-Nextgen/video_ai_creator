@echo off
setlocal

cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] Python venv tidak ditemukan: "%PY%"
  echo Jalankan instalasi venv dulu.
  pause
  exit /b 1
)

start "" "%PY%" "scene_manager_ui.py"

endlocal
