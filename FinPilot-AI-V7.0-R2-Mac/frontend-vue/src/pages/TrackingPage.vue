<script setup>
import GgOutline from '@/components/GgOutline.vue'
import { track } from '@/stores/footprint.js'
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import AppModal from '@/components/AppModal.vue'
import R2SectionTabs from '@/components/v7/R2SectionTabs.vue'
import { useSectionTabs } from '@/composables/r2Layout.js'
import { workspace, untrack, watchNoteText } from '@/stores/workspace.js'
import { researchSymbol } from '@/stores/research.js'
import { overlays, openStockDetail } from '@/stores/overlays.js'
import { snapshots, loadSnapshots } from '@/stores/snapshots.js'
import { ui } from '@/stores/ui.js'
import { assistant, current as currentConversation, newConversation } from '@/stores/assistant.js'
import { api } from '@/api/client.js'

// 公告與事件：追蹤股票的官方公告、法說會與研究觀察條件（對應舊版 trackingPage）。
// 清單與「我的追蹤」是同一份；在這裡新增或移除，兩頁同步。
const router = useRouter()
const modal = ref('') // reeval | all
const reevalTarget = ref(null)

watch(() => [...workspace.tracked], (codes) => loadSnapshots(codes), { immediate: true })

// 右欄：證交所官方 RSS 的最新消息，相同標題只留最新一則。
const NEWS_LIMIT = 7
const news = ref([])
const newsState = ref('loading')
onMounted(async () => {
  try {
    const items = await api.twseNews(20)
    const seen = new Set()
    news.value = (Array.isArray(items) ? items : items.items || [])
      .filter((n) => !seen.has(n.title) && seen.add(n.title))
      .slice(0, NEWS_LIMIT)
    newsState.value = 'done'
  } catch {
    newsState.value = 'failed'
  }
})
const newsTime = (iso) => (iso ? new Date(iso).toLocaleString('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '')

const CELL_LIMIT = 4
const has = (v) => Number.isFinite(v)
const fmtNum = (v) => (has(v) ? Number(v).toLocaleString('zh-TW') : '—')
const fmtPct = (v, sign = true) => (has(v) ? `${sign && v > 0 ? '+' : ''}${Math.round(v * 100) / 100}%` : '—')
const tone = (v) => (!has(v) || v === 0 ? '' : v > 0 ? 'price-up' : 'price-down')
function quoteFacts(code) {
  const s = snapshots[code] || {}
  const previous = has(s.close) && has(s.change) ? s.close - s.change : null
  const latest = (s.events || []).map((e) => e.published_at || e.event_date).filter(Boolean).sort().at(-1)
  return {
    close: s.close, tradeDate: s.tradeDate || '',
    changePct: previous ? (s.change / previous) * 100 : null,
    ret: s.metrics?.period_return_pct, vol: s.metrics?.annualized_volatility_pct,
    latestEvent: latest ? String(latest).slice(0, 10) : '',
  }
}

const list = computed(() =>
  workspace.tracked.map((code) => ({
    code,
    name: snapshots[code]?.name || '',
    market: snapshots[code]?.market || '市場待確認',
    ...quoteFacts(code),
    direction: watchNoteText(code) || '尚未有研究方向，可按「重新評估」建立研究',
  })),
)

const shown = computed(() => list.value.slice(0, CELL_LIMIT))

// 追蹤標的的官方公告（對應舊版 visibleMonitorEvents），新的在前，最多 20 筆。
const events = computed(() =>
  workspace.tracked
    .flatMap((code) =>
      (snapshots[code]?.events || []).map((e) => ({
        code,
        name: snapshots[code]?.name || '',
        // 官方標題常夾著換行，整理成一行再顯示或帶進助手。
        label: String(e.title || '重大訊息').replace(/\s*\n\s*/g, '').replace(/\s+/g, ' ').trim(),
        date: e.published_at || e.event_date || snapshots[code]?.asOf || '日期未提供',
        url: /^https?:\/\//.test(e.metadata?.source_url || '') ? e.metadata.source_url : null,
      })),
    )
    .sort((a, b) => String(b.date).localeCompare(String(a.date)))
    .slice(0, 20),
)

// 有時間的顯示到分鐘，只有日期的維持原樣。
function eventTime(value) {
  const date = new Date(value)
  if (!String(value).includes('T') || Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}
const EVENT_KINDS = [[/法人說明會|法說|機構投資人/, '法說會'], [/營收/, '營收'], [/股利|除權|除息/, '股利'], [/董事|監察人|經理人/, '人事'], [/處分|取得|併購|投資/, '資產']]
const kindOf = (title) => EVENT_KINDS.find(([pattern]) => pattern.test(title))?.[1] || '公告'

// 公告少時，補上每檔的狀況和閱讀方式，不讓一則公告懸在空白中間。
const TIP_LIMIT = 2
const COVERAGE_ROWS = 6

// 公告清單不捲動：依卡片高度算出放得下幾則，多的收進「查看全部」視窗。
const evMain = ref(null)
const evSpace = ref(0)
let evObserver = null
// 每則公告標題收成一行（完整標題在滑鼠提示與「查看全部」），列高才會一致。
const EV_MORE = 46
const evRow = ref(58)
watch(evMain, (el) => {
  evObserver?.disconnect()
  if (!el) return
  evObserver = new ResizeObserver(([entry]) => {
    evSpace.value = entry.contentRect.height
    evRow.value = el.querySelector('.list-row')?.offsetHeight || evRow.value
  })
  evObserver.observe(el)
})
onBeforeUnmount(() => evObserver?.disconnect())
const evFit = computed(() => {
  if (!evSpace.value || events.value.length * evRow.value <= evSpace.value) return events.value.length
  return Math.max(1, Math.floor((evSpace.value - EV_MORE) / evRow.value))
})
const shownEvents = computed(() => events.value.slice(0, evFit.value))
const READ_STEPS = [
  ['影響多久？', '會影響長期營收，還是一次性的事件。'],
  ['和追蹤理由有關嗎？', '對照你當初在意的觀察條件。'],
  ['要重新評估嗎？', '理由被削弱時，可以建立新研究。'],
]
const coverage = computed(() => workspace.tracked.map((code) => ({
  code, name: snapshots[code]?.name || '', count: snapshots[code]?.events?.length || 0,
})).sort((a, b) => b.count - a.count))
const coveredCount = computed(() => coverage.value.filter((row) => row.count).length)

// 帶進助手，使用者看過、可修改後才送出。
function askEvent(event) {
  if (currentConversation.value?.messages.length) newConversation()
  assistant.view = 'chat'
  ui.assistantOpen = true
  ui.assistantDraft = `${event.code} ${event.name} 發布公告「${event.label}」，這類公告通常代表什麼？投資人要注意哪些事？`
}

function openReeval(stock) {
  reevalTarget.value = stock
  modal.value = 'reeval'
}
function research(stock) {
  modal.value = ''
  researchSymbol(stock.code, stock.name)
  router.push('/research')
}

// 窄螢幕時分成三個區塊切換（對應舊版 applyR2Layout）。
const { current: tab, hidden: tabHidden } = useSectionTabs('tracking', 3)
</script>

<template>
  <div class="page with-top-space">
    <div class="workspace">
      <section class="page-banner">
        <h1>公告與事件</h1>
        <p>整理你追蹤股票的重大訊息與法說會公告；股票表現請到「我的追蹤」。</p>
      </section>

      <R2SectionTabs v-model="tab" :labels="['公告與事件', '追蹤清單', '最新消息']" />
      <div class="tracking-dashboard" data-tour="tracking-kpis">
        <div class="tracking-main" :hidden="tabHidden(0) && tabHidden(1)">
          <section class="card tr-events" data-tour="tracking-events" :hidden="tabHidden(0)">
            <div class="card-header"><h2>追蹤股票的公告</h2><span class="tag good">MOPS 每日重大訊息</span></div>
            <div v-if="events.length" class="tr-ev-body">
              <div ref="evMain" class="tr-ev-main">
                <div class="list">
                  <div v-for="(e, i) in shownEvents" :key="`${e.code}-${i}`" class="list-row">
                    <div class="list-dot">{{ i + 1 }}</div>
                    <div class="list-copy">
                      <strong>{{ e.code }} {{ e.name }}<span class="tag medium">{{ kindOf(e.label) }}</span></strong>
                      <small class="tr-ev-line">
                        <a v-if="e.url" :href="e.url" :title="e.label" target="_blank" rel="noopener noreferrer" @click="track('announcement', e.url)">{{ e.label }}</a>
                        <span v-else :title="e.label">{{ e.label }}</span>
                        <time>· {{ eventTime(e.date) }}</time>
                      </small>
                    </div>
                    <button class="outline-button small" type="button" @click="askEvent(e)">詢問助手</button>
                  </div>
                </div>
                <button v-if="shownEvents.length < events.length" class="tr-ev-more" type="button" @click="modal = 'events'"><span>還有 {{ events.length - shownEvents.length }} 則沒有顯示</span><b>查看全部 {{ events.length }} 則公告 →</b></button>
                <section v-if="events.length <= TIP_LIMIT" class="tr-steps" aria-label="讀公告時先問自己">
                  <h3>讀公告時先問自己</h3>
                  <ol><li v-for="([title, desc], i) in READ_STEPS" :key="title"><b>{{ i + 1 }}</b><div><strong>{{ title }}</strong><small>{{ desc }}</small></div></li></ol>
                </section>
              </div>
              <aside class="tr-cover" data-tour="tracking-cover" :aria-label="`${coverage.length} 檔追蹤股票的公告狀況`">
                <h3>追蹤的 {{ coverage.length }} 檔</h3>
                <p>{{ coveredCount }} 檔有公告・{{ coverage.length - coveredCount }} 檔沒有</p>
                <ul>
                  <li v-for="row in coverage.slice(0, COVERAGE_ROWS)" :key="row.code" :class="{ 'is-none': !row.count }"><span :title="`${row.code} ${row.name}`">{{ row.code }} {{ row.name }}</span><b>{{ row.count ? `${row.count} 則` : '無' }}</b></li>
                </ul>
                <small v-if="coverage.length > COVERAGE_ROWS">另有 {{ coverage.length - COVERAGE_ROWS }} 檔未列出</small>
                <small class="tr-cover-note">「無」只代表最近可得的每日重大訊息沒有這檔。</small>
              </aside>
            </div>
            <div v-else class="list">
              <div class="tr-blank">
                <div class="tr-blank-art"><GgOutline kind="guji" /></div>
                <template v-if="workspace.tracked.length">
                  <strong>目前查詢期間沒有公告事件</strong>
                  <small>這不代表公司沒有其他歷史公告；目前來源為交易所最近可得每日重大訊息。</small>
                </template>
                <template v-else>
                  <strong>這裡還是空的</strong>
                  <small>加入追蹤後，這些股票的官方公告會出現在這裡。</small>
                  <button class="primary-button small tr-blank-go" type="button" @click="router.push('/candidates')">前往我的追蹤 →</button>
                </template>
              </div>
            </div>
          </section>

          <section class="card tr-list" data-tour="tracking-list" :hidden="tabHidden(1)">
            <div class="card-header">
              <h2>追蹤清單<small v-if="list.length">{{ list.length }} 檔</small></h2>
              <div class="tr-head-actions">
                <button v-if="list.length >= CELL_LIMIT" class="primary-button small" type="button" @click="modal = 'all'">查看全部 {{ list.length }} 檔</button>
              </div>
            </div>
            <!-- 一格一檔橫排、不捲動：1 檔佔滿、2 檔左右各一、最多 4 格，第 5 檔起收進「查看全部」 -->
            <div v-if="list.length" class="tr-grid" :class="[`count-${shown.length}`, { 'has-add': shown.length < CELL_LIMIT }]" :style="{ '--n': shown.length }">
              <article v-for="s in shown" :key="s.code" class="tr-cell">
                <div class="tr-cell-top">
                  <div class="tr-name"><strong>{{ s.code }} {{ s.name }}</strong><small>{{ s.market }}</small></div>
                  <div v-if="has(s.close)" class="tr-price"><b>{{ fmtNum(s.close) }}</b><em :class="tone(s.changePct)">{{ fmtPct(s.changePct) }}</em></div>
                </div>
                <p class="tr-direction" :title="s.direction">{{ s.direction }}</p>
                <dl v-if="shown.length <= 2" class="tr-facts">
                  <div><dt>半年報酬</dt><dd :class="tone(s.ret)">{{ fmtPct(s.ret) }}</dd></div>
                  <div><dt>年化波動</dt><dd>{{ fmtPct(s.vol, false) }}</dd></div>
                  <div><dt>最新公告</dt><dd>{{ s.latestEvent || '—' }}</dd></div>
                  <div v-if="shown.length === 1"><dt>資料日</dt><dd>{{ s.tradeDate || '—' }}</dd></div>
                </dl>
                <div class="tr-actions">
                  <button class="card-link" type="button" @click="openStockDetail(s.code, '股票詳情')">查看明細</button>
                  <button class="card-link" type="button" @click="openReeval(s)">重新評估</button>
                  <button class="card-link" type="button" :aria-label="`取消追蹤 ${s.code} ${s.name}`" @click="untrack(s.code)">移出</button>
                </div>
              </article>
              <button v-if="shown.length < CELL_LIMIT" class="tr-add" type="button" @click="overlays.stockSearch = true"><b aria-hidden="true">＋</b>加入追蹤</button>
            </div>
            <div v-else class="tracking-empty-v2 tr-empty">
              <span>◎</span>
              <strong>先加入第一檔追蹤</strong>
              <p>加入後，這裡會整理它的官方公告與研究觀察條件。</p>
              <div class="tr-empty-actions">
                <button class="primary-button small" type="button" @click="overlays.stockSearch = true">＋ 加入追蹤</button>
                <button class="soft-button small" type="button" @click="router.push('/picker')">到智慧選股找標的 →</button>
              </div>
            </div>
          </section>
        </div>

        <!-- 證交所最新消息：監控規則開關已移到「設定」 -->
        <aside class="card tr-news" data-tour="tracking-news" aria-label="證交所最新消息" :hidden="tabHidden(2)">
          <div class="card-header"><h2>證交所最新消息</h2></div>
          <ul v-if="news.length" class="tr-news-list">
            <li v-for="n in news" :key="n.title">
              <a :href="n.url" target="_blank" rel="noopener noreferrer" :title="n.title" @click="track('announcement', n.url)">{{ n.title }}</a>
              <small>{{ newsTime(n.published_at) }}</small>
            </li>
          </ul>
          <p v-else class="tr-news-empty">{{ newsState === 'loading' ? '讀取中…' : '目前無法取得最新消息' }}</p>
        </aside>
      </div>
    </div>
  </div>

  <AppModal :open="modal === 'all'" :title="`全部追蹤（${list.length} 檔）`" modal-class="tr-all-modal" @close="modal = ''">
    <div class="tr-all">
      <button class="tr-add tr-add-row" type="button" @click="modal = ''; overlays.stockSearch = true"><b aria-hidden="true">＋</b>加入追蹤</button>
      <article v-for="s in list" :key="s.code" class="tr-all-row">
        <div>
          <div class="tr-name"><strong>{{ s.code }} {{ s.name }}</strong><small>{{ s.market }}</small></div>
          <p class="tr-direction">{{ s.direction }}</p>
        </div>
        <div class="tr-actions">
          <button class="card-link" type="button" @click="modal = ''; openStockDetail(s.code, '股票詳情')">查看明細</button>
          <button class="card-link" type="button" @click="openReeval(s)">重新評估</button>
          <button class="card-link" type="button" :aria-label="`取消追蹤 ${s.code} ${s.name}`" @click="untrack(s.code)">移出</button>
        </div>
      </article>
    </div>
  </AppModal>

  <AppModal :open="modal === 'events'" :title="`追蹤股票的公告（${events.length} 則）`" modal-class="tr-all-modal" @close="modal = ''">
    <div class="list tr-ev-all">
      <div v-for="(e, i) in events" :key="`all-${e.code}-${i}`" class="list-row">
        <div class="list-dot">{{ i + 1 }}</div>
        <div class="list-copy">
          <strong>{{ e.code }} {{ e.name }}<span class="tag medium">{{ kindOf(e.label) }}</span></strong>
          <small>
            <a v-if="e.url" :href="e.url" target="_blank" rel="noopener noreferrer" @click="track('announcement', e.url)">{{ e.label }}</a>
            <template v-else>{{ e.label }}</template>
            · {{ eventTime(e.date) }}
          </small>
        </div>
        <button class="outline-button small" type="button" @click="modal = ''; askEvent(e)">詢問助手</button>
      </div>
    </div>
  </AppModal>

  <AppModal :open="modal === 'reeval'" title="重新評估" @close="modal = ''">
    <template v-if="reevalTarget">
      <h3>{{ reevalTarget.code }} {{ reevalTarget.name }}</h3>
      <div class="notice">將建立新的後端研究任務，重新取得官方資料與 Gemini 分析；不會覆蓋舊研究。</div>
      <h4>原研究方向</h4>
      <p>{{ reevalTarget.direction }}</p>
      <div class="candidate-dialog-actions">
        <button class="primary-button" type="button" @click="research(reevalTarget)">開始重新評估</button>
      </div>
    </template>
  </AppModal>
</template>

<style scoped>
/* 公告為主，追蹤清單固定高度、一格一檔，不出現捲軸 */
.tracking-main .tr-list{height:244px;display:flex;flex-direction:column;overflow:hidden}
.tracking-main .tr-list .card-header{flex:none;min-height:50px;padding-top:8px;padding-bottom:8px;border-bottom:1.5px solid #E2C3B5;background:color-mix(in srgb,#F2C4A0 12%,transparent)}
.tr-list h2 small{margin-left:8px;color:var(--muted);font-size:13px;font-weight:600}
.tr-head-actions{display:flex;align-items:center;gap:8px}
.tr-grid{flex:1;min-height:0;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:8px;padding:10px 14px 12px}
.tr-grid.has-add{grid-template-columns:repeat(var(--n),minmax(0,1fr)) 92px}
.tr-add{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:0;border:1.5px dashed #E2C3B5;border-radius:12px;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer}
.tr-add b{font-size:20px;line-height:1}
.tr-add:hover,.tr-add:focus-visible{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 6%,transparent)}
.tr-add-row{flex-direction:row;padding:10px}
.tr-cell{display:flex;flex-direction:column;gap:2px;min-width:0;min-height:0;padding:7px 12px;border:1.5px solid #E2C3B5;border-radius:12px;background:var(--pw-inner);overflow:hidden}
.tr-cell-top{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.tr-name{display:flex;align-items:baseline;gap:6px;min-width:0}
.tr-name strong{overflow:hidden;color:var(--text-strong);font-size:14px;text-overflow:ellipsis;white-space:nowrap}
.tr-name small{flex:none;color:var(--muted);font-size:11px}
.tr-price{flex:none;display:flex;align-items:baseline;gap:6px;font-variant-numeric:tabular-nums}
.tr-price b{color:var(--text-strong);font-size:14px}
.tr-price em{font-size:12px;font-style:normal;font-weight:700}
.tr-direction{margin:0;overflow:hidden;color:var(--text);font-size:13px;line-height:1.45;text-overflow:ellipsis;white-space:nowrap}
.tr-grid.count-1 .tr-direction,.tr-grid.count-2 .tr-direction{display:-webkit-box;white-space:normal;-webkit-line-clamp:2;-webkit-box-orient:vertical}
/* 3、4 格較窄：內容直向排列 */
.tr-grid.count-3 .tr-cell,.tr-grid.count-4 .tr-cell{gap:5px;padding:10px}
.tr-grid.count-3 .tr-cell-top,.tr-grid.count-4 .tr-cell-top{flex-direction:column;gap:3px}
.tr-grid.count-3 .tr-name,.tr-grid.count-4 .tr-name{flex-direction:column;gap:0;width:100%}
.tr-grid.count-3 .tr-name strong,.tr-grid.count-4 .tr-name strong{max-width:100%}
.tr-grid.count-3 .tr-direction,.tr-grid.count-4 .tr-direction{display:-webkit-box;white-space:normal;-webkit-line-clamp:3;-webkit-box-orient:vertical}
.tr-grid.count-4 .tr-actions{justify-content:space-between;gap:4px}
.tr-grid.count-4 .tr-actions .card-link{font-size:12px}
.tr-facts{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(0,1fr);gap:8px;margin:auto 0}
.tr-facts dt{color:var(--muted);font-size:12px}
.tr-facts dd:not(.price-up):not(.price-down){color:var(--text-strong)}
.tr-facts dd{margin:0;font-size:14px;font-weight:700;font-variant-numeric:tabular-nums}
.tr-actions{display:flex;gap:14px;margin-top:auto}
.tr-actions .card-link{min-height:0;padding:0;font-size:13px;white-space:nowrap}
.tr-empty{flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;padding:0 14px 10px;text-align:center}
.tr-empty p{margin:0}
.tr-empty-actions{display:flex;gap:8px;margin-top:4px}
.tr-news{display:flex;flex-direction:column;min-height:0;overflow:hidden}
.tr-news .card-header{flex:none}
.tr-news-list{flex:1;min-height:0;display:grid;grid-auto-rows:minmax(0,1fr);margin:0;padding:0 16px 8px;list-style:none}
.tr-news-list li{display:flex;flex-direction:column;justify-content:center;gap:3px;min-height:0;border-bottom:1px solid var(--line)}
.tr-news-list li:last-child{border-bottom:0}
.tr-news-list a{display:-webkit-box;overflow:hidden;color:var(--text-strong);font-size:14px;font-weight:600;line-height:1.45;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.tr-news-list a:hover{color:var(--blue);text-decoration:underline}
.tr-news-list small{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.tr-news-empty{flex:1;display:grid;place-items:center;margin:0;color:var(--muted);font-size:14px}
.tr-all{display:grid;gap:8px}
.tr-all-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;border-radius:12px;background:var(--pw-inner)}
.tr-all-row > div:first-child{min-width:0}
.tr-all-row .tr-direction{white-space:normal}
.tr-all-row .tr-actions{flex:none;margin:0}
:global(.modal.tr-all-modal){display:flex;flex-direction:column;overflow:hidden}
:global(.modal.tr-all-modal > .modal-header){flex:none}
:global(.modal.tr-all-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto}
.tracking-main .tr-events{display:flex;flex-direction:column;overflow:hidden}
.tracking-main .tr-events .list{flex:1;min-height:0;overflow:auto}
.tr-ev-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:14px;padding:6px 16px 14px}
.tr-ev-main{display:flex;flex-direction:column;gap:10px;min-width:0;min-height:0}
.tracking-main .tr-events .tr-ev-main .list{flex:0 1 auto;min-height:0;display:block;padding:0;overflow:hidden}
.tr-ev-more{flex:none;display:flex;align-items:center;justify-content:center;gap:14px;min-height:36px;margin-top:auto;padding:6px 12px;border:1.5px dashed var(--line-strong);border-radius:12px;background:transparent;color:var(--muted);font-size:13px;cursor:pointer}
.tr-ev-more b{color:var(--blue);font-weight:700}
.tr-ev-more:hover,.tr-ev-more:focus-visible{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 5%,transparent)}
.tr-ev-line{display:flex;align-items:baseline;gap:0;min-width:0}
.tr-ev-line > a,.tr-ev-line > span{overflow:hidden;min-width:0;text-overflow:ellipsis;white-space:nowrap}
.tr-ev-line time{flex:none;white-space:nowrap}
.tr-ev-main .list-copy{min-width:0}
.tr-ev-all .list-row{align-items:center}
.tr-ev-all .list-row > .outline-button{flex:none;white-space:nowrap}
.tr-ev-all .list-copy strong{display:flex;align-items:center;gap:8px}
.tr-ev-main:has(.tr-steps) .list{flex:0 1 auto!important}
.tr-ev-main .list-row{align-items:center}
.tr-ev-main .list-row > .outline-button{flex:none;white-space:nowrap}
.tr-ev-main .list-copy strong{display:flex;align-items:center;gap:8px}
.tr-ev-main .list-copy .tag{font-size:12px;padding:1px 8px}
.tr-steps{flex:1 1 0;min-height:0;display:flex;flex-direction:column;gap:8px;padding-top:10px;border-top:1px dashed var(--line)}
.tr-steps h3,.tr-cover h3{margin:0;color:var(--text-strong);font-size:14px}
.tr-steps ol{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0;padding:0;list-style:none}
.tr-ev-main:has(.list-row:nth-child(2)) .tr-steps small{display:none}
.tr-ev-main:has(.list-row:nth-child(2)) .tr-steps li{align-items:center}
.tr-steps li{display:flex;align-items:flex-start;gap:8px;min-width:0;min-height:0;padding:10px 12px;border:1.5px solid #E2C3B5;border-radius:12px;background:var(--pw-inner);overflow:hidden}
.tr-steps b{flex:none;display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue);font-size:12px}
.tr-steps li div{display:grid;gap:2px;min-width:0}
.tr-steps strong{color:var(--text-strong);font-size:14px}
.tr-steps small{color:var(--muted);font-size:13px;line-height:1.45}
.tr-cover{display:flex;flex-direction:column;gap:2px;min-height:0;padding:12px 14px;border-radius:14px;background:color-mix(in srgb,var(--blue) 6%,transparent);overflow:hidden}
.tr-cover p{margin:0 0 6px;color:var(--muted);font-size:13px}
.tr-cover ul{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;margin:0;padding:0;list-style:none;overflow:hidden}
.tr-cover li{flex:none;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}
.tr-cover li:last-child{border-bottom:0}
.tr-cover li span{min-width:0;overflow:hidden;color:var(--text-strong);text-overflow:ellipsis;white-space:nowrap}
.tr-cover li b{flex:none;color:var(--blue);font-weight:700}
.tr-cover li.is-none b{color:var(--muted);font-weight:500}
.tr-cover small{flex:none;color:var(--muted);font-size:12px;line-height:1.4}
.tr-blank{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;height:100%;min-height:0;text-align:center}
.tr-blank-art{flex:0 1 auto;width:100px;margin-bottom:6px}
.tr-blank strong{color:var(--text-strong);font-size:15px}
.tr-blank small{color:var(--muted);font-size:13px}
.tr-blank-go{flex:none;margin-top:8px}
@media (max-width:640px){
  .tracking-main .tr-list{height:auto}
  .tr-ev-body{grid-template-columns:1fr}.tr-steps ol{grid-template-columns:1fr}
  .tr-grid,.tr-grid.has-add{grid-template-columns:1fr;grid-auto-flow:row;grid-auto-rows:auto}
  .tr-add{flex-direction:row;padding:10px}
  .tr-actions,.tr-all-row{flex-wrap:wrap}
}
</style>
