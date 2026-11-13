<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import InfoTip from '@/components/InfoTip.vue'
import AppModal from '@/components/AppModal.vue'
import R2SectionTabs from '@/components/v7/R2SectionTabs.vue'
import { useSectionTabs } from '@/composables/r2Layout.js'
import { api } from '@/api/client.js'
import { toast } from '@/stores/ui.js'
import RefreshControl from '@/components/RefreshControl.vue'

// 市場總覽：大盤、類股、成交量排行（TWSE／TPEx 官方盤後日資料，盤中不會即時更新）與證交所新聞。
// 頁面只放摘要，完整排行與新聞放在「更多」彈窗。
// 取不到的資料顯示「—」，不以固定數字代替。

const data = ref(null)
const state = ref('loading') // loading | done | failed
const updatedAt = ref(null)
const refreshing = ref(false)
const replay = ref(0) // 有新資料時加一，圖表重新播放動畫
const REFRESH_INFO = '指數與成交金額取證交所開放資料與 FinMind 中日期較新者，新聞另外併入證交所官方 RSS。類股與成交量排行只有開放資料，通常隔天清晨才更新。盤中不會即時更新。'
const dataDay = computed(() => (data.value?.twse?.date ? `資料日：指數 ${data.value.twse.date}${data.value.sectors?.[0]?.date ? `，類股 ${data.value.sectors[0].date}` : ''}\n` : ''))
const refreshDetails = computed(() => dataDay.value + REFRESH_INFO)
async function loadOverview(force = false) {
  try {
    data.value = await api.marketOverview(force)
    state.value = 'done'
    updatedAt.value = new Date()
  } catch {
    if (!data.value) state.value = 'failed'
    throw new Error('load failed')
  }
}
onMounted(() => loadOverview().catch(() => {}))
// 比對各區塊的資料日與最新數字，判斷這次更新是否真的有新資料。
const signature = () => JSON.stringify([
  data.value?.twse?.date, data.value?.twse?.index, data.value?.tpex?.date, data.value?.tpex?.index,
  data.value?.sectors?.[0]?.date, data.value?.top_volume?.[0]?.date, data.value?.news?.[0]?.title, longHistory.value.at(-1)?.date,
])
async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  const before = signature()
  try {
    await loadOverview(true)
    await loadLongHistory()
    if (signature() !== before) {
      replay.value += 1
      toast(`已更新，指數資料日 ${data.value?.twse?.date || '未提供'}`)
    } else toast(`目前已是最新資料（指數資料日 ${data.value?.twse?.date || '未提供'}）`)
  } catch {
    toast('更新失敗，畫面維持上一次的資料')
  } finally {
    refreshing.value = false
  }
}

const INFO = {
  sectors: '依證交所各類股指數的當日漲跌幅排序，紅色為上漲、綠色為下跌。電子工業、機電等涵蓋多個子類股的合併指數不列入，避免重複。',
  volume: '集中市場當日成交量最大的 20 檔證券，包含 ETF，單位為張（1 張 = 1,000 股）。成交量大代表交易熱絡，不代表股價會上漲或值得買進。',
}
const NEWS_ON_PAGE = 4
const VOLUME_ON_PAGE = 5
const modal = ref('') // sectors | volume | news
const sectors = computed(() => data.value?.sectors || [])
const maxSector = computed(() => Math.max(0.01, ...sectors.value.map((r) => Math.abs(r.change_pct))))
const barWidth = (pct) => `${Math.max(3, (Math.abs(pct) / maxSector.value) * 100)}%`
const strongest = computed(() => sectors.value.slice(0, 5))
const weakest = computed(() => sectors.value.slice(-5).reverse())
const volumes = computed(() => data.value?.top_volume || [])
const news = computed(() => data.value?.news || [])

