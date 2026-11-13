<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import InfoTip from '@/components/InfoTip.vue'
import BadgeMedal from './BadgeMedal.vue'
import GgOutline from '@/components/GgOutline.vue'
import { footprint, track, weekStart } from '@/stores/footprint.js'
import { workspace } from '@/stores/workspace.js'
import { snapshots, loadSnapshots } from '@/stores/snapshots.js'
import { overlays, openStockDetail } from '@/stores/overlays.js'
import { ui } from '@/stores/ui.js'
import { assistant, current as currentConversation, newConversation } from '@/stores/assistant.js'
import { storageKey } from '@/api/runtime.js'
import { BADGES, progressOf } from '@/data/badges.js'

const emit = defineEmits(['go'])
const router = useRouter()
const num = (v) => Number(v).toLocaleString('zh-TW')
const records = computed(() => footprint.records)
const researchRows = computed(() => records.value.filter((r) => r.kind === 'research' && r.status === 'completed'))
const sumOf = (rows, key) => rows.reduce((total, row) => total + (row[key] || 0), 0)
// 每份研究以自己查資料約 30 分鐘估算。
const MINUTES_PER_RESEARCH = 30
const tokens = computed(() => sumOf(records.value, 'tokens'))
const tokenText = computed(() => (tokens.value >= 10000 ? [(tokens.value / 10000).toFixed(1), '萬'] : [num(tokens.value), '']))
const hoursSaved = computed(() => Math.round((researchRows.value.length * MINUTES_PER_RESEARCH) / 6) / 10)

const RATINGS = [['useful', '有用'], ['ok', '還好'], ['bad', '很糟']]
const rated = computed(() => records.value.filter((r) => r.rating))
const slices = computed(() => RATINGS.map(([key, label]) => {
  const count = rated.value.filter((r) => r.rating === key).length
  return { key, label, count, pct: rated.value.length ? Math.round((count / rated.value.length) * 100) : 0 }
}))
const usefulRate = computed(() => (rated.value.length ? slices.value[0].pct : null))
const R = 42, CIRC = 2 * Math.PI * R
const arcs = computed(() => {
  let offset = 0
  return slices.value.filter((s) => s.count).map((s) => {
    const full = (s.count / rated.value.length) * CIRC
    const arc = { ...s, dash: `${Math.max(full - 2, 1)} ${CIRC}`, offset: -offset }
    offset += full
    return arc
  })
})
const hoverSlice = ref(null)
const shownSlice = computed(() => slices.value.find((s) => s.key === hoverSlice.value))

const kpis = computed(() => [
  { icon: 'database', label: 'AI 替你查的資料', value: num(sumOf(researchRows.value, 'sources')), unit: '筆', note: `${researchRows.value.length} 份研究、${records.value.filter((r) => r.kind === 'assistant').length} 次問答`, tip: 'AI 研究實際取得、且有來源可查的官方資料筆數。刪除研究不會減少這個累計數字。' },
  { icon: 'shield', label: '攔下錯誤內容', value: num(sumOf(researchRows.value, 'rejected')), unit: '句', note: '數字對不上資料就刪除', tip: 'AI 寫出的句子若有數字對不上官方資料，系統會直接刪除，這裡是累計句數。' },
  { icon: 'radar', label: '使用的 Token', value: tokenText.value[0], unit: tokenText.value[1], note: `約省下 ${hoursSaved.value} 小時自己查資料`, tip: `Token 是 AI 處理文字的用量。省下的時間是估算值，以每份研究自己查約 ${MINUTES_PER_RESEARCH} 分鐘計算。` },
  { icon: 'check', label: '你的有用率', value: usefulRate.value ?? '—', unit: usefulRate.value == null ? '' : '%', note: rated.value.length ? `已評價 ${rated.value.length} 筆` : '研究或助手回答後可以評價', tip: '你評為「有用」的比例。' },
])

