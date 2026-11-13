<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppModal from '@/components/AppModal.vue'
import InfoTip from '@/components/InfoTip.vue'
import CandleChart from './CandleChart.vue'
import HoldingsModal from './HoldingsModal.vue'
import MetricFlag from '@/components/MetricFlag.vue'
import { track } from '@/stores/footprint.js'
import { api } from '@/api/client.js'
import { overlays } from '@/stores/overlays.js'
import { snapshots, loadSnapshots } from '@/stores/snapshots.js'
import { isCompared, isTracked, toggleCompare, toggleTrack } from '@/stores/workspace.js'
import { confirmResearch } from '@/stores/research.js'

// 個股分析視窗（對應舊版 showStockDetail、stockOverviewHtml、applyOverviewToDetail）。
// 價格為最近交易日收盤，不是即時報價；風險提醒由固定規則依官方資料產生。
const router = useRouter()
const months = ref(6)
const interval = ref('day') // K 棒週期：day | week（週 K 由前端以日資料合併）
const INTERVALS = [['day', '日K'], ['week', '週K']]
const loadedMonths = ref(6) // 目前畫面上的指標實際對應的期間（切換期間時，新資料載入前仍是舊期間）
const overview = ref(null)
const state = ref('idle') // loading | done | failed
const error = ref('')
const cache = new Map()

const target = computed(() => overlays.stockDetail)
const code = computed(() => target.value?.code)
const snap = computed(() => (code.value ? snapshots[code.value] : null))
const name = computed(() => overview.value?.name || snap.value?.name || '')
const type = computed(() => (/^00/.test(code.value || '') ? 'etf' : 'stock'))

async function loadOverview() {
  if (!code.value) return
  const wanted = months.value
  const key = `${code.value}:${wanted}`
  state.value = 'loading'
  try {
    const data = cache.get(key) || (await api.stockOverview(code.value, wanted))
    // 歷史日價暫時取不到（例如 FinMind 額度用完）時不記住，下次打開或切換期間會重新向後端要。
    if (data?.candles?.length) cache.set(key, data)
    if (key === `${code.value}:${months.value}`) {
      overview.value = data
      loadedMonths.value = wanted
      state.value = 'done'
    }
  } catch (e) {
    error.value = e.message || '後端未回應'
    state.value = 'failed'
  }
}

// ETF 成份股：只有取得資料的 ETF 才顯示這一區。
const TOP_HOLDINGS = 10
const holdings = ref(null)
const showAllHoldings = ref(false)
const holdingsCache = new Map()
async function loadHoldings(value) {
  holdings.value = null
  showAllHoldings.value = false
  if (type.value !== 'etf') return
  let data = holdingsCache.get(value)
  if (!data) {
    try {
      data = await api.etfHoldings(value)
    } catch {
      return
    }
    if (data.available) holdingsCache.set(value, data)
  }
  if (data.available) track('etf_view', value, { once: true })
  if (code.value === value && data.available) holdings.value = data
}
const shownHoldings = computed(() => (holdings.value?.holdings || []).slice(0, TOP_HOLDINGS))
// 按 Esc 時兩層視窗都會收到事件：完整名單開著就只關名單，股票詳情留著。
function closeDetail() {
  if (!showAllHoldings.value) overlays.stockDetail = null
}
// 關閉上層視窗時 AppModal 會解除 body 的鎖定，股票詳情還開著要補回去。
watch(showAllHoldings, (open) => {
  if (!open && target.value) nextTick(() => document.body.classList.add('modal-open'))
})
const maxHolding = computed(() => Math.max(0.01, ...(holdings.value?.holdings || []).map((row) => row.weight)))
const topWeight = computed(() => (holdings.value?.holdings || []).slice(0, TOP_HOLDINGS).reduce((sum, row) => sum + row.weight, 0))

watch(code, (value) => {
  if (!value) return
  loadHoldings(value)
  months.value = 6
  interval.value = 'day'
  loadedMonths.value = 6
  overview.value = null
  loadSnapshots([value])
  loadOverview()
})
watch(months, loadOverview)

const has = (v) => Number.isFinite(v)
const num = (v) => Number(v).toLocaleString('zh-TW')
const signed = (v, suffix = '') => (has(v) ? `${v > 0 ? '+' : ''}${num(v)}${suffix}` : '—')
const pct = (v) => (has(v) ? `${v}%` : '資料不足')

