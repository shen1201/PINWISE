# PINWISE 技術文件

投資情報與智慧選股 AI Agent｜NAPAI Agentic AI 校園落地創新應用競賽 2026｜B 組・題目一 決賽

> 本文件不含密碼、API 金鑰或可識別個資。所有金鑰只存在執行環境的 `.env`，不在程式碼與文件中。
> PINWISE 為 AI 投資研究輔助，不是自動下單或保證獲利工具。

## 目錄

1. 系統架構
2. 安裝與執行步驟
3. 相依套件
4. 模型與版本
5. API
6. 環境變數
7. 授權
8. 資料流程
9. 權限與安全
10. 已知限制
11. 故障排除

---

## 1. 系統架構

### 1.1 設計原則：AI 負責理解與解說，程式負責資料與計算

| 由 Gemini 負責 | 由程式負責 |
| --- | --- |
| 把使用者的一句白話拆成條件 | 規劃步驟、決定呼叫哪些資料工具（白名單） |
| 把結果整理成白話說明 | 從官方資料取得數字並計算指標 |
| | 逐句核對 AI 回答中的數字、日期、來源 |

所有數字（報酬、波動、回撤、本益比等）都由 Python 計算或取自官方資料，不由模型生成。

### 1.2 元件

```
瀏覽器（Vue 3 前端）
   │  HTTPS（同源）
   ▼
ngrok 固定網址 ──► FastAPI 後端（埠 8080）
                    ├─ security/    存取控制、速率限制、Gemini 用量預算、訪客工作階段
                    ├─ services/    選股、研究任務、助手、輸入理解、工具分派、指標計算
                    ├─ providers/   外部資料來源（一個來源一個類別）
                    ├─ storage/     PostgreSQL 或本機 JSON
                    └─ 靜態檔案     打包好的前端（frontend-vue/dist）
                         │
                         ▼
          TWSE / TPEx / MOPS OpenAPI、FinMind、投信官網、Google Gemini
```

| 層 | 技術 | 位置 |
| --- | --- | --- |
| 前端 | Vue 3.5 + Vue Router 4.5 + Vite 6 | `frontend-vue/` |
| 樣式與圖片 | CSS、PNG/JPG | `css/`、`assets/` |
| 後端 | Python 3.11.9 + FastAPI | `backend/app/` |
| AI | Google Gemini（`google-genai` SDK） | `backend/app/providers/gemini.py` |
| 儲存 | PostgreSQL（選用）或 `backend/data/` JSON 檔 | `backend/app/storage/` |
| 對外展示 | ngrok 固定網址，後端同時提供 API 與前端 | `start_public_demo.cmd` |

### 1.3 後端模組

| 目錄 | 主要檔案與用途 |
| --- | --- |
| `providers/` | `twse.py`、`tpex.py`（上市櫃行情）、`mops.py`（公司資料、重大訊息）、`finmind.py`（歷史日價）、`fundamentals.py`（本益比、殖利率、月營收、EPS）、`news.py`、`investor_relations.py`（新聞、法說會）、`esg.py`、`etf_holdings.py`、`fubon_etf.py`（ESG、ETF 成份股）、`gemini.py`、`shioaji.py`（選配唯讀行情） |
| `services/` | `ai_picker.py`（自然語言選股）、`research.py`、`research_jobs.py`（研究與非同步任務）、`assistant.py`、`assistant_claims.py`（助手與逐句檢核）、`input_understanding.py`（輸入理解）、`tool_router.py`（工具白名單分派）、`conversation_memory.py`（對話記憶）、`analytics.py`（指標計算） |
| `security/` | `preview_security.py`：存取中介層、速率限制、並發限制、Gemini 每日用量預算、訪客工作階段 |
| `storage/` | `database.py`、`repositories.py`、`auth.py`：資料庫、工作區、帳號與登入 |
| `core/` | `config.py`（設定與上下限）、`http_client.py`（重試與快取）、`provenance.py`（資料來源標註） |

---

