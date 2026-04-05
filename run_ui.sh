#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[ERROR] Python venv tidak ditemukan: \"$PY\""
  echo "Jalankan instalasi venv dulu."
  exit 1
fi

nohup "$PY" "scene_manager_ui.py" >/dev/null 2>&1 &