const latest = computed(() => overview.value?.latest || {})
const f = computed(() => overview.value?.fundamentals || {})
// K 線尚未載入時先用快照的預設半年指標。
const m = computed(() => overview.value?.metrics || snap.value?.metrics || {})
const PERIOD = { 3: '3 個月', 6: '半年', 12: '1 年' }
const period = computed(() => (overview.value ? PERIOD[loadedMonths.value] : PERIOD[6]))
// 句中用：數字開頭（3 個月、1 年）前面補空格，例如「如果 3 個月前買進」。
const periodIn = computed(() => (/^\d/.test(period.value) ? ` ${period.value}` : period.value))

// 兩個來源取日期較新的收盤：TWSE OpenAPI 常比 FinMind 晚一個交易日更新。
const price = computed(() => {
  const list = []
  if (latest.value.close != null)
    list.push({ close: latest.value.close, date: latest.value.date || '', change: latest.value.change, changePct: latest.value.change_pct, source: latest.value.source || 'FinMind' })
  if (snap.value?.close != null)
    list.push({ close: snap.value.close, date: snap.value.tradeDate || '', source: snap.value.market || 'TWSE' })
  return list.sort((a, b) => b.date.localeCompare(a.date))[0] || null
})

const volLevel = (v) => (v >= 45 ? ['波動大', 'is-high'] : v >= 25 ? ['中等', 'is-mid'] : ['相對平穩', 'is-low'])

// 指標小卡：{ label, value, tip（定義＋白話）, badge: [文字, class], sub: 第二行數值 }
// 分兩組：股價表現（隨期間切換）與基本面（官方最新資料），每組各自排滿一列。
const priceTiles = computed(() => {
  const r = m.value.period_return_pct, v = m.value.annualized_volatility_pct, dd = m.value.max_drawdown_pct
  return [
    { field: 'period_return_pct', label: '區間報酬', value: has(r) ? signed(r, '%') : '資料不足',
      note: has(r) ? (r === 0 ? `與${periodIn.value}前持平` : `${period.value}前買進約${r > 0 ? '賺' : '虧'} ${Math.abs(r)}%`) : '',
      tip: '期間第一個與最後一個交易日收盤價的變化。\n不含股利，也不代表未來表現。' },
    { field: 'annualized_volatility_pct', label: '年化波動', value: pct(v), badge: has(v) ? volLevel(v) : null,
      note: has(v) ? `一年常見起伏約 ±${Math.round(v)}%` : '',
      tip: `把每日漲跌幅換算成一年的起伏程度，數字越大，股價上下震盪越劇烈。\n本系統以 25% 以下為相對平穩、45% 以上為波動大。${has(v) ? `\n此數字以${periodIn.value}的日資料計算。` : ''}` },
    { field: 'max_drawdown_pct', label: '最大回撤', value: pct(dd),
      note: has(dd) ? `期間內最多從高點跌 ${Math.abs(dd)}%` : '',
      tip: '期間內從某個高點跌到之後最低點的最大跌幅。\n可以用來感受：如果買在最高點，帳面最多曾虧多少。' },
  ]
})

