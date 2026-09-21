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

echo ============================================================
echo Menjalankan seluruh scene secara berurutan
echo ComfyUI server: %SERVER%
echo ============================================================

echo.
echo [1/4] bj_video_mid_process_2
"%PYTHON%" "%MAIN%" --server "%SERVER%" --project "bj_video_mid_process_2"
if errorlevel 1 (
    echo [ERROR] Project bj_video_mid_process_2 gagal.
    exit /b 1
)

echo.
echo [2/4] bj_video_mid_process_rika
"%PYTHON%" "%MAIN%" --server "%SERVER%" --project "bj_video_mid_process_rika"
if errorlevel 1 (
    echo [ERROR] Project bj_video_mid_process_rika gagal.
    exit /b 1
)

echo.
echo [3/4] hj_video_mid_process_2
"%PYTHON%" "%MAIN%" --server "%SERVER%" --project "hj_video_mid_process_2"
if errorlevel 1 (
    echo [ERROR] Project hj_video_mid_process_2 gagal.
    exit /b 1
)

echo.
echo [4/4] hj_video_mid_process_rika
"%PYTHON%" "%MAIN%" --server "%SERVER%" --project "hj_video_mid_process_rika"
if errorlevel 1 (
    echo [ERROR] Project hj_video_mid_process_rika gagal.
    exit /b 1
)

echo.
echo ============================================================
echo Semua project dan scene selesai diproses.
echo ============================================================
exit /b 0
