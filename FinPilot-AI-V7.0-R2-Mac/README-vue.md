# PINWISE 前端（Vue 版）

`frontend-vue/` 是 Vue 3 + Vite 寫的前端，也是目前唯一的前端。樣式和圖片直接使用根目錄的 `css/`、`assets/`。

## 啟動

先依 [README.md](README.md) 啟動後端，再：

```sh
cd frontend-vue
npm install    # 第一次或 package.json 有變動時
npm run dev
```

開啟 <http://localhost:5173>（不要用 127.0.0.1）。

- `/api` 會自動轉給後端 `http://127.0.0.1:8080`。後端在別的連接埠時，用 `FINPILOT_BACKEND_URL` 指定。
- `npm run build` 會輸出到 `frontend-vue/dist/`。

## 程式結構

```
src/
├─ main.js         進入點：載入 css/ 五層樣式；線上模式先顯示存取入口
├─ App.vue         外框：側欄、頁面區、全域彈窗
├─ router.js       12 個頁面的路由
├─ api/
│  ├─ client.js    所有後端請求
│  └─ runtime.js   執行環境設定、API 網址、存取權杖
├─ stores/         共用狀態（設定、助手、研究、選股、自選股…）
├─ pages/          各頁面
├─ components/     元件
├─ data/           固定資料（側欄、導覽、FAQ、名詞）
└─ utils/          工具函式
```

## 開發注意事項

- **API 請求**一律透過 `api/client.js`，不要在元件裡直接 `fetch`，否則不會帶上 API 網址與權杖。
- **樣式**沿用 `css/` 的 class 名稱，改 class 前先查 CSS 規則。`body[data-page]` 有大量 CSS 依賴，不要移除。
- **圖片**一律用 `import x from '@root/assets/…'`，不要寫相對路徑字串。
- **v-html** 只能放固定圖示和 `markdown()` 的輸出，不要放未處理的使用者輸入。
- **導覽步驟**（`data/tours.js`）用 CSS 選擇器找元素，改頁面結構時要一起更新。
- **彈窗**用 `AppModal`，關閉時不渲染；不能只靠 `hidden` 隱藏。

## 線上模式

`index.html` 會先載入 `/runtime-config.js`，`api/runtime.js` 依裡面的 `accessMode` 決定怎麼連後端：

| `accessMode` | 行為 |
| --- | --- |
| `local` | 本機開發，直接進入 |
| `shared-token` | 先輸入預覽權杖 |
| `demo-session` | 自動申請短期訪客工作階段（需要邀請碼時先輸入） |

訪客模式下，每個分頁的 localStorage 資料分開存放。

## 與舊版的差異

舊版（已移除）的功能都已搬過來，以下是刻意改變或還沒做的：

- 登入後不會把資料同步到資料庫，資料只存在瀏覽器。
- 研究歷史沒有封存、回收桶、重新命名。
- 側邊欄用 ↑↓ 排序，沒有拖曳。
- 說明圖示 ⓘ 改成滑鼠停留顯示。
- 不會讀取舊版留在瀏覽器裡的資料。


- **資料不互通**：Vue 版的資料存在獨立的 localStorage 鍵（`pinwise_vue_settings`、`pinwise_vue_conversations`、`pinwise_vue_research`、`pinwise_vue_picker`、`pinwise_vue_workspace`），與舊版分開，兩邊看不到彼此的資料。
- **帳號登入後不會同步工作區**：登入、註冊、登出與後端驗證都可使用（需要後端設定 `DATABASE_URL`），但舊版登入後會把設定與對話同步到資料庫（`/api/workspace`）；Vue 版的資料格式不同，為避免覆蓋舊版存在資料庫的資料，目前不做同步，資料只存在瀏覽器。
- **追蹤頁「新增追蹤標的」**：舊版會跳到智慧選股；Vue 版改為直接搜尋代號或名稱加入。
- **自選股「前往股票比較」**：舊版會先跳出選擇要帶入哪幾檔的視窗；Vue 版直接前往比較頁，比較清單在各頁按「加入比較」決定。
- **研究歷史**：可查看、切換與刪除；舊版的封存、回收桶、重新命名沒有搬移。
- **側邊欄管理**：可用 ↑↓ 調整順序與開關顯示；舊版的拖曳排序沒有搬移。隱藏的頁面仍可從其他頁面的連結開啟，不會跳出「加入側邊欄」提醒。
- **說明圖示 ⓘ**：舊版是點擊後跳出的說明泡泡；Vue 版改為滑鼠停留時顯示說明文字。
- **市場總覽**：會先讀取資料來源狀態並顯示「公開來源 N / 9 可用」；舊版要先到資料與證據中心才會讀取。