const has = (v) => Number.isFinite(v)
const num = (v) => (has(v) ? Number(v).toLocaleString('zh-TW', { maximumFractionDigits: 2 }) : '—')
const signed = (v, suffix = '') => (has(v) ? `${v > 0 ? '+' : ''}${num(v)}${suffix}` : '')
const tone = (v) => (!has(v) || v === 0 ? '' : v > 0 ? 'price-up' : 'price-down')
// 官方成交量單位為股，畫面用張。
const lots = (shares) => {
  if (!has(shares)) return '—'
  const v = Math.round(shares / 1000)
  return v >= 1e4 ? `${(v / 1e4).toFixed(1)} 萬張` : `${num(v)} 張`
}
const money = (v) => (!has(v) ? '—' : v >= 1e12 ? `${(v / 1e12).toFixed(2)} 兆` : `${Math.round(v / 1e8).toLocaleString('zh-TW')} 億`)
const missing = computed(() => (state.value === 'loading' ? '讀取中…' : '目前無法取得'))

const tiles = computed(() => {
  const t = data.value?.twse, o = data.value?.tpex
  const change = (m) => (m ? `${signed(m.change)}（${signed(m.change_pct, '%')}）` : missing.value)
  return [
    { icon: 'chart', label: '加權指數', value: num(t?.index), note: change(t), cls: tone(t?.change), info: '臺灣證券交易所編製的「發行量加權股價指數」，用來看上市股票的整體漲跌，市值越大的公司影響越大。下方是與前一交易日比較的漲跌點數與幅度，紅色為上漲、綠色為下跌。' },
    { icon: 'trending', label: '櫃買指數', value: num(o?.index), note: change(o), cls: tone(o?.change), info: '證券櫃檯買賣中心編製的指數，用來看上櫃股票的整體漲跌。下方是與前一交易日比較的漲跌點數與幅度，紅色為上漲、綠色為下跌。' },
    { icon: 'compare', label: '上市成交金額', value: money(t?.trade_value_twd), note: t?.date || missing.value, cls: '', info: '上市（集中）市場當日的成交總金額，單位為新臺幣，可用來了解當天的交易熱度。下方是資料日期。' },
    { icon: 'compare', label: '上櫃成交金額', value: money(o?.trade_value_twd), note: o?.date || missing.value, cls: '', info: '上櫃（櫃買）市場當日的成交總金額，單位為新臺幣，可用來了解當天的交易熱度。下方是資料日期。' },
  ]
})

// 近 5 日加權指數走勢
// 圖表尺寸跟著卡片實際大小走，避免固定比例在高卡片裡上下留白。
const PAD = { l: 8, r: 8, t: 26, b: 22 }
const hover = ref(-1)
const chartBox = ref(null)
const size = ref({ w: 300, h: 240 })
let observer = null
watch(chartBox, (el) => {
  observer?.disconnect()
  if (!el) return
  observer = new ResizeObserver(([entry]) => {
    const { width, height } = entry.contentRect
    if (width > 0 && height > 0) size.value = { w: width, h: height }
  })
  observer.observe(el)
})
onBeforeUnmount(() => observer?.disconnect())
// 走勢期間：5 日用官方資料；15 日與一個月需要較長歷史，由 FinMind 提供（收盤值與官方一致）。
const RANGES = [['5', '5 日'], ['15', '15 日'], ['month', '一個月']]
const range = ref('5')
const longHistory = ref([])
const longState = ref('loading') // loading | done | failed
async function loadLongHistory() {
  try {
    const response = await api.marketIndexHistory()
    if (response.points?.length) longHistory.value = response.points
    longState.value = longHistory.value.length ? 'done' : 'failed'
  } catch {
    longState.value = longHistory.value.length ? 'done' : 'failed'
  }
}
onMounted(loadLongHistory)
function rowsForRange() {
  if (range.value === '5') return data.value?.twse?.history || []
  const all = longHistory.value
  if (!all.length) return []
  if (range.value === '15') return all.slice(-15)
  const cutoff = new Date(`${all.at(-1).date}T00:00:00`)
  cutoff.setMonth(cutoff.getMonth() - 1)
  const day = `${cutoff.getFullYear()}-${String(cutoff.getMonth() + 1).padStart(2, '0')}-${String(cutoff.getDate()).padStart(2, '0')}`
  return all.filter((r) => r.date >= day)
}
const trend = computed(() => {
  const rows = rowsForRange()
  if (rows.length < 2) return null
  const values = rows.map((r) => r.index)
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1
  const { w: W, h: H } = size.value
  const x = (i) => PAD.l + 18 + (i * (W - PAD.l - PAD.r - 36)) / (rows.length - 1)
  const y = (v) => PAD.t + ((max - v) / span) * (H - PAD.t - PAD.b)
  const dense = rows.length > 8
  const tickEvery = Math.ceil(rows.length / 5)
  const last = rows.length - 1
  const points = rows.map((r, i) => ({
    ...r, x: x(i), y: y(r.index), day: r.date.slice(5).replace('-', '/'), short: Math.round(r.index).toLocaleString('zh-TW'),
    // 點多時只標最高、最低與最新，日期也隔幾個才標，避免文字重疊
    labeled: !dense || i === last || r.index === max || r.index === min,
    ticked: !dense || (last - i) % tickEvery === 0,
  }))
  const first = values[0], end = values.at(-1)
  return { points, dense, line: points.map((p) => `${p.x},${p.y}`).join(' '), up: end >= first, change: end - first, pct: ((end - first) / first) * 100 }
})
const hitWidth = computed(() => (trend.value ? Math.max(8, (size.value.w - 52) / (trend.value.points.length - 1)) : 52))
const trendMissing = computed(() => (range.value !== '5' && longState.value === 'loading' ? '讀取中…' : range.value !== '5' && longState.value === 'failed' ? '較長期間的資料目前無法取得' : missing.value))

