#!/bin/bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
DESTINATION="${1:-}"

if [ -z "$DESTINATION" ]; then
  echo "用法：$0 /path/to/new/finpilot-submission" >&2
  exit 2
fi

case "$DESTINATION" in
  /|"$SOURCE_DIR"|"$SOURCE_DIR"/*)
    echo "拒絕：輸出目錄不可是根目錄、專案目錄或專案內部。" >&2
    exit 2
    ;;
esac

if [ -e "$DESTINATION" ]; then
  echo "拒絕覆寫已有路徑：$DESTINATION" >&2
  exit 2
fi

mkdir -p "$DESTINATION"
rsync -a \
  --exclude '.git/' \
  --include 'backend/.env.example' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '__pycache__/' \
  --exclude '*.py[cod]' \
  --exclude '.pytest_cache/' \
  --exclude '.DS_Store' \
  --exclude '*.zip' \
  --exclude '*.log' \
  --exclude '*.db' \
  --exclude '*.sqlite' \
  --exclude '*.sqlite3' \
  --exclude '*.pem' \
  --exclude '*.key' \
  --exclude '*.p12' \
  --exclude '*.pfx' \
  --exclude 'backend/cache/' \
  --exclude 'backend/data/' \
  --exclude 'docs/traces/' \
  --exclude 'qa/browser-current*/' \
  --exclude 'qa/browser-baseline/' \
  "$SOURCE_DIR/" "$DESTINATION/"

if find "$DESTINATION" -type f \( -name '.env' -o -name '.env.*' \) ! -path '*/backend/.env.example' -print -quit | grep -q .; then
  echo "失敗：輸出仍包含真實環境檔。" >&2
  exit 1
fi

if rg -l --hidden --glob '!backend/.env.example' --glob '!scripts/package_submission.sh' \
  '(GEMINI_API_KEY|FINMIND_TOKEN|SHIOAJI_API_KEY|SHIOAJI_SECRET_KEY)[[:space:]]*=[[:space:]]*[^[:space:]#]+' \
  "$DESTINATION" | grep -q .; then
  echo "失敗：輸出中發現可能的憑證賦值，請手動檢查。" >&2
  exit 1
fi

if rg -l --hidden -- '-----BEGIN [A-Z ]*PRIVATE KEY-----' "$DESTINATION" | grep -q .; then
  echo "失敗：輸出中發現私鑰內容，請手動檢查。" >&2
  exit 1
fi

echo "已產生去密鑰送件目錄：$DESTINATION"
echo "請在提交前另行確認 assets/ 圖像授權與個人資料。"