## 2. 安裝與執行步驟

### 2.1 需求

- Python 3.11 以上（開發使用 3.11.9）
- Node.js 18 以上
- Google Gemini API Key（AI 功能需要）
- 選用：PostgreSQL、ngrok

### 2.2 後端

在 `FinPilot-AI-V7.0-R2-Mac/` 目錄執行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.lock
```

複製 `backend/.env.example` 的內容到專案根目錄的 `.env`，至少填入 `GEMINI_API_KEY`，然後啟動：

```powershell
.venv\Scripts\python -m backend.run
```

macOS／Linux 把 `.venv\Scripts\python` 換成 `.venv/bin/python`。API 文件在 <http://127.0.0.1:8080/docs>。

### 2.3 前端（開發模式）

```sh
cd frontend-vue
npm install
npm run dev
```

開啟 <http://localhost:5173>。`/api` 請求會自動轉給 `http://127.0.0.1:8080`。

### 2.4 公開展示（ngrok）

1. 安裝 ngrok，執行 `ngrok config add-authtoken <token>`，並申請免費固定網址。
2. 在 `.env` 開啟訪客模式（見第 6 節「公開展示」）。
3. 把 `start_public_demo.cmd` 的 `PUBLIC_URL` 改成固定網址並執行，它會依序：
   - 打包前端（`npm run build` → `frontend-vue/dist/`）；
   - 啟動後端（8080，同時提供 API 與前端）；
   - 啟動 ngrok 通道。

### 2.5 測試

```sh
FINPILOT_SKIP_DOTENV=1 .venv/bin/python -m unittest discover -s backend/tests -v
```

`qa/` 內另有 API 驗收腳本與假資料後端（不呼叫真實 Gemini）。

---

## 3. 相依套件

### 3.1 後端（`backend/requirements.txt`，完整鎖定版本見 `requirements.lock`）

| 套件 | 版本 | 用途 |
| --- | --- | --- |
| fastapi | 0.141.1 | Web 框架 |
| uvicorn[standard] | 0.52.4 | ASGI 伺服器 |
| httpx | 0.28.1 | 呼叫外部資料來源 |
| pydantic | 2.13.4 | 請求與回應模型 |
| google-genai | 1.75.0 | Gemini API SDK |
| psycopg[binary,pool] | 3.3.6 | PostgreSQL 連線 |
| python-dotenv | 1.2.3 | 讀取 `.env` |
| pypinyin | 0.55.0 | 中文名稱搜尋輔助 |
| tzdata | 2026.5 | Windows 時區資料 |
| shioaji（選配） | ≥1.7, <2 | 永豐金唯讀行情；`requirements-shioaji.txt` |

### 3.2 前端（`frontend-vue/package.json`）

| 套件 | 版本 | 用途 |
| --- | --- | --- |
| vue | 3.5.13 | 前端框架 |
| vue-router | 4.5.0 | 路由 |
| vite | 6.3.5 | 開發伺服器與打包 |
| @vitejs/plugin-vue | 5.2.4 | Vite 的 Vue 外掛 |

---

## 4. 模型與版本

| 項目 | 內容 |
| --- | --- |
| 模型 | Google Gemini `gemini-3.5-flash-lite`（由 `GEMINI_MODEL` 設定，可不改程式碼直接替換） |
| SDK | `google-genai` 1.75.0 |
| 呼叫位置 | 只有後端呼叫；前端與瀏覽器不持有金鑰 |
| 使用場景 | 理解使用者需求、整理研究報告、助手白話回答、選股理由說明 |
| 不交給模型的事 | 篩選、排序、所有數字計算、資料來源判定 |

**輸出控管（預設值）**

| 項目 | 預設 |
| --- | --- |
| 助手單次輸入上限 | 1,200 字 |
| 助手單次輸出上限 | 1,024 tokens |
| 助手記憶的歷史訊息 | 8 則 |
| 助手每題最多工具呼叫 | 3 次 |
| 研究報告輸出上限 | 2,048 tokens |
| 串流逾時 | 90 秒 |

