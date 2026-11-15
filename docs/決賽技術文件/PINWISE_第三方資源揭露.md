# PINWISE 第三方資源揭露

投資情報與智慧選股 AI Agent｜NAPAI Agentic AI 校園落地創新應用競賽 2026｜B 組・題目一 決賽

> 本文件揭露 PINWISE 使用的開源軟體、模型、資料集與 API、生成式 AI，以及其他第三方內容與服務，並說明來源、用途與授權範圍。授權資訊依各套件的發布資料與各服務公開條款整理（2026 年 11 月查閱），不構成法律意見。

## 目錄

1. 總覽
2. 生成式 AI
3. AI 模型與 API
4. 資料集與資料 API
5. 開源軟體：後端
6. 開源軟體：前端
7. 開發與執行環境
8. 第三方服務與內容
9. 授權遵循說明

---

## 1. 總覽

| 類別 | 項目 | 用途 | 授權範圍摘要 |
| --- | --- | --- | --- |
| 生成式 AI（產品內） | Google Gemini API | 理解需求、白話解說 | Gemini API 服務條款；目前為免費方案 |
| 生成式 AI（開發） | Claude Code（Anthropic） | 協助撰寫與修改程式、整理文件 | Anthropic 服務條款；產出由團隊審閱後採用 |
| 生成式 AI（素材） | ChatGPT 圖像生成（OpenAI） | Logo、網站背景與助手插圖 | OpenAI 服務條款；輸出權利歸使用者 |
| 資料 API | 證交所、櫃買中心、公開資訊觀測站 OpenAPI | 行情、基本面、重大訊息、ESG | 政府開放資料；商業使用範圍尚待確認 |
| 資料 API | FinMind | 歷史日價、波動計算 | 匿名免費額度；商業使用條款尚待確認 |
| 第三方內容 | 8 家投信官網 ETF 成份股 | ETF 成份股與重疊比較 | 各網站條款尚待確認 |
| 開源軟體 | 後端 Python 套件 41 個、前端 npm 套件 86 個 | 系統開發與執行 | MIT、BSD、Apache-2.0 等寬鬆授權，另有 LGPL-3.0、MPL-2.0 |
| 服務 | ngrok、GitHub、Google 表單、Google 雲端硬碟 | 對外展示、版本管理、問卷、影片 | 各服務使用條款 |

**AI 使用原則**：所有數字（行情、報酬、波動、回撤、基本面）都由程式從官方資料取得或計算，不由生成式 AI 產生。AI 只負責理解需求與白話說明，回答會經過程式逐句檢核。

---

## 2. 生成式 AI

### 2.1 產品內使用：Google Gemini

| 項目 | 內容 |
| --- | --- |
| 提供者 | Google |
| 模型 | `gemini-3.5-flash-lite`（可由環境變數 `GEMINI_MODEL` 更換） |
| 存取方式 | Gemini API，透過 `google-genai` Python SDK 1.75.0，只由後端呼叫 |
| 用途 | ① 把使用者的白話需求拆成篩選條件；② 根據程式取得與計算的資料，撰寫研究報告、選股理由與助手回答 |
| 不交給模型的事 | 篩選、排序、所有數字計算、資料來源判定 |
| 授權範圍 | 依 Google Gemini API 服務條款與 Google API 服務條款使用。目前使用免費方案：輸入與輸出可能被 Google 用於改善產品，也可能由人工檢視，因此網站提醒使用者不要輸入個人資料。正式上線應改用付費方案 |
| 揭露方式 | 網站內「資料與證據中心」標示 AI 回答「不算證據」；研究報告與助手回答附資料來源與日期 |

### 2.2 開發過程使用：Claude Code