// 每週使用次數：近 8 週，單一數列。
const weeks = computed(() => {
  const list = []
  const cursor = new Date(`${weekStart()}T12:00:00`)
  for (let i = 0; i < 8; i++) {
    list.unshift(weekStart(cursor))
    cursor.setDate(cursor.getDate() - 7)
  }
  return list.map((week) => ({ week, label: week.slice(5).replace('-', '/'), count: records.value.filter((r) => r.at && weekStart(new Date(r.at)) === week).length }))
})
// 切到「月」可以往前翻年份；每月次數不受明細筆數上限影響。
const usageView = ref('week')
const thisYear = new Date().getFullYear()
const usageYear = ref(thisYear)
const firstYear = computed(() => Math.min(thisYear, ...Object.keys(footprint.monthly).map((key) => Number(key.slice(0, 4)))))
const months = computed(() => Array.from({ length: 12 }, (_, i) => {
  const key = `${usageYear.value}-${String(i + 1).padStart(2, '0')}`
  return { key, label: `${i + 1}月`, count: footprint.monthly[key] || 0, title: `${usageYear.value} 年 ${i + 1} 月 ${footprint.monthly[key] || 0} 次` }
}))
const bars = computed(() => (usageView.value === 'week' ? weeks.value.map((w) => ({ key: w.week, label: w.label, count: w.count, title: `${w.label} 當週 ${w.count} 次` })) : months.value))
// 刻度以 5 次為一格；次數變多時放大間距，避免線太密。
const axisStep = computed(() => {
  const max = Math.max(...bars.value.map((bar) => bar.count))
  return [5, 10, 20, 50, 100, 200, 500].find((step) => max / step <= 5) || 1000
})
const axisMax = computed(() => Math.max(1, Math.ceil(Math.max(...bars.value.map((bar) => bar.count)) / axisStep.value)) * axisStep.value)
const axisTicks = computed(() => Array.from({ length: axisMax.value / axisStep.value + 1 }, (_, i) => i * axisStep.value))
const hoverBar = ref(null)
const usageNote = computed(() => {
  if (hoverBar.value) return hoverBar.value.title
  if (usageView.value === 'week') return `本週 ${weeks.value.at(-1).count} 次`
  return `全年 ${months.value.reduce((sum, m) => sum + m.count, 0)} 次`
})

// ── 風險觀察 ──
function readJson(key, fallback) {
  try {
    return { ...fallback, ...JSON.parse(localStorage.getItem(key) || '{}') }
  } catch {
    return fallback
  }
}
function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 瀏覽器不允許儲存時，只保留到重新整理為止。
  }
}
const STOP_KEY = storageKey('pinwise_vue_stop_line')
const STOP_OPTIONS = [10, 15, 20]
const stop = reactive(readJson(STOP_KEY, { line: 15 }))
watch(stop, (value) => writeJson(STOP_KEY, value))
// 只看追蹤清單：研究過但沒追蹤、或已經移除的標的都不列入。
const codes = computed(() => [...workspace.tracked])
watch(codes, (list) => loadSnapshots(list), { immediate: true })
const nameOf = (code) => snapshots[code]?.name || code
const risks = computed(() => codes.value.filter((code) => snapshots[code]?.metrics?.latest_close != null).map((code) => {
  const s = snapshots[code], m = s.metrics
  if ((m.suspected_split_dates || []).length) return { code, rank: 1, level: 'check', tag: '待確認', reason: '價格疑似分割，跌幅不可信' }
  const fromHigh = m.period_high ? Math.round(((m.period_high - m.latest_close) / m.period_high) * 1000) / 10 : 0
  const prev = s.close != null && s.change != null ? s.close - s.change : null
  const dayPct = prev ? Math.round((s.change / prev) * 1000) / 10 : 0
  if (Math.abs(dayPct) >= 7) return { code, rank: 3, level: 'warn', tag: '需留意', surge: dayPct > 0, reason: `最近一日${dayPct > 0 ? '大漲' : '大跌'} ${Math.abs(dayPct)}%` }
  if (fromHigh >= stop.line) return { code, rank: 2, level: 'warn', tag: '需留意', reason: `距半年高點已回落 ${fromHigh}%` }
  if (m.annualized_volatility_pct >= 45) return { code, rank: 1, level: 'note', tag: '波動大', reason: `年化波動 ${m.annualized_volatility_pct}%` }
  return { code, rank: 0, level: 'ok', tag: '正常', reason: `距半年高點 ${fromHigh}%` }
}).sort((a, b) => b.rank - a.rank))
const RISK_ROWS = 4
const riskSummary = computed(() => [
  ['需留意', risks.value.filter((r) => r.level === 'warn').length, 'is-warn'],
  ['波動大或待確認', risks.value.filter((r) => r.level === 'note' || r.level === 'check').length, 'is-note'],
  ['正常', risks.value.filter((r) => r.level === 'ok').length, 'is-ok'],
])
function openRisk(row) {
  if (row.level === 'warn') track('risk_check', row.code)
  if (row.surge) track('surge_pause', row.code, { once: true })
  openStockDetail(row.code, '股票詳情')
}