---

## 5. API

後端啟動後，完整互動式文件在 `/docs`（OpenAPI）。

| 分類 | 方法與路徑 | 說明 |
| --- | --- | --- |
| 健康檢查 | `GET /healthz`、`GET /api/health` | 服務狀態 |
| | `GET /api/sources/status`、`GET /api/sources/health` | 各資料來源連線狀態與最新資料日 |
| 市場與個股 | `GET /api/market/overview` | 市場總覽 |
| | `GET /api/market/index-history` | 大盤指數歷史 |
| | `GET /api/market/quote/{symbol}` | 個股日行情 |
| | `GET /api/market/history/{symbol}` | 個股歷史價 |
| | `GET /api/stocks/{symbol}/overview` | 個股總覽（行情、基本面、指標） |
| | `POST /api/stocks/snapshots` | 多檔快照（追蹤、比較用） |
| | `GET /api/companies/{symbol}` | 公司基本資料 |
| ESG／ETF | `GET /api/esg`、`GET /api/esg/{symbol}` | ESG 揭露 |
| | `GET /api/etf/{symbol}/holdings` | ETF 成份股 |
| 選股 | `POST /api/stocks/select` | 條件選股 |
| | `POST /api/stocks/ai-select` | 自然語言智慧選股 |
| | `POST /api/input/understand` | 輸入理解（白名單式解析） |
| AI 助手 | `POST /api/assistant/stream` | 串流回答（SSE） |
| AI 研究 | `POST /api/research` | 同步研究 |
| | `POST /api/research/jobs` | 建立非同步研究任務 |
| | `GET /api/research/jobs/{job_id}` | 查詢任務進度與結果 |
| | `POST /api/research/jobs/{job_id}/pause`、`/resume` | 暫停、繼續 |
| | `DELETE /api/research/jobs/{job_id}` | 取消任務 |
| | `DELETE /api/research/jobs/{job_id}/record` | 刪除研究紀錄 |
| 公告與新聞 | `GET /api/mops/material-events` | 重大訊息 |
| | `GET /api/news`、`GET /api/news/rss` | 證交所新聞 |
| | `GET /api/ir/conferences` | 法說會 |
| 使用者 | `POST /api/feedback` | 使用者回饋 |
| | `GET /api/workspace`、`PUT /api/workspace/state`、`PUT /api/workspace/conversations` | 工作區儲存 |
| | `POST /api/auth/register`、`/login`、`/logout`、`GET /api/auth/me` | 帳號（需 PostgreSQL） |
| | `GET /api/database/status` | 儲存模式 |
| 展示 | `POST /api/demo/session` | 申請訪客工作階段 |
| | `GET /runtime-config.js` | 前端執行設定（不含任何金鑰） |

**AI 可呼叫的資料工具（白名單）**：`market_snapshot`、`price_history`、`company_profile`、`material_events`、`investor_conferences`。不在清單內的工具呼叫會被拒絕；系統不執行模型產生的程式碼或網址。

---

## 6. 環境變數

設定檔為專案根目錄的 `.env`（已被 Git 忽略，不會上傳）。範本見 `backend/.env.example`。修改後需重新啟動後端。

### 6.1 必要

| 變數 | 說明 |
| --- | --- |
| `GEMINI_API_KEY` | Gemini 金鑰。未設定時公開資料功能可用，AI 功能會回報錯誤，不會以示範內容代替 |

