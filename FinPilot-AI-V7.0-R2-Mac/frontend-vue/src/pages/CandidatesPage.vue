<script setup>
import MetricFlag from '@/components/MetricFlag.vue'
import AppModal from '@/components/AppModal.vue'
import WatchRow from '@/components/watchlist/WatchRow.vue'
import GgOutline from '@/components/GgOutline.vue'
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { workspace, isCompared, toggleCompare, track, untrack, SOURCE_LABELS } from '@/stores/workspace.js'
import { overlays, openStockDetail } from '@/stores/overlays.js'
import { toast } from '@/stores/ui.js'
import AppIcon from '@/components/AppIcon.vue'
import RefreshControl from '@/components/RefreshControl.vue'
import { snapshots, loadSnapshots } from '@/stores/snapshots.js'
import { usePopularStocks } from '@/composables/popularStocks.js'

// 我的追蹤：追蹤清單（＝唯一的清單）的表現總覽。
// 同一批股票的官方公告與觀察條件在「公告與事件」頁。
const router = useRouter()
const sortKey = ref('added') // added | return | volatility | change
const hover = ref('')

watch(() => [...workspace.tracked], (codes) => loadSnapshots(codes), { immediate: true })

const has = (v) => Number.isFinite(v)
const LEVELS = [
  ['low', '偏低', '25% 以下', 'var(--wl-lv-low)'],
  ['medium', '中等', '25%～45%', 'var(--wl-lv-mid)'],
  ['high', '偏高', '45% 以上', 'var(--wl-lv-high)'],
]
const levelOf = (v) => (!has(v) ? '' : v >= 45 ? 'high' : v >= 25 ? 'medium' : 'low')
const levelName = (key) => LEVELS.find(([k]) => k === key)?.[1] || '資料不足'

const rows = computed(() =>
  workspace.tracked.map((code, index) => {
    const s = snapshots[code] || {}
    const m = s.metrics || {}
    const meta = workspace.trackedMeta[code] || {}
    const events = (s.events || []).map((e) => e.published_at || e.event_date).filter(Boolean).sort().reverse()
    const prev = has(s.close) && has(s.change) ? s.close - s.change : null
    return {
      code, index,
      name: s.name || '',
      loading: !snapshots[code],
      close: s.close, change: s.change,
      changePct: has(prev) && prev ? (s.change / prev) * 100 : null,
      tradeDate: s.tradeDate || '',
      metrics: m, ret: m.period_return_pct, vol: m.annualized_volatility_pct, level: levelOf(m.annualized_volatility_pct),
      latestEvent: events[0] ? String(events[0]).slice(0, 10) : '',
      notes: workspace.watchNotes[code]?.length || 0,
      source: SOURCE_LABELS[meta.source] || '—',
      addedAt: meta.addedAt || '',
    }
  }),
)

const sorted = computed(() => {
  const list = [...rows.value]
  const num = (v) => (has(v) ? v : -Infinity)
  if (sortKey.value === 'return') return list.sort((a, b) => num(b.ret) - num(a.ret))
  if (sortKey.value === 'volatility') return list.sort((a, b) => num(b.vol) - num(a.vol))
  if (sortKey.value === 'change') return list.sort((a, b) => num(b.changePct) - num(a.changePct))
  return list.sort((a, b) => b.index - a.index) // 最近加入在前
})

// 清單區最多放 6 檔，列高依檔數分配：1 檔約占 1/3、2 檔約 1/2、3 檔接近填滿、4 檔以上填滿；
// 5 檔時第 6 格是虛線「還可以再追蹤 1 檔」；超過 6 檔時最下面一行虛線「查看所有追蹤」。
const LIST_MAX = 6
const COLS = [['標的', ''], ['收盤', 'num'], ['漲跌', 'num'], ['半年報酬', 'num'], ['年化波動', ''], ['最新公告', ''], ['操作', 'act']]
const showAll = ref(false)
const visibleRows = computed(() => sorted.value.slice(0, LIST_MAX))
const hiddenCount = computed(() => Math.max(0, rows.value.length - LIST_MAX))
const slotLeft = computed(() => (rows.value.length === LIST_MAX - 1 ? 1 : 0))
const gridRows = computed(() => `auto repeat(${visibleRows.value.length + slotLeft.value}, minmax(46px, 1fr))${hiddenCount.value ? ' auto' : ''}`)
watch(() => rows.value.length, (n) => n <= LIST_MAX && (showAll.value = false))