// ── 目標試算 ──
const GOAL_KEY = storageKey('pinwise_vue_goal')
const RATES = [3, 5, 7]
const LEVELS = [[10, '起步者'], [25, '累積者'], [50, '穩健者'], [75, '達標在望'], [100, '目標達成']]
const goal = reactive(readJson(GOAL_KEY, { target: 1000, current: 50, monthly: 10000, years: 20, rate: 5 }))
watch(goal, (value) => writeJson(GOAL_KEY, value))
const clamp = (v, min, max) => Math.min(max, Math.max(min, Number(v) || 0))
const plan = computed(() => ({
  target: clamp(goal.target, 0, 1000000) * 10000, current: clamp(goal.current, 0, 1000000) * 10000,
  monthly: clamp(goal.monthly, 0, 100000000), years: Math.round(clamp(goal.years, 1, 50)), i: goal.rate / 100 / 12,
}))
const future = (months) => {
  const { current, monthly, i } = plan.value
  const growth = (1 + i) ** months
  return current * growth + monthly * ((growth - 1) / i)
}
const points = computed(() => Array.from({ length: plan.value.years + 1 }, (_, year) => ({ year, value: future(year * 12), invested: plan.value.current + plan.value.monthly * year * 12 })))
const final = computed(() => points.value.at(-1))
const progress = computed(() => (plan.value.target ? Math.round((final.value.value / plan.value.target) * 100) : 0))
const level = computed(() => [...LEVELS].reverse().find(([pct]) => progress.value >= pct)?.[1] || '準備中')
watch(progress, (value) => value >= 100 && track('goal_100', '', { once: true }), { immediate: true })
const gapMonthly = computed(() => {
  const { target, current, years, i, monthly } = plan.value
  const growth = (1 + i) ** (years * 12)
  return Math.max(0, Math.ceil(((target - current * growth) * i) / (growth - 1) - monthly))
})
// 把試算帶進助手，使用者看過、可修改後才送出。
function askPlan() {
  const { years, monthly, target, current } = plan.value
  if (currentConversation.value?.messages.length) newConversation()
  assistant.view = 'chat'
  ui.assistantOpen = true
  ui.assistantDraft = `我想做長期存錢規劃：${years} 年後想存到 ${wan(target)}，現在有 ${wan(current)}，每月投入 ${num(monthly)} 元，假設年報酬 ${goal.rate}%，估計最後約 ${wan(final.value.value)}。這樣的存錢計畫合理嗎？可以調整哪些地方？要注意哪些風險？`
}
const wan = (v) => `${num(Math.round(v / 10000))} 萬`
const chartBox = ref(null)
const size = reactive({ w: 420, h: 130 })
let observer
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    size.w = Math.max(160, entry.contentRect.width)
    size.h = Math.max(80, entry.contentRect.height)
  })
  if (chartBox.value) observer.observe(chartBox.value)
})
onBeforeUnmount(() => observer?.disconnect())
const PAD = { l: 42, r: 8, t: 6, b: 18 }
const yMax = computed(() => Math.max(plan.value.target, final.value.value, 1) * 1.08)
const xOf = (year) => PAD.l + (year / plan.value.years) * (size.w - PAD.l - PAD.r)
const yOf = (v) => size.h - PAD.b - (v / yMax.value) * (size.h - PAD.t - PAD.b)
const lineOf = (key) => points.value.map((p) => `${xOf(p.year).toFixed(1)},${yOf(p[key]).toFixed(1)}`).join(' ')
const ticks = computed(() => [0, 1, 2, 3].map((k) => (yMax.value * k) / 3))
const xTicks = computed(() => [0, Math.round(plan.value.years / 2), plan.value.years])
const hoverYear = ref(null)
function onChartMove(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  hoverYear.value = Math.round(Math.min(1, Math.max(0, (event.clientX - rect.left - PAD.l) / (rect.width - PAD.l - PAD.r))) * plan.value.years)
}
const hoverPoint = computed(() => (hoverYear.value == null ? null : points.value[hoverYear.value]))