const fundTiles = computed(() => {
  const x = f.value, list = []
  if (has(x.pe_ratio)) list.push({ label: '本益比', value: `${x.pe_ratio} 倍`, badge: x.pe_ratio >= 25 ? ['偏高', 'is-high'] : null,
    note: `股價約是 ${Math.round(x.pe_ratio)} 年的獲利`,
    tip: '股價 ÷ 每股盈餘，代表市場願意為每 1 元獲利付幾元。\n偏低可能較便宜，也可能是市場預期獲利會下滑；公司虧損時交易所不公布。\n本系統以 25 倍以上標示為偏高。' })
  if (has(x.dividend_yield_pct)) list.push({ label: '殖利率', value: `${x.dividend_yield_pct}%`,
    note: `每 100 元年領約 ${x.dividend_yield_pct} 元股利`,
    tip: '每年現金股利 ÷ 股價。\n股利每年可能不同，高殖利率不等於沒有風險；股價大跌也會讓殖利率變高。' })
  if (has(x.pb_ratio)) list.push({ label: '股價淨值比', value: `${x.pb_ratio} 倍`,
    note: x.pb_ratio < 1 ? '股價低於帳面淨值' : `股價是帳面淨值的 ${Math.round(x.pb_ratio * 10) / 10} 倍`,
    tip: '股價 ÷ 每股淨值（帳面資產扣掉負債）。\n低於 1 代表股價低於帳面價值；常用來看金融、傳產等資產型公司，科技股通常較高。' })
  if (has(x.revenue_yoy_pct)) list.push({
    label: '營收年增', value: `單月 ${signed(x.revenue_yoy_pct, '%')}`,
    sub: has(x.revenue_ytd_yoy_pct) ? `累計 ${signed(x.revenue_ytd_yoy_pct, '%')}` : '',
    badge: x.revenue_yoy_pct < 0 ? ['年減', 'is-high'] : null,
    tip: `單月：${x.revenue_month || '最新'} 月營收和去年同月相比。\n累計：今年 1 月到 ${x.revenue_month ? Number(x.revenue_month.slice(5)) : '最新'} 月的營收加總，和去年同期相比。\n兩者範圍不同，數字不一樣是正常的；單月容易受季節或一次性因素影響，累計比較能看出整體趨勢。` })
  if (has(x.eps_ytd)) list.push({ label: '累計 EPS', value: `${x.eps_ytd} 元`,
    note: `${x.eps_period || '今年累計'}每股${x.eps_ytd >= 0 ? '賺' : '虧'} ${Math.abs(x.eps_ytd)} 元`,
    tip: '每股盈餘：稅後淨利 ÷ 股數，代表每一股賺了多少錢。' })
  if (has(x.operating_margin_pct)) list.push({ label: '營業利益率', value: `${x.operating_margin_pct}%`,
    note: `每 100 元營收本業賺 ${x.operating_margin_pct} 元`,
    tip: '本業獲利 ÷ 營收，代表公司靠本業賺錢的效率；不含投資收益等業外項目。' })
  return list
})
// 每列欄數：4 張以內一列排滿；5～6 張分兩列各 3 張。
const cols = (n) => (n <= 4 ? n : Math.ceil(n / 2))

// 風險提醒：只放指標卡沒有直接說出的判斷，避免重複。
const risks = computed(() => {
  const x = f.value, list = [], vol = m.value.annualized_volatility_pct
  if (has(vol) && vol >= 45) list.push(`股價波動大：年化波動 ${vol}%，短期漲跌可能很劇烈。`)
  if (has(x.pe_ratio) && x.pe_ratio >= 25) list.push(`本益比 ${x.pe_ratio} 倍，市場評價偏高；獲利成長不如預期時，股價可能修正。`)
  if (has(x.revenue_yoy_pct) && x.revenue_yoy_pct < 0) list.push(`最新月營收年減 ${Math.abs(x.revenue_yoy_pct)}%，需留意業績是否轉弱。`)
  return list
})


const gaps = computed(() => {
  const errors = overview.value?.errors?.length ? overview.value.errors : snap.value?.errors || []
  return errors.length ? errors.map((e) => `${e.source || '來源'}：${e.message}`).join('；') : ''
})


async function startResearch() {
  const task = await confirmResearch(`研究 ${code.value} ${name.value} ${type.value === 'etf' ? '的表現與風險' : '的產業位置、主要成長動能與風險'}`, {
    requestedSymbols: [code.value], researchType: 'single_company',
    inputUnderstanding: { candidates: [{ symbol: code.value, name: name.value }] },
  })
  if (!task) return
  overlays.stockDetail = null
  router.push('/research')
}
</script>

