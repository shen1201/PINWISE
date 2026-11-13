# FinPilot AI V7.0 R2（PINWISE）

以官方公開資料為核心的台股研究與智慧選股原型。前端是 Vue 3（`frontend-vue/`），後端是 Python / FastAPI（`backend/`）。所有金鑰只放在後端，不會進到瀏覽器。

> 研究與競賽原型，不是投資建議。行情為最近可得的日資料，不是即時行情。

## 快速啟動

需要 Python 3.11+ 與 Node.js 18+，開兩個終端機。

**1. 後端**（專案根目錄）

```powershell
python -m venv .venv                                         # 第一次
.venv\Scripts\python -m pip install -r backend/requirements.lock   # 第一次
.venv\Scripts\python -m backend.run
```

macOS 把 `.venv\Scripts\python` 換成 `.venv/bin/python`。

**2. 前端**

```sh
cd frontend-vue
npm install    # 第一次
npm run dev
```

開啟 <http://localhost:5173>。API 文件在 <http://127.0.0.1:8080/docs>。

> 後端的 8080 只提供 API，不提供畫面，直接開會看到 404。`start.command` 也會開 8080，請改開 5173。

## 設定（`.env`）

在專案根目錄建立 `.env`（已被 Git 忽略）。只有 Gemini 是 AI 功能必要的，其他都有免費預設值。完整選項見 [backend/.env.example](backend/.env.example)。

