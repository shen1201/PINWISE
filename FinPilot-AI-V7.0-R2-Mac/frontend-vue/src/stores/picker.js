import { reactive, computed } from 'vue'
import { addRecord } from './footprint.js'
import { api } from '@/api/client.js'
import { toast, preferencesPayload } from './ui.js'
import { storageKey } from '../api/runtime.js'

// 智慧選股（對應舊版 js/pages-workspaces.js 的 beginPickerAnalysis 與相關函式）。
// 只有文字需求、沒有進階條件時走 AI 選股；有進階條件時走一般條件篩選。
const STORE_KEY = storageKey('pinwise_vue_picker')
const HISTORY_LIMIT = 5
const EMPTY = { search: '', type: 'all', industry: 'all', period: 'all', risk: 'all' }

// 進階條件。值（左）是送給後端的代碼，不要更改；文字（右）可以調整。
export const TYPE_OPTIONS = [['all', '全部類型'], ['stock', '台股個股'], ['etf', 'ETF']]
// 依交易所產業分類近似，不是完整供應鏈名單；值需對應後端 INDUSTRY_CODES。
export const INDUSTRY_OPTIONS = [
  ['all', '全部產業'], ['semi', '半導體'], ['ai-server', 'AI 伺服器'], ['power', '電力／資料中心'],
  ['ev', '電動車供應鏈'], ['biotech', '生技醫療'], ['finance', '金融'], ['shipping', '航運'],
]
// 波動程度：以年化波動篩選，門檻與股票詳情標記一致（25%／45%）。
export const RISK_OPTIONS = [
  ['all', '不限'], ['low', '偏低（年化波動 25% 以下）'], ['medium', '中等（25%～45%）'], ['high', '偏高（45% 以上）'],
]
// 波動計算期間：只在有選波動程度時使用，決定用多長的歷史日價計算波動。
export const PERIOD_OPTIONS = [['3m', '近 6 個月'], ['1y', '近 3 年'], ['3y', '近 5 年']]
const RISK_SHORT = { low: '波動偏低', medium: '波動中等', high: '波動偏高' }

// 條件互相限制的規則都在這裡，查詢前與讀取舊資料時都會套用，避免矛盾組合：
// 1. 選了產業 → 只篩個股（ETF 沒有產業分類，後端會全部放行）
// 2. 選了 ETF → 產業清空
// 3. 沒選波動程度 → 計算期間不使用；有選 → 期間預設近 6 個月
export function normalizeConditions(source) {
  const next = { ...EMPTY, ...source }
  if (!TYPE_OPTIONS.some(([v]) => v === next.type)) next.type = 'all'
  if (!INDUSTRY_OPTIONS.some(([v]) => v === next.industry)) next.industry = 'all'
  if (!RISK_OPTIONS.some(([v]) => v === next.risk)) next.risk = 'all'
  if (next.type === 'etf') next.industry = 'all'
  if (next.industry !== 'all') next.type = 'stock'
  if (next.risk === 'all') next.period = 'all'
  else if (!PERIOD_OPTIONS.some(([v]) => v === next.period)) next.period = '3m'
  return next
}

// 每一項都先用官方資料確認過查得到結果；波動條件要避開目前查無結果的組合。
export const PRESETS = [
  ['semi', '半導體有哪些值得研究的公司？', '產業', '台灣半導體有哪些值得研究的公司？', '半導體公司'],
  ['ai-server', 'AI 伺服器供應鏈有哪些標的？', '產業', 'AI 伺服器供應鏈有哪些候選標的？', 'AI 伺服器供應鏈'],
  ['power', '電力與資料中心相關公司有哪些？', '產業', '電力與資料中心相關公司有哪些？', '電力與資料中心'],
  ['biotech', '生技醫療有哪些公司？', '產業', '生技醫療產業有哪些值得研究的公司？', '生技醫療'],
  ['finance-mid', '波動中等的金融股有哪些？', '波動', '波動中等的金融股有哪些？', '中等波動・金融股'],
  ['semi-high', '波動偏高的半導體股有哪些？', '波動', '波動偏高的半導體股有哪些？', '偏高波動・半導體股'],
  ['etf-low', '波動偏低的 ETF 有哪些？', 'ETF', '波動偏低的 ETF 有哪些？', '偏低波動 ETF'],
  ['etf-dividend', '高股息 ETF 有哪些？', 'ETF', '高股息 ETF 有哪些？', '高股息 ETF'],
]

const label = (options, key) => options.find(([value]) => value === key)?.[1]

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}')
    return saved && typeof saved === 'object' ? saved : {}
  } catch {
    return {}
  }
}
const saved = load()

