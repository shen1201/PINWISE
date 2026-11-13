import { reactive } from 'vue'
import { api } from '@/api/client.js'

// 標的日資料快取（對應舊版 refreshLiveSnapshots 與 state.marketSnapshots）；5 分鐘內不重複查詢。
const FRESH_MS = 5 * 60 * 1000
const MAX_SYMBOLS = 20

export const snapshots = reactive({}) // code -> { found, name, market, type, close, tradeDate, metrics, errors, loadedAt }
const pending = new Set()

function normalize(item) {
  const quote = item.quote || {}
  return {
    found: item.found !== false,
    name: item.name || quote.name || item.company?.short_name || item.symbol,
    market: item.market || quote.market || '',
    type: /^00/.test(item.symbol) ? 'etf' : 'stock',
    close: quote.close ?? null,
    change: quote.change ?? null,
    tradeDate: quote.trade_date || null,
    metrics: item.metrics || {},
    events: item.events || [],
    asOf: item.as_of || null,
    errors: item.errors || [],
    loadedAt: Date.now(),
  }
}

export async function loadSnapshots(codes, { force = false } = {}) {
  const now = Date.now()
  const needed = [...new Set(codes.filter(Boolean))]
    .filter((code) => force || !snapshots[code] || now - snapshots[code].loadedAt > FRESH_MS)
    .filter((code) => !pending.has(code))
    .slice(0, MAX_SYMBOLS)
  if (!needed.length) return
  needed.forEach((code) => pending.add(code))
  try {
    const response = await api.stockSnapshots(needed)
    ;(response.items || []).forEach((item) => (snapshots[item.symbol] = normalize(item)))
  } catch (error) {
    needed.forEach((code) => {
      snapshots[code] = { found: false, errors: [{ message: error.message || '後端未啟動或資料來源無法連線' }], metrics: {}, loadedAt: Date.now() }
    })
  } finally {
    needed.forEach((code) => pending.delete(code))
  }
}

export function quoteText(code) {
  const s = snapshots[code]
  return s?.close != null ? `${Number(s.close).toLocaleString('zh-TW')}（${s.tradeDate || '日期未提供'} 日資料）` : '日資料缺漏'
}

export function quoteStatus(code) {
  const s = snapshots[code]
  if (!s) return '正在取得官方日資料…'
  if (s.close != null) return `已取得 ${s.tradeDate || '日期未提供'} 官方日資料`
  if (s.errors?.length) return `取得失敗：${s.errors[0].message || '資料來源錯誤'}`
  if (s.found === false) return '官方日資料找不到此標的'
  return '尚未取得官方日資料'
}

// 誇張或疑似失真的指標給提示：有單日異常跳動時三個價格指標都不可靠；否則只標幅度異常的那一項。
const EXTREME = {
  period_return_pct: (v) => v >= 100 || v <= -50,
  annualized_volatility_pct: (v) => v >= 100,
  max_drawdown_pct: (v) => v <= -60,
}
export function metricWarning(metrics, field) {
  if (!metrics || !EXTREME[field]) return ''
  const dates = metrics.suspected_split_dates || []
  if (dates.length) return `${dates.join('、')} 單日股價跳動超出正常漲跌範圍，可能是股票分割、減資或合併造成的價格調整，也可能是資料異常。歷史價未還原，這個數字可能失真，建議到公司或投信公告確認。`
  const value = metrics[field]
  if (value == null || !EXTREME[field](value)) return ''
  return '這個數字幅度異常大，可能是重大事件、財報變化、題材炒作或成交量偏低造成，槓桿型商品也會放大漲跌。建議搭配公告確認。'
}

export function metricText(code, key, suffix = '') {
  const value = snapshots[code]?.metrics?.[key]
  return value == null ? '資料不足' : `${Number(value).toLocaleString('zh-TW')} ${suffix}`.trim()
}