| 項目 | 內容 |
| --- | --- |
| 提供者 | Anthropic |
| 工具 | Claude Code（AI 程式開發助手） |
| 用途 | 協助撰寫、修改與除錯程式碼，整理 README、技術文件與本揭露文件 |
| 使用方式 | 團隊提出需求並審閱、測試 AI 產出，決定是否採用；Git 紀錄中由 AI 協助的 commit 標有 `Co-Authored-By: Claude` |
| 授權範圍 | 依 Anthropic 服務條款，使用者擁有產出內容的權利 |

### 2.3 素材生成：ChatGPT 圖像生成

| 項目 | 內容 |
| --- | --- |
| 提供者 | OpenAI |
| 工具 | ChatGPT 圖像生成 |
| 授權範圍 | 依 OpenAI 使用條款，使用者擁有輸出內容的權利，可用於本專案 |
| 標示 | 部分圖檔內含 OpenAI 的 C2PA 內容憑證（標記為 AI 生成） |

由 ChatGPT 生成的檔案：

| 檔案（`assets/`） | 用途 |
| --- | --- |
| `pinwise-logo.png`、`pinwise-mark.png`、`pinwise-favicon.png` | PINWISE Logo、側欄標誌、瀏覽器分頁圖示，也用於簡報 |
| `hero-taipei-sunset.png` | 首頁主視覺背景 |
| `scene-coast-blue-hour.png`、`scene-courtyard-day.jpg`、`scene-garden-terrace.jpg`、`scene-library-warm.png`、`scene-mountain-dawn.png` | 可切換的網站背景主題 |
| `finpilot-assistant.png` | 助手插圖 |

---

## 3. AI 模型與 API

| 名稱 | 提供者 | 用途 | 授權範圍 |
| --- | --- | --- | --- |
| Gemini API（`gemini-3.5-flash-lite`） | Google | 見 2.1 | Gemini API 服務條款 |
| `google-genai` SDK 1.75.0 | Google | 呼叫 Gemini API | Apache-2.0 |
| Shioaji API（選配，預設關閉） | 永豐金證券 | 唯讀行情健康檢查，不下單、不載入憑證 | 永豐金 API 使用條款；本專案展示時未啟用 |

本專案未使用其他預訓練模型，也未自行訓練或微調模型。

---

## 4. 資料集與資料 API

| 資料 | 來源 | 存取方式 | 用途 | 授權範圍 |
| --- | --- | --- | --- | --- |
| 上市股票日行情、公司資料、基本面（本益比、殖利率、股價淨值比）、月營收、EPS、ESG 揭露 | 臺灣證券交易所 | TWSE OpenAPI（`openapi.twse.com.tw`） | 市場總覽、選股、研究、ESG 專區 | 證交所網站條款規定以自動程式下載資料須經同意，已授權政府資料開放平臺的資料除外；各資料集能否商用尚未向官方確認 |
| 上櫃股票日行情、公司資料、基本面、ESG 揭露 | 證券櫃檯買賣中心 | TPEx OpenAPI（`www.tpex.org.tw/openapi`） | 同上 | 同上 |
| 重大訊息、法說會公告 | 公開資訊觀測站 | 經證交所、櫃買中心 OpenAPI 取得 | 公告與事件、研究 | 同上 |
| 證交所新聞 | 臺灣證券交易所 | RSS（只取標題與連結） | 公告與事件 | 已列於政府資料開放平臺；RSS 管道是否適用同一授權尚未確認。只顯示標題並連回原網站，不轉載內文 |
| 歷史日收盤價 | FinMind（原始資料來自交易所） | FinMind API v4（匿名額度，Token 選填） | 期間報酬、年化波動、最大回撤計算 | 尚未查到資料商業使用的公開條款 |
| ETF 成份股 | 元大、富邦、國泰、台新、復華、野村、兆豐、永豐投信官網 | 讀取各投信公開頁面 | ETF 成份股、重疊比較 | 各網站條款尚未逐一確認，也尚未取得同意 |

**資料揭露做法**

