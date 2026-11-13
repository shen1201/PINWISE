<script setup>
import { ref } from 'vue'
import OverviewTab from '@/components/footprint/OverviewTab.vue'
import HistoryTab from '@/components/footprint/HistoryTab.vue'
import BadgesTab from '@/components/footprint/BadgesTab.vue'
import AuditTab from '@/components/footprint/AuditTab.vue'

// 我的投資足跡：PINWISE 替使用者做過的事、使用者的評價與收集進度。
const TABS = [['overview', '總覽'], ['history', '歷程'], ['badges', '徽章'], ['audit', 'AI 查核']]
const tab = ref('overview')
// 從總覽點「有用／還好／很糟」時，直接打開歷程並篩選該評價。
const ratingFilter = ref('all')
function go(target) {
  const [next, rating] = String(target).split(':')
  ratingFilter.value = rating || 'all'
  tab.value = next
}
</script>

<template>
  <div class="page with-top-space scorecard-page">
    <div class="workspace scorecard-workspace">
      <section class="page-banner fp-banner">
        <div class="fp-banner-copy">
          <h1>我的投資足跡</h1>
          <p>記錄 PINWISE 替你做過的事、你的評價，以及離目標還有多遠。</p>
        </div>
        <nav class="fp-tabs" role="tablist" aria-label="投資足跡分頁" data-tour="fp-tabs">
          <button v-for="[key, label] in TABS" :key="key" type="button" role="tab" :data-tab="key" :aria-selected="String(tab === key)" :class="{ active: tab === key }" @click="go(key)">{{ label }}</button>
        </nav>
      </section>
      <OverviewTab v-if="tab === 'overview'" @go="go" />
      <HistoryTab v-else-if="tab === 'history'" v-model:rating="ratingFilter" />
      <BadgesTab v-else-if="tab === 'badges'" />
      <AuditTab v-else />
    </div>
  </div>
</template>

<style scoped>
.scorecard-page{--sc-a:#2A78D6;--sc-b:#C76E12;--sc-c:#8A4FD0;--sc-up:#D9534F;--sc-down:#1E9E72;--sc-track:color-mix(in srgb,var(--blue) 10%,transparent)}
:global(body[data-theme="dark"] .scorecard-page){--sc-a:#3F86E4;--sc-b:#C97C24;--sc-c:#9A6BDA;--sc-up:#FF9A9A;--sc-down:#6FE3B4}
@media (min-width:901px){:global(body[data-page="scorecard"] .page-host .scorecard-workspace){display:flex!important;flex-direction:column;gap:8px}}
/* 分頁放在標題卡內，右邊預留搜尋股票與鈴鐺的位置 */
.fp-banner{display:flex!important;flex-wrap:wrap;align-items:center;gap:6px 16px}
:global(body[data-page="scorecard"] .page-host .page-banner.fp-banner){padding-right:236px!important}
.fp-banner-copy{flex:1 1 auto;min-width:0}
.fp-tabs{position:relative;z-index:1;flex:none;display:flex;gap:2px;padding:3px;border:1.5px solid var(--pw-small-line);border-radius:12px;background:var(--surface-solid,#fff)}
.fp-tabs button{min-width:76px;padding:5px 10px;border:0;border-radius:9px;background:transparent;color:var(--text);font-size:14px;font-weight:600;cursor:pointer}
.fp-tabs button:hover{color:var(--blue)}
.fp-tabs button.active{background:linear-gradient(115deg,#FFF3C4,#FFDC82);color:#3A2600;font-weight:800}
.scorecard-page :deep(.fp-grow){flex:1 1 0;min-height:0}
.scorecard-page :deep(.fp-card){display:flex;flex-direction:column;gap:8px;min-height:0;margin:0;padding:11px 15px;overflow:hidden}
.scorecard-page :deep(.fp-card > header){flex:none;display:flex;align-items:center;justify-content:space-between;gap:8px}
.scorecard-page :deep(.fp-card h2){display:flex;align-items:center;margin:0;color:var(--text-strong);font-size:16px}
.scorecard-page :deep(.fp-card > header small){color:var(--muted);font-size:12px}
.scorecard-page :deep(.fp-link){padding:0;border:0;background:transparent;color:var(--muted);font-size:12px;cursor:pointer}
.scorecard-page :deep(.fp-link:hover){color:var(--blue)}
.scorecard-page :deep(.fp-empty){flex:1;display:grid;place-content:center;justify-items:center;gap:10px;color:var(--text);font-size:14px;text-align:center}
.scorecard-page :deep(.fp-kpis){flex:none;display:grid;gap:8px}
.scorecard-page :deep(.fp-kpis article){display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin:0;padding:8px 14px}
.scorecard-page :deep(.fp-kpis article > div){display:grid;min-width:0}
.scorecard-page :deep(.fp-kpis small){display:flex;align-items:center;color:var(--muted);font-size:13px;font-weight:600}
.scorecard-page :deep(.fp-kpis strong){color:var(--text-strong);font-size:23px;line-height:1.2;font-variant-numeric:tabular-nums}
.scorecard-page :deep(.fp-kpis strong i){margin-left:4px;color:var(--muted);font-size:13px;font-style:normal;font-weight:600}
.scorecard-page :deep(.fp-kpis article > div > span){overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.scorecard-page :deep(.fp-kpis em){flex:none;display:grid;place-items:center;width:30px;height:30px;border-radius:10px;background:var(--sc-track);color:var(--blue)}
.scorecard-page :deep(.fp-chips){display:flex;align-items:center;gap:4px}
.scorecard-page :deep(.fp-chips small){margin-right:2px;color:var(--muted);font-size:12px}
.scorecard-page :deep(.fp-chips button){min-width:38px;padding:2px 8px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--text);font-size:12px;cursor:pointer}
.scorecard-page :deep(.fp-chips button.active){border-color:var(--blue);background:color-mix(in srgb,var(--blue) 14%,transparent);color:var(--blue);font-weight:700}
.scorecard-page :deep(.fp-tag){display:inline-block;padding:1px 9px;border-radius:999px;background:var(--sc-track);color:var(--blue);font-size:12px;font-weight:700;white-space:nowrap}
.scorecard-page :deep(.fp-table){flex:1;min-height:0;overflow:hidden;border:1.5px solid #E2C3B5;border-radius:14px;background:var(--pw-inner)}
:global(body[data-theme="dark"] .scorecard-page .fp-table){border-color:var(--pw-small-line)}
@media (max-width:900px){.scorecard-page :deep(.fp-kpis){grid-template-columns:repeat(2,minmax(0,1fr))!important}}
</style>