// KPI
const kpi = computed(() => {
  const r = rows.value
  const up = r.filter((x) => has(x.change) && x.change > 0).length
  const down = r.filter((x) => has(x.change) && x.change < 0).length
  const best = [...r].filter((x) => has(x.ret)).sort((a, b) => b.ret - a.ret)[0]
  const withEvents = r.filter((x) => x.latestEvent).length
  const date = r.map((x) => x.tradeDate).filter(Boolean).sort().at(-1) || ''
  return { up, down, flat: r.filter((x) => has(x.change) && x.change === 0).length, best, withEvents, date }
})

// 波動分布（甜甜圈）：依序 偏低→中等→偏高，同一色相由淺到深
const R = 52, STROKE = 18, C = 2 * Math.PI * R
const dist = computed(() => {
  const total = rows.value.length
  const counts = LEVELS.map(([key, label, range, color]) => ({ key, label, range, color, n: rows.value.filter((x) => x.level === key).length }))
  const missing = total - counts.reduce((sum, c) => sum + c.n, 0)
  const parts = [...counts, ...(missing ? [{ key: 'none', label: '資料不足', range: '歷史日價不足', color: '#c9ced6', n: missing }] : [])]
  let offset = 0
  const gap = parts.filter((p) => p.n).length > 1 ? 2 : 0
  const segs = parts.map((p) => {
    const len = total ? (p.n / total) * C : 0
    const seg = { ...p, pct: total ? Math.round((p.n / total) * 100) : 0, dash: `${Math.max(0, len - gap)} ${C}`, offset: -offset }
    offset += len
    return seg
  })
  return { total, segs }
})

// 各檔波動：由高到低。疑似分割的數字不參與比例尺，避免把其他長條壓扁。
const VOL_LIMIT = 7
const volAll = computed(() => rows.value.filter((r) => has(r.vol)).sort((a, b) => b.vol - a.vol))
const volRows = computed(() => {
  const scale = Math.max(50, ...volAll.value.filter((r) => !r.metrics.suspected_split_dates?.length).map((r) => r.vol))
  return volAll.value.slice(0, VOL_LIMIT).map((r) => ({
    ...r,
    width: Math.max(2, Math.min(100, (r.vol / scale) * 100)),
    color: LEVELS.find(([key]) => key === r.level)?.[3],
  }))
})
const volGhosts = computed(() => VOL_PREVIEW.slice(volRows.value.length))
const volHint = computed(() => (volAll.value.length > VOL_LIMIT ? `最高的 ${VOL_LIMIT} 檔` : '由高到低'))

// 空資料：KPI 只放「—」，不用假數字；下方提供實際可做的動作。
const EMPTY_KPIS = [['追蹤中', '加入後開始統計'], ['最近交易日', '會顯示漲跌家數'], ['近半年表現最佳', '依歷史日價計算'], ['近期有公告', '來自 MOPS 重大訊息']]
const START_WAYS = [
  ['search', '搜尋股票', '輸入代號或名稱直接加入', () => (overlays.stockSearch = true)],
  ['chart', '智慧選股', '用一句話找出候選標的', () => router.push('/picker')],
  ['book', 'AI 標的研究', '研究完成後加入追蹤', () => router.push('/research')],
]
const { popular: QUICK_STOCKS, date: quickDate } = usePopularStocks()
const PREVIEW_COLS = ['標的', '收盤', '漲跌', '半年報酬', '年化波動', '最新公告']
const VOL_PREVIEW = [84, 66, 50, 34, 20]
// 追蹤太少時比不出差異，提示再加幾檔；代表性的常用標的排除已追蹤的。
const moreCount = computed(() => ({ 1: '2～3', 2: '1～2', 3: '1' })[rows.value.length] || '')
const quickLeft = computed(() => QUICK_STOCKS.value.filter(([code]) => !workspace.tracked.includes(code)))

// 依目前狀態給下一步建議
const nextStep = computed(() => {
  const r = rows.value
  if (workspace.compare.length >= 2) return { text: `比較清單已有 ${workspace.compare.length} 檔，可以開始並排比較。`, label: '前往股票比較', to: '/compare' }
  const withEvent = r.find((x) => x.latestEvent)
  if (withEvent) return { text: `${withEvent.code} ${withEvent.name} 有最新公告（${withEvent.latestEvent}）。`, label: '查看公告與事件', to: '/tracking' }
  if (r.length >= 2) return { text: '挑 2～3 檔按「比較」，就能用同一組指標並排比較。', label: '', to: '' }
  return { text: '再加一檔就能開始比較，累積 3～4 檔最容易看出差異。', label: '前往智慧選股', to: '/picker' }
})

