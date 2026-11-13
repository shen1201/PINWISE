# CSS 樣式層

PINWISE / FinPilot R2 前端的所有樣式。這五個檔是從早期多個版本補丁檔（`styles.css`、`layout-v68/v69/v610.css`、`palette-v612.css`、`polish-v613.css`、`workspace-v7/r2.css` …）**按職責收攏**而成，每個檔開頭的 `Consolidated from:` 註解記錄了來源。

## 檔案分層

| 檔案 | 職責 |
| --- | --- |
| `base.css` | reset、字體、全域變數（設計 token）|
| `layout.css` | 框架、側欄、版面、RWD（響應式）|
| `theme.css` | 色彩、深色模式、字級 |
| `components.css` | 按鈕、卡片、表單、modal、狀態元件 |
| `pages.css` | 各頁面專屬規則 |

## 載入順序不可更動

在 [`../frontend-vue/src/main.js`](../frontend-vue/src/main.js) 中固定依此順序匯入：

```js
import '@root/css/base.css'
import '@root/css/layout.css'
import '@root/css/theme.css'
import '@root/css/components.css'
import '@root/css/pages.css'
```

CSS 具有**層疊（cascade）**特性：後載入的規則會覆蓋前面同層級的規則。這些檔當初合併時刻意保留原始來源順序（各檔註解中的 `Source order is preserved to keep the existing cascade stable`），順序一旦改變畫面就可能跑版。新增規則時請放進**對應職責的檔案**，不要為了方便全部塞進 `pages.css` 或在尾端再疊一層補丁。

Vite 打包時會依內容產生帶雜湊的檔名，改動 CSS 後不需要手動處理快取版本字串。

## 為什麼不合成單一檔案？

技術上可以 concat，但不建議在原始碼層這麼做：

- **好處有限**：只少掉 4 個 HTTP 請求；在同源服務下幾乎無感。
- **壞處明確**：換來一個 400KB＋、難以定位的巨檔，維護更難、改動更容易踩到 cascade、git 衝突更多。

若要減少請求數／體積，正確做法是在**部署建置階段**把五層 concat + minify 成一包，原始碼仍維持分層。Vue 版的 `npm run build` 已經這樣做：五層會依匯入順序合併、壓縮成單一 CSS 檔。

## 維護須知（會踩的雷）

- **資產路徑要相對於本資料夾**：CSS 內的 `url(...)` 以 CSS 檔位置為基準，指向 `assets/` 時必須寫成 `url('../assets/xxx')`（例如 `base.css` 的背景圖）。
- **JS 寫入的 CSS 變數也一樣**：Vue 版的 [`../frontend-vue/src/stores/ui.js`](../frontend-vue/src/stores/ui.js) 會把背景場景寫進 `--scene`，再由本資料夾的 CSS 以 `var(--scene)` 使用；瀏覽器會以「使用 `var()` 的 CSS 檔」為基準解析相對路徑。因此圖片一律用 `import x from '@root/assets/…'` 取得 Vite 產生的絕對網址，不要在 JS 寫 `assets/xxx` 這類相對路徑字串，否則會被解析成 `css/assets/xxx` 而 404、背景消失。
- **新增 CSS 檔**：要在 `main.js` 依職責順序加入 `import`，否則不會載入。
- **舊版相關設定**：後端 [`../backend/app/main.py`](../backend/app/main.py) 的 `FrontendStaticFiles` 白名單與 `scripts/build_netlify_*.sh` 都是為已移除的舊版前端寫的，目前不影響 Vue 版。

## 已知技術債

`base.css` 偏大，且五個檔累積了不少 `!important` 與新舊重複的 token（版本補丁一路疊加的結果）。這屬於「CSS 內容清理」範疇，與分檔方式無關；日後可做一次死碼／重複 token 審查來瘦身，但需保留既有 cascade 行為。
