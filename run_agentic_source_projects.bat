@echo off
setlocal

cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "CLI=agentic\agentic_cli.py"

if not exist "%PY%" (
  echo [ERROR] Python venv tidak ditemukan: "%PY%"
  echo Jalankan instalasi venv terlebih dahulu.
  exit /b 1
)

if not exist "%CLI%" (
  echo [ERROR] CLI Agentic tidak ditemukan: "%CLI%"
  exit /b 1
)

rem Argumen pertama opsional: alamat ComfyUI, contoh nextgenserver:8188
set "SERVER_ARG="
if not "%~1"=="" set "SERVER_ARG=--server %~1"

set "PROJECTS=bj_source_video_2 bj_source_video_rika hj_source_video_2 hj_source_video_rika pov_source_video_2 pov_source_video_rika"

echo.
echo ============================================================
echo FASE 1/2 - Generate Config Agentic
echo ============================================================
for %%P in (%PROJECTS%) do (
  echo.
  echo [GENERATE] %%P
  "%PY%" "%CLI%" --project "%%P" --mode generate
  if errorlevel 1 (
    echo [ERROR] Generate Config Agentic gagal untuk %%P
    exit /b 1
  )
)

echo.
echo ============================================================
echo FASE 2/2 - Execute Agentic
echo ============================================================
for %%P in (%PROJECTS%) do (
  echo.
  echo [EXECUTE] %%P
  "%PY%" "%CLI%" --project "%%P" --mode execute %SERVER_ARG%
  if errorlevel 1 (
    echo [ERROR] Execute Agentic gagal untuk %%P
    exit /b 1
  )
)

echo.
echo ============================================================
echo Semua project selesai diproses.
echo ============================================================
exit /b 0