const fmtPct = (v, sign = true) => (has(v) ? `${sign && v > 0 ? '+' : ''}${Math.round(v * 100) / 100}%` : '—')
const tone = (v) => (!has(v) ? '' : v > 0 ? 'price-up' : v < 0 ? 'price-down' : '')

// 更新：重新取得追蹤股票的資料；有新資料時圓餅圖轉一圈。
const refreshing = ref(false)
const replay = ref(0)
const updatedAt = computed(() => Math.max(0, ...workspace.tracked.map((code) => snapshots[code]?.loadedAt || 0)) || null)
const REFRESH_INFO = '收盤價取交易所開放資料與 FinMind 中日期較新者；半年報酬與波動來自 FinMind 歷史日價。盤中不會即時更新。'
const refreshDetails = computed(() => (kpi.value.date ? `資料日：${kpi.value.date}\n` : '') + REFRESH_INFO)
const rowSignature = () => JSON.stringify(rows.value.map((r) => [r.code, r.close, r.change, r.tradeDate, r.ret, r.vol]))
async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  const before = rowSignature()
  await loadSnapshots([...workspace.tracked], { force: true })
  refreshing.value = false
  if (rowSignature() !== before) {
    replay.value += 1
    toast(`已更新，資料日 ${kpi.value.date || '未提供'}`)
  } else toast(`目前已是最新資料（資料日 ${kpi.value.date || '未提供'}）`)
}

function addFromSearch(stock) {
  if (track([stock.code], 'search')) toast(`已加入追蹤：${stock.code} ${stock.name}`)
}
</script>

