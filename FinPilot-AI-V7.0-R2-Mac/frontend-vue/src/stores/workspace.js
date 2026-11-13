import { reactive, watch } from 'vue'
import { toast } from './ui.js'
import { ensureNavVisible } from './navReminder.js'
import { storageKey } from '../api/runtime.js'

// 追蹤與比較清單（追蹤＝唯一的清單：「我的追蹤」看表現、「公告與事件」看同一批股票的公告）。
// 選股、研究結果、股票詳情、比較頁共用；存在獨立的 localStorage 鍵。
// 舊版的「候選清單」已移除，讀取時直接捨棄舊資料。
const STORE_KEY = storageKey('pinwise_vue_workspace')
const COMPARE_LIMIT = 3

const DEFAULT_RULES = { disclosure: true, revenue: true, price: true }
// 加入來源的顯示文字
export const SOURCE_LABELS = { picker: '智慧選股', research: 'AI 研究', search: '搜尋', compare: '股票比較', manual: '手動加入' }

function load() {
  let saved = {}
  try {
    saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {}
  } catch {}
  const tracked = Array.isArray(saved.tracked) ? saved.tracked : []
  return {
    compare: Array.isArray(saved.compare) ? saved.compare : [],
    // 追蹤的股票代號（順序＝加入順序）
    tracked,
    // 追蹤股票的加入時間與來源：code -> { addedAt, source }
    trackedMeta: saved.trackedMeta && typeof saved.trackedMeta === 'object' ? saved.trackedMeta : {},
    // 研究提出的觀察條件：code -> [{ item, why, researchId, addedAt }]
    watchNotes: saved.watchNotes && typeof saved.watchNotes === 'object' ? saved.watchNotes : {},
    // 監控規則：網頁開著時由 stores/alerts.js 檢查並通知（月營收尚未接上）。
    // 舊版的價格波動預設關閉且不會執行；開始真的檢查時（rulesVersion 2）改回預設開啟一次。
    monitorRules: { ...DEFAULT_RULES, ...saved.monitorRules, ...((saved.rulesVersion || 1) < 2 ? { price: true } : {}) },
    rulesVersion: 2,
  }
}

export const workspace = reactive(load())

watch(
  workspace,
  (value) => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(value))
    } catch {}
  },
  { deep: true },
)

export const isCompared = (code) => workspace.compare.includes(code)
export const isTracked = (code) => workspace.tracked.includes(code)

export function toggleCompare(code) {
  const index = workspace.compare.indexOf(code)
  if (index >= 0) {
    workspace.compare.splice(index, 1)
    toast('已從比較清單移除')
    return
  }
  if (workspace.compare.length >= COMPARE_LIMIT) return toast(`比較清單最多 ${COMPARE_LIMIT} 檔，請先移除一檔`)
  workspace.compare.push(code)
  toast(workspace.compare.length < 2 ? '已加入比較，再選 1 檔即可開始' : '已加入比較清單')
  ensureNavVisible('compare')
}

function addTracked(codes, source) {
  const now = new Date().toISOString()
  const added = codes.filter((code) => code && !workspace.tracked.includes(code))
  added.forEach((code) => {
    workspace.tracked.push(code)
    workspace.trackedMeta[code] = { addedAt: now, source: source || 'manual' }
  })
  if (added.length) ensureNavVisible('candidates')
  return added.length
}

// source：picker / research / search / compare / manual
export function toggleTrack(code, source = 'manual') {
  if (workspace.tracked.includes(code)) {
    untrack(code)
    return
  }
  addTracked([code], source)
  toast('已加入追蹤')
}

export function track(codes, source = 'manual') {
  return addTracked(codes, source)
}

export function untrack(code) {
  workspace.tracked = workspace.tracked.filter((c) => c !== code)
  delete workspace.trackedMeta[code]
  toast('已取消追蹤')
}

// 研究結果的觀察條件加入追蹤，並保存條件內容（對應舊版 trackWatchItems）。
export function trackWatchItems(items, researchId) {
  const withSymbol = items.filter((w) => w.symbol)
  const now = new Date().toISOString()
  withSymbol.forEach((w) => {
    const notes = (workspace.watchNotes[w.symbol] ||= [])
    if (!notes.some((n) => n.item === w.item)) notes.push({ item: w.item, why: w.why, researchId, addedAt: now })
  })
  track(withSymbol.map((w) => w.symbol), 'research')
  return withSymbol.length
}

export const watchNoteText = (code) => {
  const notes = workspace.watchNotes[code]
  return notes?.length ? '觀察：' + notes.map((n) => n.item).join('；') : ''
}