// 下一枚徽章：完成度最高、但還沒拿滿的公開徽章。
const nextBadge = computed(() => BADGES.filter((b) => b.group !== 'hidden').map((b) => ({ badge: b, ...progressOf(b) })).filter((b) => b.next != null).sort((a, b) => b.pct - a.pct)[0] || null)
</script>

<template>
  <div class="fp-kpis ov-kpis" data-tour="score-kpis">
    <article v-for="kpi in kpis" :key="kpi.label" class="card surface-solid">
      <div><small>{{ kpi.label }}<InfoTip :text="kpi.tip" :label="kpi.label" /></small><strong>{{ kpi.value }}<i>{{ kpi.unit }}</i></strong><span :title="kpi.note">{{ kpi.note }}</span></div>
      <em aria-hidden="true"><AppIcon :name="kpi.icon" :size="17" /></em>
    </article>
  </div>

  <div class="ov-mid fp-grow">
    <section class="card surface-solid fp-card">
      <header>
        <h2>使用次數</h2>
        <div class="fp-chips" role="group" aria-label="統計單位"><button type="button" :class="{ active: usageView === 'week' }" @click="usageView = 'week'">週</button><button type="button" :class="{ active: usageView === 'month' }" @click="usageView = 'month'">月</button></div>
        <div v-if="usageView === 'month'" class="ov-year"><button type="button" aria-label="上一年" :disabled="usageYear <= firstYear" @click="usageYear--">‹</button><span>{{ usageYear }}</span><button type="button" aria-label="下一年" :disabled="usageYear >= thisYear" @click="usageYear++">›</button></div>
        <small>{{ usageNote }}</small>
      </header>
      <div v-if="records.length" class="ov-bars" :style="{ '--n': bars.length }" @mouseleave="hoverBar = null">
        <div class="ov-axis-grid" aria-hidden="true"><div v-for="tick in axisTicks" :key="tick" :style="{ bottom: `${(tick / axisMax) * 100}%` }"><span>{{ tick }}</span></div></div>
        <div v-for="bar in bars" :key="bar.key" class="ov-bar" :title="bar.title" @mouseenter="hoverBar = bar">
          <div class="ov-bar-track"><b v-if="bar.count" :style="{ height: `${(bar.count / axisMax) * 100}%` }"></b></div>
          <small>{{ bar.label }}</small>
        </div>
      </div>
      <div v-else class="fp-empty"><strong>還沒有使用紀錄</strong><button class="outline-button small" type="button" @click="router.push('/picker')">從智慧選股開始 →</button></div>
    </section>

    <section class="card surface-solid fp-card" data-tour="score-rating">
      <header><h2>你的評價</h2><small>共 {{ rated.length }} 筆</small></header>
      <div v-if="rated.length" class="ov-donut">
        <svg viewBox="0 0 104 104" role="img" :aria-label="slices.map((s) => `${s.label} ${s.count} 筆`).join('、')">
          <circle cx="52" cy="52" :r="R" class="ov-track" />
          <circle v-for="arc in arcs" :key="arc.key" cx="52" cy="52" :r="R" class="ov-arc" :class="[`is-${arc.key}`, { dim: hoverSlice && hoverSlice !== arc.key }]" :stroke-dasharray="arc.dash" :stroke-dashoffset="arc.offset" transform="rotate(-90 52 52)" @mouseenter="hoverSlice = arc.key" @mouseleave="hoverSlice = null" />
          <text x="52" y="50" text-anchor="middle" class="ov-num">{{ shownSlice ? shownSlice.count : rated.length }}</text>
          <text x="52" y="64" text-anchor="middle" class="ov-sub">{{ shownSlice ? shownSlice.label : '筆評價' }}</text>
        </svg>
        <ul><li v-for="s in slices" :key="s.key" class="ov-rate-link" role="button" tabindex="0" :title="`查看評為「${s.label}」的紀錄`" @click="emit('go', `history:${s.key}`)" @keydown.enter="emit('go', `history:${s.key}`)" @mouseenter="hoverSlice = s.key" @mouseleave="hoverSlice = null"><i :class="`is-${s.key}`"></i><span>{{ s.label }}</span><b>{{ s.count }}</b><small>{{ s.pct }}%</small></li></ul>
      </div>
      <div v-else class="fp-empty"><strong>還沒有評價</strong><span>助手回答後偶爾會問你覺得如何，也可以在「歷程」直接評價。</span></div>
    </section>

    <section class="card surface-solid fp-card" data-tour="score-risk">
      <header>
        <h2>風險觀察<InfoTip text="提醒線由你自己決定，不是停損建議。回落是和近半年最高收盤價比較，不是你的買進成本。" label="風險觀察" /></h2>
        <div class="fp-chips" role="group" aria-label="提醒線"><small>提醒線</small><button v-for="value in STOP_OPTIONS" :key="value" type="button" :class="{ active: stop.line === value }" @click="stop.line = value">{{ value }}%</button></div>
      </header>
      <template v-if="risks.length">
        <div class="ov-risk-sum"><span v-for="[label, count, cls] in riskSummary" :key="label" :class="cls"><b>{{ count }}</b>{{ label }}</span></div>
        <ul class="ov-risks" :style="{ '--rows': RISK_ROWS }">
          <li v-for="row in risks.slice(0, RISK_ROWS)" :key="row.code"><button type="button" @click="openRisk(row)"><span><b>{{ row.code }}</b>{{ nameOf(row.code) }}</span><small>{{ row.reason }}</small><em :class="`is-${row.level}`">{{ row.level === 'ok' ? '✓' : '！' }} {{ row.tag }}</em></button></li>
          <li v-if="risks.length < RISK_ROWS" class="ov-risk-add" :style="{ gridRow: `span ${RISK_ROWS - risks.length}` }"><button type="button" @click="overlays.stockSearch = true"><strong>＋ 再加一檔一起觀察</strong><small>從搜尋股票加入追蹤，這裡會自動檢查</small></button></li>
        </ul>
      </template>
      <div v-else class="fp-empty ov-risk-empty">
        <div class="ov-mascot"><GgOutline /></div>
        <strong>先加一檔，我幫你盯。</strong>
        <span>股怪會檢查大漲大跌和高點回落</span>
        <button class="primary-button small" type="button" @click="overlays.stockSearch = true">＋ 加入追蹤</button>
      </div>
    </section>
  </div>

  <div class="ov-bottom">
    <section class="card surface-solid ov-goal" data-tour="score-goal">
      <div class="ov-form">
        <div class="ov-goal-head"><h2>離目標還有多遠</h2><button class="primary-button small" type="button" @click="askPlan">問助手規劃</button></div>
        <div class="ov-fields">
          <label>目標金額<span><input v-model.number="goal.target" type="number" min="0" /><i>萬</i></span></label>
          <label>目前已有<span><input v-model.number="goal.current" type="number" min="0" /><i>萬</i></span></label>
          <label>每月投入<span><input v-model.number="goal.monthly" type="number" min="0" step="1000" /><i>元</i></span></label>
          <label>投入年數<span><input v-model.number="goal.years" type="number" min="1" max="50" /><i>年</i></span></label>
        </div>
        <div class="fp-chips" role="group" aria-label="假設年報酬"><small>假設年報酬</small><button v-for="value in RATES" :key="value" type="button" :class="{ active: goal.rate === value }" @click="goal.rate = value">{{ value }}%</button></div>
      </div>
      <div class="ov-chart-wrap">
        <div class="ov-legend"><span><i class="is-value"></i>預估資產</span><span><i class="is-invested"></i>累積投入</span><span><i class="is-target"></i>目標</span><small>單位：萬元</small></div>
        <div ref="chartBox" class="ov-chart">
          <svg :width="size.w" :height="size.h" role="img" :aria-label="`${plan.years} 年後預估 ${wan(final.value)}，目標 ${wan(plan.target)}`" @mousemove="onChartMove" @mouseleave="hoverYear = null">
            <g v-for="tick in ticks" :key="tick"><line :x1="PAD.l" :x2="size.w - PAD.r" :y1="yOf(tick)" :y2="yOf(tick)" class="ov-grid" /><text :x="PAD.l - 6" :y="yOf(tick) + 4" text-anchor="end" class="ov-axis">{{ num(Math.round(tick / 10000)) }}</text></g>
            <text v-for="year in xTicks" :key="year" :x="xOf(year)" :y="size.h - 4" :text-anchor="year === 0 ? 'start' : year === plan.years ? 'end' : 'middle'" class="ov-axis">{{ year }} 年</text>
            <line :x1="PAD.l" :x2="size.w - PAD.r" :y1="yOf(plan.target)" :y2="yOf(plan.target)" class="ov-target" />
            <polyline :points="lineOf('invested')" class="ov-line is-invested" /><polyline :points="lineOf('value')" class="ov-line is-value" />
            <g v-if="hoverPoint"><line :x1="xOf(hoverPoint.year)" :x2="xOf(hoverPoint.year)" :y1="PAD.t" :y2="size.h - PAD.b" class="ov-cross" /><circle :cx="xOf(hoverPoint.year)" :cy="yOf(hoverPoint.value)" r="4" class="ov-dot" /></g>
          </svg>
          <div v-if="hoverPoint" class="ov-tip" :style="{ left: `${Math.min(size.w - 140, xOf(hoverPoint.year) + 10)}px` }"><b>第 {{ hoverPoint.year }} 年</b><span>預估資產 {{ wan(hoverPoint.value) }}</span><span>累積投入 {{ wan(hoverPoint.invested) }}</span></div>
        </div>
      </div>
      <div class="ov-result">
        <span class="fp-tag">{{ level }}</span>
        <strong>{{ wan(final.value) }}</strong>
        <small>{{ plan.years }} 年後預估，達成 {{ progress }}%</small>
        <div class="ov-meter" aria-hidden="true"><u :style="{ width: `${Math.min(100, progress)}%` }"></u></div>
        <p v-if="gapMonthly">每月再多 <b>{{ num(gapMonthly) }} 元</b>可達標</p><p v-else>照這個計畫可以達標</p>
        <small class="ov-note">報酬為固定假設，只是試算。</small>
      </div>
    </section>
    <section class="card surface-solid fp-card ov-next">
      <header><h2>下一枚徽章</h2><button class="fp-link" type="button" @click="emit('go', 'badges')">全部 →</button></header>
      <div v-if="nextBadge" class="ov-next-body">
        <div class="ov-next-art"><BadgeMedal :badge="nextBadge.badge.id" :shape="nextBadge.badge.shape" :tier="['bronze', 'silver', 'gold'][nextBadge.earned]" locked /></div>
        <strong>{{ nextBadge.badge.name }}</strong>
        <small>{{ nextBadge.badge.desc }}</small>
        <div class="ov-meter" aria-hidden="true"><u :style="{ width: `${nextBadge.pct}%` }"></u></div>
        <small>{{ nextBadge.value }} / {{ nextBadge.next }} {{ nextBadge.badge.unit }}</small>
      </div>
    </section>
  </div>
