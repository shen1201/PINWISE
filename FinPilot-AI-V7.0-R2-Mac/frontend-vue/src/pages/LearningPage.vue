<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import R2SectionTabs from '@/components/v7/R2SectionTabs.vue'
import { useSectionTabs } from '@/composables/r2Layout.js'
import { recommendedReading } from '@/data/articles.js'
import { settings } from '@/stores/ui.js'
import { overlays, openHelp, openArticle } from '@/stores/overlays.js'
import { startTour } from '@/stores/tour.js'
import { tours } from '@/data/tours.js'

// 學習專區：上方是第一次使用的路線，下方是需要時再查的內容。
const route = useRoute()
const router = useRouter()
const STEPS = [
  ['找標的', '智慧選股', '不知道看哪幾檔時，用一句話描述需求。', '/picker'],
  ['深入了解', 'AI 標的研究', '針對一檔股票或 ETF 整理理由與風險。', '/research'],
  ['放在一起看', '股票比較', '用同一組標準對照兩、三檔的差異。', '/compare'],
  ['持續留意', '我的追蹤', '留下關注的標的，之後回來檢查。', '/candidates'],
]
const LOOKUPS = [
  ['guide', '各頁操作教學', '每一頁的功能與按鈕說明', () => (overlays.featureGuide = true)],
  ['help', '常見問題', '功能、資料與操作方式', () => openHelp('faq')],
  ['indicator', '投資名詞', '用白話查 P/E、回撤、成份股', () => openHelp('glossary')],
]

// 偏好「專業深入」時，把第一篇移到最後。
const reading = computed(() => {
  const list = [...recommendedReading]
  if (settings.personalPrefs.explanationStyle === '專業深入') list.push(list.shift())
  return list
})
const startGuide = () => startTour('full', { restore: true, currentPath: route.fullPath })

// 窄螢幕時分成兩個區塊切換。
const { current: tab, hidden: tabHidden } = useSectionTabs('learning', 2)
</script>

<template>
  <div class="page with-top-space learning-dashboard-page">
    <div class="workspace learning-workspace learning-dashboard-workspace">
      <section class="page-banner">
        <h1>學習專區</h1>
        <p>第一次使用先看新手起步，之後需要時再回來查問題和名詞。</p>
      </section>
      <R2SectionTabs v-model="tab" :labels="['新手起步', '閱讀與查找']" />

      <section class="card surface-solid ln-card ln-start" :hidden="tabHidden(0)">
        <header class="ln-head">
          <div><h2>新手起步</h2><p>第一次使用照這四步走，每一步都可以直接前往。</p></div>
          <button class="primary-button small" type="button" @click="startGuide">開始導覽（{{ tours.full.length }} 步）→</button>
        </header>
        <ol class="ln-frame ln-steps">
          <li v-for="([action, page, desc, path], i) in STEPS" :key="path">
            <button type="button" @click="router.push(path)">
              <b aria-hidden="true">{{ i + 1 }}</b>
              <span><small>{{ action }}</small><strong>{{ page }}</strong><em>{{ desc }}</em></span>
            </button>
          </li>
        </ol>
      </section>

      <div class="ln-lower" :hidden="tabHidden(1)">
        <section class="card surface-solid ln-card">
          <header class="ln-head"><div><h2>新手小知識</h2><p>建議依序閱讀，每篇約一分鐘。</p></div></header>
          <div class="ln-frame ln-table">
            <button v-for="([title, desc, key], i) in reading" :key="key" type="button" @click="openArticle(key)">
              <b>{{ i + 1 }}</b><strong>{{ title }}</strong><span>{{ desc }}</span><i>閱讀 →</i>
            </button>
          </div>
        </section>
        <section class="card surface-solid ln-card">
          <header class="ln-head"><div><h2>查找與教學</h2><p>遇到問題時從這裡找。</p></div></header>
          <div class="ln-frame ln-lookups">
            <button v-for="[icon, title, desc, action] in LOOKUPS" :key="title" type="button" @click="action">
              <AppIcon :name="icon" :size="20" />
              <span><strong>{{ title }}</strong><small>{{ desc }}</small></span>
              <i aria-hidden="true">→</i>
            </button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ln-card{display:flex;flex-direction:column;gap:10px;min-height:0;margin:0;padding:12px 18px;overflow:hidden}
.ln-head{flex:none;display:flex;align-items:center;justify-content:space-between;gap:16px}
.ln-head h2{margin:0;color:var(--text-strong);font-size:18px}
.ln-head p{margin:2px 0 0;color:var(--muted);font-size:13px}
.ln-frame{min-height:0;border:1.5px solid #E2C3B5;border-radius:14px;background:var(--pw-inner)}
:global(body[data-theme="dark"] .ln-frame){border-color:var(--pw-small-line)}
.ln-frame button{width:100%;border:0;background:transparent;color:var(--text);text-align:left;cursor:pointer}
.ln-frame button:hover,.ln-frame button:focus-visible{background:color-mix(in srgb,var(--blue) 7%,transparent)}
.ln-frame b{display:grid;place-items:center;flex:none;width:26px;height:26px;border-radius:50%;background:color-mix(in srgb,var(--blue) 14%,transparent);color:var(--blue);font-size:13px}
.ln-frame strong{color:var(--text-strong)}
.ln-frame i{color:var(--blue);font-style:normal;font-weight:700}

.ln-steps{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));margin:0;padding:0;list-style:none;overflow:hidden}
.ln-steps li + li{border-left:1px solid var(--line)}
.ln-steps button{display:flex;align-items:flex-start;gap:10px;height:100%;padding:12px 14px}
.ln-steps span{display:grid;gap:2px;min-width:0}
.ln-steps small{color:var(--muted);font-size:12px}
.ln-steps strong{font-size:16px}
.ln-steps em{color:var(--text);font-size:13px;font-style:normal;line-height:1.4}

.ln-lower{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(0,1fr);gap:10px;min-height:0}
.ln-table,.ln-lookups{flex:1;display:grid;grid-auto-rows:minmax(0,1fr);overflow:hidden}
.ln-table button{display:grid;grid-template-columns:26px 212px minmax(0,1fr) auto;align-items:center;gap:12px;min-height:0;padding:0 14px}
.ln-table button + button,.ln-lookups button + button{border-top:1px solid var(--line)}
.ln-table strong{font-size:14px;white-space:nowrap}
.ln-table span{overflow:hidden;color:var(--muted);font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.ln-table i{font-size:13px}
.ln-lookups button{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:12px;min-height:0;padding:0 14px;color:var(--blue)}
.ln-lookups span{display:grid;gap:1px;min-width:0}
.ln-lookups strong{font-size:15px}
.ln-lookups small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}

@media (min-width:901px){
  :global(body[data-page="learning"] .page-host .learning-dashboard-workspace){display:flex!important;flex-direction:column}
  .ln-start{flex:none}
  .ln-lower{flex:1}
}
@media (max-width:900px){
  .ln-steps,.ln-lower{grid-template-columns:1fr}
  .ln-steps li + li{border-left:0;border-top:1px solid var(--line)}
  .ln-table button{grid-template-columns:26px minmax(0,1fr) auto;padding:12px 14px}
  .ln-table span{display:none}
  .ln-lookups button{padding:12px 14px}
}
</style>
