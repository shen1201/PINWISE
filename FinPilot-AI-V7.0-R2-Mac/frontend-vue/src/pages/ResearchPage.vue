<script setup>
import { track } from '@/stores/footprint.js'
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import AppModal from '@/components/AppModal.vue'
import ResearchSection from '@/components/research/ResearchSection.vue'
import ResearchHistoryDrawer from '@/components/research/ResearchHistoryDrawer.vue'
import R2SectionTabs from '@/components/v7/R2SectionTabs.vue'
import { useSectionTabs } from '@/composables/r2Layout.js'
import { researchTopics } from '@/data/nav.js'
import { exportResearchPdf } from '@/utils/researchReport.js'
import { ui } from '@/stores/ui.js'
import {
  research, activeTask, visibleTasks, isCompleted,
  failureText, beginResearch, toggle,
} from '@/stores/research.js'

const router = useRouter()
const query = ref('')
const submitting = ref(false)
const openSection = ref('')
const historyOpen = ref(false)
watch(openSection, (section) => {
  if (section === 'evidence') track('source_open', task.value?.id)
  if (section === 'risk') track('risk_read', task.value?.id)
})

const SECTIONS = [
  ['summary', 'book', '研究摘要', '研究重點與候選'],
  ['risk', 'shield', '風險與反方證據', '風險與相反觀點', '哪些情況會改變結論？'],
  ['evidence', 'database', '資料與來源', '引用與核對狀態', '資料來自哪裡？數字如何核對？'],
  ['trace', 'radar', 'Agent 執行紀錄', '每階段的研究過程', '這次研究做了哪些步驟？'],
]
// 摘要直接顯示在頁面下方，右上只留另外三個入口。
const featureSections = SECTIONS.slice(1)
const sectionTitle = computed(() => SECTIONS.find((s) => s[0] === openSection.value)?.[2] || '')

const task = activeTask
const progress = computed(() => Math.round(task.value?.progress || 0))
// 進度條顯示用：進頁面時從 0 平滑跑到目前進度，之後隨進度變化平滑前進。
const shownProgress = ref(0)
onMounted(() => requestAnimationFrame(() => (shownProgress.value = task.value ? progress.value : 0)))
watch(() => (task.value ? progress.value : 0), (value) => (shownProgress.value = value))
const completed = computed(() => isCompleted(task.value))
const paused = computed(() => task.value?.status === 'paused')
const waiting = computed(() => ['pause_requested', 'cancel_requested'].includes(task.value?.status))

const heading = computed(() => {
  const t = task.value
  if (!t) return '你想研究哪一檔？'
  if (completed.value) return '這份研究已完成'
  if (t.failed) return t.failureRetryable === false ? '研究已停止' : '研究需要重新嘗試'
  if (paused.value) return '研究已暫停'
  if (t.status === 'cancel_requested') return '正在安全取消'
  return '正在整理你的研究'
})
const liveStatus = computed(() => {
  const t = task.value
  if (completed.value) return '已完成'
  if (t.failed) return '執行失敗'
  if (t.status === 'cancelled') return '已取消'
  if (t.status === 'cancel_requested') return '等待安全取消'
  if (t.status === 'pause_requested') return '等待安全暫停'
  if (paused.value) return '研究已暫停'
  return '研究中'
})

const coverageLabel = computed(() => {
  const c = task.value?.metrics?.coverage
  if (task.value?.dataMode === 'fixture') return '● 隔離測試，不是真實市場證據'
  return c ? `● 已驗證證據 ${c.completeness_pct}%（${c.available_sources}/${c.total_sources} 項）` : '● 資料待核對'
})

// Agent 即時動態：同一步驟只留最新狀態（開始 → 完成）。
const STEP_MARK = { started: '…', completed: '✓', failed: '!', skipped: '–', retrying: '↻', cancelled: '–' }
const liveSteps = computed(() => {
  const steps = new Map()
  for (const e of task.value?.agentTrace || []) steps.set(`${e.agent}|${e.action}|${e.source}`, e)
  return [...steps.values()].map((e) => ({
    key: e.id,
    status: e.status,
    mark: STEP_MARK[e.status] || '·',
    agent: e.agent,
    action: e.action,
    detail: e.detail === task.value.query ? '' : String(e.detail || '').replace('正規化資料', '資料'),
  }))
})
const liveBox = ref(null)
watch(() => liveSteps.value.length, async () => {
  await nextTick()
  if (liveBox.value) liveBox.value.scrollTop = liveBox.value.scrollHeight
})