### 6.2 服務

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `FINPILOT_HOST` / `FINPILOT_PORT` | 127.0.0.1 / 8080 | 監聽位址與埠（也接受平台提供的 `PORT`） |
| `FINPILOT_LOG_LEVEL` | info | 紀錄層級 |
| `FINPILOT_REQUEST_TIMEOUT_SECONDS` | 12 | 外部請求逾時 |
| `FINPILOT_RETRY_ATTEMPTS` | 2 | 外部請求重試次數 |
| `FINPILOT_CACHE_TTL_SECONDS` | 300 | 快取秒數 |
| `FINPILOT_PUBLIC_DATA_STALE_HOURS` | 72 | 公開資料超過幾小時視為過舊 |
| `FINPILOT_DATA_DIR` | `backend/data` | JSON 儲存位置 |
| `FINPILOT_STARTUP_SOURCE_CHECK` | true | 啟動時檢查各資料來源 |
| `GEMINI_MODEL` | gemini-3.5-flash-lite | 使用的 Gemini 模型 |
| `FINPILOT_GEMINI_ENABLED` | true | 是否呼叫 Gemini |

### 6.3 資料來源

| 變數 | 說明 |
| --- | --- |
| `TWSE_OPENAPI_BASE_URL`、`TPEX_OPENAPI_BASE_URL`、`TWSE_NEWS_RSS_URL` | 官方公開端點，已有預設值 |
| `FINMIND_BASE_URL`、`FINMIND_TOKEN` | FinMind；Token 選填，未填時使用匿名免費額度 |
| `SHIOAJI_ENABLED`、`SHIOAJI_API_KEY`、`SHIOAJI_SECRET_KEY`、`SHIOAJI_SIMULATION` | 選配，預設關閉；只讀行情，不下單 |
| `DATABASE_URL` | PostgreSQL 連線字串；未設定時使用 JSON 檔 |

### 6.4 公開展示與保護

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `FINPILOT_DEMO_ACCESS_ENABLED` | false | 開啟訪客模式，每位訪客自動取得短期工作階段 |
| `FINPILOT_DEMO_SESSION_SECRET` | — | 簽署工作階段用的隨機字串（開啟訪客模式時必填） |
| `FINPILOT_DEMO_SESSION_TTL_SECONDS` | 14400 | 工作階段有效時間（4 小時） |
| `FINPILOT_DEMO_SESSION_ISSUE_LIMIT_PER_MINUTE` | 8 | 每分鐘最多發出幾個工作階段 |
| `FINPILOT_DEMO_INVITE_TOKEN` | — | 設定後訪客需輸入邀請碼 |
| `FINPILOT_CORS_ORIGINS` | — | 允許的前端網址，逗號分隔，不可填 `*` |
| `FINPILOT_RATE_LIMIT_PER_MINUTE` | 60 | 每位訪客每分鐘 API 上限 |
| `FINPILOT_SYSTEM_RATE_LIMIT_PER_MINUTE` | 240 | 全站每分鐘 API 上限 |
| `FINPILOT_DAILY_GEMINI_CALL_LIMIT` / `_TOKEN_LIMIT` | 20 / 250,000 | 全站每日 Gemini 呼叫與 token 上限（台灣時間 00:00 重置） |
| `FINPILOT_VISITOR_DAILY_GEMINI_CALL_LIMIT` / `_TOKEN_LIMIT` | 20 / 250,000 | 每位訪客每日 Gemini 上限 |
| `FINPILOT_ASSISTANT_MAX_CONCURRENT` / `_PER_VISITOR` | 2 / 1 | 助手同時執行數 |
| `FINPILOT_RESEARCH_MAX_CONCURRENT` / `_PER_VISITOR` | 1 / 1 | 研究同時執行數 |
| `FINPILOT_PREVIEW_AUTH_REQUIRED`、`FINPILOT_PREVIEW_TOKEN` | false | 共用權杖保護模式（雲端預覽用） |
| `FINPILOT_PREVIEW_FIXTURE_MODE` | false | 假資料模式，不連外部服務與 Gemini |

助手輸出上限相關變數見第 4 節。

---

## 7. 授權

### 7.1 本專案程式碼

本專案為競賽作品，目前未採用開源授權，著作權由 PINWISE 團隊保留。評審與主辦單位可為評選目的檢視、執行本程式。

### 7.2 第三方套件

所用套件皆為開源授權，例如 FastAPI、Vue、Vite、httpx、pydantic 為 MIT 或 BSD 授權，google-genai 為 Apache-2.0。使用時依各套件授權條款辦理。

