@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "PYTHON=.venv\Scripts\python.exe"
set "MAIN=main.py"
set "SERVER=%~1"

if "%SERVER%"=="" set "SERVER=nextgenserver:8188"

if not exist "%PYTHON%" (
    echo [ERROR] Python venv tidak ditemukan: "%CD%\%PYTHON%"
    exit /b 1
)

if not exist "%MAIN%" (
    echo [ERROR] Entry point tidak ditemukan: "%CD%\%MAIN%"
    exit /b 1
)

set "PROJECTS=hj_video_rika pov_video_rika"

echo ============================================================
echo Menjalankan seluruh scene secara berurutan
echo ComfyUI server: %SERVER%
echo ============================================================

for %%P in (%PROJECTS%) do (
    echo.
    echo [RUN] %%P
    "%PYTHON%" "%MAIN%" --server "%SERVER%" --project "%%P"
    if errorlevel 1 (
        echo [ERROR] Project %%P gagal. Proses dihentikan.
        exit /b 1
    )
)

echo.
echo ============================================================
echo Semua project dan scene selesai diproses.
echo ============================================================
exit /b 0