export const picker = reactive({
  // 重新打開頁面時，上一次已送出的進階條件不留在輸入框（舊版會一直顯示「1」）。
  draft: { ...normalizeConditions(saved.draft), ...(saved.state === 'completed' ? { type: 'all', industry: 'all', period: 'all', risk: 'all' } : {}) },
  applied: normalizeConditions(saved.applied),
  analyzed: Boolean(saved.analyzed),
  state: saved.state === 'loading' ? 'idle' : saved.state || 'idle', // idle | loading | completed | failed
  step: '',
  error: saved.error || '',
  results: Array.isArray(saved.results) ? saved.results : [],
  ai: saved.ai || null,
  // 後端回傳的篩選過程（各步驟剩幾檔），用來說明是哪個條件把結果篩光。
  funnel: saved.funnel || null,
  // 最近的選股紀錄（最多 5 筆，只存在此瀏覽器）：{ id, at, applied, count, results, ai, funnel }
  history: Array.isArray(saved.history) ? saved.history.slice(0, HISTORY_LIMIT) : [],
  // 正在查看的舊紀錄時間；重新篩選後清空
  viewingAt: null,
})

function save() {
  const { draft, applied, analyzed, state, error, results, ai, funnel, history } = picker
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ draft, applied, analyzed, state, error, results, ai, funnel, history }))
  } catch {}
}

// 計算期間附屬於波動程度，不另外計數。
export const advancedCount = (source) => ['type', 'industry', 'risk'].filter((key) => source[key] && source[key] !== 'all').length
// 進階條件只用在當次查詢：查完會從輸入框清掉（已套用的條件仍在結果上方的標籤，可以個別移除）。
// 所以「已變更」只看使用者新輸入或新設定的部分，不把清掉的進階條件當成變更。
const ADVANCED_KEYS = ['type', 'industry', 'period', 'risk']
export const draftDirty = computed(() => {
  const d = picker.draft, a = picker.applied
  const searchChanged = Boolean(d.search.trim()) && d.search.trim() !== a.search.trim()
  const advancedChanged = advancedCount(d) > 0 && ADVANCED_KEYS.some((key) => d[key] !== a[key])
  return searchChanged || advancedChanged
})
export function clearDraftAdvanced() {
  picker.draft = { ...picker.draft, type: 'all', industry: 'all', period: 'all', risk: 'all' }
  save()
}

export const conditions = computed(() => {
  const a = picker.applied
  const items = []
  if (a.search.trim()) items.push(['search', `需求：${a.search.trim()}`])
  if (a.type !== 'all') items.push(['type', a.type === 'etf' ? 'ETF' : '個股'])
  if (a.industry !== 'all') items.push(['industry', label(INDUSTRY_OPTIONS, a.industry)])
  if (a.risk !== 'all') items.push(['risk', `${RISK_SHORT[a.risk]}（${label(PERIOD_OPTIONS, a.period) || '近 6 個月'}計算）`])
  return items
})

export const requestSummary = computed(() => {
  const details = conditions.value.filter(([key]) => key !== 'search').map(([, text]) => text)
  const search = picker.applied.search.trim()
  return search ? `AI 已將「${search}」與${details.length ? details.join('、') : '未限定的進階條件'}一併整理。` : '直接描述需求，AI 會將問題與進階條件一起整理。'
})

// 後端項目 → 卡片資料（對應舊版 upsertLiveStock，只保留畫面用到的欄位）。
function normalize(item, aiItem, industryKey = 'all') {
  const quote = item.quote || item
  const status = quote.metadata?.data_status || item.metadata?.data_status || 'unverified'
  const type = item.product_type || (/^00/.test(item.symbol) ? 'etf' : 'stock')
  return {
    code: item.symbol,
    name: item.name || quote.name || item.symbol,
    market: item.market || quote.market || '',
    type,
    industry: type === 'etf' ? 'ETF' : item.industry || (industryKey !== 'all' && label(INDUSTRY_OPTIONS, industryKey)) || '股票',
    price: quote.close ?? null,
    tradeDate: quote.trade_date || item.as_of || null,
    tag: status === 'fixture' ? '隔離測試資料' : ['real', 'cache'].includes(status) ? '官方日資料' : '尚未驗證資料',
    reason: item.selection_reason || '由官方市場資料取得的標的',
    risk: '仍需核對公司公告、財務與市場風險',
    aiReasons: aiItem?.reasons || null,
    explanation: aiItem?.explanation || '',
  }
}

