import { watch } from 'vue'
import { storageKey } from '@/api/runtime.js'
import { settings, notify, toast } from './ui.js'
import { workspace } from './workspace.js'
import { snapshots, loadSnapshots } from './snapshots.js'

// 追蹤股票與系統狀態的通知：網頁開著時，每 10 分鐘重新取得追蹤股票的官方日資料並檢查。
// 規則與「我的投資足跡 → 風險觀察」相同：單日漲跌 ≥ 7%、距半年高點回落超過自己設的提醒線；
// 另外是追蹤股票的新公告、資料來源連不上、AI 每日額度用完。
// 資料是收盤日資料與交易所每日重大訊息，不是盤中即時；網頁關閉時不會通知。
const REFRESH_MS = 10 * 60 * 1000
const SPIKE_PCT = 7
const EVENT_DAYS = 3
const SEEN_KEY = storageKey('pinwise_vue_alert_seen')
const STOP_KEY = storageKey('pinwise_vue_stop_line')

function read(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback
  } catch {
    return fallback
  }
}
// 已通知過的事件：刪掉通知也不會再跳一次；回落回到提醒線以內才會重新提醒。
const seen = read(SEEN_KEY, {})
function remember(key, value = 1) {
  seen[key] = value
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(seen))
  } catch {
    // 瀏覽器不允許儲存時，只在這次開啟期間避免重複。
  }
}
const today = () => new Date().toLocaleDateString('sv')
const pct = (value) => Math.round(value * 10) / 10

// 同一次檢查先收集；同一類超過 2 則就合併成一則（例如第一次打開時好幾檔同時離高點很遠），
// 避免通知中心一次塞滿。
const GROUP = {
  spike: ['檔單日漲跌超過 7%', '/scorecard', '大漲大跌時先看有沒有公告，再想原本的理由是否還成立。'],
  drop: ['檔距半年高點回落超過提醒線', '/scorecard', '這不是停損建議，可以到投資足跡的「風險觀察」查看與調整提醒線。'],
  event: ['檔追蹤股票有新公告', '/tracking', '可以到「公告與事件」交給助手解讀。'],
}
let batch = []
const push = (entry, group = '', item = '') => batch.push({ entry, group, item })
let fresh = 0
function add(entry) {
  const before = settings.notifications.length
  notify(entry)
  if (settings.notifications.length > before) fresh++
}
function flush() {
  const groups = {}
  batch.forEach((row) => (groups[row.group] ||= []).push(row))
  Object.entries(groups).forEach(([group, rows]) => {
    if (!group || rows.length <= 2) return rows.forEach((row) => add(row.entry))
    const [title, link, note] = GROUP[group]
    add({
      id: `${group}|batch|${rows.map((row) => row.entry.id).join(',')}`, type: 'tracking', link,
      title: `${rows.length} ${title}`, body: `${rows.map((row) => row.item).join('、')}。${note}`,
    })
  })
  batch = []
  // 同一批檢查只跳一次提示，避免一次湧出好幾個 toast。
  if (!fresh) return
  toast(fresh === 1 ? `🔔 ${settings.notifications[0].title}` : `🔔 有 ${fresh} 則新通知，點右上角鈴鐺查看`, 4200)
  fresh = 0
}
const announce = flush