<template>
  <AppModal :open="Boolean(target)" :title="target?.title || '標的詳情'" modal-class="stock-detail-modal" @close="closeDetail">
    <div v-if="code" class="stock-detail-shell">
      <header class="stock-detail-hero sd-hero">
        <div class="sd-name">
          <h3>{{ code }} {{ name }}</h3>
          <div class="sd-tags">
            <span class="tag">{{ type === 'etf' ? 'ETF' : '股票' }}</span>
            <span class="tag demo">{{ price ? '官方日資料' : '尚未驗證資料' }}</span>
          </div>
        </div>
        <div class="sd-price">
          <div class="sd-price-line">
            <strong>{{ price ? num(price.close) : '資料缺漏' }}</strong>
            <span v-if="price && has(price.change)" :class="{ 'price-up': price.change > 0, 'price-down': price.change < 0 }">
              {{ signed(price.change) }}{{ has(price.changePct) ? `（${signed(price.changePct, '%')}）` : '' }}
            </span>
          </div>
          <small>{{ price ? `${price.date || '日期未提供'} · ${price.source} · ` : '' }}最近交易日收盤，非即時</small>
        </div>
      </header>

      <div class="stock-overview">
        <div v-if="state === 'loading' && !overview" class="empty-state">正在載入股價走勢與財務資料…</div>
        <div v-else-if="state === 'failed'" class="notice"><strong>股價走勢暫時無法載入</strong><span>{{ error }}</span></div>
        <template v-else-if="overview">
          <div class="sd-chart-head">
            <div class="sd-interval">
            <div class="stock-overview-range" role="group" aria-label="K 棒週期">
              <button
                v-for="[value, label] in INTERVALS"
                :key="value"
                type="button"
                :class="{ active: interval === value }"
                :aria-pressed="String(interval === value)"
                @click="interval = value"
              >{{ label }}</button>
            </div>
            <!-- 3 個月只有約 13 根週 K：提示放在按鈕右側同一行，不把 K 線往下推 -->
            <span v-if="months === 3 && interval === 'week'" class="sd-hint" role="status">
              週 K 只有約 13 根，建議用日 K 看完整走勢與成交量
              <button type="button" class="card-link" @click="interval = 'day'">切換日 K</button>
            </span>
            </div>
            <div class="stock-overview-range" role="group" aria-label="K 線期間">
              <button v-for="[value, label] in [[3, '3 個月'], [6, '6 個月'], [12, '1 年']]" :key="value" type="button" :class="{ active: months === value }" :aria-pressed="String(months === value)" @click="months = value">{{ label }}</button>
            </div>
          </div>
          <div v-if="!overview.candles?.length" class="empty-state">
            歷史日價來源暫時沒有回應（可能是免費額度用完），稍後再試。
            <button type="button" class="card-link" @click="loadOverview">立即重試</button>
          </div>
          <CandleChart v-else :candles="overview.candles || []" :interval="interval" />
        </template>
      </div>

      <div class="sd-groups" :aria-busy="String(state === 'loading')">
        <template v-for="group in [{ title: `股價表現（${period}）`, tiles: priceTiles }, { title: '基本面（官方最新資料）', tiles: fundTiles }]" :key="group.title">
          <section v-if="group.tiles.length" class="sd-group">
            <h4>{{ group.title }}</h4>
            <div class="sd-tiles" :style="{ '--cols': cols(group.tiles.length) }">
              <div v-for="tile in group.tiles" :key="tile.label" class="sd-tile">
                <small>{{ tile.label }}<InfoTip :text="tile.tip" :label="tile.label" /></small>
                <div class="sd-value">
                  <strong>{{ tile.value }}</strong>
                  <MetricFlag v-if="tile.field" :metrics="m" :field="tile.field" />
                  <span v-if="tile.badge" class="sd-badge" :class="tile.badge[1]">{{ tile.badge[0] }}</span>
                </div>
                <span v-if="tile.sub" class="sd-sub">{{ tile.sub }}</span>
                <span v-if="tile.note" class="sd-note">{{ tile.note }}</span>
              </div>
            </div>
          </section>
        </template>
      </div>

      <section v-if="holdings" class="sd-holdings">
        <div class="sd-holdings-head">
          <h4>成份股<small>共 {{ holdings.holdings.length }} 檔，前 {{ Math.min(TOP_HOLDINGS, holdings.holdings.length) }} 大佔 {{ num(Math.round(topWeight * 100) / 100) }}%</small></h4>
          <small>資料日 {{ holdings.as_of }} · <a :href="holdings.source_url" target="_blank" rel="noopener noreferrer">{{ holdings.issuer }}</a></small>
        </div>
        <ol class="sd-holding-list">
          <li v-for="row in shownHoldings" :key="row.code" :title="`${row.code} ${row.name}：${row.weight}%`">
            <span><b>{{ row.code }}</b> {{ row.name }}</span>
            <i aria-hidden="true"><u :style="{ width: `${Math.max(1, (row.weight / maxHolding) * 100)}%` }"></u></i>
            <em>{{ row.weight.toFixed(2) }}%</em>
          </li>
        </ol>
        <button v-if="holdings.holdings.length > TOP_HOLDINGS" class="card-link sd-holdings-more" type="button" @click="showAllHoldings = true">
          查看全部 {{ holdings.holdings.length }} 檔
        </button>
      </section>

      <section v-if="risks.length" class="sd-risks" :class="{ 'is-single': risks.length === 1 }">
        <strong>⚠ 風險提醒</strong>
        <span v-if="risks.length === 1">{{ risks[0] }}</span>
        <ul v-else><li v-for="r in risks" :key="r">{{ r }}</li></ul>
      </section>

      <details class="sd-more">
        <summary>資料來源與期間</summary>
        <ul>
          <li>{{ m.period_start ? `${m.period_start} 至 ${m.period_end}，共 ${m.observations || 0} 筆有效日收盤（FinMind 每日開高低收）。` : '歷史日價不足，未計算期間指標。' }}</li>
          <li v-if="overview?.notice">{{ overview.notice }}</li>
          <li v-if="type === 'etf'">ETF 沒有官方本益比、營收與 EPS 資料。</li>
          <li v-else-if="!Object.keys(f).length && overview">此代號目前沒有官方本益比、營收與 EPS 資料。</li>
          <li>{{ gaps ? `資料缺漏：${gaps}` : '本次查詢未回報來源錯誤；仍應核對原始公告與完整財報。' }}</li>
          <li>日資料不標示為即時行情；程式計算值與風險提醒（波動 45%、本益比 25 倍為門檻）不由 Gemini 生成，也不是投資建議。</li>
        </ul>
      </details>

      <div class="stock-detail-actions sd-actions">
        <button class="outline-button" type="button" @click="toggleTrack(code, 'search')">{{ isTracked(code) ? '取消追蹤' : '＋ 加入追蹤' }}</button>
        <button class="outline-button" type="button" @click="toggleCompare(code)">{{ isCompared(code) ? '取消比較' : '＋ 加入比較' }}</button>
        <button class="primary-button" type="button" @click="startResearch">建立 AI 標的研究</button>
      </div>
    </div>
  </AppModal>
  <HoldingsModal :open="showAllHoldings && Boolean(holdings)" :code="code" :holdings="holdings" @close="showAllHoldings = false" />
