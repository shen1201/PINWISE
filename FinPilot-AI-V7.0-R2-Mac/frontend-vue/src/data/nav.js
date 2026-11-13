// 搬自 js/data.js 的 navMeta 與 ICON_PATHS（只取側欄與首頁用到的圖示）。
export const navMeta = {
  home: ['home', '首頁'],
  research: ['book', 'AI 標的研究'],
  picker: ['chart', '智慧選股'],
  candidates: ['star', '我的追蹤'],
  tracking: ['radar', '公告與事件'],
  compare: ['compare', '股票比較'],
  scorecard: ['trophy', '我的投資足跡'],
  market: ['globe', '市場總覽'],
  evidence: ['database', '資料與證據中心'],
  learning: ['compass', '學習專區'],
  esg: ['leaf', 'ESG 專區'],
  settings: ['settings', '設定'],
}

export const navGroups = [
  ['主要功能', ['home', 'picker', 'research', 'candidates', 'tracking']],
  ['分析與資訊', ['market', 'compare', 'scorecard', 'evidence']],
  ['學習與說明', ['learning', 'esg']],
]

export const ICON_PATHS = {
  leaf: '<path d="M5 19c0-8 5-14 15-15 0 10-5 16-13 15"/><path d="M5 21c1-5 4-9 9-12"/>',
  home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9 21v-6h6v6"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="m12 12 6-5"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0V4Z"/><path d="M6 6H3v2a4 4 0 0 0 5 4M18 6h3v2a4 4 0 0 1-5 4M12 13v5M8 21h8M9 18h6"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5v-16ZM20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5v-16Z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  compare: '<path d="M7 7h14M17 3l4 4-4 4M17 17H3M7 13l-4 4 4 4"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6V21h-4v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H3v-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6V3h4v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
  bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  star: '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m15 9-2 4-4 2 2-4 4-2Z"/>',
  trending: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.5 2.5 0 1 1 4 2c-1 .7-1.6 1.2-1.6 2.5M12 17h.01"/>',
  guide: '<path d="M4 4h16v16H4z"/><path d="M8 8h8M8 12h5M8 16h3"/>',
  indicator: '<path d="M4 20V13h4v7M10 20V8h4v12M16 20V4h4v16"/>',
  bot: '<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M9 7V4h6v3M8 13h.01M16 13h.01M9 17h6"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  play: '<path d="m8 5 11 7-11 7V5Z"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  shield: '<path d="M12 3 5 6v5c0 5 3.5 8.5 7 10 3.5-1.5 7-5 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
}

// 研究頁的熱門主題（搬自 js/pages-core.js 的 researchPage）。
export const researchTopics = [
  ['台積電', '研究台積電的成長與風險'],
  ['聯發科', '研究聯發科的獲利與風險'],
  ['鴻海', '研究鴻海的營收動能與風險'],
  ['富邦金', '研究富邦金的獲利與股利'],
  ['0050', '研究 0050 的風險與表現'],
]

// 舊版要求研究題目時，首頁主題按鈕帶入的問題（搬自 js/events.js）。
export const topicQueries = {
  // 首頁主題範例：帶進「AI 標的研究」輸入框。標的研究一次只研究一檔，所以每個主題都指定一檔代表標的
  // （只寫產業名稱會被導回智慧選股）。
  熱門主題: '台積電 2330 的成長動能與風險',
  'AI 概念股': '廣達 2382 在 AI 伺服器的成長與風險',
  '高股息 ETF': '0056 高股息 ETF 的配息穩定度與風險',
  電動車產業: '台達電 2308 在電動車的布局與風險',
  生技醫療: '藥華藥 6446 的成長動能與風險',
}
