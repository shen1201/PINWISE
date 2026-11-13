<script setup>
import { computed } from 'vue'

// K 線與成交量（對應舊版 candleChartSvg）：紅漲綠跌，滑鼠移到 K 棒顯示開高低收。
// 後端只提供日資料；週 K 在前端合併：開＝第一天開盤、收＝最後一天收盤、高低取極值、量加總。
// 月 K 太粗、根數太少，不提供。
const props = defineProps({
  candles: { type: Array, default: () => [] },
  interval: { type: String, default: 'day' }, // day | week
})

// 價格區加高（210→250）讓走勢更明顯；量能區高度不變。
const W = 720, PRICE_H = 250, VOL_TOP = 268, VOL_H = 52, H = 340, LEFT = 8, RIGHT = 62
const fmt = (v) => Number(v).toLocaleString('zh-TW', { maximumFractionDigits: 2 })
const UNIT = { day: '日', week: '週' }

// 日期字串（YYYY-MM-DD）以 UTC 解析，避免時區讓星期幾算錯。
const parse = (d) => new Date(`${d}T00:00:00Z`)
const iso = (date) => date.toISOString().slice(0, 10)
function weekStart(d) {
  const date = parse(d)
  date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7)) // 週一
  return iso(date)
}
// 最後一根週 K 是否尚未走完：與今天同一週，且最後資料不是週五。
function unfinishedWeek(lastDate) {
  const today = iso(new Date(Date.now() - new Date().getTimezoneOffset() * 60000))
  return weekStart(lastDate) === weekStart(today) && parse(lastDate).getUTCDay() !== 5
}

function aggregate(rows, interval) {
  if (interval !== 'week') return rows.map((c) => ({ ...c, start: c.date, end: c.date }))
  const groups = []
  for (const c of rows) {
    const key = weekStart(c.date)
    const g = groups.at(-1)
    if (g && g.key === key) {
      g.high = Math.max(g.high, c.high)
      g.low = Math.min(g.low, c.low)
      g.close = c.close
      g.volume += c.volume || 0
      g.end = c.date
    } else {
      groups.push({ key, date: c.date, start: c.date, end: c.date, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume || 0 })
    }
  }
  // 期間起點常落在週中，第一根只含幾天，會誤導；起點明顯被切斷時捨去。
  // 容許假日：週的第一個交易日是週一或週二，都視為完整。
  if (groups.length > 2 && ![1, 2].includes(parse(groups[0].start).getUTCDay())) groups.shift()
  return groups
}

// 最高／最低價標籤：靠近左右邊緣時改為向內對齊，避免文字超出圖面。
function marker(x, y, text) {
  const anchor = x < LEFT + 60 ? 'start' : x > W - RIGHT - 60 ? 'end' : 'middle'
  return { x, y, text, anchor }
}