</template>

<style scoped>
.sd-holdings{display:grid;gap:8px;margin-top:12px}
.sd-holdings-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 12px}
.sd-holdings-head h4{margin:0;color:var(--text-strong);font-size:15px}
.sd-holdings-head h4 small{margin-left:8px;color:var(--muted);font-size:12px;font-weight:500}
.sd-holdings-head > small{color:var(--muted);font-size:12px}
.sd-holdings-head a{color:var(--blue)}
.sd-holding-list{margin:0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 24px}
.sd-holding-list li{display:grid;grid-template-columns:172px minmax(0,1fr) 54px;align-items:center;gap:8px;font-size:13px;color:var(--text)}
.sd-holding-list span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sd-holding-list span b{color:var(--text-strong)}
.sd-holding-list i{display:block;height:8px;border-radius:4px;background:color-mix(in srgb,var(--blue) 10%,transparent)}
.sd-holding-list u{display:block;height:100%;border-radius:0 4px 4px 0;background:#2A78D6}
.sd-holding-list em{color:var(--text-strong);font-style:normal;font-weight:700;text-align:right;font-variant-numeric:tabular-nums}
.sd-holdings-more{justify-self:start;min-height:0;padding:0;font-size:13px}
@media (max-width:640px){.sd-holding-list{grid-template-columns:1fr}}
/* 頂部：名稱與價格各一行，比原本矮約 40px */
.sd-hero{align-items:center;padding:12px 17px}
.sd-name h3{margin:0 0 6px;font-size:24px}
.sd-tags{display:flex;flex-wrap:wrap;gap:6px}
.sd-price{display:grid;gap:2px;text-align:right}
.sd-price-line{display:flex;align-items:baseline;justify-content:flex-end;gap:10px}
.sd-price small{color:var(--muted);font-size:12px}
.sd-price strong{color:var(--text-strong);font-size:28px;line-height:1.15;font-variant-numeric:tabular-nums}
.sd-price-line span{font-weight:700;font-size:15px;font-variant-numeric:tabular-nums}
.sd-chart-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px;margin-bottom:6px}
.sd-interval{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;min-width:0}
.sd-hint{display:inline-flex;align-items:center;gap:8px;padding:4px 10px;border-radius:999px;background:color-mix(in srgb,var(--orange) 12%,transparent);color:var(--text);font-size:12px;line-height:1.4}
.sd-hint .card-link{font-size:12px;white-space:nowrap}
/* 指標卡：兩組，每組欄數＝卡片數（5 張以上分兩列），不留空格 */
.sd-groups{display:grid;gap:12px}
.sd-groups[aria-busy="true"]{opacity:.6}
.sd-group h4{margin:0 0 6px;color:var(--muted);font-size:13px;font-weight:700}
.sd-tiles{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:8px}
.sd-tile{display:grid;align-content:start;gap:4px;padding:12px 14px;border:1px solid var(--line);border-radius:13px;background:color-mix(in srgb,var(--blue) 4%,transparent)}
.sd-tile small{display:flex;align-items:center;color:var(--muted);font-size:13px}
.sd-tile strong{color:var(--text-strong);font-size:22px;line-height:1.25;font-variant-numeric:tabular-nums}
.sd-value{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}
.sd-note{color:var(--muted);font-size:13px;line-height:1.45}
.sd-sub{color:var(--text-strong);font-size:15px;font-weight:700;font-variant-numeric:tabular-nums}
.sd-badge{justify-self:start;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700}
.sd-badge.is-low{color:var(--green);background:color-mix(in srgb,var(--green) 13%,transparent)}
.sd-badge.is-mid{color:var(--orange);background:color-mix(in srgb,var(--orange) 15%,transparent)}
.sd-badge.is-high{color:var(--red);background:color-mix(in srgb,var(--red) 12%,transparent)}
.sd-risks{padding:10px 14px;border:1px solid color-mix(in srgb,var(--red) 25%,transparent);border-radius:13px;background:color-mix(in srgb,var(--red) 6%,transparent)}
.sd-risks strong{color:var(--text-strong);font-size:13px}
.sd-risks.is-single{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;padding:9px 14px}
.sd-risks.is-single span{color:var(--text);font-size:13px}
.sd-risks ul{margin:6px 0 0;padding-left:18px;color:var(--text);font-size:13px;line-height:1.6}
.sd-more{border:1px solid var(--line);border-radius:13px;padding:0 14px}
.sd-more summary{padding:10px 0;color:var(--muted);font-size:13px;font-weight:700;cursor:pointer}
.sd-more ul{margin:0 0 12px;padding-left:18px;color:var(--text);font-size:13px;line-height:1.6}
/* 只留一個捲軸：外框不捲動，標題固定，內容區填滿剩餘高度並自己捲動。
   內距在此明確指定（舊 CSS 依情境有 14～24px 多種），底部為 0 讓按鈕列貼齊底部。 */
:global(.modal.stock-detail-modal){display:flex;flex-direction:column;overflow:hidden}
:global(.modal.stock-detail-modal > .modal-header){flex:none}
:global(.modal.stock-detail-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto;padding:20px 24px 0}
.sd-actions{grid-template-columns:repeat(3,minmax(0,1fr))!important;position:sticky;bottom:0;z-index:2;margin:0 -24px;padding:12px 24px 20px;background:var(--surface-solid,var(--fp-surface-solid));border-top:1px solid var(--line)}
@media (max-width:640px){
  :global(.modal.stock-detail-modal > .modal-body){padding:16px 16px 0}
  .sd-actions{margin:0 -16px;padding:10px 16px 16px;grid-template-columns:repeat(2,minmax(0,1fr))!important}
  .sd-actions > button{white-space:nowrap}
  .sd-actions > .primary-button{grid-column:1 / -1}
  .sd-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .sd-hero{flex-direction:column;align-items:flex-start}
  .sd-price{text-align:left}
  .sd-price-line{justify-content:flex-start}
}
</style>
