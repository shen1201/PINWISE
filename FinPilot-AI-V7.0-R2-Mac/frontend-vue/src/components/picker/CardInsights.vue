<script>
// 同一檔標的在選股頁只抓一次（存 Promise，同時發出的請求也會共用）；失敗時移除，下次可重試。
const overviewCache = new Map()
const holdingsCache = new Map()
</script>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import InfoTip from '@/components/InfoTip.vue'
import { api } from '@/api/client.js'

// 選股卡片補充資訊：近 6 個月走勢線與報酬／波動／回撤；個股另列估值與營收，ETF 另列前三大成份股。
// 數字全部來自後端官方資料與程式計算，失敗時整區不顯示，不影響卡片其他內容。
const props = defineProps({ code: { type: String, required: true }, type: { type: String, default: 'stock' }, layout: { type: String, default: 'compact' } })

const TIPS = {
  return: '期間內第一個與最後一個交易日收盤價的變化百分比；不含股利，也不代表未來表現。',
  volatility: '把每日漲跌幅換算成一年的起伏程度。本系統以 25% 以下為較平穩、45% 以上為波動大。',
  drawdown: '期間內從某個高點跌到之後最低點的最大跌幅，可以感受最壞情況下帳面可能虧多少。',
  yield: '每年現金股利 ÷ 股價；越高代表每年領回比例越高，但股利可能變動。',
  pe: '股價 ÷ 每股盈餘，代表市場願意為每 1 元獲利付幾元；偏低可能較便宜，也可能是獲利預期下滑。',
  revenue: '本月營收和去年同月相比的成長幅度；單月可能受季節或一次性因素影響。',
  holdings: '投信公開揭露的持股，依權重排序；買進 ETF 等於同時持有這些公司。',
}

const data = ref(null)
const holdings = ref(null)
const state = ref('loading') // loading | ready | failed

async function cached(map, key, load) {
  if (!map.has(key)) map.set(key, load())
  try {
    return await map.get(key)
  } catch (error) {
    map.delete(key)
    throw error
  }
}

// 歷史日價來源（FinMind）偶爾暫時拒絕（例如免費額度用完），後端仍回傳成功但沒有 K 線；
// 這種情況不記入快取，並自動再試，避免卡片留下一整塊空白。
const RETRY_DELAYS = [5000, 20000]
let retryTimer = 0
let attempt = 0
const willRetry = ref(false)
const failReason = ref('')

async function fetchOverview(code) {
  const result = await cached(overviewCache, code, () => api.stockOverview(code, 6))
  if (!result?.candles?.length) {
    overviewCache.delete(code)
    throw new Error('歷史日價暫時無法取得')
  }
  return result
}

function retryNow() {
  clearTimeout(retryTimer)
  attempt = 0
  load(props.code)
}

async function load(code, isRetry = false) {
  clearTimeout(retryTimer)
  if (!isRetry) attempt = 0
  state.value = 'loading'
  data.value = null
  holdings.value = null
  try {
    data.value = await fetchOverview(code)
    state.value = 'ready'
  } catch (error) {
    if (code !== props.code) return
    failReason.value = error?.message || ''
    willRetry.value = attempt < RETRY_DELAYS.length
    state.value = 'failed'
    if (willRetry.value) retryTimer = setTimeout(() => load(code, true), RETRY_DELAYS[attempt++])
  }
  if (props.type === 'etf') {
    try {
      const result = await cached(holdingsCache, code, () => api.etfHoldings(code))
      holdings.value = result?.available && result.holdings?.length ? result : null
    } catch {
      holdings.value = null
    }
  }
}
watch(() => props.code, (code) => load(code), { immediate: true })
onBeforeUnmount(() => clearTimeout(retryTimer))

const has = (value) => Number.isFinite(value)
const signed = (value, suffix = '%') => `${value > 0 ? '+' : ''}${value}${suffix}`
const metrics = computed(() => data.value?.metrics || {})
const facts = computed(() => data.value?.fundamentals || {})

