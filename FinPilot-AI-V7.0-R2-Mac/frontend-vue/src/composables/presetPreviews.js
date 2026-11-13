import { reactive } from 'vue'
import { api } from '@/api/client.js'

// 常用條件的預覽：只用官方日資料篩選，不呼叫 Gemini。波動條件要算歷史日價，所以一次只跑兩個，也只抓一次。
const BASE = { query: '', product_type: 'stock', market: 'all', limit: 3 }
const QUERIES = {
  semi: { industry: 'semi' },
  'ai-server': { industry: 'ai-server' },
  power: { industry: 'power' },
  biotech: { industry: 'biotech' },
  'finance-mid': { industry: 'finance', risk: 'medium', period: '3m' },
  'semi-high': { industry: 'semi', risk: 'high', period: '3m' },
  'etf-low': { product_type: 'etf', risk: 'low', period: '3m' },
  'etf-dividend': { product_type: 'etf', query: '高股息' },
}
const RUN_AT_ONCE = 2

const has = (value) => Number.isFinite(value)
function toRow(item, usesRisk) {
  const quote = item.quote || {}
  const previous = has(quote.close) && has(quote.change) ? quote.close - quote.change : null
  const pct = previous ? Math.round((quote.change / previous) * 1000) / 10 : null
  const vol = item.metrics?.annualized_volatility_pct
  return {
    code: item.symbol, name: item.name,
    value: usesRisk ? (has(vol) ? `${Math.round(vol)}%` : '—') : has(pct) ? `${pct > 0 ? '+' : ''}${pct}%` : '—',
    tone: usesRisk || !has(pct) || pct === 0 ? '' : pct > 0 ? 'up' : 'down',
  }
}
function toPreview(response, usesRisk) {
  const funnel = response.funnel || {}
  return {
    state: 'ready', usesRisk,
    rows: (response.items || []).map((item) => toRow(item, usesRisk)),
    count: usesRisk ? `前 ${funnel.risk_checked ?? 0} 檔有 ${funnel.risk_matched ?? 0} 檔符合` : `共 ${Number(funnel.matched || 0).toLocaleString('zh-TW')} 檔`,
  }
}

export const presetPreviews = reactive({})
let started = false

// 失敗的項目下次進頁面可重試；已取得的不重抓。
export async function loadPresetPreviews() {
  if (started) return
  started = true
  const queue = Object.keys(QUERIES).filter((id) => presetPreviews[id]?.state !== 'ready')
  queue.forEach((id) => (presetPreviews[id] = { state: 'loading', rows: [], count: '' }))
  async function worker() {
    while (queue.length) {
      const id = queue.shift()
      const query = { ...BASE, ...QUERIES[id] }
      try {
        presetPreviews[id] = toPreview(await api.selectStocks(query), Boolean(query.risk))
      } catch {
        presetPreviews[id] = { state: 'failed', rows: [], count: '' }
      }
    }
  }
  await Promise.all(Array.from({ length: RUN_AT_ONCE }, worker))
  started = false
}