### 7.3 資料來源

| 資料 | 來源 | 更新頻率 | 授權狀態 |
| --- | --- | --- | --- |
| 股價與成交量、基本面、月營收、ESG 揭露 | 證交所、櫃買中心 OpenAPI | 每交易日／月／季／年 | 網站條款規定以程式下載須經同意，已授權政府資料開放平臺的資料除外；各資料集能否商用尚未向官方確認 |
| 重大訊息與法說 | 公開資訊觀測站（經證交所／櫃買 OpenAPI） | 每日 | 同上 |
| 歷史報酬與波動 | FinMind（原始資料來自交易所） | 每交易日 | 尚未查到商業使用的公開條款 |
| 證交所新聞 | 證交所 RSS（僅標題與連結） | 不定期 | 已列於政府資料開放平臺，RSS 管道是否適用同一授權尚未確認 |
| ETF 成份股 | 元大、富邦、國泰、台新、復華、野村、兆豐、永豐投信官網 | 依各投信公布 | 各網站條款尚未逐一確認 |
| AI 整理與回答 | Google Gemini（不視為證據） | 每次提問 | 目前使用免費方案，輸入可能用於改善產品；正式上線應改用付費方案 |

PINWISE 目前為競賽展示。若要正式上線，須先取得各資料提供者的正式授權或書面同意，並依條款標示來源。網站內「資料與證據中心」也有相同說明。

---

## 8. 資料流程

### 8.1 AI 標的研究（主要流程）

```
使用者提問
  → ① 輸入理解：Gemini 把白話拆成條件；程式以白名單驗證，不執行模型產生的程式碼或網址
  → ② 使用者確認：研究開始前先確認範圍，執行中可暫停、繼續或取消
  → ③ 規劃步驟：程式決定需要哪些資料工具
  → ④ 取得資料：呼叫官方來源，記錄每筆資料的來源與日期；查不到時放寬條件或改走備援來源
  → ⑤ 程式計算：期間報酬、年化波動、最大回撤、區間高低、平均成交量
  → ⑥ AI 整理：Gemini 只根據 ④⑤ 的結果撰寫說明
  → ⑦ 逐句檢核：依標的、數值、單位、日期、期間與來源逐句核對，不合格的句子與其相依結論會被移除
  → ⑧ 輸出：研究結論、重點指標、風險、後續觀察條件，以及每項證據的來源與日期
```

每一步都會留下紀錄（Agent trace），畫面即時顯示進度。

### 8.2 智慧選股

一句話需求 → Gemini 解讀成條件 → 程式用 TWSE／TPEx 日資料篩選市場、產業與產品類型，用 FinMind 日收盤計算年化波動 → 程式排序 → Gemini 為每檔撰寫選股理由。篩選與排序不交給模型。

### 8.3 PINWISE 助手

使用者提問 → 後端判斷是否需要資料工具（每題最多 3 次）→ 取得官方資料 → Gemini 串流回答 → 工具型回答須先通過後端事實檢核才開始顯示。助手記得前幾輪提到的標的，可以接續追問。

### 8.4 資料儲存

| 資料 | 位置 |
| --- | --- |
| 研究任務、Agent trace、Gemini 用量 | PostgreSQL；未設定時存為 `backend/data/` JSON 檔 |
| 使用者偏好、追蹤清單、對話 | 瀏覽器 localStorage（訪客模式下每位訪客分開） |
| 帳號與登入工作階段 | PostgreSQL（密碼以 scrypt 雜湊儲存） |
| 外部資料快取 | 記憶體，預設 300 秒 |

---

## 9. 權限與安全

### 9.1 金鑰保護

- 所有金鑰（Gemini、FinMind、資料庫）只存在後端的 `.env`，不送到瀏覽器、不寫入前端打包檔、不上傳到 Git。
- 前端從 `/runtime-config.js` 取得執行設定，內容不含任何金鑰。
- 後端只開放允許清單內的靜態檔案，`.env` 等檔案無法從網址存取。