async function submit() {
  const q = query.value.trim()
  if (!q || submitting.value) return
  submitting.value = true
  try {
    if (await beginResearch(q, 'research')) query.value = ''
  } finally {
    submitting.value = false
  }
}

function openTask(id, section = '') {
  research.activeId = id
  historyOpen.value = false
  openSection.value = section
}

// 窄螢幕時分成兩個區塊切換（對應舊版 applyR2Layout）。
const { current: tab, hidden: tabHidden } = useSectionTabs('research', 2)
</script>

<template>
  <div class="page with-top-space research-empty-page research-landing-v3 rp-compact" :class="task ? 'has-current-task' : 'is-empty-research'">
    <div class="workspace">
      <header class="research-landing-heading page-banner">
        <h1>AI 標的研究</h1>
        <p>選一檔股票或 ETF，確認範圍後，查看研究結論、數據與風險。</p>
        <button class="rp-history-entry" type="button" data-history-entry data-tour="research-history" :aria-expanded="String(historyOpen)" @click="historyOpen = !historyOpen">
          <AppIcon name="book" :size="17" /><span>最近研究</span><b v-if="visibleTasks.length">{{ visibleTasks.length }}</b>
        </button>
      </header>
      <R2SectionTabs v-model="tab" :labels="['目前研究', '研究內容']" />

      <div class="research-landing-grid" :hidden="tabHidden(0) && tabHidden(1)">
        <section class="card research-empty-card" data-tour="research-entry" :hidden="tabHidden(0)">
          <!-- 有研究時，下方狀態列已說明進度，隱藏標題 -->
          <h2 v-if="!task" class="rp-start-title">{{ heading }}</h2>

          <div v-if="task" class="research-current-strip" :class="{ 'is-complete': completed }">
            <span class="research-current-tag">{{ liveStatus }}</span>
            <strong :title="task.query">{{ task.query }}</strong>
            <!-- 已完成不放按鈕，題目使用整列寬度；研究結果從右側卡片進入 -->
            <button v-if="completed" class="research-current-action" type="button" @click="exportResearchPdf(task)">匯出 PDF</button>
            <button v-else-if="task.status === 'cancelled'" class="research-current-action" type="button" disabled>已取消</button>
            <button v-else-if="task.failed && task.failureRetryable === false" class="research-current-action" type="button" @click="openSection = 'summary'">
              查看原因<AppIcon name="info" :size="15" />
            </button>
            <button v-else class="research-current-action" type="button" :disabled="waiting" @click="toggle(task)">
              {{ task.failed ? '重試' : paused ? '繼續' : '暫停' }}<AppIcon :name="task.failed || paused ? 'play' : 'pause'" :size="15" />
            </button>
          </div>

          <div v-if="task?.failed && task.failureMessage" class="notice research-failure-summary">
            <strong>失敗原因</strong><span>{{ failureText(task) }}</span>
          </div>

          <form class="research-empty-form" @submit.prevent="submit">
            <label class="sr-only" for="researchEmptyInput">研究問題</label>
            <div>
              <span class="research-search-glyph"><AppIcon name="search" :size="21" /></span>
              <input id="researchEmptyInput" v-model="query" type="text" autocomplete="off" placeholder="輸入代號、名稱或問題，例如：0050 的風險" required />
              <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? '理解中…' : '開始研究 →' }}</button>
            </div>
          </form>
          <p v-if="!task" class="rp-next-hint">下一步會先請你確認研究面向與期間。</p>
          <div class="research-landing-topics">
            <span>試試看</span>
            <button v-for="[label, topic] in researchTopics" :key="label" type="button" @click="query = topic">{{ label }}</button>
          </div>

          <div v-if="task" class="research-landing-process" data-tour="research-process">
            <strong>後端研究進度</strong>
            <div class="research-landing-track" :class="{ 'has-progress': task, 'is-complete': completed }" :aria-label="task ? `目前進度 ${progress}%` : '尚未開始研究'">
              <span class="rp-fill" :style="{ width: `${shownProgress}%` }"></span>
            </div>
            <b>{{ task ? (task.failed ? '停在 ' : '') + progress + '%' : '—' }}</b>
            <span class="research-phase-labels">理解條件 <i>›</i> 工具與資料 <i>›</i> 指標計算 <i>›</i> Gemini 分析 <i>›</i> 檢核保存</span>
          </div>
        </section>

        <div class="research-landing-features" :class="{ 'rp-locked': !task }" aria-label="研究內容" data-tour="research-sections" :hidden="tabHidden(1)">
          <h3 v-if="!task" class="rp-locked-title">研究完成後可查看</h3>
          <template v-for="[key, icon, title, desc, preview] in featureSections" :key="key">
            <button v-if="task" type="button" class="research-landing-feature is-available" :aria-label="`${title}，查看內容`" @click="openSection = key">
              <span class="research-landing-feature-icon"><AppIcon :name="icon" :size="30" /></span>
              <h3>{{ title }}</h3><p>{{ desc }}</p><small>查看內容 →</small>
            </button>
            <article v-else class="research-landing-feature is-locked" :aria-label="`${title}，完成研究後可查看`">
              <span class="research-landing-feature-icon"><AppIcon :name="icon" :size="30" /></span>
              <h3>{{ title }}</h3><p>{{ preview }}</p>
            </article>
          </template>
        </div>
      </div>

      <!-- 下方大區塊：研究完成直接顯示摘要；進行中或失敗顯示 Agent 每一步在做什麼 -->
      <section class="rp-bottom" :class="{ 'is-preview': !task }" :hidden="tabHidden(0)">
        <!-- 還沒有研究：報告預覽，只有區塊名稱，不放任何數字 -->
        <div v-if="!task" class="rp-preview" aria-label="研究報告預覽">
          <div class="rp-pv-head">
            <h2>研究報告預覽</h2>
            <span class="rp-pv-tag">尚未開始研究</span>
            <span class="rp-pv-quality">資料完整度<i></i></span>
            <small>一次研究一檔股票或 ETF</small>
          </div>
          <div class="rp-pv-box rp-pv-c"><h3>一句話結論</h3><i></i><i class="short"></i></div>
          <div class="rp-pv-box rp-pv-t">
            <h3>重點指標</h3>
            <div class="rp-pv-table">
              <div class="rp-pv-row is-head"><span>標的</span><span>期間報酬</span><span>年化波動</span><span>月營收年增</span><span>本益比</span></div>
              <div class="rp-pv-row is-body"><i v-for="m in 5" :key="m"></i></div>
            </div>
          </div>
          <div class="rp-pv-box rp-pv-r"><h3>主要風險</h3><i></i><i class="short"></i></div>
          <div class="rp-pv-box rp-pv-w"><h3>後續觀察條件</h3><i></i><i class="short"></i></div>
        </div>
        <ResearchSection v-else-if="completed" :key="task.id" :task="task" section="summary" inline />
        <div v-else class="rp-live" aria-live="polite">
          <h3>Agent 即時動態</h3>
          <ol v-if="liveSteps.length" ref="liveBox">
            <li v-for="s in liveSteps" :key="s.key" :class="`is-${s.status}`">
              <span class="rp-live-mark" aria-hidden="true">{{ s.mark }}</span>
              <b>{{ s.agent }}</b>
              <span class="rp-live-text" :title="s.detail"><strong>{{ s.action }}</strong><template v-if="s.detail">：{{ s.detail }}</template></span>
            </li>
          </ol>
          <p v-else>研究已排入佇列，Agent 開始後每一步都會顯示在這裡。</p>
        </div>

        <!-- 只有完全沒有研究紀錄時出現；有紀錄時會自動帶出最新一筆，這行就讓給摘要 -->
        <div v-if="!task" class="rp-strip">
          <span>ⓘ 行情採收盤後日資料</span>
          <button type="button" @click="router.push('/picker')">還沒決定標的？前往智慧選股 →</button>
        </div>
      </section>
    </div>
  </div>

  <!-- 研究結果分頁 -->
  <AppModal
    :open="Boolean(openSection && task)"
    :title="sectionTitle"
    :status="openSection === 'summary' ? coverageLabel : ''"
    :modal-class="['research-section-modal', `research-section-${openSection}`]"
    backdrop-class="research-detail-backdrop"
    @close="openSection = ''"
  >
    <ResearchSection v-if="task" :key="`${task.id}-${openSection}`" :task="task" :section="openSection" />
  </AppModal>

  <!-- 最近研究任務：右側抽屜 -->
  <ResearchHistoryDrawer :open="historyOpen" @close="historyOpen = false" @select="openTask" />