async function analyze(input) {
  const draft = normalizeConditions(input)
  picker.draft = { ...draft }
  if (!draft.search.trim() && !advancedCount(draft)) {
    toast('請先描述需求或設定進階條件')
    return false
  }
  picker.state = 'loading'
  picker.error = ''
  picker.step = '正在查詢 TWSE／TPEx 官方日資料…'
  try {
    let items
    if (draft.search.trim() && !advancedCount(draft)) {
      picker.step = 'AI 正在理解需求，並以官方估值、營收與行情篩選…'
      const response = await api.aiSelectStocks({ query: draft.search.trim(), limit: 12, preferences: preferencesPayload() })
      picker.ai = {
        plan: response.plan || {},
        funnel: response.funnel || [],
        overall: response.overall_explanation || '',
        glossary: response.glossary || [],
        notice: response.notice || '',
        prefs: preferencesPayload(),
      }
      items = (response.items || []).map((item) => normalize(item, item))
      picker.funnel = null
      addRecord({ id: `picker_${Date.now()}`, kind: 'picker', at: new Date().toISOString(), label: draft.search.trim().slice(0, 60), status: 'completed', tokens: Number(response.tokens) || 0, count: items.length })
    } else {
      picker.ai = null
      const response = await api.selectStocks({
        query: draft.search.trim(), product_type: draft.type, market: 'all',
        industry: draft.industry === 'all' ? null : draft.industry,
        period: draft.period === 'all' ? null : draft.period,
        risk: draft.risk === 'all' ? null : draft.risk, limit: 20,
      })
      items = (response.items || []).map((item) => normalize(item, null, draft.industry))
      picker.funnel = response.funnel || null
    }
    Object.assign(picker, { applied: { ...draft }, results: items, analyzed: true, state: 'completed', viewingAt: null })
    remember(draft, items)
    picker.draft = { ...draft, type: 'all', industry: 'all', period: 'all', risk: 'all' }
    toast('已依官方最近可得日資料完成篩選')
    return true
  } catch (error) {
    Object.assign(picker, { applied: { ...draft }, results: [], analyzed: true, state: 'failed', error: error.message || '無法取得後端選股結果', funnel: null })
    toast(`選股失敗：${picker.error}`)
    return false
  } finally {
    picker.step = ''
    save()
  }
}

export const submitDraft = () => analyze({ ...picker.draft })

// 研究頁與助手導向選股時，直接帶入句子並分析。
export function analyzeQuery(query) {
  return analyze({ ...EMPTY, search: query })
}

export function applyPreset(question) {
  picker.draft = { ...EMPTY, search: question }
  toast('已帶入問題，送出後更新結果')
}

export function removeCondition(key) {
  const next = { ...picker.applied, [key]: key === 'search' ? '' : 'all' }
  if (next.search.trim() || advancedCount(next)) return analyze(next)
  reset(false)
}

export function reset(notify = true) {
  Object.assign(picker, { draft: { ...EMPTY }, applied: { ...EMPTY }, analyzed: false, state: 'idle', error: '', results: [], ai: null, funnel: null, viewingAt: null })
  save()
  if (notify) toast('已清除選股條件')
}

// 沒有結果時，建議放寬一個條件（對應舊版 pickerRelaxationSuggestion）。
const RISK_TEXT = { low: '偏低', medium: '中等', high: '偏高' }
const RISK_RANGE = { low: '25% 以下', medium: '25%～45%', high: '45% 以上' }
const pct = (v) => `${Math.round(v * 10) / 10}%`