### 9.2 使用者存取

| 模式 | 適用 | 行為 |
| --- | --- | --- |
| 本機（local） | 開發 | 直接使用 |
| 訪客工作階段（demo-session） | 公開展示 | 每位訪客自動取得簽章權杖（預設 4 小時），各自的紀錄互不相通；可加邀請碼 |
| 共用權杖（shared-token） | 雲端預覽 | 所有 API 都需要相同的 Bearer 權杖 |
| 帳號登入 | 選用 | 帳號密碼註冊登入（需 PostgreSQL），有登入嘗試次數限制 |

### 9.3 濫用防護

- 每位訪客與全站的每分鐘 API 上限，超過時回應 429，並提示稍後再試。
- Gemini 每日呼叫與 token 預算（全站與每位訪客分開計算），超過後 AI 功能暫停到隔日。
- 助手與研究的同時執行數上限，每位訪客同時只能跑一個。
- CORS 只允許指定網址。

### 9.4 Agent 權限邊界

- AI 只能呼叫 5 個白名單資料工具，全部唯讀。
- 不執行模型產生的程式碼或網址，未確認的網址不會出現在回答中。
- 不提供買賣指令、不連接下單；Shioaji 只讀行情、不載入憑證。
- 研究開始前需使用者確認，執行中可暫停或取消。
- 提醒使用者不要在提問中輸入個人資料；回饋內容會先遮蔽 email、電話、身分證字號。

---

## 10. 已知限制

| 限制 | 說明 |
| --- | --- |
| 非即時行情 | 使用最近可得的日資料，畫面會標示資料日期 |
| 展示依賴開發電腦 | 公開網址透過 ngrok 由開發電腦提供，電腦關機時無法連線 |
| Gemini 額度 | 使用免費方案並設有每日上限，額度用完時 AI 功能暫停到隔日（台灣時間 00:00 重置） |
| 手機版 | 以電腦使用為主，手機版版面仍在調整 |
| 資料覆蓋 | 沒有盤中即時價；中信、群益、凱基、統一等投信的 ETF 成份股尚未納入 |
| 資料授權 | 各資料來源的商業使用授權尚未全部確認（見第 7 節） |
| 工作區同步 | 登入帳號後，偏好與追蹤清單目前只存在瀏覽器，不同步到資料庫 |
| 使用者驗證 | 問卷 28 份，功能改善依問卷與實測判讀，尚未經大規模使用者驗證 |
| 雲端部署腳本 | Netlify 打包腳本尚未改為打包 Vue 前端，目前以 ngrok 方式展示 |

---

## 11. 故障排除

| 狀況 | 原因與處理 |
| --- | --- |
| 畫面打得開，但資料都載入失敗 | 後端沒啟動或不在 8080。開啟 `http://127.0.0.1:8080/api/health` 確認 |
| 開 8080 看到 404 | 還沒打包前端。開發時請開 5173，或先執行 `npm run build` |
| 8080 被佔用 | 有舊的後端沒關閉。Windows 可用 `Get-NetTCPConnection -LocalPort 8080 -State Listen` 找出程序並結束 |
| AI 回答「配額限制」或 429 | Gemini 額度用完，等額度恢復，不要連續重送 |
| 顯示「展示系統目前忙碌」 | 達到全站每分鐘上限，稍等一分鐘再試 |
| 公開網址打不開 | 確認「PINWISE backend」與「PINWISE ngrok」兩個視窗都還開著 |
| 首次開啟出現 ngrok 提示頁 | 按「Visit Site」即可進入 |
| 公開網址的畫面是舊的 | 重新執行 `start_public_demo.cmd`，重新打包前端 |
| 修改 `.env` 沒有生效 | 重新啟動後端 |
| 資料庫連線失敗、後端無法啟動 | 檢查 `DATABASE_URL`；密碼含 `@ : / # %` 時須改寫成 URL 編碼 |