</template>

<style scoped>
/* 進度條：舊版 CSS 在軌道內放了一個佔滿高度的 ::before，把填色擠出可視範圍，這裡移除。
   填色為品牌漸層（藍→紫→桃紅→金），寬度變化時平滑前進。 */
.research-landing-track::before{display:none!important}
.research-landing-track > .rp-fill{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#3b7dec 0%,#8a63e8 38%,#e0559b 72%,#e7a93c 100%)!important;transition:width .9s cubic-bezier(.22,.8,.3,1)}
/* 有研究時：卡片頂端多留空間，並收緊各區塊間距，讓總高度放得進固定高度的卡片。
   內容改為靠上排列，就算日後內容變多也只會超出底部，不會再把頂端切掉。
   選擇器加上 body[data-page] 與 .page-host 以蓋過共用 CSS 的同名規則。 */
body[data-page="research"] .page-host .rp-compact .research-empty-card{justify-content:flex-start!important;min-height:0!important;padding-top:16px!important;padding-bottom:14px!important;gap:10px!important}
body[data-page="research"] .page-host .rp-compact .research-current-strip{padding-top:4px!important;padding-bottom:4px!important}
body[data-page="research"] .page-host .rp-compact .research-input-guide{margin:0!important;line-height:1.55!important}
body[data-page="research"] .page-host .rp-compact .research-landing-process{margin-top:0!important;padding-top:6px!important;padding-bottom:4px!important}
/* 最近研究任務移到抽屜後，主要卡片填滿剩餘高度 */
@media (min-width:901px){
  body[data-page="research"] .page-host .research-landing-v3 .workspace{display:flex!important;flex-direction:column}
  body[data-page="research"] .page-host .research-landing-v3 .research-landing-grid{flex:1 1 auto;min-height:0}
  /* 有研究時：上方維持原高度，右上三個入口橫排，下方大區塊佔滿其餘高度 */
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .research-landing-grid{flex:0 0 auto;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr)!important}
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .research-landing-features{grid-template-columns:repeat(3,minmax(0,1fr))!important;grid-template-rows:minmax(0,1fr)!important;gap:10px}
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .research-landing-feature{justify-content:center;min-height:0;padding:12px!important}
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .research-landing-feature-icon{width:40px;height:40px}
  .rp-bottom{flex:1 1 auto;min-height:0;overflow:hidden}
  /* 空狀態：三張卡收進同一個外框，只說明內容，不可點 */
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .research-landing-features.rp-locked{grid-template-rows:auto minmax(0,1fr)!important;padding:12px 14px;border:1px solid rgba(199,218,245,.95);border-radius:22px;background:rgba(255,255,255,.92)}
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .rp-locked .research-landing-feature{justify-content:flex-start;padding:10px!important;border-radius:14px;background:#fff;box-shadow:none;transform:none}
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .rp-locked .research-landing-feature-icon{width:32px;height:32px;border-radius:10px}
  body[data-page="research"] .page-host .research-landing-v3.rp-compact .rp-locked .research-landing-feature h3{margin:6px 0 3px;font-size:14px;white-space:nowrap}
}
.rp-bottom{padding:12px 16px;border:1px solid rgba(199,218,245,.95);border-radius:22px;background:rgba(255,255,255,.95);box-shadow:0 12px 28px rgba(31,69,127,.12)}
:global(body[data-theme="dark"] .rp-bottom){background:#14263f}
/* 最近研究入口：放在標題列右側、搜尋股票左邊 */
.research-landing-v3 .research-landing-heading{position:relative}
.rp-history-entry{position:absolute;z-index:5;top:50%;right:192px;transform:translateY(-50%);display:inline-flex;align-items:center;gap:7px;min-height:44px;padding:0 16px;border:1px solid color-mix(in srgb,var(--blue) 35%,transparent);border-radius:999px;background:linear-gradient(115deg,#eaf2ff,#f1eaff);color:#2b5fc4;font-size:14px;font-weight:800;text-shadow:none;cursor:pointer;box-shadow:0 6px 16px rgba(58,82,191,.14)}
.rp-history-entry:hover,.rp-history-entry[aria-expanded="true"]{border-color:var(--blue);box-shadow:0 8px 20px rgba(58,82,191,.22)}
.rp-history-entry b{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 6px;border-radius:999px;background:#3b7dec;color:#fff;font-size:12px}
:global(body[data-theme="dark"] .rp-history-entry){background:#1c3355;color:#cfe0ff}
@media (max-width:1100px){.rp-history-entry{position:static;margin-top:8px;transform:none}}
.rp-preview{display:grid;grid-template-columns:minmax(0,1fr) 300px;grid-template-rows:auto auto minmax(0,1fr) minmax(0,1fr);grid-template-areas:"h h" "c c" "t r" "t w";gap:8px;height:100%;min-height:0}
.rp-locked-title{grid-column:1/-1;margin:0;color:var(--muted);font-size:13px;font-weight:700}
:global(body[data-theme="dark"] .rp-locked){background:#14263f!important}
.rp-start-title{margin:0;color:var(--text-strong);font-size:21px}
.rp-next-hint{margin:0;color:var(--muted);font-size:13px}
/* 主按鈕與智慧選股一致 */
body[data-page="research"] .page-host .research-empty-form button.primary-button{background:linear-gradient(105deg,#347ff6,#7865ee)!important;box-shadow:0 8px 20px rgba(58,82,191,.24)}
.rp-bottom.is-preview{display:flex;flex-direction:column}
.rp-bottom.is-preview .rp-preview{flex:1 1 auto;height:auto}
.rp-strip{flex:none;display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:8px;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}
.rp-strip button{padding:0;border:0;background:transparent;color:var(--blue);font:inherit;font-weight:800;cursor:pointer}
.rp-strip button:hover{text-decoration:underline}
.rp-pv-head{grid-area:h;display:flex;align-items:center;gap:10px}
.rp-pv-tag{padding:2px 10px;border-radius:999px;background:color-mix(in srgb,var(--muted) 14%,transparent);color:var(--muted);font-size:12px;font-weight:700}
.rp-pv-quality{display:inline-flex;align-items:center;gap:6px;color:var(--muted);font-size:12px}
.rp-pv-quality i{display:block;width:64px;height:8px;border-radius:6px;background:color-mix(in srgb,var(--blue) 11%,transparent)}
.rp-pv-head small{margin-left:auto}
.rp-pv-table{flex:1;min-height:0;display:flex;flex-direction:column;padding:0 14px;border:1px solid var(--line);border-radius:12px}
.rp-pv-row.is-head{padding-top:8px}
.rp-pv-row.is-body{flex:1;min-height:30px}
.rp-pv-head h2{margin:0;color:var(--text-strong);font-size:17px}
.rp-pv-head small{color:var(--muted);font-size:13px}
.rp-pv-box{display:flex;flex-direction:column;gap:9px;min-height:0;padding:10px 14px;border:1px dashed var(--line-strong);border-radius:13px;overflow:hidden}
.rp-pv-box h3{margin:0;color:var(--muted);font-size:13px;font-weight:700}
.rp-pv-box i{display:block;height:9px;border-radius:6px;background:color-mix(in srgb,var(--blue) 11%,transparent)}
.rp-pv-box i.short{width:58%}
.rp-pv-c{grid-area:c}.rp-pv-t{grid-area:t}.rp-pv-r{grid-area:r}.rp-pv-w{grid-area:w}
.rp-pv-row{display:grid;grid-template-columns:1.3fr repeat(4,minmax(0,1fr));align-items:center;gap:18px}
.rp-pv-row.is-head{padding-bottom:6px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;font-weight:700}
@media (max-width:900px){.rp-preview{grid-template-columns:1fr;grid-template-rows:none;grid-template-areas:"h" "c" "t" "r" "w";height:auto}}
.rp-live{height:100%;display:flex;flex-direction:column;gap:6px;min-height:150px}
.rp-live h3{margin:0;color:var(--text-strong);font-size:14px}
.rp-live p{margin:0;color:var(--muted);font-size:13px}
.rp-live ol{flex:1;min-height:0;margin:0;padding:0 4px 0 0;list-style:none;overflow-y:auto;display:flex;flex-direction:column;gap:2px}
.rp-live li{flex:none;display:grid;grid-template-columns:20px 118px minmax(0,1fr);align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid var(--line);font-size:13px}
.rp-live li:last-child{border-bottom:0}
.rp-live-mark{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue);font-weight:800;font-size:12px}
.rp-live .is-completed .rp-live-mark{background:color-mix(in srgb,var(--green) 16%,transparent);color:var(--green)}
.rp-live .is-failed .rp-live-mark{background:color-mix(in srgb,var(--red) 14%,transparent);color:var(--red)}
.rp-live li b{overflow:hidden;color:var(--muted);font-size:12px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}
.rp-live-text{overflow:hidden;color:var(--text);text-overflow:ellipsis;white-space:nowrap}
.rp-live-text strong{color:var(--text-strong);font-weight:700}
.research-current-strip.is-complete strong{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
</style>
