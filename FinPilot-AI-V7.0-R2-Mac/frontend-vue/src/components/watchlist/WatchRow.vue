<script setup>
import MetricFlag from '@/components/MetricFlag.vue'
import { isCompared, toggleCompare, untrack } from '@/stores/workspace.js'
import { openStockDetail } from '@/stores/overlays.js'

// 追蹤清單的一列：「我的追蹤」主表與「查看所有追蹤」抽屜共用。
defineProps({ row: { type: Object, required: true } })

const LEVEL_NAMES = { low: '偏低', medium: '中等', high: '偏高' }
const has = (v) => Number.isFinite(v)
const fmtNum = (v) => (has(v) ? Number(v).toLocaleString('zh-TW') : '—')
const fmtPct = (v, sign = true) => (has(v) ? `${sign && v > 0 ? '+' : ''}${Math.round(v * 100) / 100}%` : '—')
const tone = (v) => (!has(v) ? '' : v > 0 ? 'price-up' : v < 0 ? 'price-down' : '')
</script>

<template>
  <div class="wl-gr" role="row">
    <div role="cell" class="wl-c-name">
      <button class="wl-name" type="button" :title="`${row.code} ${row.name}`" @click="openStockDetail(row.code, '股票詳情')"><strong>{{ row.code }}</strong> {{ row.name }}</button>
      <small class="wl-sub">{{ row.source !== '—' ? `來自${row.source}` : '' }}<span v-if="row.notes" class="wl-chip">觀察條件 {{ row.notes }}</span></small>
    </div>
    <div role="cell" class="num">{{ row.loading ? '讀取中…' : fmtNum(row.close) }}</div>
    <div role="cell" class="num" :class="tone(row.change)">{{ fmtPct(row.changePct) }}</div>
    <div role="cell" class="num" :class="tone(row.ret)">{{ fmtPct(row.ret) }}<MetricFlag :metrics="row.metrics" field="period_return_pct" /></div>
    <div role="cell" class="wl-c-vol"><span v-if="row.level" class="wl-level" :class="`is-${row.level}`">{{ LEVEL_NAMES[row.level] }}</span> <small>{{ has(row.vol) ? fmtPct(row.vol, false) : '—' }}</small><MetricFlag :metrics="row.metrics" field="annualized_volatility_pct" /></div>
    <div role="cell">{{ row.latestEvent || '—' }}</div>
    <div role="cell" class="act">
      <button class="card-link" type="button" :aria-pressed="String(isCompared(row.code))" @click="toggleCompare(row.code)">{{ isCompared(row.code) ? '✓ 比較中' : '比較' }}</button>
      <button class="wl-remove" type="button" :aria-label="`取消追蹤：${row.code}`" title="取消追蹤" @click="untrack(row.code)">×</button>
    </div>
  </div>
</template>

<style scoped>
.wl-gr{display:grid;grid-template-columns:var(--wl-cols);align-items:center;gap:0 8px;min-height:0;padding:0 6px;border-bottom:1px solid var(--line);font-size:14px;color:var(--text)}
.wl-gr:hover{background:color-mix(in srgb,var(--blue) 4%,transparent)}
.wl-gr > div{min-width:0;white-space:nowrap}
.wl-gr .num{text-align:right;font-variant-numeric:tabular-nums}
.wl-gr .act{display:flex;align-items:center;justify-content:flex-end}
.wl-gr small{color:var(--muted);font-size:12px}
.wl-c-name{display:grid;gap:2px}
.wl-name{overflow:hidden;max-width:100%;padding:0;border:0;background:transparent;color:var(--text-strong);font-size:14px;text-align:left;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}
.wl-name:hover{text-decoration:underline}
.wl-sub{display:block;overflow:hidden;text-overflow:ellipsis}
.wl-chip{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue)!important;font-size:11px}
.wl-level{display:inline-block;padding:1px 8px;border-radius:999px;color:#fff;font-size:12px;font-weight:700}
.wl-level.is-low{background:var(--wl-lv-low);color:#0d366b}
.wl-level.is-medium{background:var(--wl-lv-mid)}
.wl-level.is-high{background:var(--wl-lv-high)}
:global(body[data-theme="dark"] .my-watchlist .wl-level){color:#0d2340}
.act .card-link{font-size:13px}
.wl-remove{flex:none;margin-left:6px;width:24px;height:24px;border:0;border-radius:50%;background:transparent;color:var(--muted);font-size:16px;cursor:pointer}
.wl-remove:hover{background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
</style>
