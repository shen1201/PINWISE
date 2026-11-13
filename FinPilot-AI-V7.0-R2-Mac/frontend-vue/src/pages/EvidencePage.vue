<script setup>
import { track } from '@/stores/footprint.js'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppModal from '@/components/AppModal.vue'
import R2SectionTabs from '@/components/v7/R2SectionTabs.vue'
import { useSectionTabs } from '@/composables/r2Layout.js'
import AppIcon from '@/components/AppIcon.vue'
import InfoTip from '@/components/InfoTip.vue'
import { visibleTasks, formatDate } from '@/stores/research.js'
import { sourceHealth, refreshSourceHealth, HEALTH_LABELS } from '@/stores/sourceHealth.js'
import { DATA_SOURCES, LICENSE_NOTICE, LICENSE_REASONS, PRIVACY_NOTICE, DATA_GAPS } from '@/data/dataSources.js'

// 資料與證據中心（對應舊版 evidencePage 與 evidenceTaskDetailHtml）。
const router = useRouter()
const modal = ref('') // all | task
const selected = ref(null)
const panel = ref('sources') // sources | research

onMounted(refreshSourceHealth)

const VISIBLE = 4
const tasks = computed(() => visibleTasks.value)
// 表格 1～3 筆時才放得下來源明細；最後一格留給「查看完整依據」。
const RECORD_SLOTS = { 1: 11, 2: 7, 3: 3 }
const latestRecords = computed(() => (tasks.value[0]?.sourceRecords || []).slice(0, RECORD_SLOTS[tasks.value.length] || 0))
const EMPTY_POINTS = [['來源與時間', '資料出自哪裡、何時更新'], ['對應研究', '哪一項內容支持哪一個判斷'], ['核對狀態', '區分預計查核與已取得資料']]

