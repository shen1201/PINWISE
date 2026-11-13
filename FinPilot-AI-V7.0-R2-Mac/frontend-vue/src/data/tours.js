// 搬自 js/tours.js；selector 已對應 Vue 版頁面的元素（研究頁版面不同，改用 Vue 版的區塊）。
export const tours = {
  // 新手導覽只走主要流程；各頁的細部操作在 featureGuides。
  full: [
    { page: 'picker', selector: '[data-tour="picker-controls"]', title: '1. 智慧選股｜還不知道看哪幾檔', text: '用自己的話描述想找的標的，系統會列出值得研究的名單與列入原因。' },
    { page: 'picker', selector: '.top-search-button', title: '2. 搜尋股票｜直接查一檔', text: '知道代號或名稱時，任何頁面都能從這裡查 K 線與報酬；ETF 還能看成份股。' },
    { page: 'research', selector: '[data-tour="research-entry"]', title: '3. AI 標的研究｜深入一檔', text: '針對一檔股票或 ETF 整理理由、風險與資料來源，送出前會先確認研究範圍。' },
    { page: 'compare', selector: '.comparison-search-card', title: '4. 股票比較｜放在一起看', text: '最多三檔，用同一組標準對照；有不懂的地方可以直接問助手。' },
    { page: 'candidates', selector: '.wl-kpis', title: '5. 我的追蹤｜持續留意', text: '把關注的標的留在這裡比較表現與波動，之後可到「公告與事件」看官方公告有沒有影響原本的想法。' },
    { page: 'candidates', selector: '.assistant-dock', title: '6. PINWISE 助手｜隨時問', text: '看不懂名詞、數字或結果時，直接用白話問。問到個股時助手會先查官方資料再回答，回答僅供參考。' },
  ],
  home: [
    { page: 'home', selector: '.hero-query', title: '研究輸入框', text: '輸入一檔股票或 ETF 和想了解的方向；送出前會先確認研究範圍。' },
    { page: 'home', selector: '.topic-row', title: '熱門主題', text: '點主題會把研究問題範例填進上方輸入框，可以直接修改，再按「開始 AI 研究」。' },
    { page: 'home', selector: '.hero-query button', title: '開始 AI 研究', text: '按下後會建立新的研究任務，舊研究不會被覆蓋；一般問答請用左下角助手。' },
    { page: 'home', selector: '.top-search-button', title: '搜尋股票', text: '想直接查某一檔時，從右上角搜尋，任何頁面都能使用。' },
  ],
  research: [
    { page: 'research', selector: '[data-tour="research-entry"]', title: '建立研究問題', text: '輸入一檔股票或 ETF 建立研究任務；送出前會先確認研究範圍。' },
    { page: 'research', selector: '[data-tour="research-process"]', title: '研究進度', text: '進度會依後端研究任務的階段狀態更新，可暫停、繼續或重試。' },
    { page: 'research', selector: '[data-tour="research-sections"]', title: '研究內容', text: '完成後摘要會直接顯示在頁面下方，這裡可以查看風險、來源與 Agent 執行紀錄。' },
    { page: 'research', selector: '[data-tour="research-history"]', title: '最近研究任務', text: '過去的研究都收在這裡，點開會從右側滑出，可以回到任一份結果。' },
  ],
  // 智慧選股：先教怎麼問，再依目前畫面介紹起始方向或選股結果（optional 的步驟找不到就跳過）。
  picker: [
    { page: 'picker', selector: '[data-tour="picker-search"] input', title: '用一句話說需求', text: '例如「波動不要太大的高股息 ETF」「AI 伺服器有哪些公司」。打錯字也沒關係，AI 會依原意理解。' },
    { page: 'picker', selector: '#pickerSearchBtn', title: '交給 AI 分析', text: 'AI 先把句子轉成條件，再由程式用證交所、櫃買中心的官方資料篩選與排序；數字不是 AI 自己寫的。' },
    { page: 'picker', selector: '[data-tour="picker-advanced"]', title: '進階條件（需要時才用）', text: '想直接限定個股或 ETF、產業、波動高低時再打開。送出後會自動清掉，不會影響下一次。' },
    { page: 'picker', selector: '[data-tour="picker-presets"]', optional: true, title: '不知道怎麼問？', text: '先看這些常見方向，每格都是官方資料的真實前三名；按「帶入問題」就會填進上面的輸入框。' },
    { page: 'picker', selector: '.pk-switch', optional: true, title: '回到之前的選股', text: '切到「選股紀錄」可以打開最近 5 次的結果，不用重新查。' },
    { page: 'picker', selector: '.smart-stock-card', optional: true, title: '讀懂一張結果卡', text: '看「為什麼列入」與近 6 個月走勢、波動、回撤；有興趣就按「加入追蹤」或「加入比較」，想深入按「查看分析」。' },
    { page: 'picker', selector: '.pk-status', optional: true, title: '篩選過程與偏好', text: '這裡寫出從多少檔篩到剩幾檔、參考了你的哪些偏好；按「查看篩選過程」看每一步。' },
  ],
  // 公告與事件：公告怎麼讀 → 交給助手 → 每檔狀況 → 追蹤清單 → 官方消息 → 主動通知。
  tracking: [
    { page: 'tracking', selector: '[data-tour="tracking-events"] .list-row', optional: true, title: '追蹤股票的新公告', text: '你追蹤的股票在交易所重大訊息裡的公告，新的在前；標籤先告訴你是人事、營收、股利還是法說會。' },
    { page: 'tracking', selector: '[data-tour="tracking-events"] .list-row .outline-button', optional: true, title: '看不懂就問助手', text: '按「詢問助手」會把這則公告帶進助手，用白話說明它可能代表什麼、要注意什麼。' },
    { page: 'tracking', selector: '[data-tour="tracking-cover"]', optional: true, title: '每檔有沒有公告', text: '一眼看出哪幾檔有新消息。「無」只代表最近的每日重大訊息沒有這檔，不代表公司沒事。' },
    { page: 'tracking', selector: '[data-tour="tracking-events"]', title: '追蹤股票的公告', text: '加入追蹤後，這些股票的交易所重大訊息會整理在這裡；目前還沒有可顯示的公告。' , optional: true, onlyIfMissing: '[data-tour="tracking-events"] .list-row' },
    { page: 'tracking', selector: '[data-tour="tracking-list"]', title: '回頭檢查原本的想法', text: '每張卡片是一檔追蹤股票和當初記下的觀察條件；有新公告時按「重新評估」，看理由是否還成立。' },
    { page: 'tracking', selector: '[data-tour="tracking-news"]', optional: true, title: '證交所最新消息', text: '交易所發布的市場消息（新股上市、制度變更等），點標題會開官方原文。' },
    { page: 'tracking', selector: '.notification-bell', title: '不用一直回來看', text: '網頁開著時每 10 分鐘檢查一次：追蹤股票有新公告、大漲大跌或離高點太遠，會在這個鈴鐺通知你。' },
  ],
  // 我的投資足跡：會自動切換分頁，依序介紹四個分頁。
  scorecard: [
    { page: 'scorecard', selector: '[data-tour="fp-tabs"]', click: '[data-tab="overview"]', title: '四個分頁', text: '總覽看整體狀況、歷程看每次使用、徽章看收集進度、AI 查核看系統替你擋下了什麼。接下來依序帶你看。' },
    { page: 'scorecard', selector: '[data-tour="score-kpis"]', click: '[data-tab="overview"]', title: 'PINWISE 替你做了什麼', text: '累計查了多少官方資料、攔下多少對不上資料的句子，以及花了多少 Token。' },
    { page: 'scorecard', selector: '[data-tour="score-rating"]', click: '[data-tab="overview"]', title: '你的評價', text: '助手偶爾會問這次回答有沒有幫助。點「有用」「還好」「很糟」可以直接看對應的紀錄。' },
    { page: 'scorecard', selector: '[data-tour="score-risk"]', click: '[data-tab="overview"]', title: '風險觀察', text: '自己選提醒線（10%／15%／20%），檢查追蹤股票是否大漲大跌或從高點回落；超過時也會在鈴鐺通知。這不是停損建議。' },
    { page: 'scorecard', selector: '[data-tour="score-goal"]', click: '[data-tab="overview"]', optional: true, title: '離目標還有多遠', text: '輸入目標金額、每月投入和年數，看預估達成率與每月缺口；可以按「問助手規劃」。' },
    { page: 'scorecard', selector: '[data-tour="fp-history-filters"]', click: '[data-tab="history"]', title: '歷程', text: '每次研究、助手問答、選股都在這裡；可以依類型或評價篩選，也看得到你打過的文字回饋。' },
    { page: 'scorecard', selector: '[data-tour="fp-badge-hero"]', click: '[data-tab="badges"]', title: '徽章', text: '依核對資料、比較、看公告等好習慣累積，每天最多算 3 次；不獎勵交易、報酬或多用 AI，也沒有排名。' },
    { page: 'scorecard', selector: '[data-tour="fp-audit-kpis"]', click: '[data-tab="audit"]', title: 'AI 查核', text: '每份研究的資料覆蓋率、被擋下的錯誤類型，以及 Agent 每一步做了什麼，都可以點開檢查。' },
  ],
}

// 功能教學清單（對應舊版 openFeatureGuide）。
export const featureGuides = [
  ['home', 'home', '首頁', '研究輸入、熱門主題與開始研究'],
  ['research', 'bot', 'AI 標的研究', '研究任務、進度、Agent 流程與資料來源'],
  ['picker', 'chart', '智慧選股', '怎麼問、進階條件、讀懂結果卡'],
  ['tracking', 'radar', '公告與事件', '讀公告、問助手、重新評估與鈴鐺通知'],
  ['scorecard', 'trophy', '我的投資足跡', '總覽、歷程、徽章與 AI 查核四個分頁'],
]