</template>

<style scoped>
.ov-kpis{grid-template-columns:repeat(4,minmax(0,1fr))}
.ov-mid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,.9fr) minmax(0,1.25fr);gap:8px}
.ov-bottom{flex:0 0 190px;display:grid;grid-template-columns:minmax(0,1fr) 208px;gap:8px;min-height:0}
.ov-year{display:flex;align-items:center;gap:2px;color:var(--text-strong);font-size:12px;font-weight:700;font-variant-numeric:tabular-nums}
.ov-year button{width:20px;height:20px;padding:0;border:0;border-radius:6px;background:transparent;color:var(--blue);font-size:15px;line-height:1;cursor:pointer}
.ov-year button:disabled{color:var(--muted);opacity:.4;cursor:default}
.ov-bars{position:relative;flex:1;display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:2px;min-height:0;padding:8px 0 0 24px}
/* 橫向刻度線：範圍對齊長條區，扣掉上方留白與下方日期列 */
.ov-axis-grid{position:absolute;inset:8px 0 20px 0;pointer-events:none}
.ov-axis-grid div{position:absolute;left:24px;right:0;height:0;border-top:1px solid var(--line)}
.ov-axis-grid span{position:absolute;left:-24px;top:-8px;width:19px;color:var(--muted);font-size:11px;line-height:16px;text-align:right;font-variant-numeric:tabular-nums}
.ov-bar{position:relative;z-index:1;display:flex;flex-direction:column;gap:4px;min-height:0;border-radius:6px}
.ov-bar:hover{background:var(--sc-track)}
.ov-bar-track{flex:1;display:flex;align-items:flex-end;justify-content:center;min-height:0}
.ov-bar-track b{display:block;width:min(18px,70%);border-radius:4px 4px 0 0;background:var(--sc-a)}
.ov-bar small{color:var(--muted);font-size:11px;height:16px;line-height:16px;text-align:center;white-space:nowrap;font-variant-numeric:tabular-nums}
.ov-donut{flex:1;display:grid;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:10px;min-height:0}
.ov-donut svg{width:100%;max-height:100%}
.ov-track{fill:none;stroke:var(--sc-track);stroke-width:12}
.ov-arc{fill:none;stroke-width:12;transition:opacity .15s}
.ov-arc.dim{opacity:.35}
.ov-arc.is-useful,.ov-donut li i.is-useful{stroke:var(--sc-a);background:var(--sc-a)}
.ov-arc.is-ok,.ov-donut li i.is-ok{stroke:var(--sc-c);background:var(--sc-c)}
.ov-arc.is-bad,.ov-donut li i.is-bad{stroke:var(--sc-b);background:var(--sc-b)}
.ov-num{fill:var(--text-strong);font-size:20px;font-weight:800}
.ov-sub{fill:var(--muted);font-size:9px}
.ov-donut ul{display:grid;gap:9px;margin:0;padding:0;list-style:none}
.ov-donut li{display:grid;grid-template-columns:10px minmax(0,1fr) auto 32px;align-items:center;gap:6px;color:var(--text);font-size:13px;white-space:nowrap}
.ov-donut li i{width:10px;height:10px;border-radius:3px}
.ov-donut li b{color:var(--text-strong)}
.ov-donut li small{color:var(--muted);font-size:12px;text-align:right}
.ov-risk-sum{flex:none;display:flex;gap:6px}
.ov-risk-sum span{flex:1;display:flex;align-items:baseline;justify-content:center;gap:5px;padding:3px 6px;border-radius:9px;background:var(--pw-inner);color:var(--muted);font-size:12px;white-space:nowrap}
.ov-risk-sum b{color:var(--text-strong);font-size:16px}
.ov-risk-sum .is-warn b{color:var(--red)}
.ov-risk-add{border-top:0!important}
.ov-risk-add button{display:grid!important;grid-template-areas:none!important;grid-template-columns:1fr!important;justify-items:center;align-content:center;gap:2px;margin-top:4px;height:calc(100% - 4px)!important;border:1.5px dashed var(--pw-small-line)!important;border-radius:10px;text-align:center!important}
.ov-risk-add strong{color:var(--blue);font-size:13px}
.ov-risk-add small{grid-area:auto!important}
.ov-risk-empty{gap:4px!important}
.ov-risk-empty span{color:var(--muted);font-size:12px}
.ov-risk-empty button{margin-top:4px}
.ov-mascot{width:96px;margin-bottom:6px}
.ov-risks{flex:1;display:grid;grid-template-rows:repeat(var(--rows),minmax(0,1fr));margin:0;padding:0;list-style:none;min-height:0}
.ov-risks li + li{border-top:1px solid var(--line)}
.ov-risks button{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'name tag' 'why tag';align-content:center;column-gap:8px;width:100%;height:100%;padding:0 4px;border:0;background:transparent;color:var(--text);text-align:left;cursor:pointer}
.ov-risks button:hover,.ov-risks button:focus-visible{background:var(--sc-track)}
.ov-risks span{grid-area:name;overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.ov-risks span b{margin-right:6px;color:var(--text-strong)}
.ov-risks small{grid-area:why;color:var(--muted);font-size:12px}
.ov-risks em{grid-area:tag;align-self:center;padding:2px 9px;border-radius:999px;font-size:12px;font-style:normal;font-weight:700}
.ov-risks em.is-warn{background:color-mix(in srgb,var(--red) 14%,transparent);color:var(--red)}
.ov-risks em.is-note,.ov-risks em.is-check{background:color-mix(in srgb,var(--orange) 16%,transparent);color:#B85F1F}
.ov-risks em.is-ok{background:var(--sc-track);color:var(--muted)}
:global(body[data-theme="dark"] .ov-risks em.is-note),:global(body[data-theme="dark"] .ov-risks em.is-check){color:#F0B070}
.ov-goal{display:grid;grid-template-columns:minmax(0,262px) minmax(0,1fr) minmax(0,168px);gap:14px;min-height:0;margin:0;padding:10px 15px;overflow:hidden}
.ov-goal-head{display:flex;align-items:center;justify-content:space-between;gap:6px}
.ov-goal-head .primary-button{min-height:0;padding:3px 10px;font-size:12px;white-space:nowrap}
.ov-goal h2{margin:0;color:var(--text-strong);font-size:16px}
.ov-form{display:flex;flex-direction:column;justify-content:space-between;gap:5px;min-height:0}
.ov-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 8px}
.ov-fields label{display:grid;gap:1px;color:var(--muted);font-size:12px}
.ov-fields label span{display:flex;align-items:center;gap:4px;height:30px;padding:0 9px;border:1px solid var(--pw-small-line);border-radius:9px;background:var(--pw-inner)}
.ov-fields label span:focus-within{border-color:var(--blue)}
.ov-fields input{width:100%;min-width:0;height:100%;padding:0;border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important;color:var(--text-strong);font-size:14px;font-weight:600;font-variant-numeric:tabular-nums;-moz-appearance:textfield}
.ov-fields input::-webkit-outer-spin-button,.ov-fields input::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
.ov-fields i{color:var(--muted);font-size:12px;font-style:normal}
.ov-chart-wrap{display:flex;flex-direction:column;gap:3px;min-width:0;min-height:0}
.ov-legend{flex:none;display:flex;gap:12px;color:var(--text);font-size:12px}
.ov-legend span{display:flex;align-items:center;gap:5px}
.ov-legend i{width:14px;height:2px;border-radius:2px}
.ov-legend i.is-value{background:var(--sc-a)}
.ov-legend i.is-invested{background:var(--sc-c)}
.ov-legend i.is-target{height:0;border-top:2px dashed var(--sc-b)}
.ov-legend small{margin-left:auto;color:var(--muted);font-size:12px}
.ov-chart{position:relative;flex:1;min-height:0;overflow:hidden}
.ov-chart svg{display:block}
.ov-grid{stroke:var(--line);stroke-width:1}
.ov-axis{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.ov-target{stroke:var(--sc-b);stroke-width:1.5;stroke-dasharray:5 4}
.ov-line{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.ov-line.is-value{stroke:var(--sc-a)}
.ov-line.is-invested{stroke:var(--sc-c)}
.ov-cross{stroke:var(--muted);stroke-width:1}
.ov-dot{fill:var(--sc-a);stroke:var(--surface-solid,#fff);stroke-width:2}
.ov-tip{position:absolute;top:2px;display:grid;gap:1px;min-width:128px;padding:6px 9px;border-radius:9px;background:var(--tooltip-bg,#0f2a4d);color:#fff;font-size:12px;pointer-events:none}
.ov-result{display:flex;flex-direction:column;justify-content:center;align-items:flex-start;gap:3px;min-width:0;padding-left:14px;border-left:1px solid var(--line)}
.ov-result strong{color:var(--text-strong);font-size:23px;line-height:1.15;font-variant-numeric:tabular-nums}
.ov-result small{color:var(--muted);font-size:12px}
.ov-result p{margin:0;color:var(--text);font-size:13px}
.ov-result b{color:var(--text-strong)}
.ov-note{line-height:1.3}
.ov-meter{width:100%;height:8px;border-radius:4px;background:var(--sc-track);overflow:hidden}
.ov-meter u{display:block;height:100%;border-radius:4px;background:var(--sc-a)}
.ov-next-body{flex:1;display:grid;justify-items:center;align-content:center;gap:2px;min-height:0;text-align:center}
.ov-next-art{width:52px;height:52px}
.ov-next-body strong{color:var(--text-strong);font-size:15px}
.ov-next-body small{color:var(--muted);font-size:12px;line-height:1.3}
@media (max-width:900px){
  .ov-mid,.ov-bottom,.ov-goal{grid-template-columns:1fr}
  .ov-bottom{flex:none}
  .ov-chart{height:170px;flex:none}
  .ov-result{padding-left:0;border-left:0}
}
.ov-rate-link{cursor:pointer;border-radius:8px}
.ov-rate-link:hover,.ov-rate-link:focus-visible{background:color-mix(in srgb,var(--blue) 7%,transparent)}
</style>
