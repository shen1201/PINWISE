#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

FINPILOT_PYTHON=".venv/bin/python"
FINPILOT_REQUIREMENTS="backend/requirements.lock"
FINPILOT_LOCK_STAMP=".venv/.finpilot-requirements-lock.sha256"
if [ ! -x "$FINPILOT_PYTHON" ]; then
  echo "首次啟動：建立 Python 虛擬環境…"
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
fi

FINPILOT_LOCK_HASH="$(shasum -a 256 "$FINPILOT_REQUIREMENTS" | awk '{print $1}')"
FINPILOT_INSTALLED_HASH="$(test -f "$FINPILOT_LOCK_STAMP" && sed -n '1p' "$FINPILOT_LOCK_STAMP" || true)"
if [ "$FINPILOT_LOCK_HASH" != "$FINPILOT_INSTALLED_HASH" ] || ! "$FINPILOT_PYTHON" -c "import fastapi, httpx, google.genai, uvicorn" >/dev/null 2>&1; then
  echo "依 requirements.lock 安裝固定版本後端套件…"
  "$FINPILOT_PYTHON" -m pip install -r "$FINPILOT_REQUIREMENTS"
  printf '%s\n' "$FINPILOT_LOCK_HASH" > "$FINPILOT_LOCK_STAMP"
fi

FINPILOT_URL="$("$FINPILOT_PYTHON" -m backend.run --print-url)"
"$FINPILOT_PYTHON" -m backend.run &
FINPILOT_PID=$!
trap 'kill "$FINPILOT_PID" 2>/dev/null || true' EXIT INT TERM

for _ in {1..30}; do
  if curl -fsS "$FINPILOT_URL/api/health" >/dev/null 2>&1; then
    open "$FINPILOT_URL"
    echo "FinPilot 已啟動：$FINPILOT_URL"
    echo "此視窗會顯示後端狀態；關閉視窗即可停止服務。"
    wait "$FINPILOT_PID"
    exit $?
  fi
  sleep 1
done

echo "FinPilot 後端未能在 30 秒內啟動，請查看上方錯誤訊息。"
kill "$FINPILOT_PID" 2>/dev/null || true
exit 1