- 每筆資料保留來源與資料日期，網站內「資料與證據中心」列出各來源的狀態、更新日期與授權疑慮。
- 資料只用於非商業的競賽展示。若要正式上線，須先取得各資料提供者的正式授權或書面同意，並依條款標示來源。

**自行收集的資料**

| 資料 | 收集方式 | 用途 | 說明 |
| --- | --- | --- | --- |
| 使用者問卷 28 份 | Google 表單，匿名線上問卷 | 需求分析（Kano 分析、阻力分析） | 未收集可識別個資；文件中只呈現統計結果 |

---

## 5. 開源軟體：後端

Python 套件，版本鎖定於 `backend/requirements.lock`。直接相依套件以粗體標示。

| 套件 | 版本 | 授權 | 用途 |
| --- | --- | --- | --- |
| **fastapi** | 0.141.1 | MIT | Web 框架 |
| **uvicorn** | 0.52.4 | BSD-3-Clause | ASGI 伺服器 |
| **httpx** | 0.28.1 | BSD-3-Clause | 呼叫外部資料來源 |
| **pydantic** | 2.13.4 | MIT | 請求與回應模型 |
| **google-genai** | 1.75.0 | Apache-2.0 | Gemini API SDK |
| **psycopg**、psycopg-binary | 3.3.6 | LGPL-3.0-only | PostgreSQL 連線 |
| psycopg-pool | 3.3.3 | LGPL-3.0-only | PostgreSQL 連線池 |
| **python-dotenv** | 1.2.3 | BSD-3-Clause | 讀取 `.env` |
| **pypinyin** | 0.55.0 | MIT | 中文名稱搜尋輔助 |
| **tzdata** | 2026.5 | Apache-2.0 | Windows 時區資料 |
| starlette | 1.7.0 | BSD-3-Clause | FastAPI 底層框架 |
| pydantic_core | 2.46.4 | MIT | pydantic 核心 |
| anyio | 4.15.1 | MIT | 非同步支援 |
| httpcore | 1.0.9 | BSD-3-Clause | HTTP 核心 |
| h11 | 0.16.0 | MIT | HTTP/1.1 協定 |
| httptools | 0.8.0 | MIT | HTTP 解析 |
| websockets | 16.1.1 | BSD-3-Clause | WebSocket 支援 |
| watchfiles | 1.3.0 | MIT | 檔案監看 |
| uvloop（非 Windows） | 0.23.0 | MIT / Apache-2.0 | 事件迴圈 |
| google-auth | 2.61.0 | Apache-2.0 | Google 驗證 |
| requests | 2.34.2 | Apache-2.0 | HTTP 用戶端（google-auth 相依） |
| urllib3 | 2.8.0 | MIT | HTTP 用戶端 |
| certifi | 2026.7.22 | MPL-2.0 | 根憑證 |
| charset-normalizer | 3.5.2 | MIT | 編碼偵測 |
| idna | 3.20 | BSD-3-Clause | 國際化網域名稱 |
| cryptography | 50.0.2 | Apache-2.0 或 BSD-3-Clause | 加密函式 |
| cffi | 2.1.1 | MIT-0 | C 介面 |
| pycparser | 3.0 | BSD-3-Clause | C 解析 |
| pyasn1 | 0.6.4 | BSD-2-Clause | ASN.1 |
| pyasn1_modules | 0.4.2 | BSD-2-Clause | ASN.1 模組 |
| tenacity | 9.1.4 | Apache-2.0 | 重試機制 |
| distro | 1.9.0 | Apache-2.0 | 作業系統資訊 |
| PyYAML | 6.0.3 | MIT | YAML 解析 |
| click | 8.5.0 | BSD-3-Clause | 命令列 |
| colorama（Windows） | 0.4.6 | BSD-3-Clause | 終端機色彩 |
| sniffio | 1.3.1 | MIT / Apache-2.0 | 非同步偵測 |
| typing_extensions | 4.16.0 | PSF-2.0 | 型別擴充 |
| typing-inspection | 0.4.4 | MIT | 型別檢查 |
| annotated-types | 0.8.0 | MIT | 型別註記 |
| annotated-doc | 0.0.5 | MIT | 型別註記文件 |
| shioaji（選配，預設未安裝） | ≥1.7, <2 | 永豐金證券條款 | 選配行情來源 |