// 篩選說明：依後端回傳的篩選過程，說明「是哪一步把結果篩光」，並提供對應的調整按鈕。
// 回傳 { reason, details[], actions[{ label, patch }] }；有結果時 reason 為空，只留 details（範圍說明）。
export const filterHelp = computed(() => {
  const a = picker.applied
  const f = picker.funnel || {}
  const empty = !picker.results.length
  const details = []
  const actions = []
  const base = conditions.value.filter(([key]) => key !== 'risk').map(([, text]) => text).join('、') || '全部標的'
  if (f.scope === 'passive_reference')
    details.push('「被動元件」不是交易所的產業分類，目前使用人工核對的小名單（國巨、華新科），不是完整產業清單。')
  if (a.risk !== 'all' && f.risk_checked != null && f.matched > f.risk_shortlist_limit)
    details.push(`為控制資料查詢量，波動篩選只檢查成交金額前 ${f.risk_shortlist_limit} 檔（符合其他條件的共 ${f.matched} 檔）。`)
  if (!empty) return { reason: '', details, actions }

  let reason = ''
  if (f.scope === 'unsupported_industry') {
    reason = '這個產業目前沒有可對應的交易所分類。'
    actions.push({ label: '移除產業限制', patch: { industry: 'all' } })
  } else if (f.matched === 0 || f.matched == null) {
    reason = `沒有標的符合「${base}」。`
    if (a.search.trim()) {
      details.push('文字需求會比對股票代號與名稱，建議改用公司代號、公司名稱或產業名稱。')
      actions.push({ label: '清除文字需求', patch: { search: '' } })
    }
    if (a.industry !== 'all') actions.push({ label: '移除產業限制', patch: { industry: 'all' } })
    if (a.type !== 'all' && a.industry === 'all') actions.push({ label: '同時查看個股與 ETF', patch: { type: 'all' } })
    if (a.risk !== 'all') actions.push({ label: '移除波動條件', patch: { risk: 'all' } })
  } else if (a.risk !== 'all' && f.risk_matched === 0) {
    const sample = f.matched_sample?.length ? `（${f.matched_sample.slice(0, 3).join('、')}${f.matched > 3 ? '…' : ''}）` : ''
    reason = `符合「${base}」的有 ${f.matched} 檔${sample}，但年化波動都不在「${RISK_TEXT[a.risk]}（${RISK_RANGE[a.risk]}）」範圍。`
    const vols = (f.risk_checked_sample || []).slice(0, 4).map((item) => `${item.name || item.symbol} ${pct(item.volatility_pct)}`)
    if (vols.length) details.unshift(`實際年化波動：${vols.join('、')}（近 ${Math.round((f.risk_window_days || 180) / 30)} 個月計算）。`)
    const best = Object.entries(f.risk_level_counts || {}).filter(([level, n]) => level !== a.risk && n > 0).sort((x, y) => y[1] - x[1])[0]
    if (best) actions.push({ label: `改成波動${RISK_TEXT[best[0]]}（${best[1]} 檔符合）`, patch: { risk: best[0] } })
    actions.push({ label: '移除波動條件', patch: { risk: 'all' } })
  } else {
    reason = conditions.value.length ? `目前套用的「${conditions.value.map(([, t]) => t).join('、')}」沒有相符標的。` : '目前資料中沒有可列出的標的。'
    actions.push({ label: '清除全部條件', patch: { ...EMPTY } })
  }
  return { reason, details, actions }
})

// 篩選成功就記一筆；相同條件只保留最新一次。
const sameConditions = (x, y) => Object.keys(EMPTY).every((key) => (x[key] || '').toString().trim() === (y[key] || '').toString().trim())
function remember(applied, items) {
  const record = {
    id: `pick_${Date.now()}`, at: new Date().toISOString(), applied: { ...applied }, count: items.length,
    results: items.slice(0, 20), ai: picker.ai, funnel: picker.funnel,
  }
  picker.history = [record, ...picker.history.filter((r) => !sameConditions(r.applied, applied))].slice(0, HISTORY_LIMIT)
}

// 條件的簡短說明，給紀錄列表用（例如「個股・波動偏高（近 6 個月計算）」）。
export function conditionText(a) {
  const parts = []
  if (a.type !== 'all') parts.push(a.type === 'etf' ? 'ETF' : '個股')
  if (a.industry !== 'all') parts.push(label(INDUSTRY_OPTIONS, a.industry))
  if (a.risk !== 'all') parts.push(`${RISK_SHORT[a.risk]}（${label(PERIOD_OPTIONS, a.period) || '近 6 個月'}計算）`)
  return parts.join('・') || (a.search.trim() ? 'AI 分析' : '全部標的')
}

// 查看舊紀錄：直接顯示當時存下的結果，不重新查詢（畫面會標示資料時間）。
export function viewRecord(record) {
  Object.assign(picker, {
    draft: { ...normalizeConditions(record.applied), type: 'all', industry: 'all', period: 'all', risk: 'all' }, applied: normalizeConditions(record.applied),
    results: record.results || [], ai: record.ai || null, funnel: record.funnel || null,
    analyzed: true, state: 'completed', error: '', viewingAt: record.at,
  })
  save()
}
// 從結果畫面回到「最近的選股紀錄」，保留目前的搜尋條件。
export function backToHistory() {
  Object.assign(picker, { analyzed: false, viewingAt: null, draft: { ...picker.draft, type: 'all', industry: 'all', period: 'all', risk: 'all' } })
  save()
}
export function rerunRecord(record) {
  return analyze(record.applied)
}
export function removeRecord(id) {
  picker.history = picker.history.filter((r) => r.id !== id)
  save()
}

export function applyPatch(patch) {
  const next = { ...picker.applied, ...patch }
  if (next.search.trim() || advancedCount(next)) return analyze(next)
  reset(false)
  toast('請重新描述你的需求')
}

export function applyAdvanced(values) {
  return analyze({ ...picker.draft, ...values })
}