| 用途 | 變數 | 必要嗎 |
| --- | --- | --- |
| AI 研究與助手 | `GEMINI_API_KEY`（[申請](https://aistudio.google.com/app/apikey)） | AI 功能需要 |
| 帳號登入、資料存資料庫 | `DATABASE_URL` | 選填，未設定時存在 `backend/data/` |
| FinMind 歷史價 | `FINMIND_TOKEN` | 選填 |
| Shioaji 行情檢查 | `SHIOAJI_ENABLED` 等 | 選填，預設關閉 |

改了 `.env` 要**重啟後端**才會生效。

## 常見問題

- **畫面打得開但資料都失敗**：後端沒啟動或不在 8080，先開 <http://127.0.0.1:8080/api/health> 確認。
- **8080 被佔用**：有舊的後端沒關。Windows 可用 `Get-NetTCPConnection -LocalPort 8080 -State Listen` 找出程序並關閉。
- **Gemini 429**：配額用完，等額度恢復，不要連續重送。

## 專案結構

| 路徑 | 內容 |
| --- | --- |
| `frontend-vue/` | Vue 前端，見 [README-vue.md](README-vue.md) |
| `css/`、`assets/` | 前端的樣式與圖片（由 Vue 匯入，**不可刪**），見 [css/README-css.md](css/README-css.md) |
| `backend/app/` | FastAPI：`main.py` 路由、`services/` 研究與選股、`providers/` 資料來源、`security/` 存取控制、`storage/` 資料庫 |
| `backend/tests/` | 後端測試 |
| `qa/` | 後端 API 驗收腳本與假資料後端（見下方「測試」） |
| `scripts/`、`netlify.toml`、`render.yaml` | 部署設定（見下方「部署」） |

## 測試

```sh
FINPILOT_SKIP_DOTENV=1 .venv/bin/python -m unittest discover -s backend/tests -v
```

`qa/` 裡的 `p3_*.py` 測後端 API（`p3_security_acceptance.py` 會被後端測試呼叫，不可刪），`*_fixture_server.py` 用假資料啟動後端、不呼叫真的 Gemini。舊版前端的瀏覽器測試已移除，Vue 版目前沒有瀏覽器測試。

## 部署

- 後端：Render（`render.yaml`），啟動指令 `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`。金鑰放在平台的秘密設定，不要上傳 `.env`。
- 前端：`scripts/build_netlify_live.sh` 還在複製已移除的舊版檔案，**目前會失敗**，要先改成打包 `frontend-vue/`。

## 舊版前端

原生 JavaScript 舊版（根目錄 `index.html`、`js/`）已移除，可從 Git 取回：移除前最後一版是 commit `158044c`。

## 已整合功能

- 研究 Agent：理解問題 → 規劃任務 → 選擇工具 → 取得與核對資料 → 程式計算指標 → Gemini 分析 → 輸出檢核 → 保存報告與證據。
- 任務控制：後端異步任務、事件進度、重複送出去重、有限重試、安全工作邊界暫停／繼續／取消。已在執行的外部 API 呼叫不會假裝立即中斷。
- 量化指標：期間報酬、年化波動、最大回撤、區間高低與平均成交量由 Python 計算，不由模型生成。
- 智慧選股：使用 TWSE／TPEx 日資料篩選市場、產品與產業；風險條件使用 FinMind 日收盤計算年化波動度。
- 工作區：候選、比較、追蹤、研究記錄與證據中心共用真實後端快照，並保留舊版瀏覽器記錄相容性。
- 資料狀態：實際檢查 TWSE、TPEx、MOPS、FinMind、官方新聞、法說公告、Gemini 與 Shioaji。
- 單一 AI 助手：由 Python 後端串流，支援多輪標的記憶、受限資料工具、停止／重試、歧義確認與兩股比較。工具型回答先通過後端事實檢核才開始顯示。
- 逐項證據驗證（P2-A）：工具型回答依標的、數值、單位、日期、期間與來源逐句核對；只處理不合格主張及其相依結論，保留其他可靠分析。使用者情境價格不會被當成行情，未確認網址不會輸出。
- 金融研究品質（P2-B）：依行情、投資決策、比較、目標價、估值與風險問題調整回答深度；簡單查價使用最小行情 scope，目標價差距由 Python 計算，無法取得的財務／ETF／籌碼欄位會明示而不補造。

### 助手互動原則

- 回答以 grapheme 安全的逐字效果呈現，不切壞中文、emoji 或組合字元；串流中不反覆解析 Markdown。
- 使用者停在底部時，助手會自然跟隨新內容；向上閱讀時會保留位置，只顯示一個「↓」按鈕，點擊後才回到最新訊息。
- 「已完成」、「已由你停止」、「配額限制」、「逾時」與「串流中斷」分開顯示。停止或失敗時保留已顯示內容並標記不完整，可由使用者按重試。
- 日行情一律顯示資料日期且不稱為即時價；來源缺漏不以示範資料替代。

## API 設定表

| 用途／來源 | 基本啟動必要 | 需要金鑰 | 官方申請／文件 | `.env` 變數 |
| --- | --- | --- | --- | --- |
| Gemini 助手與研究分析 | 公開資料瀏覽不需要；助手與完整 AI 研究需要 | 是 | [建立 Key](https://aistudio.google.com/app/apikey)、[官方 API Key 文件](https://ai.google.dev/gemini-api/docs/api-key) | `GEMINI_API_KEY`、`GEMINI_MODEL`；助手限制另見 `.env.example` |
| TWSE 日行情、上市公司、重大訊息、新聞 | 否，已有免費預設端點 | 否 | [TWSE OpenAPI](https://openapi.twse.com.tw/)、[RSS 使用說明](https://www.twse.com.tw/zh/terms/rss.html) | `TWSE_OPENAPI_BASE_URL`、`TWSE_NEWS_RSS_URL` |
| TPEx 日行情、上櫃公司、重大訊息 | 否，已有免費預設端點 | 否 | [TPEx OpenAPI](https://www.tpex.org.tw/openapi/) | `TPEX_OPENAPI_BASE_URL` |
| MOPS 衍生公司／公告資料 | 否；使用 TWSE／TPEx 官方 OpenAPI 資料集 | 否 | [公開資訊觀測站](https://mops.twse.com.tw/) | 共用上述 TWSE／TPEx 變數 |
| FinMind 歷史日價 | 否；匿名額度可用 | Token 選填 | [官方快速開始與 Token 說明](https://finmind.github.io/quickstart/)、[註冊](https://finmindtrade.com/) | `FINMIND_BASE_URL`、`FINMIND_TOKEN` |
| 公司法說公告 | 否；從每日重大訊息篩選 | 否 | 共用 TWSE／TPEx 官方 OpenAPI | 共用上述 TWSE／TPEx 變數 |
| Shioaji 選配行情健康檢查 | 否，預設關閉 | 啟用時需要 Key／Secret | [官方申請說明](https://sinotrade.github.io/tutor/prepare/token/)、[API 管理](https://www.sinotrade.com.tw/newweb/PythonAPIKey/) | `SHIOAJI_ENABLED`、`SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_SIMULATION` |
| PostgreSQL 儲存與帳號登入 | 否；未設定時使用 `backend/data/` 的 JSON 檔 | 資料庫密碼 | [PostgreSQL](https://www.postgresql.org/download/) | `DATABASE_URL` |

服務執行參數 `FINPILOT_HOST`、`FINPILOT_PORT`、`PORT`、逾時、重試與快取均有預設值。設定 `DATABASE_URL` 後，研究任務、Agent trace、Gemini 用量與使用者工作區改存 PostgreSQL，資料庫與資料表會在啟動時自動建立；密碼含 `@ : / # %` 時須改寫為 URL 編碼。側邊「PINWISE 助手」透過 Python 後端串流呼叫 Gemini；前端不持有金鑰。`FINPILOT_ASSISTANT_MAX_INPUT_CHARS`、`FINPILOT_ASSISTANT_MAX_OUTPUT_TOKENS`、`FINPILOT_ASSISTANT_MAX_HISTORY_MESSAGES`、`FINPILOT_ASSISTANT_MAX_TOOL_CALLS` 均有安全預設值。Shioaji 本專案不載入 CA、不下單。