const formatNewsDate = (iso) => (iso ? String(iso).slice(0, 10) : '')

// 窄螢幕時分成三個區塊切換（對應舊版 applyR2Layout）。
const { current: tab, hidden: tabHidden } = useSectionTabs('market', 3)
</script>

<template>
  <div class="page with-top-space market-page">
    <div class="workspace market-workspace">
      <section class="page-banner">
        <h1>市場總覽</h1>
        <p>用一個畫面掌握台股大盤狀態；數字為收盤資料，盤中不會即時更新。</p>
        <RefreshControl :loading="refreshing" :updated-at="updatedAt" :details="refreshDetails" @refresh="refresh" />
      </section>
      <R2SectionTabs v-model="tab" :labels="['大盤', '類股與成交量', '走勢與事件']" />
      <section class="mk-tiles" :hidden="tabHidden(0)">
        <article v-for="t in tiles" :key="t.label" class="mk-tile">
          <span class="mk-icon"><AppIcon :name="t.icon" :size="20" /></span>
          <div><small>{{ t.label }}<InfoTip :text="t.info" :label="t.label" /></small><strong>{{ t.value }}</strong><em :class="t.cls">{{ t.note }}</em></div>
        </article>
      </section>

      <div class="mk-grid">
        <div class="mk-col" :hidden="tabHidden(1)">
          <section class="mk-card">
            <div class="mk-head">
              <h2>類股漲跌排行<InfoTip :text="INFO.sectors" label="類股漲跌排行" /><small v-if="sectors[0]?.date">{{ sectors[0].date }}</small></h2>
              <button v-if="sectors.length" class="mk-more" type="button" @click="modal = 'sectors'">更多 →</button>
            </div>
            <div v-if="sectors.length" class="mk-pair">
              <div v-for="[title, rows] in [['表現最強', strongest], ['表現最弱', weakest]]" :key="title">
                <h3>{{ title }}</h3>
                <ul :key="replay" class="mk-rows">
                  <li v-for="r in rows" :key="r.name" :title="`${r.name} ${signed(r.change_pct, '%')}`"><span>{{ r.name }}</span><i class="mk-bar" :class="r.change_pct >= 0 ? 'is-up' : 'is-down'" aria-hidden="true"><u :style="{ width: barWidth(r.change_pct) }"></u></i><b :class="tone(r.change_pct)">{{ signed(r.change_pct, '%') }}</b></li>
                </ul>
              </div>
            </div>
            <div v-else class="mk-empty">{{ missing }}</div>
          </section>

          <section class="mk-card">
            <div class="mk-head">
              <h2>成交量排行<InfoTip :text="INFO.volume" label="成交量排行" /><small v-if="volumes[0]?.date">{{ volumes[0].date }}</small></h2>
              <button v-if="volumes.length" class="mk-more" type="button" @click="modal = 'volume'">更多 →</button>
            </div>
            <div v-if="volumes.length" class="mk-volume">
              <p class="mk-volume-head"><span>標的</span><span>收盤</span><span>漲跌幅</span><span>成交量</span></p>
              <p v-for="r in volumes.slice(0, VOLUME_ON_PAGE)" :key="r.code">
                <span :title="`${r.code} ${r.name}`"><b>{{ r.code }}</b> {{ r.name }}</span>
                <span>{{ num(r.close) }}</span>
                <span :class="tone(r.change_pct)">{{ has(r.change_pct) ? signed(r.change_pct, '%') : '—' }}</span>
                <span>{{ lots(r.volume) }}</span>
              </p>
            </div>
            <div v-else class="mk-empty">{{ missing }}</div>
          </section>
        </div>

        <div class="mk-col" :hidden="tabHidden(2)">
          <section class="mk-card">
            <div class="mk-head">
              <h2>加權指數走勢</h2>
              <div class="mk-range" role="group" aria-label="走勢期間" title="資料來自證交所開放資料與 FinMind，取日期較新者">
                <button v-for="[k, l] in RANGES" :key="k" type="button" :class="{ active: range === k }" :aria-pressed="String(range === k)" @click="range = k; hover = -1">{{ l }}</button>
              </div>
              <small v-if="trend" :class="tone(trend.change)">{{ signed(Math.round(trend.change)) }} 點（{{ signed(Math.round(trend.pct * 100) / 100, '%') }}）</small>
            </div>
            <div v-if="trend" ref="chartBox" class="mk-chart">
              <svg :viewBox="`0 0 ${size.w} ${size.h}`" :width="size.w" :height="size.h" role="img" :aria-label="`近 ${trend.points.length} 個交易日加權指數，最新 ${num(trend.points.at(-1).index)}`" @mouseleave="hover = -1">
                <line :x1="PAD.l" :x2="size.w - PAD.r" :y1="size.h - PAD.b" :y2="size.h - PAD.b" class="mk-axis" />
                <polyline :key="`${range}-${replay}`" :points="trend.line" pathLength="1" class="mk-line" fill="none" />
                <g v-for="(p, i) in trend.points" :key="p.date">
                  <circle :cx="p.x" :cy="p.y" :r="hover === i ? 6 : trend.dense ? 2.5 : 4" class="mk-dot" />
                  <text v-if="p.labeled || hover === i" :x="Math.min(p.x, size.w - 30)" :y="Math.max(p.y - 12, 12)" text-anchor="middle" class="mk-value">{{ p.short }}</text>
                  <text v-if="p.ticked || hover === i" :x="p.x" :y="size.h - 7" text-anchor="middle" class="mk-tick">{{ p.day }}</text>
                  <rect :x="p.x - hitWidth / 2" :y="0" :width="hitWidth" :height="size.h" fill="transparent" @mouseenter="hover = i" />
                </g>
              </svg>
            </div>
            <div v-else class="mk-empty">{{ trendMissing }}</div>
          </section>

          <section class="mk-card">
            <div class="mk-head">
              <h2>近期市場事件<small>證交所新聞</small></h2>
              <button v-if="news.length" class="mk-more" type="button" @click="modal = 'news'">更多 →</button>
            </div>
            <ul v-if="news.length" class="mk-news">
              <li v-for="(n, i) in news.slice(0, NEWS_ON_PAGE)" :key="i">
                <a :href="n.url" target="_blank" rel="noopener noreferrer" :title="n.title">{{ n.title }}</a>
                <small>{{ formatNewsDate(n.published_at) }}</small>
              </li>
            </ul>
            <div v-else class="mk-empty">{{ state === 'loading' ? '讀取中…' : '目前沒有可顯示的新聞' }}</div>
          </section>
        </div>
      </div>
    </div>
  </div>

  <AppModal :open="modal === 'sectors'" title="類股漲跌排行" modal-class="mk-modal" @close="modal = ''">
    <table class="mk-table">
      <thead><tr><th>類股</th><th class="num">收盤指數</th><th class="num">漲跌幅</th></tr></thead>
      <tbody>
        <tr v-for="r in sectors" :key="r.name"><td>{{ r.name }}</td><td class="num">{{ num(r.close) }}</td><td class="num" :class="tone(r.change_pct)">{{ signed(r.change_pct, '%') }}</td></tr>
      </tbody>
    </table>
  </AppModal>

  <AppModal :open="modal === 'volume'" title="成交量前 20 名" modal-class="mk-modal" @close="modal = ''">
    <table class="mk-table">
      <thead><tr><th>排名</th><th>標的</th><th class="num">收盤</th><th class="num">漲跌幅</th><th class="num">成交量</th></tr></thead>
      <tbody>
        <tr v-for="r in volumes" :key="r.code">
          <td>{{ r.rank }}</td><td><strong>{{ r.code }}</strong> {{ r.name }}</td><td class="num">{{ num(r.close) }}</td>
          <td class="num" :class="tone(r.change_pct)">{{ has(r.change_pct) ? signed(r.change_pct, '%') : '—' }}</td><td class="num">{{ lots(r.volume) }}</td>
        </tr>
      </tbody>
    </table>
  </AppModal>

  <AppModal :open="modal === 'news'" title="近期市場事件" modal-class="mk-modal" @close="modal = ''">
    <ul class="mk-news-all">
      <li v-for="(n, i) in news" :key="i">
        <a :href="n.url" target="_blank" rel="noopener noreferrer">{{ n.title }}</a>
        <small>{{ formatNewsDate(n.published_at) }}</small>
      </li>
    </ul>
  </AppModal>
