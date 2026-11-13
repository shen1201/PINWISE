<script setup>
import { onMounted } from 'vue'
import AppIcon from '@/components/AppIcon.vue'
import { PRESETS } from '@/stores/picker.js'
import { presetPreviews, loadPresetPreviews } from '@/composables/presetPreviews.js'

// 第一次使用的起始畫面：每個常用條件直接看到目前的候選，再決定要不要交給 AI。
defineEmits(['pick', 'detail'])
onMounted(loadPresetPreviews)
const TAG_CLASS = { 產業: 'is-g0', 波動: 'is-g1', ETF: 'is-g2' }
const FLOW = [['layers', '候選名單'], ['check', '列入原因'], ['compass', '研究、追蹤或比較']]
const preview = (id) => presetPreviews[id] || { state: 'loading', rows: [], count: '' }
</script>

<template>
  <div class="pt">
    <header class="pt-head">
      <div><h2>先看看這些方向</h2><p>依最近交易日成交金額排序，不是推薦；想深入就帶入問題交給 AI。</p></div>
      <slot name="side"></slot>
      <ol v-if="!$slots.side" class="pt-flow" aria-label="送出後會看到">
        <li class="pt-flow-label">送出後會看到</li>
        <li v-for="[icon, label] in FLOW" :key="label"><AppIcon :name="icon" :size="14" />{{ label }}</li>
      </ol>
    </header>
    <div class="pt-grid" data-tour="picker-presets">
      <article v-for="[id, , tag, question, title] in PRESETS" :key="id" class="pt-tile" :class="TAG_CLASS[tag]">
        <div class="pt-tile-top"><span class="pt-tag">{{ tag }}</span><small>{{ preview(id).count }}</small></div>
        <h3>{{ title }}</h3>
        <div class="pt-rows">
          <small class="pt-rows-label">{{ preview(id).usesRisk ? '成交金額前三 · 年化波動' : '成交金額前三 · 最近漲跌' }}</small>
          <template v-if="preview(id).state === 'loading'"><i v-for="n in 3" :key="n" class="pt-ghost" aria-hidden="true"></i></template>
          <button v-for="row in preview(id).rows" :key="row.code" type="button" class="pt-row" :title="`查看 ${row.code} ${row.name}`" @click="$emit('detail', row.code)">
            <span>{{ row.name }}</span><b :class="row.tone && `is-${row.tone}`">{{ row.value }}</b>
          </button>
          <p v-if="preview(id).state === 'ready' && !preview(id).rows.length" class="pt-note">成交金額最高的幾檔，目前都不在這個波動範圍。</p>
          <p v-if="preview(id).state === 'failed'" class="pt-note">暫時取不到資料，仍可帶入問題。</p>
        </div>
        <button class="pt-go" type="button" @click="$emit('pick', question)">帶入問題 →</button>
      </article>
    </div>
  </div>
</template>

<style scoped>
.pt{flex:1;min-height:0;height:100%;display:flex;flex-direction:column;gap:10px}
.pt-head{flex:none;display:flex;align-items:center;justify-content:space-between;gap:16px}
.pt-head h2{margin:0;color:var(--text-strong);font-size:18px}
.pt-head p{margin:1px 0 0;color:var(--muted);font-size:13px}
.pt-flow{flex:none;display:flex;align-items:center;gap:12px;margin:0;padding:0;list-style:none;color:var(--text);font-size:12px;white-space:nowrap}
.pt-flow li{display:inline-flex;align-items:center;gap:4px}
.pt-flow li :deep(svg){color:var(--blue)}
.pt-flow .pt-flow-label{color:var(--muted);font-weight:700}
.pt-grid{flex:1;min-height:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr));gap:10px}
.pt-tile{--g:#2A78D6;display:flex;flex-direction:column;gap:5px;min-width:0;min-height:0;padding:10px 12px;border:1.5px solid var(--pw-small-line);border-radius:14px;background:var(--pw-inner);overflow:hidden;transition:border-color .15s,box-shadow .15s}
.pt-tile:hover{border-color:var(--g);box-shadow:0 6px 14px rgba(31,69,127,.1)}
.pt-tile.is-g1{--g:#C76E12}
.pt-tile.is-g2{--g:#8A4FD0}
:global(body[data-theme="dark"] .pt-tile.is-g0){--g:#8DB4F5}
:global(body[data-theme="dark"] .pt-tile.is-g1){--g:#F0B070}
:global(body[data-theme="dark"] .pt-tile.is-g2){--g:#C7A2F2}
.pt-tile-top{flex:none;display:flex;align-items:center;justify-content:space-between;gap:8px}
.pt-tag{color:var(--g);font-size:12px;font-weight:800}
.pt-tile-top small{min-width:0;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.pt-tile h3{flex:none;margin:0;overflow:hidden;color:var(--text-strong);font-size:15px;text-overflow:ellipsis;white-space:nowrap}
.pt-rows{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:1px;padding:4px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.pt-rows-label{flex:none;color:var(--muted);font-size:11px}
.pt-row{flex:0 1 auto;display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px;padding:0 4px;border:0;border-radius:6px;background:transparent;color:var(--text-strong);font-size:13px;text-align:left;cursor:pointer}
.pt-row:hover,.pt-row:focus-visible{background:color-mix(in srgb,var(--g) 10%,transparent)}
.pt-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pt-row b{flex:none;font-weight:700;font-variant-numeric:tabular-nums}
.pt-row b.is-up{color:var(--candle-up,#D9534F)}
.pt-row b.is-down{color:var(--candle-down,#1E9E72)}
:global(body[data-theme="dark"]) .pt-row b.is-up{color:#FF9A9A}
:global(body[data-theme="dark"]) .pt-row b.is-down{color:#6FE3B4}
.pt-ghost{display:block;height:9px;margin:6px 4px;border-radius:5px;background:color-mix(in srgb,var(--muted) 16%,transparent)}
.pt-note{margin:2px 0 0;color:var(--muted);font-size:12px;line-height:1.45}
.pt-go{flex:none;align-self:flex-end;padding:0;border:0;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer}
.pt-go:hover{text-decoration:underline}
@media (max-width:1000px){.pt-grid{grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:none;grid-auto-rows:minmax(170px,auto)}.pt{height:auto}.pt-head{flex-wrap:wrap}}
@media (max-width:640px){.pt-grid{grid-template-columns:1fr}}
</style>