---

## 6. 開源軟體：前端

npm 套件共 86 個（含間接相依），版本鎖定於 `frontend-vue/package-lock.json`。授權分布：MIT 83 個、BSD-2-Clause 1 個、BSD-3-Clause 1 個、ISC 1 個。

| 套件 | 版本 | 授權 | 用途 |
| --- | --- | --- | --- |
| vue | 3.5.13 | MIT | 前端框架（含 `@vue/*` 子套件） |
| vue-router | 4.5.0 | MIT | 頁面路由 |
| vite | 6.3.5 | MIT | 開發伺服器與打包（僅開發） |
| @vitejs/plugin-vue | 5.2.4 | MIT | Vite 的 Vue 外掛（僅開發） |
| rollup | 4.65.0 | MIT | 打包（Vite 相依，僅開發） |
| esbuild | 0.25.12 | MIT | 編譯（Vite 相依，僅開發） |
| postcss | 8.5.31 | MIT | CSS 處理 |

前端未使用第三方 UI 元件庫、圖示庫或圖表庫：介面圖示為專案內自行定義的 SVG 路徑，圖表以自行撰寫的 SVG 繪製。

---

## 7. 開發與執行環境

| 項目 | 版本 | 授權 | 用途 |
| --- | --- | --- | --- |
| Python | 3.11.9 | PSF License | 後端執行環境 |
| Node.js | 18 以上（開發使用 24） | MIT | 前端建置 |
| PostgreSQL（選用） | — | PostgreSQL License | 資料庫 |
| PptxGenJS | — | MIT | 產生決賽簡報初版 |
| Microsoft PowerPoint、Word | — | 商業授權 | 編輯簡報與提案、匯出 PDF |
| 微軟正黑體（Microsoft JhengHei） | — | Windows 隨附字型 | 簡報與文件字型；嵌入 PDF 用於檢視與列印 |

---

## 8. 第三方服務與內容

| 服務 | 提供者 | 用途 | 授權範圍 |
| --- | --- | --- | --- |
| ngrok（免費方案，固定網址） | ngrok | 將展示用電腦的網站公開給評審試用 | ngrok 服務條款 |
| GitHub | GitHub | 程式碼版本管理與交付 | GitHub 服務條款 |
| Google 表單 | Google | 匿名使用者問卷 | Google 服務條款 |
| Google 雲端硬碟 | Google | 存放 Demo 影片 | Google 服務條款 |

`render.yaml`、`netlify.toml` 為保留的雲端部署設定，決賽展示時未使用 Render 與 Netlify。

---

## 9. 授權遵循說明

- **寬鬆授權（MIT、BSD、Apache-2.0、ISC、PSF、MIT-0）**：以原樣使用，未修改原始碼；完整授權條款隨各套件安裝於 `node_modules/` 與 Python 虛擬環境中。
- **LGPL-3.0（psycopg）**：以未修改的函式庫透過 Python 動態載入使用，使用者可自行替換版本，符合 LGPL 的使用條件。
- **MPL-2.0（certifi）**：未修改原始檔，以原樣使用。
- **資料來源**：只用於非商業的競賽展示，介面中標示來源與資料日期；正式上線前須取得授權。
- **生成式 AI 產出**：程式碼由團隊審閱並測試後採用；圖像依 OpenAI 條款使用並在本文件揭露；產品內 AI 回答一律標示資料來源，數字由程式提供。
- **本專案程式碼**：目前未採用開源授權，著作權由 PINWISE 團隊保留；評審與主辦單位可為評選目的檢視與執行。
