# PINWISE R2 後端介紹

這是一個用 **FastAPI + Python** 寫的後端，提供台灣股市的公開資料與 AI 分析。它和前端（`index.html` 與各 CSS/JS）**同源部署**，並刻意讓 `.env` 等機敏設定不會外洩給瀏覽器。

- **進入點**：[`../run.py`](../run.py) 以 `uvicorn` 啟動 [`main.py`](main.py) 裡的 `app`
- **相依套件**：FastAPI、uvicorn、httpx、pydantic、google-genai、psycopg（PostgreSQL）（見 [`../requirements.txt`](../requirements.txt)）
- 全後端約 7,800 行，刻意避開框架以外的沉重相依

## 分層結構

```
main.py  ── FastAPI 路由、中介層、啟動/關閉生命週期
  │
  ├─ providers/   與外部資料源溝通（一個來源＝一個類別）
  ├─ services/    商業邏輯（串接多個 provider）
  ├─ storage/     持久化與帳號（database / repositories / auth）
  ├─ core/        橫向基礎建設（config / models / http_client / normalization / provenance）
  └─ security/    存取控制（preview_security：中介層、速率限制、用量預算、demo session）
```

> `main.py` 刻意保留在 `app/` 根目錄，作為應用組裝入口。

### storage/（持久化與帳號）

| 檔案 | 用途 |
| --- | --- |
| `database.py` | PostgreSQL 連線、建表、`database_summary` |
| `repositories.py` | `WorkspaceRepository`、`PostgresJobStore`、`PostgresUsageBudget`（把工作區、研究任務、用量預算存進 DB） |
| `auth.py` | `AccountRepository`（帳號、session）、`AccountSessionMiddleware`、`LoginRateLimiter` |

> 雙模式：有設 `DATABASE_URL` 就用 PostgreSQL，沒設就自動退回本機 JSON 檔（`backend/data/`）。

### core/（橫向基礎建設）

| 檔案 | 用途 |
| --- | --- |
| `config.py` | 讀 `.env`、設定值上下限夾擠（clamp） |
| `models.py` | pydantic 請求/回應模型 |
| `http_client.py` | 具重試/快取的 HTTP 客戶端 |
| `normalization.py` | 股票代號正規化與欄位解析 |
| `provenance.py` | 資料來源標註（真實/示範） |

### security/（存取控制）

| 檔案 | 用途 |
| --- | --- |
| `preview_security.py` | `PreviewAccessMiddleware`、速率限制、`GeminiUsageBudget`、`DemoSessionManager`、並發限制 |

### providers/（外部資料源）

分別封裝台灣的**官方與公開來源**：

| 檔案 | 用途 |
| --- | --- |
| `twse.py` / `tpex.py` | 上市、上櫃的每日行情與官方公開資料 |
| `mops.py` | 公司基本資料與每日重大訊息 |
| `finmind.py` | 歷史日價（供 K 線圖使用） |
| `fundamentals.py` | 本益比、殖利率、股價淨值比、月營收、累計 EPS 等官方財務 |
| `news.py` / `investor_relations.py` | 官方新聞 RSS、法說會 |
| `gemini.py` | Google Gemini（AI 生成），附帶用量預算控管 |
| `shioaji.py` | 選配的唯讀行情來源 |
| `preview.py` | **隔離預覽模式**用的假 provider（完全不連外部，用於示範） |

### services/（商業邏輯）

| 檔案 | 用途 |
| --- | --- |
| `market.py` | 選股與快照 |
| `ai_picker.py` | 自然語言選股（AI 負責解讀與說明，篩選/排序只用官方資料） |
| `assistant.py` + `assistant_claims.py` | 串流 AI 助手，以及對其主張做查核 |
| `research.py` + `research_jobs.py` | 深度研究（同步執行＋非同步任務管理） |
| `input_understanding.py` | 確定性、允許清單式的輸入解讀（不執行模型產生的程式碼或 URL） |
| `tool_router.py` / `conversation_memory.py` / `analytics.py` | 工具分派、對話記憶、指標計算 |

## API 路由（出自 `main.py`）

- `/healthz`、`/api/health`、`/api/sources/status`、`/api/sources/health` — 健康檢查與各來源狀態
- `/api/market/quote/{symbol}`、`/api/stocks/{symbol}/overview`、`/api/market/history/{symbol}` — 行情、K 線、歷史資料
- `/api/stocks/select`、`/api/stocks/ai-select`、`/api/stocks/snapshots` — 選股
- `/api/assistant/stream`（SSE 串流）、`/api/research`、`/api/research/jobs/...` — AI 助手與研究
- `/api/companies/{symbol}`、`/api/mops/material-events`、`/api/news`、`/api/ir/conferences` — 公司資料與公告
- `/api/auth/...`、`/api/workspace/...`、`/api/database/status` — 帳號、工作區儲存、資料庫狀態

## 幾個關鍵設計重點

1. **雙模式儲存** — 有 `DATABASE_URL` 就用 PostgreSQL，沒有就自動退回本機 JSON 檔（見 `main.py`）。為避免資料分散兩處，DB 連線失敗會直接 fail-fast。
2. **隔離預覽（fixture mode）** — 完全不呼叫外部服務與真實 Gemini，改用假 provider，用於安全示範。
3. **多層安全** — `PreviewAccessMiddleware`、`AccountSessionMiddleware`、CORS 允許清單、速率限制、Gemini 用量預算、訪客展示 session（見 [`preview_security.py`](preview_security.py)）。靜態檔也用 `FrontendStaticFiles` 僅開放允許清單內的檔案。
4. **AI 不造假** — 缺少 API Key 時助手會回錯誤「不改用示範回答」；篩選與排序一律用官方資料，AI 只做解讀與說明。
5. **設定全走環境變數** — [`config.py`](config.py) 讀取 `.env`，並對每個值做上下限夾擠（clamp）。