</template>

<style scoped>
.market-workspace{display:flex;flex-direction:column;gap:12px}
.mk-tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;flex:none}
.mk-tile,.mk-card{border:1px solid var(--line);border-radius:18px;background:var(--surface-solid,rgba(255,255,255,.96));box-shadow:0 6px 18px rgba(16,47,86,.06)}
.mk-tile{display:flex;align-items:center;gap:12px;padding:14px 16px}
.mk-tile > div{display:grid;gap:2px;min-width:0}
.mk-tile small{color:var(--muted);font-size:13px;font-weight:700}
.mk-tile strong{color:var(--text-strong);font-size:24px;line-height:1.2;font-variant-numeric:tabular-nums}
.mk-tile em{font-style:normal;font-size:13px;font-variant-numeric:tabular-nums}
.mk-tile em:not(.price-up):not(.price-down){color:var(--muted)}
.mk-icon{flex:none;display:grid;place-items:center;width:40px;height:40px;border-radius:12px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue)}
.market-workspace [hidden]{display:none!important}
.mk-grid{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:12px}
.mk-col{display:grid;grid-template-rows:minmax(0,1fr) minmax(0,1fr);gap:12px;min-height:0}
.mk-card{display:flex;flex-direction:column;min-height:0;padding:12px 16px;overflow:hidden}
.mk-card h2{display:flex;align-items:center;gap:6px;margin:0;color:var(--text-strong);font-size:16px}
.mk-card h2 small{color:var(--muted);font-size:12px;font-weight:500}
.mk-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:6px;flex:none}
.mk-head h2{white-space:nowrap}
.mk-head > small{white-space:nowrap;font-size:12px}
.mk-range{display:flex;flex:none;gap:3px;margin-left:auto}
.mk-range button{padding:3px 7px;white-space:nowrap;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--text);font-size:12px;cursor:pointer}
.mk-range button.active{border-color:var(--blue);background:var(--blue);color:#fff}
.mk-more{padding:0;border:0;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
.mk-more:hover{text-decoration:underline}
.mk-pair{flex:1;min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
.mk-pair > div{display:flex;flex-direction:column;min-height:0}
.mk-card h3{margin:0 0 2px;color:var(--muted);font-size:12px;font-weight:700}
.mk-rows{flex:1;min-height:0;margin:0;padding:0;list-style:none;display:grid;grid-auto-rows:1fr}
.mk-rows li{display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:1px solid var(--line);font-size:13px}
.mk-rows li:last-child{border-bottom:0}
.mk-rows span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.mk-rows b{flex:none;min-width:54px;text-align:right;font-variant-numeric:tabular-nums}
.mk-rows li > span{flex:none;width:92px}
.mk-bar{flex:1;min-width:0;display:block;height:6px}
.mk-bar u{display:block;height:100%;border-radius:0 4px 4px 0;transform-origin:left center;animation:mk-grow .7s cubic-bezier(.22,.8,.3,1) both}
.mk-bar.is-up u{background:var(--red)}
.mk-bar.is-down u{background:var(--green)}
@keyframes mk-grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes mk-draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@media (prefers-reduced-motion:reduce){.mk-bar u,.mk-line{animation:none}}
.mk-head small{font-size:13px;font-weight:700}
.mk-chart{flex:1;min-height:0;overflow:hidden}
.mk-chart svg{display:block}
.mk-volume{flex:1;min-height:0;display:grid;grid-template-rows:auto repeat(5,minmax(0,1fr))}
.mk-volume p{display:grid;grid-template-columns:minmax(0,1fr) 64px 66px 82px;align-items:center;gap:8px;margin:0;border-bottom:1px solid var(--line);font-size:13px;color:var(--text)}
.mk-volume p:last-child{border-bottom:0}
.mk-volume p span{font-variant-numeric:tabular-nums;text-align:right}
.mk-volume p span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.mk-volume p span:first-child b{color:var(--text-strong)}
.mk-volume .mk-volume-head{padding-bottom:3px;color:var(--muted);font-size:12px;font-weight:700}
.mk-axis{stroke:var(--line-strong);stroke-width:1}
.mk-line{stroke:#2a78d6;stroke-width:2;stroke-linejoin:round;stroke-linecap:round;stroke-dasharray:1;animation:mk-draw .9s ease-out both}
.mk-dot{fill:#2a78d6;stroke:var(--surface-solid,#fff);stroke-width:2;transition:r .12s ease}
.mk-tick{fill:var(--muted);font-size:11px}
.mk-value{fill:var(--text-strong);font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;paint-order:stroke;stroke:var(--surface-solid,#fff);stroke-width:4px;stroke-linejoin:round}
.mk-news{flex:1;min-height:0;margin:0;padding:0;list-style:none;display:grid;grid-auto-rows:1fr;gap:2px;overflow:hidden}
.mk-news li{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px;border-bottom:1px solid var(--line);font-size:13px}
.mk-news li:last-child{border-bottom:0}
.mk-news a{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text)}
.mk-news a:hover{color:var(--blue);text-decoration:underline}
.mk-news small{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.mk-empty{flex:1;display:grid;place-items:center;color:var(--muted);font-size:14px}
:global(body[data-theme="dark"] .mk-tile),:global(body[data-theme="dark"] .mk-card){background:#14263f}
.mk-table{width:100%;border-collapse:collapse;font-size:14px;table-layout:auto!important}
.mk-table th{padding:6px 8px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;text-align:left}
.mk-table td:not(.price-up):not(.price-down){color:var(--text)}
.mk-table td{padding:7px 8px;border-bottom:1px solid var(--line);overflow:visible!important;text-overflow:clip!important;max-width:none!important;white-space:normal!important}
:global(.modal.mk-modal){display:flex;flex-direction:column;overflow:hidden}
:global(.modal.mk-modal > .modal-header){flex:none}
:global(.modal.mk-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto}
.mk-table .num{text-align:right;font-variant-numeric:tabular-nums}
.mk-news-all{margin:0;padding:0;list-style:none}
.mk-news-all li{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:baseline;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:14px}
.mk-news-all li:last-child{border-bottom:0}
.mk-news-all a{color:var(--text)}
.mk-news-all a:hover{color:var(--blue);text-decoration:underline}
.mk-news-all small{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
@media (max-width:1100px){.mk-grid{grid-template-columns:1fr;overflow:auto}.mk-col{grid-template-rows:auto auto}.mk-chart{min-height:200px;flex:none;height:200px}.mk-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