const chart = computed(() => {
  const daily = props.candles.filter((c) => [c.open, c.high, c.low, c.close].every(Number.isFinite))
  const unit = UNIT[props.interval] || '日'
  const rows = aggregate(daily, props.interval)
  if (rows.length < 2) return null
  const partial = props.interval === 'week' && unfinishedWeek(rows.at(-1).end)
  const plotW = W - LEFT - RIGHT
  const hi = Math.max(...rows.map((c) => c.high)), lo = Math.min(...rows.map((c) => c.low))
  // 上下各留 8% 空間放最高／最低價標籤。
  const pad = (hi - lo) * 0.08 || 1, top = hi + pad, bottom = lo - pad
  const y = (v) => 8 + ((top - v) / (top - bottom)) * (PRICE_H - 8)
  const step = plotW / rows.length, bodyW = Math.max(1, step * 0.62)
  const maxVol = Math.max(1, ...rows.map((c) => c.volume || 0))
  const bars = rows.map((c, i) => {
    const x = LEFT + i * step + step / 2
    const vol = ((c.volume || 0) / maxVol) * VOL_H
    const span = c.start === c.end ? c.start : `${c.start}～${c.end}`
    const note = partial && i === rows.length - 1 ? `（本${unit}尚未結束）` : ''
    return {
      key: c.start,
      title: `${span}${note}　開 ${fmt(c.open)}　高 ${fmt(c.high)}　低 ${fmt(c.low)}　收 ${fmt(c.close)}　量 ${fmt(Math.round((c.volume || 0) / 1000))} 張`,
      color: c.close >= c.open ? 'var(--candle-up)' : 'var(--candle-down)',
      x, yHigh: y(c.high), yLow: y(c.low),
      bodyX: x - bodyW / 2, bodyY: y(Math.max(c.open, c.close)), bodyH: Math.max(1, Math.abs(y(c.open) - y(c.close))), bodyW,
      volY: VOL_TOP + VOL_H - vol, volH: vol,
    }
  })
  const grid = [0, 0.5, 1].map((t) => {
    const v = bottom + (top - bottom) * (1 - t)
    return { y: y(v), label: fmt(v) }
  })
  const hiBar = bars[rows.findIndex((c) => c.high === hi)]
  const loBar = bars[rows.findIndex((c) => c.low === lo)]
  const marks = [
    marker(hiBar.x, Math.max(11, hiBar.yHigh - 5), `最高 ${fmt(hi)}`),
    marker(loBar.x, Math.min(PRICE_H + 12, loBar.yLow + 14), `最低 ${fmt(lo)}`),
  ]
  const first = rows[0].start, last = rows.at(-1).end
  return {
    bars, grid, marks, first, last, unit, partial, count: rows.length,
    label: `${first} 至 ${last} 的${unit} K 線與成交量，共 ${rows.length} 根，最高 ${fmt(hi)}、最低 ${fmt(lo)}`,
  }
})
</script>

<template>
  <div v-if="!chart" class="empty-state">歷史日價不足，無法繪製 K 線。</div>
  <figure v-else class="candle-chart">
    <svg :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="chart.label">
      <template v-for="g in chart.grid" :key="g.y">
        <line :x1="LEFT" :x2="W - RIGHT" :y1="g.y" :y2="g.y" class="candle-grid" />
        <text :x="W - RIGHT + 6" :y="g.y + 4" class="candle-axis">{{ g.label }}</text>
      </template>
      <g v-for="b in chart.bars" :key="b.key">
        <title>{{ b.title }}</title>
        <line :x1="b.x" :x2="b.x" :y1="b.yHigh" :y2="b.yLow" :stroke="b.color" stroke-width="1" />
        <rect :x="b.bodyX" :y="b.bodyY" :width="b.bodyW" :height="b.bodyH" :fill="b.color" />
        <rect :x="b.bodyX" :y="b.volY" :width="b.bodyW" :height="b.volH" :fill="b.color" opacity=".45" />
      </g>
      <text v-for="mk in chart.marks" :key="mk.text" :x="mk.x" :y="mk.y" :text-anchor="mk.anchor" class="candle-mark">{{ mk.text }}</text>
      <text :x="LEFT" :y="H - 4" class="candle-axis">{{ chart.first }}</text>
      <text :x="W - RIGHT" :y="H - 4" text-anchor="end" class="candle-axis">{{ chart.last }}</text>
      <text :x="W - RIGHT + 6" :y="VOL_TOP + 10" class="candle-axis">量</text>
    </svg>
    <figcaption>
      {{ chart.unit }} K 線（紅漲綠跌）與成交量，共 {{ chart.count }} 根；滑鼠移到 K 棒可看{{ chart.unit === '日' ? '當日' : '該週' }}開高低收。
      <template v-if="chart.partial">最後一根為本週至今，尚未結束。</template>
    </figcaption>
  </figure>
</template>

<style scoped>
.candle-mark{fill:var(--text-strong);font-size:12px;font-weight:700;paint-order:stroke;stroke:var(--surface-solid,#fff);stroke-width:3px;stroke-linejoin:round}
</style>