// 資料來源依用途排序；後端新增來源時排在最後。
const SOURCE_ORDER = ['TWSE', 'TPEx', 'FinMind', 'MOPS', '官方基本面', '公司法說會', '官方新聞', 'Gemini', 'Shioaji']
const orderedSources = computed(() => {
  const rank = (row) => { const i = SOURCE_ORDER.indexOf(row.source); return i < 0 ? 99 : i }
  return [...sourceHealth.rows].sort((a, b) => rank(a) - rank(b))
})
// 交易所開放資料隔天清晨才更新，幾天內的落差屬正常（含週末與連假）；放太久仍標為過期。
const DAILY_SOURCES = ['TWSE', 'TPEx']
const NORMAL_LAG_DAYS = 5
function isNormalLag(row) {
  if (row.status !== 'stale' || !DAILY_SOURCES.includes(row.source) || !row.latest_data_at) return false
  const days = (Date.now() - new Date(row.latest_data_at).getTime()) / 86400000
  return days >= 0 && days <= NORMAL_LAG_DAYS
}
function stateOf(row) {
  if (isNormalLag(row)) return { key: 'daily', label: '隔日更新' }
  const key = row.status === 'healthy' ? 'ok' : ['stale', 'degraded'].includes(row.status) ? 'warn' : row.status === 'error' ? 'bad' : 'idle'
  return { key, label: HEALTH_LABELS[row.status] || row.status }
}
// 圓餅圖：相同顯示文字合併成一塊，順序固定，顏色跟著狀態走。
const STATE_RANK = { ok: 0, daily: 1, warn: 2, bad: 3, idle: 4 }
const DONUT_R = 46
const DONUT_C = 2 * Math.PI * DONUT_R
const totalSources = computed(() => sourceHealth.rows.length)
const usable = computed(() => sourceHealth.rows.filter((row) => ['ok', 'daily'].includes(stateOf(row).key)).length)
const statusParts = computed(() => {
  const groups = new Map()
  for (const row of sourceHealth.rows) {
    const state = stateOf(row)
    if (!groups.has(state.label)) groups.set(state.label, { ...state, n: 0 })
    groups.get(state.label).n += 1
  }
  const total = totalSources.value
  let offset = 0
  const list = [...groups.values()].sort((a, b) => STATE_RANK[a.key] - STATE_RANK[b.key])
  const gap = list.length > 1 ? 2 : 0
  return list.map((part) => {
    const length = total ? (part.n / total) * DONUT_C : 0
    const item = { ...part, key: `is-${part.key}`, pct: total ? Math.round((part.n / total) * 100) : 0, dash: `${Math.max(0, length - gap)} ${DONUT_C}`, offset: -offset, color: 'currentColor' }
    offset += length
    return item
  })
})
const coverage = (task) => {
  const { total, verified: ok } = stats(task)
  return total ? Math.round((ok / total) * 100) : 0
}
// 有時間的顯示到分鐘，只有日期的維持原樣。
function sourceTime(value) {
  const text = String(value)
  if (!text.includes('T')) return text
  const d = new Date(text)
  if (!Number.isFinite(d.getTime())) return text
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const urlSafe = (r) => /^https?:\/\//i.test(r?.url || '') && !/\.invalid(?:[/:]|$)/i.test(r.url)
const verified = (r) => !r?.missing && ['real', 'cache'].includes(r?.data_status) && !/^gemini$/i.test(r.provider || r.source || '') && urlSafe(r)
const STATUS = { real: '真實取得', cache: '快取', fixture: '隔離資料', missing: '缺失', unverified: '尚未驗證' }
const recordStatus = (r) => (r.missing ? '缺失' : STATUS[r.data_status] || '尚未驗證')
const recordMeta = (r) =>
  [r.provider, r.subjects?.join('、'), [r.period_start, r.period_end].filter(Boolean).join(' ～ '), r.latest_data_at ? `資料日 ${r.latest_data_at}` : '', r.fetched_at ? `取得 ${formatDate(r.fetched_at)}` : '', r.stale ? '資料較舊' : '']
    .filter(Boolean)
    .join(' · ')

const stats = (task) => {
  const sources = task.sourceRecords || []
  return { total: sources.length, verified: sources.filter(verified).length, missing: sources.filter((s) => s.missing).length }
}

function openTask(task) {
  track('source_open', task.id)
  selected.value = task
  modal.value = 'task'
}

// 窄螢幕時分成兩個區塊切換（對應舊版 applyR2Layout）。
const { current: tab, hidden: tabHidden } = useSectionTabs('evidence', 2)
</script>

<template>
  <div class="page with-top-space evidence-center-page">
    <div class="workspace evidence-center-workspace">
      <section class="page-banner">
        <h1>資料與證據中心</h1>
        <p>確認資料是否連線、最後更新時間，以及每份研究的依據能否追溯。</p>
      </section>
      <R2SectionTabs v-model="tab" :labels="['資料來源', '研究依據']" />
      <div class="ev-grid">
        <!-- ① 來源總覽：整體是否健康 -->
        <section class="card ev-card ev-overview" :hidden="tabHidden(0)">
          <header class="ev-head">
            <h2>來源總覽<InfoTip text="狀態來自後端記錄的健康檢查；來源正常不等於已取得個別標的的行情，日資料也不是即時價格。可到「設定 → 資料連線」逐項重新檢查。" label="來源總覽" /></h2>
          </header>
          <div v-if="sourceHealth.loading && !sourceHealth.rows.length" class="ev-note">正在讀取資料來源狀態…</div>
          <div v-else-if="sourceHealth.error" class="ev-note">無法取得後端狀態：{{ sourceHealth.error }}</div>
          <div v-else class="ev-dist">
            <svg viewBox="0 0 120 120" class="ev-donut" role="img" :aria-label="`資料來源狀態：${statusParts.map((p) => `${p.label} ${p.n} 個`).join('、')}`">
              <circle cx="60" cy="60" :r="DONUT_R" fill="none" stroke="var(--line)" stroke-width="14" />
              <circle
                v-for="p in statusParts"
                :key="p.key"
                cx="60" cy="60" :r="DONUT_R" fill="none" :stroke="p.color" stroke-width="14"
                :stroke-dasharray="p.dash" :stroke-dashoffset="p.offset" transform="rotate(-90 60 60)"
                class="ev-seg" :class="p.key"
              ><title>{{ p.label }}：{{ p.n }} 個，{{ p.pct }}%</title></circle>
              <text x="60" y="58" text-anchor="middle" class="ev-donut-num">{{ usable }}/{{ totalSources }}</text>
              <text x="60" y="76" text-anchor="middle" class="ev-donut-unit">可用</text>
            </svg>
            <ul class="ev-legend">
              <li v-for="p in statusParts" :key="p.key"><i :class="p.key"></i><span>{{ p.label }}</span><b>{{ p.n }}</b><small>{{ p.pct }}%</small></li>
            </ul>
          </div>
        </section>

        <!-- ② 各來源狀態 -->
        <section class="card ev-card ev-sources" :hidden="tabHidden(0)">
          <header class="ev-head"><h2>各來源狀態</h2></header>
          <div v-if="sourceHealth.rows.length" class="ev-tiles">
            <article v-for="row in orderedSources" :key="row.source" class="ev-source">
              <div><strong>{{ row.source }}</strong><small>{{ row.latest_data_at ? sourceTime(row.latest_data_at) : '未提供資料日期' }}</small></div>
              <b :class="`is-${stateOf(row).key}`">{{ stateOf(row).label }}</b>
            </article>
          </div>
          <div v-else class="ev-note">{{ sourceHealth.loading ? '正在讀取…' : '目前沒有來源資料' }}</div>
        </section>

        <!-- ③ 研究依據：每份研究能否追溯 -->
        <section class="card ev-card ev-research" :hidden="tabHidden(1)">
          <header class="ev-head">
            <h2 v-if="panel === 'sources'">資料來源與授權<InfoTip text="這裡說明每種資料從哪裡來、用在哪些頁面。連線狀態與最新資料日請看上方的「各來源狀態」。" label="資料來源與授權" /></h2>
            <h2 v-else>研究依據<InfoTip text="研究完成與來源驗證是兩件事。尚未連線或缺漏的項目，不會當成已驗證證據。" label="研究依據" /></h2>
            <div class="ev-head-side">
              <template v-if="panel === 'research'">
                <button v-if="tasks.length > VISIBLE" class="outline-button small" type="button" @click="modal = 'all'">查看全部（{{ tasks.length }}）</button>
                <span v-else class="ev-total">{{ tasks.length }} 份研究</span>
              </template>
              <div class="ev-switch" role="group" aria-label="切換內容">
                <button v-for="[key, label] in [['sources', '資料來源'], ['research', '研究依據']]" :key="key" type="button" :class="{ active: panel === key }" :aria-pressed="String(panel === key)" @click="panel = key">{{ label }}</button>
              </div>
            </div>
          </header>
          <div v-if="panel === 'sources'" class="ev-src">
            <div class="ev-src-table" role="table" aria-label="資料來源說明">
              <div class="ev-src-row is-head" role="row"><span role="columnheader">資料種類</span><span role="columnheader">來源</span><span role="columnheader">更新頻率</span><span role="columnheader">用在</span></div>
              <div v-for="row in DATA_SOURCES" :key="row.kind" class="ev-src-row" role="row">
                <strong role="cell"><i aria-hidden="true"><AppIcon :name="row.icon" :size="14" /></i>{{ row.kind }}</strong>
                <span role="cell" class="ev-src-from"><template v-for="(part, i) in row.source" :key="i"><a v-if="Array.isArray(part)" :href="part[1]" target="_blank" rel="noopener noreferrer">{{ part[0] }}</a><template v-else>{{ part }}</template></template></span>
                <span role="cell">{{ row.cycle }}</span>
                <span role="cell">{{ row.usedIn }}</span>
              </div>
            </div>
            <aside class="ev-legal">
              <h3><InfoTip :text="LICENSE_REASONS" label="各來源授權疑慮">！</InfoTip>正式上線前要處理</h3>
              <p>{{ LICENSE_NOTICE }}</p>
              <p class="ev-legal-strong">{{ PRIVACY_NOTICE }}<small>滑鼠移到上方「！」可以看各來源的原因。</small></p>
              <dl><dt>目前沒有</dt><dd>{{ DATA_GAPS }}</dd></dl>
            </aside>
          </div>
          <template v-else>
          <div v-if="tasks.length" class="ev-table-wrap">
            <table class="ev-table">
              <thead><tr><th>研究題目</th><th>更新時間</th><th class="num">來源</th><th class="num">已驗證</th><th class="num">缺漏</th><th>覆蓋率</th><th class="act"><span class="sr-only">操作</span></th></tr></thead>
              <tbody>
                <tr v-for="task in tasks.slice(0, VISIBLE)" :key="task.id">
                  <td class="ev-q" :title="task.query">{{ task.query }}</td>
                  <td>{{ formatDate(task.updatedAt) }}</td>
                  <td class="num">{{ stats(task).total }}</td>
                  <td class="num">{{ stats(task).verified }}</td>
                  <td class="num" :class="{ 'is-miss': stats(task).missing }">{{ stats(task).missing }}</td>
                  <td><span class="ev-meter" role="img" :aria-label="`覆蓋率 ${coverage(task)}%`"><i :style="{ width: `${coverage(task)}%` }"></i></span><b class="ev-pct">{{ coverage(task) }}%</b></td>
                  <td class="act"><button class="card-link" type="button" @click="openTask(task)">查看依據 →</button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- 研究筆數少時，下方列出最新一份研究的來源明細 -->
          <section v-if="latestRecords.length" class="ev-records">
            <h3>最新研究的來源明細<small :title="tasks[0].query">{{ tasks[0].query }}</small></h3>
            <div class="ev-record-grid">
              <article v-for="(r, i) in latestRecords" :key="i">
                <div><strong :title="r.source || r.title">{{ r.source || r.title || '資料來源' }}</strong><small>{{ r.missing ? '本期間無資料' : r.latest_data_at ? `資料日 ${r.latest_data_at}` : '未提供資料日期' }}</small></div>
                <b :class="r.missing ? 'is-miss' : 'is-ok'">{{ recordStatus(r) }}</b>
              </article>
              <button type="button" class="ev-record-more" @click="openTask(tasks[0])">查看完整依據 →<small>{{ stats(tasks[0]).total }} 個來源項目</small></button>
            </div>
          </section>
          <div v-if="!tasks.length" class="ev-empty">
            <div class="ev-empty-top">
              <span class="ev-symbol"><AppIcon name="database" :size="24" /></span>
              <div><h3>讓每個研究方向都有依據</h3><p>完成第一份研究後，可以在這裡回查資料來源及待核對內容。</p></div>
              <button class="primary-button" type="button" @click="router.push('/research')">開始第一份研究 →</button>
            </div>
            <ul>
              <li v-for="[title, desc] in EMPTY_POINTS" :key="title"><strong>{{ title }}</strong><small>{{ desc }}</small></li>
            </ul>
          </div>
          </template>
        </section>
      </div>
    </div>
  </div>

  <AppModal :open="modal === 'all'" :title="`全部研究依據（${tasks.length}）`" modal-class="evidence-list-modal" @close="modal = ''">
    <div class="evidence-list-modal-body evidence-research-list">
      <article v-for="task in tasks" :key="task.id">
        <div class="evidence-research-main">
          <strong>{{ task.query }}</strong>
          <small>{{ stats(task).total }} 個來源項目 · 更新 {{ formatDate(task.updatedAt) }}</small>
        </div>
        <div class="evidence-research-status"><span>已驗證 {{ stats(task).verified }}</span><span>缺漏 {{ stats(task).missing }}</span></div>
        <button class="outline-button" type="button" @click="openTask(task)">查看完整依據</button>
      </article>
    </div>
  </AppModal>

  <AppModal :open="modal === 'task'" title="研究依據與資料狀態" modal-class="evidence-detail-modal" @close="modal = ''">
    <div v-if="selected" class="evidence-detail">
      <header>
        <span class="eyebrow">{{ selected.jobId || selected.id }}</span>
        <h3>{{ selected.query }}</h3>
        <p>{{ selected.summary || '研究尚未完成，沒有摘要。' }}</p>
      </header>
      <div class="notice">
        <strong>{{ selected.dataMode === 'fixture' ? '隔離測試結果' : selected.verificationStatus === 'sourced' ? '已取得預定證據，仍有能力限制' : '有限度分析，資料尚不完整' }}</strong>
        <span>完成研究流程不等於全部結論已驗證；請對照來源與資料限制。</span>
      </div>
      <div class="evidence-detail-stats">
        <span><small>來源項目</small><strong>{{ stats(selected).total }}</strong></span>
        <span><small>已驗證</small><strong>{{ stats(selected).verified }}</strong></span>
        <span><small>缺漏</small><strong>{{ stats(selected).missing }}</strong></span>
        <span><small>最後更新</small><strong>{{ formatDate(selected.updatedAt) }}</strong></span>
      </div>
      <section>
        <h4>來源、期間與缺漏</h4>
        <div class="evidence-detail-list">
          <article v-for="(source, index) in selected.sourceRecords || []" :key="index">
            <b>{{ index + 1 }}</b>
            <div>
              <strong>{{ source.source || source.title || '資料來源' }}</strong>
              <small>{{ recordMeta(source) || '日期未提供' }}</small>
              <a v-if="urlSafe(source)" :href="source.url" target="_blank" rel="noopener noreferrer">原始來源</a>
            </div>
            <span>{{ recordStatus(source) }}</span>
          </article>
          <div v-if="!selected.sourceRecords?.length" class="empty-state">尚未建立來源清單。</div>
        </div>
      </section>
      <div class="notice">
        <strong>模型與提示</strong>
        <span>{{ selected.backendModel || '未保存模型' }} · 耗時 {{ selected.backendDurationMs == null ? '未提供' : `${selected.backendDurationMs} ms` }}</span>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
/* 彈窗只留一條捲軸：外框不捲，標題固定，內容區自己捲動 */
:global(body .modal.evidence-detail-modal),:global(body .modal.evidence-list-modal){display:flex!important;flex-direction:column;overflow:hidden!important}
:global(body .modal.evidence-detail-modal > .modal-header),:global(body .modal.evidence-list-modal > .modal-header){flex:none}
:global(body .modal.evidence-detail-modal > .modal-body),:global(body .modal.evidence-list-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none!important;overflow-y:auto!important}
:global(body .modal.evidence-detail-modal .evidence-detail),:global(body .modal.evidence-detail-modal .evidence-detail-list),:global(body .modal.evidence-list-modal .evidence-list-modal-body){max-height:none!important;overflow:visible!important}
.ev-grid{--ev-ok:#2A78D6;--ev-daily:#D4589B;--ev-warn:#E08A1E;--ev-bad:#D9483B;--ev-idle:#AEB6C2;flex:1;min-height:0;display:grid;grid-template-columns:270px minmax(0,1fr);grid-template-rows:minmax(0,5fr) minmax(0,7fr);grid-template-areas:"a b" "c c";gap:12px}
:global(body[data-theme="dark"] .ev-grid){--ev-ok:#3F86E0;--ev-daily:#C95E9F;--ev-warn:#C98A2C;--ev-idle:#6B7690}
.ev-overview{grid-area:a}.ev-sources{grid-area:b}.ev-research{grid-area:c}
.ev-card{display:flex;flex-direction:column;min-height:0;margin:0;padding:10px 16px 12px;overflow:hidden}
.ev-head{flex:none;display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:36px;padding-bottom:6px;border-bottom:1.5px solid #E2C3B5}
.ev-head h2{display:flex;align-items:center;gap:4px;margin:0;color:var(--text-strong);font-size:17px}
.ev-total{flex:none;color:var(--muted);font-size:13px;font-weight:700}
.ev-head-side{flex:none;display:flex;align-items:center;gap:10px}
.ev-switch{display:flex;gap:2px;padding:2px;border:1px solid var(--line);border-radius:999px}
.ev-switch button{padding:3px 12px;border:0;border-radius:999px;background:transparent;color:var(--muted);font-size:13px;font-weight:700;cursor:pointer}
.ev-switch button:hover{color:var(--text-strong)}
.ev-switch button.active{background:var(--blue);color:#fff}
.ev-src{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 262px;gap:14px;padding-top:6px}
.ev-src-table{min-height:0;display:grid;grid-template-rows:auto repeat(6,minmax(0,1fr)) minmax(0,1.45fr) minmax(0,1fr)}
.ev-src-row{display:grid;grid-template-columns:152px minmax(0,1fr) 92px 176px;align-items:center;gap:10px;min-height:0;border-top:1px solid var(--line);color:var(--text);font-size:13px}
.ev-src-row.is-head{padding-bottom:4px;border-top:0;color:var(--muted);font-size:12px;font-weight:700}
.ev-src-row strong{display:flex;align-items:center;gap:7px;min-width:0;color:var(--text-strong);font-size:13px;white-space:nowrap}
.ev-src-row strong i{flex:none;display:grid;place-items:center;width:22px;height:22px;border-radius:7px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue);font-style:normal}
.ev-src-from{line-height:1.3;white-space:pre-line}
.ev-src-from a{color:var(--blue);font-weight:600}
.ev-src-from a:hover{text-decoration:underline}
.ev-legal{display:flex;flex-direction:column;gap:7px;min-height:0;padding:12px 14px;border:1.5px solid color-mix(in srgb,#E08A1E 34%,transparent);border-radius:14px;background:color-mix(in srgb,#E08A1E 8%,var(--pw-inner));overflow:hidden}
.ev-legal h3{display:flex;align-items:center;gap:7px;margin:0;color:var(--text-strong);font-size:14px}
.ev-legal h3 :deep(.info-tip){flex:none;width:20px;height:20px;margin:0;background:#C76E12!important;color:#fff;font-size:12px;font-weight:800}
.ev-legal p{margin:0;color:var(--text);font-size:13px;line-height:1.55}
.ev-legal-strong{font-weight:700}
.ev-legal-strong small{display:block;color:var(--muted);font-size:12px;font-weight:500}
.ev-legal dl{margin:auto 0 0;padding-top:7px;border-top:1px dashed color-mix(in srgb,#E08A1E 38%,transparent)}
.ev-legal dt{color:var(--text-strong);font-size:12px;font-weight:700}
.ev-legal dd{margin:1px 0 0;color:var(--muted);font-size:12px;line-height:1.45}
:global(body[data-theme="dark"] .ev-switch button.active){color:#0d2340}
.ev-note{flex:1;display:grid;place-items:center;color:var(--muted);font-size:14px;text-align:center}
.ev-dist{flex:1;min-height:0;display:grid;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:10px}
.ev-donut{width:104px;height:104px}
.ev-seg.is-ok,.ev-legend i.is-ok{color:var(--ev-ok);background:var(--ev-ok)}
.ev-seg.is-daily,.ev-legend i.is-daily{color:var(--ev-daily);background:var(--ev-daily)}
.ev-seg.is-warn,.ev-legend i.is-warn{color:var(--ev-warn);background:var(--ev-warn)}
.ev-seg.is-bad,.ev-legend i.is-bad{color:var(--ev-bad);background:var(--ev-bad)}
.ev-seg.is-idle,.ev-legend i.is-idle{color:var(--ev-idle);background:var(--ev-idle)}
.ev-donut-num{fill:var(--text-strong);font-size:22px;font-weight:800}
.ev-donut-unit{fill:var(--muted);font-size:12px}
.ev-legend{margin:0;padding:0;list-style:none;display:grid;gap:5px}
.ev-legend li{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:6px;font-size:13px;color:var(--text)}
.ev-legend i{width:10px;height:10px;border-radius:3px}
.ev-legend span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ev-legend b{color:var(--text-strong);font-variant-numeric:tabular-nums}
.ev-legend small{display:none}
.ev-tiles{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:minmax(0,1fr);gap:6px;padding-top:8px}
.ev-source{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:0;min-width:0;padding:0 10px;border:1.5px solid #E2C3B5;border-radius:10px;background:var(--pw-inner)}
.ev-source div{display:grid;min-width:0}
.ev-source strong{overflow:hidden;color:var(--text-strong);font-size:14px;line-height:1.25;text-overflow:ellipsis;white-space:nowrap}
.ev-source small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.ev-source b{flex:none;padding:2px 8px;border-radius:999px;font-size:12px;background:color-mix(in srgb,var(--muted) 14%,transparent);color:var(--muted)}
.ev-source b.is-ok{background:color-mix(in srgb,#2A78D6 12%,transparent);color:#1F62B5}
.ev-source b.is-daily{background:color-mix(in srgb,#D4589B 13%,transparent);color:#A83374}
.ev-source b.is-warn{background:color-mix(in srgb,#E08A1E 16%,transparent);color:#A85F0C}
.ev-source b.is-bad{background:color-mix(in srgb,#D9483B 12%,transparent);color:#B5352A}
:global(body[data-theme="dark"] .ev-source b.is-ok){background:rgba(91,155,234,.2);color:#BFDBFF}
:global(body[data-theme="dark"] .ev-source b.is-daily){background:rgba(224,123,181,.2);color:#F7C6E2}
:global(body[data-theme="dark"] .ev-source b.is-warn){background:rgba(237,162,63,.2);color:#FFD9A0}
:global(body[data-theme="dark"] .ev-source b.is-bad){background:rgba(217,72,59,.24);color:#FFC2BB}
:global(body[data-theme="dark"] .ev-table td.is-miss){color:#FFD9A0}
.ev-table-wrap{flex:none;padding-top:4px}
.ev-records{flex:1;min-height:0;display:flex;flex-direction:column;gap:6px;padding-top:8px;border-top:1px solid var(--line)}
.ev-records h3{flex:none;display:flex;align-items:baseline;gap:8px;min-width:0;margin:0;color:var(--text-strong);font-size:14px}
.ev-records h3 small{overflow:hidden;color:var(--muted);font-size:12px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.ev-record-grid{flex:1;min-height:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));grid-auto-rows:minmax(0,1fr);gap:6px}
.ev-record-grid article{display:flex;align-items:center;justify-content:space-between;gap:6px;min-width:0;min-height:0;padding:0 10px;border:1.5px solid #E2C3B5;border-radius:10px;background:var(--pw-inner)}
.ev-record-grid article div{display:grid;min-width:0}
.ev-record-grid strong{overflow:hidden;color:var(--text-strong);font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.ev-record-grid small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.ev-record-grid b{flex:none;font-size:12px}
.ev-record-grid b.is-ok{color:#1F62B5}
.ev-record-grid b.is-miss{color:#A85F0C}
.ev-record-more{display:grid;place-content:center;gap:2px;min-width:0;min-height:0;border:1.5px dashed #D8B7A6;border-radius:10px;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer}
.ev-record-more:hover,.ev-record-more:focus-visible{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 7%,transparent)}
:global(body[data-theme="dark"][data-page] .page-host .page .ev-record-grid article){background:#374A6E}
:global(body[data-theme="dark"] .ev-record-grid b.is-ok){color:#BFDBFF}
:global(body[data-theme="dark"] .ev-record-grid b.is-miss){color:#FFD9A0}
.ev-table{width:100%;border-collapse:collapse;table-layout:fixed!important;font-size:14px}
.ev-table th{padding:6px 8px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;font-weight:700;text-align:left}
.ev-table th:nth-child(2){width:100px}.ev-table th:nth-child(3),.ev-table th:nth-child(4),.ev-table th:nth-child(5){width:60px}.ev-table th:nth-child(6){width:150px}.ev-table th:nth-child(7){width:100px}
.ev-table td{height:46px;padding:0 8px;border-bottom:1px solid var(--line);color:var(--text);white-space:nowrap}
.ev-table tr:last-child td{border-bottom:0}
.ev-table .ev-q{overflow:hidden;color:var(--text-strong);font-weight:700;text-overflow:ellipsis}
.ev-table .num{text-align:right;font-variant-numeric:tabular-nums}
.ev-table .act{text-align:right}
.ev-table td.is-miss:not(.x){color:#A85F0C;font-weight:700}
.ev-table .card-link{min-height:0;padding:0;font-size:13px}
.ev-meter{display:inline-block;width:84px;height:7px;border-radius:4px;background:var(--line);vertical-align:middle;overflow:hidden}
.ev-meter i{display:block;height:100%;border-radius:0 4px 4px 0;background:var(--ev-ok)}
.ev-pct{margin-left:8px;color:var(--text-strong);font-size:13px;font-variant-numeric:tabular-nums}
.ev-empty{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:16px}
.ev-empty-top{display:flex;align-items:center;gap:14px}
.ev-empty-top div{flex:1;min-width:0}
.ev-symbol{flex:none;display:grid;place-items:center;width:48px;height:48px;border-radius:14px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue)}
.ev-empty h3{margin:0;color:var(--text-strong);font-size:19px}
.ev-empty p{margin:3px 0 0;color:var(--muted);font-size:14px}
.ev-empty ul{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0;padding:0;list-style:none}
.ev-empty li{display:grid;gap:3px;padding:14px;border:1.5px solid #E2C3B5;border-radius:12px;background:var(--pw-inner)}
.ev-empty li strong{color:var(--text-strong);font-size:14px}
.ev-empty li small{color:var(--muted);font-size:12px;line-height:1.5}
@media (max-width:900px){
  .ev-grid{grid-template-columns:1fr;grid-template-rows:none;grid-template-areas:"a" "b" "c";overflow:auto}
  .ev-tiles{grid-template-columns:1fr 1fr;grid-auto-rows:64px}
  .ev-table th:nth-child(2),.ev-table td:nth-child(2),.ev-table th:nth-child(3),.ev-table td:nth-child(3),.ev-table th:nth-child(5),.ev-table td:nth-child(5){display:none}
  .ev-table th:nth-child(6){width:96px}.ev-meter{display:none}
  .ev-record-grid{grid-template-columns:1fr 1fr;grid-auto-rows:56px}
  .ev-empty-top{flex-wrap:wrap}.ev-empty ul{grid-template-columns:1fr}
  .ev-src{grid-template-columns:1fr}.ev-src-table{grid-template-rows:none;grid-auto-rows:minmax(48px,auto)}
  .ev-src-row{grid-template-columns:minmax(0,1fr)}.ev-src-row > :nth-child(3),.ev-src-row > :nth-child(4){display:none}.ev-src-row{padding:7px 0}.ev-src-row.is-head{display:none}
  .ev-head-side{flex-wrap:wrap;justify-content:flex-end}
}
</style>
