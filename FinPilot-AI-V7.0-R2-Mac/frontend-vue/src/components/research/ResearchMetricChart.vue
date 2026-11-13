<script setup>
import { computed } from 'vue'

// 研究摘要的指標比較圖：每個指標一張小橫條圖，所有候選並排比較。
// 各指標單位不同，因此每張圖獨立縮放；含負值的指標以 0 為軸線左右延伸。
const props = defineProps({
  stocks: { type: Array, required: true }, // [{ code, name }]
  metrics: { type: Object, default: () => ({}) },
})

const COLORS = ['var(--blue)', 'var(--pink)', 'var(--mint)', 'var(--orange)', 'var(--purple)', 'var(--navy-2)']

const METRICS = [
  { key: 'period_return_pct', label: '期間報酬', unit: '%' },
  { key: 'annualized_volatility_pct', label: '年化波動', unit: '%' },
  { key: 'max_drawdown_pct', label: '最大回撤', unit: '%' },
  { key: 'revenue_yoy_pct', label: '月營收年增', unit: '%', note: (m) => m.revenue_month },
  { key: 'pe_ratio', label: '本益比', unit: ' 倍' },
  { key: 'dividend_yield_pct', label: '殖利率', unit: '%' },
]

const series = computed(() => props.stocks.map((s, i) => ({ ...s, color: COLORS[i % COLORS.length] })))

const panels = computed(() => METRICS.map((def) => {
  const rows = series.value.map((s) => {
    const m = props.metrics?.[s.code] || {}
    const v = m[def.key]
    return { ...s, value: Number.isFinite(v) ? v : null }
  })
  const values = rows.filter((r) => r.value !== null).map((r) => r.value)
  if (!values.length) return null
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const span = hi - lo || 1
  const months = [...new Set(series.value.map((s) => def.note?.(props.metrics?.[s.code] || {})).filter(Boolean))]
  return {
    ...def,
    sub: months.length === 1 ? months[0] : '',
    zero: lo < 0 ? (-lo / span) * 100 : null,
    rows: rows.map((r) => ({
      ...r,
      left: r.value === null ? 0 : ((Math.min(0, r.value) - lo) / span) * 100,
      width: r.value === null ? 0 : (Math.abs(r.value) / span) * 100,
      text: r.value === null ? '無資料' : `${r.value}${def.unit}`,
    })),
  }
}).filter(Boolean))
</script>

<template>
  <div v-if="panels.length" class="metric-chart">
    <div class="metric-chart-head">
      <strong>指標比較</strong>
      <ul class="metric-legend">
        <li v-for="s in series" :key="s.code"><i :style="{ background: s.color }"></i>{{ s.code }} {{ s.name }}</li>
      </ul>
    </div>
    <div class="metric-grid">
      <figure v-for="p in panels" :key="p.key" class="metric-panel">
        <figcaption>{{ p.label }}<small v-if="p.sub">{{ p.sub }}</small></figcaption>
        <div
          v-for="r in p.rows"
          :key="r.code"
          class="metric-row"
          role="img"
          :aria-label="`${r.code} ${r.name} ${p.label} ${r.text}`"
        >
          <span class="metric-code">{{ r.code }}</span>
          <span class="metric-track">
            <span v-if="p.zero !== null" class="metric-zero" :style="{ left: `${p.zero}%` }"></span>
            <span
              v-if="r.value !== null"
              class="metric-bar"
              :style="{ left: `${r.left}%`, width: `max(${r.width}%, 2px)`, background: r.color }"
            ></span>
          </span>
          <span class="metric-value" :class="{ 'is-empty': r.value === null }">{{ r.text }}</span>
        </div>
      </figure>
    </div>
  </div>
</template>

<style scoped>
.metric-chart{display:grid;gap:12px;margin:4px 0 16px}
.metric-chart-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px}
.metric-chart-head strong{color:var(--text-strong);font-size:16px}
.metric-legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin:0;padding:0;list-style:none;font-size:13px;color:var(--muted)}
.metric-legend li{display:flex;align-items:center;gap:6px}
.metric-legend i{width:10px;height:10px;border-radius:3px;flex:none}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}
.metric-panel{margin:0;padding:12px 14px;border:1px solid var(--line);border-radius:var(--radius-md);background:color-mix(in srgb,var(--blue) 5%,transparent)}
.metric-panel figcaption{display:flex;align-items:baseline;gap:8px;margin-bottom:8px;font-weight:700;color:var(--text-strong);font-size:14px}
.metric-panel figcaption small{font-weight:500;color:var(--muted);font-size:12px}
.metric-row{display:grid;grid-template-columns:42px 1fr 74px;align-items:center;gap:8px;min-height:22px;font-size:13px}
.metric-code{color:var(--muted);font-variant-numeric:tabular-nums}
.metric-track{position:relative;height:10px}
.metric-zero{position:absolute;top:-3px;bottom:-3px;width:1px;background:var(--line-strong)}
.metric-bar{position:absolute;top:0;bottom:0;border-radius:3px}
.metric-value{text-align:right;color:var(--text-strong);font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.metric-value.is-empty{color:var(--muted);font-weight:400}
</style>
