// 資料來源說明：只寫資料從哪來、用在哪裡；連線狀態和最新資料日看「各來源狀態」。
// LICENSE_REASONS 依各來源公開條款整理（2026-11-10 查閱），不是法律意見；條款更新時要一起改。
const TWSE = 'https://openapi.twse.com.tw/'
const TPEX = 'https://www.tpex.org.tw/openapi/'

export const DATA_SOURCES = [
  { icon: 'chart', kind: '股價與成交量', source: [['證交所', TWSE], '、', ['櫃買中心', TPEX], ' OpenAPI'], cycle: '每交易日', usedIn: '市場總覽、追蹤、比較' },
  { icon: 'trending', kind: '歷史報酬與波動', source: [['FinMind', 'https://finmindtrade.com/'], '（原始資料來自交易所）'], cycle: '每交易日', usedIn: '追蹤、比較、AI 研究' },
  { icon: 'database', kind: '基本面與月營收', source: [['證交所', TWSE], '、', ['櫃買中心', TPEX], ' OpenAPI'], cycle: '每日／月／季', usedIn: '股票詳情、AI 研究' },
  { icon: 'bell', kind: '重大訊息與法說', source: [['公開資訊觀測站', 'https://mops.twse.com.tw/'], '（OpenAPI）'], cycle: '每日', usedIn: '公告與事件、AI 研究' },
  { icon: 'book', kind: '證交所新聞', source: [['證交所 RSS', 'https://www.twse.com.tw/'], '（僅標題與連結）'], cycle: '不定期', usedIn: '公告與事件' },
  { icon: 'leaf', kind: 'ESG 揭露', source: [['證交所', TWSE], '、', ['櫃買中心', TPEX], '（公司自行申報）'], cycle: '年度', usedIn: 'ESG 專區' },
  { icon: 'layers', kind: 'ETF 成份股', source: ['元大、富邦、國泰、台新\n復華、野村、兆豐、永豐投信官網'], cycle: '依各投信公布', usedIn: '股票詳情、比較' },
  { icon: 'bot', kind: 'AI 整理與回答', source: [['Google Gemini', 'https://ai.google.dev/'], '（不算證據）'], cycle: '每次提問', usedIn: 'AI 研究、助手、智慧選股' },
]

export const LICENSE_NOTICE = 'PINWISE 目前為競賽展示。表格中的資料，授權範圍尚未完全確認；若要正式上線，須先取得資料提供者的正式授權或書面同意，並依其條款標示來源。'
export const LICENSE_REASONS = [
  '證交所、櫃買中心：網站條款規定，以自動程式下載資料須經同意，已授權政府資料開放平臺的資料除外；各 OpenAPI 資料集是否都在開放範圍內、能否商用，尚未向官方確認。',
  'FinMind：尚未查到資料商業使用的公開條款。',
  '證交所新聞：已列於政府資料開放平臺，RSS 管道是否適用同一授權尚未確認。',
  'ETF 成份股：各投信網站條款尚未逐一確認，也還沒取得同意。',
  'Gemini：目前使用免費方案，輸入與回答可能用於改善產品，也可能由人工檢視；正式上線應改用付費方案。',
].join('\n')
export const PRIVACY_NOTICE = '請勿在提問中輸入個人資料。'
export const DATA_GAPS = '盤中即時價；中信、群益、凱基、統一等投信的 ETF 成份股。'