function checkStock(code) {
  const s = snapshots[code]
  if (!s || s.close == null) return
  const name = s.name && s.name !== code ? s.name : ''
  const label = `${code}${name ? ` ${name}` : ''}`
  const m = s.metrics || {}
  const splitDoubt = (m.suspected_split_dates || []).length > 0

  if (settings.notificationPrefs.tracking && workspace.monitorRules.price && !splitDoubt) {
    const prev = s.change != null ? s.close - s.change : null
    const day = prev ? pct((s.change / prev) * 100) : 0
    const key = `spike|${code}|${s.tradeDate}`
    if (Math.abs(day) >= SPIKE_PCT && !seen[key]) {
      remember(key)
      push({
        id: key, type: 'tracking', code, title: `${label} 單日${day > 0 ? '大漲' : '大跌'} ${Math.abs(day)}%`,
        body: `${s.tradeDate || '最近交易日'}收盤 ${Number(s.close).toLocaleString('zh-TW')}。大漲大跌時先看有沒有公告，再想原本的理由是否還成立。`,
      }, 'spike', `${label} ${day > 0 ? '+' : ''}${day}%`)
    }
    const line = read(STOP_KEY, { line: 15 }).line || 15
    const fromHigh = m.period_high && m.latest_close ? pct(((m.period_high - m.latest_close) / m.period_high) * 100) : 0
    const dropKey = `drop|${code}|${line}`
    if (fromHigh >= line && !seen[dropKey]) {
      remember(dropKey)
      push({
        id: `${dropKey}|${s.tradeDate}`, type: 'tracking', code, title: `${label} 距半年高點回落 ${fromHigh}%`,
        body: `已超過你在「風險觀察」設的 ${line}% 提醒線。這不是停損建議，提醒線和比較基準都可以在投資足跡調整。`,
      }, 'drop', `${label} ${fromHigh}%`)
    } else if (fromHigh < line - 2 && seen[dropKey]) remember(dropKey, 0)
  }

  if (settings.notificationPrefs.tracking && workspace.monitorRules.disclosure) {
    const since = Date.now() - EVENT_DAYS * 86400000
    const recent = (s.events || []).filter((e) => {
      const at = new Date(e.published_at || e.event_date || '').getTime()
      return Number.isFinite(at) && at >= since && !seen[`event|${code}|${e.title}|${e.published_at || e.event_date}`]
    })
    if (recent.length) {
      const fresh = recent
      fresh.forEach((e) => remember(`event|${code}|${e.title}|${e.published_at || e.event_date}`))
      push({
        id: `event|${code}|${fresh[0].published_at || fresh[0].event_date}|${fresh.length}`, type: 'tracking', code, link: '/tracking',
        title: `${label} 有 ${fresh.length} 則新公告`,
        body: `${fresh[0].title || '重大訊息'}${fresh.length > 1 ? ` 等 ${fresh.length} 則` : ''}。可以到「公告與事件」交給助手解讀。`,
      }, 'event', `${label} ${fresh.length} 則`)
    }
  }
}

function checkSystem(codes) {
  if (!settings.notificationPrefs.system || !codes.length) return
  const failed = codes.filter((code) => snapshots[code]?.errors?.length && snapshots[code]?.close == null)
  const key = `system|data|${today()}`
  if (failed.length && failed.length === codes.filter((code) => snapshots[code]).length && !seen[key]) {
    remember(key)
    push({
      id: key, type: 'system', link: '/evidence', title: '官方資料暫時連不上',
      body: `${failed.length} 檔追蹤股票取不到最近日資料：${snapshots[failed[0]].errors[0]?.message || '資料來源錯誤'}。可以到「資料與證據中心」看各來源狀態。`,
    })
  }
}

// 助手或研究遇到每日額度上限時呼叫；一天只通知一次。
export function notifyQuota(message = '') {
  const key = `system|quota|${today()}`
  if (!settings.notificationPrefs.system || seen[key]) return
  remember(key)
  push({
    id: key, type: 'system', link: '/scorecard', title: '今天的 AI 額度已用完',
    body: `${message ? `${String(message).slice(0, 60)}。` : ''}查資料、比較與追蹤仍可使用；AI 回答與研究明天會恢復。`,
  })
  announce()
}
export const isQuotaError = (text) => /額度|每日.*(上限|預算)|budget_exhausted/.test(String(text || ''))

function runChecks() {
  const codes = [...workspace.tracked]
  codes.forEach(checkStock)
  checkSystem(codes)
  announce()
}

let started = false
export function startAlerts() {
  if (started) return
  started = true
  watch(() => [...workspace.tracked], (codes) => loadSnapshots(codes), { immediate: true })
  // 任何頁面取得新的日資料後都檢查一次（loadedAt 改變代表剛更新）。
  watch(() => workspace.tracked.map((code) => snapshots[code]?.loadedAt || 0).join(','), runChecks)
  setInterval(() => {
    if (document.visibilityState === 'visible' && workspace.tracked.length) loadSnapshots([...workspace.tracked], { force: true })
  }, REFRESH_MS)
}