<template>
  <div class="page with-top-space candidate-page my-watchlist">
    <div class="workspace candidate-workspace">
      <section class="page-banner">
        <h1>我的追蹤</h1>
        <p>你從搜尋、智慧選股或 AI 研究加入的股票都在這裡，可以比較表現與波動。</p>
        <RefreshControl v-if="rows.length" :loading="refreshing" :updated-at="updatedAt" :details="refreshDetails" @refresh="refresh" />
      </section>

      <template v-if="rows.length">
        <!-- KPI 小卡 -->
        <section class="wl-kpis">
          <article><span>追蹤中</span><strong>{{ rows.length }}<small> 檔</small></strong><em>{{ kpi.date ? `資料日 ${kpi.date}` : '正在取得日資料…' }}</em></article>
          <article><span>最近交易日</span><strong><b class="price-up">漲 {{ kpi.up }}</b><i>／</i><b class="price-down">跌 {{ kpi.down }}</b></strong><em>{{ kpi.flat ? `平盤 ${kpi.flat} 檔` : '依最近收盤漲跌計算' }}</em></article>
          <article><span>近半年表現最佳</span><strong>{{ kpi.best ? kpi.best.code : '—' }}<small v-if="kpi.best" :class="tone(kpi.best.ret)"> {{ fmtPct(kpi.best.ret) }}</small></strong><em>{{ kpi.best?.name || '歷史日價不足' }}</em></article>
          <article class="wl-kpi-link" role="button" tabindex="0" aria-label="查看公告與事件" @click="router.push('/tracking')" @keydown.enter="router.push('/tracking')"><span>近期有公告</span><strong>{{ kpi.withEvents }}<small> 檔</small></strong><em>查看公告與事件 →</em></article>
        </section>

        <div class="wl-main">
          <!-- 追蹤清單 -->
          <section class="wl-card wl-table-card">
            <div class="wl-card-head">
              <div class="wl-title">
                <h2>追蹤清單</h2>
                <button class="primary-button small" type="button" @click="overlays.stockSearch = true">＋ 加入追蹤</button>
              </div>
              <div class="wl-sort" role="group" aria-label="排序">
                <button v-for="[k, l] in [['added', '最近加入'], ['change', '今日漲跌'], ['return', '半年報酬'], ['volatility', '波動']]" :key="k" type="button" :class="{ active: sortKey === k }" :aria-pressed="String(sortKey === k)" @click="sortKey = k">{{ l }}</button>
              </div>
            </div>
            <div class="wl-grid" :class="`n-${Math.min(rows.length, 7)}`" role="table" aria-label="追蹤清單" :style="{ gridTemplateRows: gridRows }">
              <div class="wl-gr wl-gh" role="row"><span v-for="[label, cls] in COLS" :key="label" role="columnheader" :class="cls">{{ label }}</span></div>
              <WatchRow v-for="r in visibleRows" :key="r.code" :row="r" />
              <button v-if="slotLeft" class="wl-slot" type="button" @click="overlays.stockSearch = true"><span>還可以再追蹤 {{ slotLeft }} 檔</span><b>＋ 加入追蹤</b></button>
              <button v-if="hiddenCount" class="wl-slot wl-all" type="button" @click="showAll = true"><span>還有 {{ hiddenCount }} 檔沒有顯示</span><b>查看所有追蹤（共 {{ rows.length }} 檔）→</b></button>
            </div>
            <div v-if="moreCount" class="wl-more" :class="{ 'is-tight': rows.length > 2 }">
              <div class="wl-quick">
                <h3 :title="quickDate ? `依成交金額排序的個股，資料日 ${quickDate}` : ''"><b>建議再選 {{ moreCount }} 檔</b>，放在一起才看得出誰波動大、誰表現好</h3>
                <div>
                  <button v-for="[code, name] in quickLeft" :key="code" type="button" :title="`加入追蹤：${code} ${name}`" :aria-label="`加入追蹤：${code} ${name}`" @click="addFromSearch({ code, name })"><span><strong>{{ code }}</strong><small>{{ name }}</small></span><b aria-hidden="true">＋</b></button>
                </div>
              </div>
              <div v-if="rows.length <= 2" class="wl-preview-table">
                <div class="wl-preview-rows" aria-hidden="true">
                  <div v-for="n in 3 - rows.length" :key="n" class="wl-preview-row"><i v-for="c in PREVIEW_COLS" :key="c"></i></div>
                </div>
                <div class="wl-blank is-center">
                  <div class="wl-blank-art"><GgOutline kind="guji" /></div>
                  <strong>下一檔會出現在這裡</strong>
                  <small>點上面的常用標的，或按「加入追蹤」搜尋</small>
                </div>
              </div>
            </div>
          </section>

          <!-- 波動分布 -->
          <section class="wl-card wl-dist-card">
            <div class="wl-card-head"><h2>波動分布</h2><small>依近半年年化波動</small></div>
            <div class="wl-dist">
              <svg viewBox="0 0 140 140" class="wl-donut" role="img" :aria-label="`波動分布：${dist.segs.filter((s) => s.n).map((s) => `${s.label} ${s.n} 檔`).join('、')}`">
                <circle cx="70" cy="70" :r="R" fill="none" stroke="var(--line)" :stroke-width="STROKE" />
                <g :key="replay" class="wl-spin">
                <circle
                  v-for="s in dist.segs.filter((x) => x.n)"
                  :key="s.key"
                  cx="70" cy="70" :r="R" fill="none"
                  :style="{ stroke: s.color }" :stroke-width="hover === s.key ? STROKE + 4 : STROKE"
                  :stroke-dasharray="s.dash" :stroke-dashoffset="s.offset"
                  transform="rotate(-90 70 70)"
                  class="wl-seg"
                  @mouseenter="hover = s.key" @mouseleave="hover = ''"
                ><title>{{ s.label }}（{{ s.range }}）：{{ s.n }} 檔，{{ s.pct }}%</title></circle>
                </g>
                <text x="70" y="68" text-anchor="middle" class="wl-donut-num">{{ dist.total }}</text>
                <text x="70" y="86" text-anchor="middle" class="wl-donut-unit">檔</text>
              </svg>
              <ul class="wl-legend">
                <li v-for="s in dist.segs" :key="s.key" :class="{ 'is-hover': hover === s.key, 'is-zero': !s.n }" @mouseenter="hover = s.key" @mouseleave="hover = ''">
                  <i :style="{ background: s.color }"></i>
                  <span><b>{{ s.label }}</b><small>{{ s.range }}</small></span>
                  <em>{{ s.n }}</em><small class="wl-pct">{{ s.pct }}%</small>
                </li>
              </ul>
            </div>
            <div class="wl-vol">
              <div class="wl-vol-head"><h3>各檔波動</h3><small>{{ volHint }}</small></div>
              <ul v-if="volRows.length" class="wl-vol-list">
                <li v-for="r in volRows" :key="r.code" :title="`${r.code} ${r.name}：年化波動 ${fmtPct(r.vol, false)}（${levelName(r.level)}）`">
                  <b>{{ r.code }}</b>
                  <span class="wl-vol-track"><u :style="{ width: `${r.width}%`, background: r.color }"></u></span>
                  <em>{{ Math.round(r.vol) }}%<MetricFlag :metrics="r.metrics" field="annualized_volatility_pct" /></em>
                </li>
                <li v-for="width in volGhosts" :key="width" class="is-ghost" aria-hidden="true"><i></i><span class="wl-vol-track"><u :style="{ width: `${width}%` }"></u></span><i></i></li>
              </ul>
              <p v-else class="wl-vol-none">{{ rows.some((r) => r.loading) ? '讀取中…' : '歷史日價不足，暫時無法計算' }}</p>
            </div>
            <div class="wl-next">
              <span>建議下一步</span>
              <p>{{ nextStep.text }}</p>
              <button v-if="nextStep.label" class="primary-button small" type="button" @click="router.push(nextStep.to)">{{ nextStep.label }}</button>
            </div>
          </section>
        </div>
        <AppModal :open="showAll" :title="`所有追蹤（${rows.length} 檔）`" modal-class="wl-all-modal" @close="showAll = false">
          <div class="wl-grid wl-grid-all my-watchlist" role="table" aria-label="所有追蹤">
            <div class="wl-gr wl-gh" role="row"><span v-for="[label, cls] in COLS" :key="label" role="columnheader" :class="cls">{{ label }}</span></div>
            <WatchRow v-for="r in sorted" :key="r.code" :row="r" />
          </div>
        </AppModal>
      </template>

      <!-- 還沒有追蹤的股票 -->
      <template v-else>
        <section class="wl-kpis wl-kpis-empty">
          <article v-for="[label, hint] in EMPTY_KPIS" :key="label"><span>{{ label }}</span><strong>—</strong><em>{{ hint }}</em></article>
        </section>
        <div class="wl-main">
          <section class="wl-card wl-start">
            <div class="wl-card-head"><h2>追蹤清單</h2><small>還沒有追蹤的股票</small></div>
            <div class="wl-ways">
              <button v-for="[icon, title, desc, action] in START_WAYS" :key="title" type="button" @click="action()">
                <span class="wl-way-icon"><AppIcon :name="icon" :size="20" /></span>
                <strong>{{ title }}</strong><small>{{ desc }}</small>
              </button>
            </div>
            <div class="wl-quick">
              <h3 :title="quickDate ? `依成交金額排序的個股，資料日 ${quickDate}` : ''">或直接加入常用標的</h3>
              <div>
                <button v-for="[code, name] in QUICK_STOCKS" :key="code" type="button" :aria-label="`加入追蹤：${code} ${name}`" @click="addFromSearch({ code, name })"><span><strong>{{ code }}</strong><small>{{ name }}</small></span><b aria-hidden="true">＋</b></button>
              </div>
            </div>
            <div class="wl-preview-table">
              <div class="wl-preview-row is-head" aria-hidden="true"><span v-for="c in PREVIEW_COLS" :key="c">{{ c }}</span></div>
              <div class="wl-preview-rows" aria-hidden="true">
                <div v-for="n in 3" :key="n" class="wl-preview-row"><i v-for="c in PREVIEW_COLS" :key="c"></i></div>
              </div>
              <div class="wl-blank">
                <div class="wl-blank-art"><GgOutline kind="guji" /></div>
                <strong>這裡還是空的</strong>
                <small>選一檔加入，這張表就會填上數字</small>
              </div>
            </div>
          </section>
          <section class="wl-card wl-dist-card wl-dist-empty">
            <div class="wl-card-head"><h2>波動分布</h2><small>依近半年年化波動</small></div>
            <div class="wl-dist">
              <svg viewBox="0 0 140 140" class="wl-donut" aria-hidden="true">
                <circle cx="70" cy="70" :r="R" fill="none" stroke="var(--line-strong)" :stroke-width="STROKE" stroke-dasharray="6 7" />
                <text x="70" y="78" text-anchor="middle" class="wl-donut-num">0</text>
              </svg>
              <ul class="wl-range">
                <li v-for="[key, label, range, color] in LEVELS" :key="key"><i :style="{ background: color }"></i><b>{{ label }}</b><small>{{ range }}</small></li>
              </ul>
            </div>
            <div class="wl-vol">
              <div class="wl-vol-head"><h3>各檔波動</h3><small>加入後由高到低排列</small></div>
              <ul class="wl-vol-list" aria-hidden="true">
                <li v-for="width in VOL_PREVIEW" :key="width" class="is-ghost"><i></i><span class="wl-vol-track"><u :style="{ width: `${width}%` }"></u></span><i></i></li>
              </ul>
            </div>
            <div class="wl-next"><span>加入後可以</span><p>比較漲跌與波動、掌握官方公告，也能挑兩檔並排比較。</p></div>
          </section>
        </div>
      </template>
    </div>
  </div>