// 走勢線：收盤價縮放到固定高度；以期間首尾比較決定漲跌顏色（紅漲綠跌）。
const spark = computed(() => {
  const closes = (data.value?.candles || []).map((row) => row.close).filter(has)
  if (closes.length < 2) return null
  const width = 240, height = 46, pad = 3
  const max = Math.max(...closes), min = Math.min(...closes), span = max - min || 1
  const points = closes.map((close, index) => {
    const x = pad + (index / (closes.length - 1)) * (width - pad * 2)
    const y = pad + (1 - (close - min) / span) * (height - pad * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return { width, height, points: points.join(' '), area: `${pad},${height} ${points.join(' ')} ${width - pad},${height}`, up: closes.at(-1) >= closes[0] }
})

const level = (value) => (value >= 45 ? '波動大' : value >= 25 ? '波動中等' : '相對平穩')
const summary = computed(() => {
  const { period_return_pct: r, annualized_volatility_pct: v, max_drawdown_pct: d } = metrics.value
  const parts = []
  if (has(r)) parts.push(`近 6 個月${r >= 0 ? '漲' : '跌'} ${Math.abs(r)}%`)
  if (has(v)) parts.push(level(v))
  if (has(d)) parts.push(`期間最多曾下跌 ${Math.abs(d)}%`)
  return parts.length ? `${parts.join('，')}。` : ''
})

const chips = computed(() => {
  const m = metrics.value, f = facts.value, rows = []
  if (has(m.period_return_pct)) rows.push(['6 月報酬', signed(m.period_return_pct), TIPS.return, m.period_return_pct > 0 ? 'up' : m.period_return_pct < 0 ? 'down' : ''])
  if (has(m.annualized_volatility_pct)) rows.push(['年化波動', `${m.annualized_volatility_pct}%`, TIPS.volatility, ''])
  if (has(m.max_drawdown_pct)) rows.push(['最大回撤', `${m.max_drawdown_pct}%`, TIPS.drawdown, ''])
  if (props.type !== 'etf') {
    if (has(f.dividend_yield_pct)) rows.push(['殖利率', `${f.dividend_yield_pct}%`, TIPS.yield, ''])
    if (has(f.pe_ratio)) rows.push(['本益比', `${f.pe_ratio} 倍`, TIPS.pe, ''])
    if (has(f.revenue_yoy_pct)) rows.push([f.revenue_month ? `${Number(f.revenue_month.slice(5))} 月營收年增` : '月營收年增', signed(f.revenue_yoy_pct), TIPS.revenue, ''])
  }
  return rows
})
const topHoldings = computed(() => (holdings.value?.holdings || []).slice(0, 3))
</script>

<template>
  <div v-if="state === 'loading'" class="ci ci-loading" aria-live="polite">正在載入近 6 個月走勢…</div>
  <div v-else-if="state === 'failed'" class="ci ci-loading ci-failed" aria-live="polite">
    <span>近 6 個月走勢暫時無法取得{{ willRetry ? '，稍後自動重試' : '' }}</span>
    <small v-if="failReason" class="ci-reason">{{ failReason }}</small>
    <button type="button" class="card-link" @click="retryNow">立即重試</button>
  </div>
  <div v-else-if="state === 'ready' && (spark || chips.length)" class="ci" :class="`ci-${layout}`">
    <div v-if="spark" class="ci-spark">
      <svg :viewBox="`0 0 ${spark.width} ${spark.height}`" preserveAspectRatio="none" role="img" :aria-label="`近 6 個月收盤走勢，${spark.up ? '期末高於期初' : '期末低於期初'}`">
        <polygon :points="spark.area" :class="spark.up ? 'ci-area-up' : 'ci-area-down'" />
        <polyline :points="spark.points" :class="spark.up ? 'ci-line-up' : 'ci-line-down'" />
      </svg>
    </div>
    <ul class="ci-chips">
      <li v-for="[label, value, tip, tone] in chips" :key="label">
        <small>{{ label }}<InfoTip :text="tip" :label="label" /></small>
        <strong :class="tone && `ci-${tone}`">{{ value }}</strong>
      </li>
    </ul>
    <p v-if="summary && layout === 'solo'" class="ci-summary">{{ summary }}</p>
    <div v-if="topHoldings.length" class="ci-holdings">
      <small>{{ layout === 'solo' ? '前三大成份股' : '前三大' }}<InfoTip :text="TIPS.holdings" label="前三大成份股" /></small>
      <span v-for="row in topHoldings" :key="row.code">{{ row.name }} <b>{{ row.weight }}%</b></span>
    </div>
  </div>
</template>

<style scoped>
.ci{flex:1 0 auto;min-height:0;display:flex;flex-direction:column;gap:7px;padding:7px 12px;border:1px solid var(--line);border-radius:12px;background:color-mix(in srgb,var(--blue) 4%,transparent)}
.ci-loading{color:var(--muted);font-size:13px}
.ci-spark{flex:1 1 0;min-height:32px;display:flex;flex-direction:column;gap:2px}
.ci-wide{flex-direction:row;align-items:stretch;gap:12px;padding-top:5px;padding-bottom:5px}
.ci-wide .ci-spark{flex:.8 1 0}
.ci-wide .ci-chips{flex:2 1 0;align-self:center;gap:3px 10px}
.ci-wide:has(.ci-holdings){flex-wrap:wrap}
.ci-wide .ci-holdings{flex:1 0 100%}
/* 卡片較窄時成份股收成一行，完整清單在「查看分析」 */
.ci-compact .ci-chips{gap:3px 10px}
.ci-compact{padding-top:5px;padding-bottom:5px}
@media (min-width:1001px) and (min-height:601px){
  @container (max-height:300px){.ci-solo .ci-summary{display:none}}
  @container (max-height:260px){.ci-compact .ci-spark{min-height:24px}}
}
.ci-compact .ci-holdings,.ci-wide .ci-holdings{flex-wrap:nowrap;overflow:hidden;white-space:nowrap}
.ci-compact .ci-holdings small,.ci-wide .ci-holdings small{flex:none;width:auto}
.ci-spark svg{flex:1 1 0;width:100%;min-height:0;display:block}
.ci-chips,.ci-summary,.ci-holdings{flex:none}
.ci-spark polygon{stroke:none!important}
.ci-loading{flex:1 1 0;display:grid;place-items:center}
.ci-failed{place-content:center;gap:4px;text-align:center;font-size:12.5px}
.ci-reason{color:var(--muted);font-size:11.5px}
.ci-failed .card-link{justify-self:center;font-size:13px}
.ci-solo{flex:1 1 0}
.ci-solo .ci-chips{grid-template-columns:none;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr)}
.ci-spark small{color:var(--muted);font-size:12px}
.ci-line-up,.ci-line-down{fill:none;stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round}
.ci-line-up{stroke:#D9534F}.ci-line-down{stroke:#1E9E72}
.ci-area-up{fill:rgba(217,83,79,.10)}.ci-area-down{fill:rgba(30,158,114,.10)}
.ci-chips{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px 10px;margin:0;padding:0;list-style:none}
.ci-chips li{display:grid;gap:1px;min-width:0}
.ci-chips small{display:flex;align-items:center;gap:2px;color:var(--muted);font-size:12px;white-space:nowrap}
.ci-chips strong{color:var(--text-strong);font-size:15px;font-variant-numeric:tabular-nums}
.ci-up{color:#D9534F!important}.ci-down{color:#1E9E72!important}
.ci-summary{margin:0;color:var(--text);font-size:13px;line-height:1.55}
.ci-holdings{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;font-size:13px;color:var(--text)}
.ci-holdings small{display:flex;align-items:center;gap:2px;color:var(--muted);font-size:12px;width:100%}
.ci-holdings b{color:var(--text-strong);font-weight:700}
:global(body[data-theme="dark"]) .ci-line-up{stroke:#FF9A9A}
:global(body[data-theme="dark"]) .ci-line-down{stroke:#6FE3B4}
</style>