</template>

<style scoped>
.my-watchlist{--wl-lv-low:#86b6ef;--wl-lv-mid:#3987e5;--wl-lv-high:#184f95}
:global(body[data-theme="dark"] .my-watchlist){--wl-lv-low:#4f86cc;--wl-lv-mid:#7fb0ee;--wl-lv-high:#c3dcfa}
.wl-title{display:flex;align-items:center;gap:10px}
.wl-kpi-link{cursor:pointer;transition:transform .15s ease}
.wl-kpi-link:hover,.wl-kpi-link:focus-visible{transform:translateY(-2px)}
.wl-kpi-link em{color:var(--blue)!important;font-weight:700}
.wl-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;flex:none}
.wl-kpis article,.wl-card{border:1px solid var(--line);border-radius:18px;background:var(--surface-solid,rgba(255,255,255,.96));box-shadow:0 6px 18px rgba(16,47,86,.06)}
.wl-kpis article{display:grid;gap:2px;padding:12px 16px}
.wl-kpis span{color:var(--muted);font-size:13px;font-weight:700}
.wl-kpis strong{color:var(--text-strong);font-size:24px;line-height:1.15;font-variant-numeric:tabular-nums}
.wl-kpis strong small{font-size:14px;font-weight:600;color:var(--muted)}
.wl-kpis strong b{font-size:inherit;font-weight:800}
.wl-kpis strong i{margin:0 4px;color:var(--muted);font-style:normal;font-weight:400}
.wl-kpis em{color:var(--muted);font-size:12px;font-style:normal}
.wl-main{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:12px;align-items:stretch}
.wl-card{display:flex;flex-direction:column;min-height:0;padding:14px 16px}
.wl-card-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:10px}
.wl-card-head h2{margin:0;font-size:17px;color:var(--text-strong)}
.wl-card-head small{color:var(--muted);font-size:12px}
.wl-sort{display:flex;gap:4px}
.wl-sort button{padding:4px 10px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--text);font-size:12px;cursor:pointer}
.wl-sort button.active{background:var(--blue);border-color:var(--blue);color:#fff}
.wl-more{flex:1;min-height:0;display:flex;flex-direction:column;gap:10px;margin-top:10px}
/* 追蹤清單：列高依檔數分配（見 script 的說明） */
.wl-grid{--wl-cols:minmax(130px,1.6fr) minmax(56px,.7fr) minmax(64px,.8fr) minmax(76px,.9fr) minmax(124px,1.3fr) minmax(82px,.9fr) minmax(104px,1fr);flex:1 1 0;min-height:0;display:grid;overflow:hidden}
.wl-gh{display:grid;grid-template-columns:var(--wl-cols);gap:0 8px;padding:8px 6px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;font-weight:700;white-space:nowrap}
.wl-gh .num,.wl-gh .act{text-align:right}
.wl-table-card:has(.wl-grid.n-1) .wl-more{flex:2 1 0}
.wl-table-card:has(.wl-grid.n-2) .wl-more{flex:1 1 0}
.wl-more.is-tight{flex:none}
.wl-slot{display:flex;align-items:center;justify-content:center;gap:14px;min-height:0;margin-top:6px;padding:8px 12px;border:1.5px dashed var(--line-strong);border-radius:12px;background:transparent;color:var(--muted);font-size:13px;cursor:pointer;transition:border-color .15s,background .15s}
.wl-slot b{color:var(--blue);font-weight:700}
.wl-slot:hover,.wl-slot:focus-visible{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 5%,transparent)}
.wl-grid-all{display:grid;grid-template-rows:auto;grid-auto-rows:minmax(52px,auto);overflow:visible}
:global(.modal.wl-all-modal){width:min(1000px,calc(100vw - 48px));display:flex;flex-direction:column;overflow:hidden!important}
:global(.modal.wl-all-modal > .modal-header){flex:none}
/* 只會上下捲動（檔數多時），不會左右捲動 */
:global(.modal.wl-all-modal > .modal-body){flex:1 1 auto;min-height:0;overflow-x:hidden!important;overflow-y:auto;scrollbar-width:thin}
.wl-more .wl-blank-art{width:64px}
.wl-more.is-tight .wl-preview-rows{-webkit-mask-image:none;mask-image:none}
.wl-dist{display:grid;grid-template-columns:100px 1fr;align-items:center;gap:10px}
.wl-donut{width:100px;height:100px}
.wl-spin{transform-origin:70px 70px;animation:wl-spin .9s cubic-bezier(.22,.8,.3,1) both}
@keyframes wl-spin{from{transform:rotate(-270deg);opacity:.15}to{transform:rotate(0);opacity:1}}
@media (prefers-reduced-motion:reduce){.wl-spin{animation:none}}
.wl-seg{transition:stroke-width .15s ease;cursor:default}
.wl-donut-num{fill:var(--text-strong);font-size:28px;font-weight:800}
.wl-donut-unit{fill:var(--muted);font-size:12px}
.wl-legend{width:100%;margin:0;padding:0;list-style:none;display:grid;gap:4px}
.wl-legend li{display:grid;grid-template-columns:10px 1fr auto 34px;align-items:center;gap:6px;padding:3px 4px;border-radius:8px;font-size:13px}
.wl-legend li.is-hover{background:color-mix(in srgb,var(--blue) 7%,transparent)}
.wl-legend li.is-zero{opacity:.55}
.wl-legend i{width:12px;height:12px;border-radius:3px}
.wl-legend span{display:grid}
.wl-legend b{color:var(--text-strong);font-weight:700;white-space:nowrap}
.wl-legend span small{display:none}
.wl-legend em{font-style:normal;font-weight:800;color:var(--text-strong);font-variant-numeric:tabular-nums}
.wl-pct{color:var(--muted);font-size:12px;text-align:right}
.wl-kpis-empty strong{color:var(--muted)}
.wl-start{gap:12px}
.wl-ways{flex:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.wl-ways button{display:grid;grid-template-columns:36px minmax(0,1fr);align-items:center;column-gap:10px;padding:10px 12px;border:1.5px solid #E2C3B5;border-radius:14px;background:var(--pw-inner);text-align:left;cursor:pointer;transition:border-color .15s,box-shadow .15s}
.wl-ways button:hover,.wl-ways button:focus-visible{border-color:var(--blue);box-shadow:0 6px 14px rgba(31,69,127,.12)}
.wl-way-icon{grid-row:span 2;display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue)}
.wl-ways strong{color:var(--text-strong);font-size:15px}
.wl-ways small{color:var(--muted);font-size:12px;line-height:1.45}
.wl-quick{flex:none}
.wl-quick h3{margin:0 0 6px;color:var(--muted);font-size:13px;font-weight:700}
.wl-quick > div{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:6px}
.wl-quick button{display:flex;align-items:center;justify-content:space-between;gap:4px;min-width:0;padding:6px 10px;border:1px solid var(--line-strong);border-radius:12px;background:transparent;text-align:left;cursor:pointer;transition:border-color .15s,background .15s}
.wl-quick button:hover,.wl-quick button:focus-visible{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 6%,transparent)}
.wl-quick span{display:flex;align-items:baseline;gap:6px;min-width:0}
.wl-quick span strong{flex:none;white-space:nowrap}
.wl-more .wl-quick button{gap:2px;padding:6px 8px}
.wl-more .wl-quick span{gap:4px}
.wl-quick strong{color:var(--text-strong);font-size:13px;font-variant-numeric:tabular-nums}
.wl-quick small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.wl-quick b{flex:none;color:var(--blue);font-size:14px}
.wl-preview-table{position:relative;flex:1;min-height:0;display:flex;flex-direction:column;padding:0 12px;border:1px dashed var(--line-strong);border-radius:12px;overflow:hidden}
.wl-preview-row{display:grid;grid-template-columns:1.4fr repeat(5,minmax(0,1fr));align-items:center;gap:14px;border-bottom:1px solid var(--line)}
.wl-preview-row.is-head{flex:none;padding:6px 0;color:var(--muted);font-size:12px;font-weight:700}
.wl-preview-row i{display:block;height:8px;border-radius:5px;background:color-mix(in srgb,var(--blue) 11%,transparent)}
.wl-preview-rows{flex:1;min-height:0;display:grid;grid-auto-rows:minmax(0,1fr);-webkit-mask-image:radial-gradient(ellipse 30% 70% at 50% 50%,transparent 62%,#000 100%);mask-image:radial-gradient(ellipse 30% 70% at 50% 50%,transparent 62%,#000 100%)}
.wl-preview-rows .wl-preview-row:last-child{border-bottom:0}
.wl-blank{position:absolute;left:50%;top:calc(50% + 14px);transform:translate(-50%,-50%);display:grid;justify-items:center;gap:2px;text-align:center;white-space:nowrap;pointer-events:none}
.wl-blank.is-center{top:50%}
.wl-blank-art{width:84px;margin-bottom:4px}
.wl-blank strong{color:var(--text-strong);font-size:15px}
.wl-blank small{color:var(--muted);font-size:13px}
.wl-range{width:100%;margin:0;padding:0;list-style:none;display:grid;gap:8px}
.wl-range li{display:grid;grid-template-columns:12px auto 1fr;align-items:center;gap:8px;font-size:13px}
.wl-range i{width:12px;height:12px;border-radius:3px}
.wl-range b{color:var(--text-strong)}
.wl-range small{color:var(--muted);font-size:12px;text-align:right}
.wl-vol{flex:1;min-height:0;display:flex;flex-direction:column;margin-top:10px;padding-top:10px;border-top:1px dashed var(--line)}
.wl-vol-head{flex:none;display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:4px}
.wl-vol-head h3{margin:0;color:var(--text-strong);font-size:14px}
.wl-vol-head small{color:var(--muted);font-size:12px}
.wl-vol-list{flex:1;min-height:0;display:grid;grid-auto-rows:minmax(0,38px);align-content:space-evenly;margin:0;padding:0;list-style:none}
.wl-vol-list li{display:grid;grid-template-columns:54px minmax(0,1fr) 54px;align-items:center;gap:8px;min-height:0;border-radius:8px}
.wl-vol-list li:not(.is-ghost):hover{background:color-mix(in srgb,var(--blue) 6%,transparent)}
.wl-vol-list b{color:var(--text-strong);font-size:13px;font-weight:700;font-variant-numeric:tabular-nums}
.wl-vol-track{display:block;height:10px;border-radius:0 4px 4px 0;background:color-mix(in srgb,var(--blue) 7%,transparent)}
.wl-vol-track u{display:block;height:100%;border-radius:0 4px 4px 0}
.wl-vol-list em{color:var(--text);font-size:13px;font-style:normal;font-weight:700;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.wl-vol-list .is-ghost i{display:block;height:8px;border-radius:5px;background:color-mix(in srgb,var(--blue) 11%,transparent)}
.wl-vol-list .is-ghost u{background:color-mix(in srgb,var(--blue) 16%,transparent)}
.wl-vol-none{flex:1;display:grid;place-items:center;margin:0;color:var(--muted);font-size:13px;text-align:center}
.wl-next{flex:none;display:grid;gap:6px;margin-top:10px;padding-top:10px;border-top:1px dashed var(--line)}
.wl-next span{color:var(--muted);font-size:12px;font-weight:700}
.wl-next p{margin:0;color:var(--text);font-size:13px;line-height:1.6}
.wl-next .primary-button{justify-self:start}
:global(body[data-theme="dark"] .wl-kpis article),:global(body[data-theme="dark"] .wl-card){background:#14263f}
@media (max-width:1000px){.wl-grid{flex:none;overflow-x:auto;grid-auto-rows:minmax(56px,auto)}.wl-more{flex:none}.wl-more .wl-preview-table{flex:none;height:170px}.wl-main{grid-template-columns:1fr;overflow:auto}.wl-next{margin-top:10px}.wl-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.wl-ways{grid-template-columns:1fr}.wl-quick > div{grid-auto-flow:row;grid-template-columns:repeat(3,minmax(0,1fr))}.wl-preview-table{display:none}}
</style>
