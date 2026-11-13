<script setup>
import { computed, ref, watch } from 'vue'
import AppModal from '@/components/AppModal.vue'
import GgOutline from '@/components/GgOutline.vue'
import InfoTip from '@/components/InfoTip.vue'
import StockSearch from '@/components/StockSearch.vue'
import { api } from '@/api/client.js'
import { assistant, current as currentConversation, newConversation } from '@/stores/assistant.js'
import { ui, settings } from '@/stores/ui.js'
import { workspace } from '@/stores/workspace.js'

// ESG 專區：公司自行申報的揭露內容。只呈現揭露了什麼、有沒有驗證，不評分。
const PILLARS = [['E', '環境'], ['S', '社會'], ['G', '治理']]
const GREENHOUSE_TIP = '範疇一：公司自己直接排放，例如廠內燃料。\n範疇二：外購電力等能源產生的排放。\n範疇三：供應鏈、運輸等其他間接排放。'
const VERIFY_TIP = '有驗證欄位的主題中，公司填了第三方驗證或適用標準的數量。ISO 等管理系統標準不等於數字本身經過確信。'
const SIDE_ROWS = 10

// 預設看第一檔追蹤的公司；ETF（00 開頭）與存託憑證（91 開頭）沒有申報，略過。
const code = ref(workspace.tracked.find((value) => !/^(00|91)/.test(value)) || '2330')
const data = ref(null)
const state = ref('loading') // loading | ready | none | failed
const opened = ref(null)
let token = 0

async function load(value) {
  const current = ++token
  state.value = 'loading'
  try {
    const result = await api.esg(value)
    if (current !== token) return
    data.value = result.available ? result : null
    state.value = result.available ? 'ready' : result.reason === 'not_listed' ? 'none' : 'failed'
  } catch {
    if (current !== token) return
    data.value = null
    state.value = 'failed'
  }
}
watch(code, load, { immediate: true })

const tracked = ref([])
const trackedKey = computed(() => workspace.tracked.join(','))
watch(trackedKey, async () => {
  if (!workspace.tracked.length) return (tracked.value = [])
  try {
    tracked.value = (await api.esgSummaries(workspace.tracked)).items || []
  } catch {
    tracked.value = []
  }
}, { immediate: true })
// 右側只列有申報資料的追蹤標的（ETF、存託憑證等沒有資料的不列）。
const withData = computed(() => workspace.tracked.map((value) => tracked.value.find((row) => row.symbol === value)).filter(Boolean))
const trackedRows = computed(() => withData.value.slice(0, SIDE_ROWS))
const noDataCount = computed(() => (tracked.value.length || !workspace.tracked.length ? workspace.tracked.length - withData.value.length : 0))

// 進入時的說明視窗：哪些公司查得到、怎麼搜尋。可勾「今日不再顯示」，或到設定永久關閉。
const today = () => new Date().toLocaleDateString('sv')
const intro = ref(!settings.esgIntro.off && settings.esgIntro.snoozeDay !== today())
const snoozeToday = ref(false)
const INTRO_EXAMPLES = [['2330', '台積電'], ['2317', '鴻海'], ['2881', '富邦金'], ['1301', '台塑']]
function closeIntro(pick) {
  if (snoozeToday.value) settings.esgIntro.snoozeDay = today()
  intro.value = false
  if (pick) code.value = pick
}

const topicsOf = (pillar) => (data.value?.topics || []).filter((topic) => topic.pillar === pillar)
const shownHighlights = (topic) => topic.highlights.filter((entry) => entry.value != null)

function askAssistant() {
  if (currentConversation.value?.messages.length) newConversation()
  assistant.view = 'chat'
  ui.assistantOpen = true
  ui.assistantDraft = `${data.value.symbol} ${data.value.name} 的 ESG 揭露中，範疇一、二、三的溫室氣體排放各代表什麼？一般投資人看這些資料要注意哪些限制？`
}
</script>

<template>
  <div class="page with-top-space">
    <div class="workspace esg-workspace">
      <section class="page-banner">
        <h1>ESG 專區</h1>
        <p>查看上市櫃公司自行申報的永續資料，只看揭露了什麼、有沒有驗證，不替公司評分。</p>
      </section>
      <div class="esg-grid">
        <section class="card surface-solid esg-main">
          <header class="esg-head">
            <div class="esg-title">
              <h2>{{ data ? `${data.symbol} ${data.name}` : code }}</h2>
              <small v-if="data">{{ data.market === 'TWSE' ? '上市' : '上櫃' }}・民國 {{ data.report_year }} 年度・公司自行申報</small>
            </div>
            <div class="esg-search"><StockSearch :selected="[code]" action-label="查看" done-label="查看中" placeholder="代號或公司名稱" @pick="code = $event.code" /></div>
          </header>

          <template v-if="state === 'ready'">
            <div class="esg-strip">
              <div><small>已揭露主題</small><strong>{{ data.disclosed_count }}<i> / {{ data.topic_count }}</i></strong></div>
              <div><small>填有驗證或標準<InfoTip :text="VERIFY_TIP" label="驗證或標準" /></small><strong>{{ data.verified_count }}<i> / {{ data.verifiable_count }}</i></strong></div>
              <p class="esg-hint"><span>點主題可以看完整申報欄位</span><small>揭露多不代表表現好，只代表資料比較齊全</small></p>
              <button class="outline-button small" type="button" @click="askAssistant">詢問助手</button>
            </div>
            <div class="esg-rows">
              <section v-for="[pillar, name] in PILLARS" :key="pillar" class="esg-row" :class="`is-${pillar}`">
                <header><b>{{ pillar }}</b><small>{{ name }}</small></header>
                <div class="esg-tiles" :style="{ '--n': topicsOf(pillar).length }">
                  <article v-for="topic in topicsOf(pillar)" :key="topic.key" class="esg-tile" :class="{ 'is-empty': !topic.disclosed }" role="button" tabindex="0" :aria-label="`查看${topic.title}完整申報`" @click="opened = topic" @keydown.enter="opened = topic">
                    <div class="esg-tile-top">
                      <h3>{{ topic.title }}<InfoTip v-if="topic.key === 'greenhouse'" :text="GREENHOUSE_TIP" label="範疇" /></h3>
                      <span v-if="topic.verified" class="esg-mark" title="填有第三方驗證或適用標準">驗證</span>
                    </div>
                    <dl v-if="topic.disclosed">
                      <div v-for="entry in shownHighlights(topic)" :key="entry.label"><dt>{{ entry.label }}</dt><dd :title="`${entry.value} ${entry.unit}`">{{ entry.value }}<small v-if="entry.unit"> {{ entry.unit }}</small></dd></div>
                    </dl>
                    <p v-else>未填寫</p>
                    <div v-if="topic.disclosed && (topic.verification || topic.scope)" class="esg-tile-foot">
                      <small v-if="topic.verification" :title="topic.verification"><b>驗證</b>{{ topic.verification }}</small>
                      <small v-if="topic.scope" :title="topic.scope"><b>範圍</b>{{ topic.scope }}</small>
                    </div>
                  </article>
                </div>
              </section>
            </div>
          </template>

          <div v-else class="esg-blank">
            <template v-if="state === 'loading'"><strong>正在讀取申報資料…</strong><small>第一次查詢需要幾秒鐘</small></template>
            <template v-else>
              <div class="esg-blank-art"><GgOutline kind="guji" /></div>
              <strong>{{ state === 'none' ? '這檔沒有 ESG 申報資料' : '暫時取不到 ESG 資料' }}</strong>
              <small>{{ state === 'none' ? 'ETF、存託憑證與剛掛牌的公司不在這份申報範圍內，可以換一家上市櫃公司查看。' : '來源可能暫時無法連線，請稍後再試。' }}</small>
              <button v-if="state === 'none'" class="card-link" type="button" @click="intro = true">哪些公司查得到？</button>
            </template>
          </div>
        </section>

        <aside class="card surface-solid esg-side">
          <header><h2>追蹤的標的</h2><small v-if="withData.length">{{ withData.length > SIDE_ROWS ? `前 ${SIDE_ROWS} 檔，共 ${withData.length} 檔` : `${withData.length} 檔有資料` }}</small></header>
          <div v-if="trackedRows.length" class="esg-list">
            <div class="esg-list-head"><span>標的</span><span>揭露</span><span>驗證</span></div>
            <button v-for="row in trackedRows" :key="row.symbol" type="button" :class="{ active: row.symbol === code }" :title="`查看 ${row.symbol} ${row.name}`" @click="code = row.symbol">
              <span>{{ row.symbol }} {{ row.name }}</span>
              <b>{{ row.disclosed_count }}/{{ row.topic_count }}</b><b>{{ row.verified_count }}/{{ row.verifiable_count }}</b>
            </button>
            <small v-if="noDataCount" class="esg-list-note">另有 {{ noDataCount }} 檔追蹤標的沒有 ESG 申報（例如 ETF），未列出</small>
          </div>
          <div v-else class="esg-blank">
            <div class="esg-blank-art"><GgOutline kind="guji" /></div>
            <strong>{{ workspace.tracked.length ? '追蹤的標的都沒有 ESG 申報' : '這裡還是空的' }}</strong>
            <small>{{ workspace.tracked.length ? 'ETF、存託憑證等不在申報範圍內，可以用上方搜尋查看公司。' : '加入追蹤後，可以一次比對揭露情況。' }}</small>
          </div>
          <footer>
            <strong>使用前先知道</strong>
            <span>資料為公司自行申報的年度數字，交易所未逐筆查核。各公司的資料範圍和單位可能不同，不建議直接比高低。</span>
          </footer>
        </aside>
      </div>
    </div>
  </div>

  <AppModal :open="intro" title="ESG 專區怎麼查？" modal-class="esg-intro-modal" @close="closeIntro()">
    <div class="esg-intro">
      <section class="esg-intro-key">
        <h3>哪些公司查得到</h3>
        <p><b>幾乎所有上市櫃公司都有</b>：約 99% 的上市櫃股票都有申報，包含金融股與 KY 公司。</p>
        <p class="esg-intro-no"><b>查不到的通常是</b></p>
        <ul>
          <li><strong>ETF</strong>：是基金不是公司，沒有 ESG 申報；想了解可以看它的成份股。</li>
          <li><strong>存託憑證</strong>：代號 91 開頭（例如 9105 泰金寶-DR）。</li>
          <li><strong>剛掛牌的公司</strong>：還沒到第一次申報的時間。</li>
          <li><strong>興櫃公司</strong>：不在這份上市櫃申報資料內。</li>
        </ul>
      </section>
      <section>
        <h3>怎麼搜尋</h3>
        <p>在右上角輸入代號或公司名稱，或點右側「追蹤的標的」。先試試：</p>
        <div class="esg-intro-try"><button v-for="[c, n] in INTRO_EXAMPLES" :key="c" type="button" @click="closeIntro(c)">{{ c }} {{ n }}</button></div>
      </section>
      <section>
        <h3>先知道</h3>
        <p>資料是公司自行申報的民國 {{ data?.report_year || 114 }} 年度數字，交易所未逐筆查核。PINWISE 只呈現揭露了什麼、有沒有驗證，不替公司評分。</p>
      </section>
      <footer>
        <label><input v-model="snoozeToday" type="checkbox" />今日不再顯示</label>
        <small>永久關閉：設定 → 外觀與版面 → 側邊欄管理</small>
        <button class="primary-button small" type="button" @click="closeIntro()">開始查詢</button>
      </footer>
    </div>
  </AppModal>

  <AppModal :open="Boolean(opened)" :title="opened?.title || ''" modal-class="esg-modal" @close="opened = null">
    <div v-if="opened" class="esg-detail">
      <div v-for="field in opened.fields" :key="field.label"><span>{{ field.label }}</span><b :class="{ 'is-none': field.value == null }">{{ field.value ?? '未填寫' }}</b></div>
      <a :href="opened.source_url" target="_blank" rel="noopener noreferrer">查看官方原始資料</a>
    </div>
  </AppModal>
</template>

<style scoped>
.esg-workspace{height:100%;display:flex;flex-direction:column}
.esg-grid{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1fr) 256px;gap:12px}
.esg-main,.esg-side{display:flex;flex-direction:column;gap:8px;min-width:0;min-height:0;margin:0;padding:12px 16px;overflow:visible}
.esg-head{flex:none;position:relative;z-index:6;display:flex;align-items:center;justify-content:space-between;gap:14px}
.esg-title{min-width:0}
.esg-title h2{margin:0;overflow:hidden;color:var(--text-strong);font-size:19px;text-overflow:ellipsis;white-space:nowrap}
.esg-title small{color:var(--muted);font-size:12px}
.esg-search{position:relative;flex:0 1 330px;min-width:240px}
.esg-search :deep(.comparison-search-results){position:absolute;top:calc(100% + 6px);left:0;right:0;z-index:20}
.esg-strip{flex:none;display:flex;align-items:center;gap:18px;padding:7px 12px;border-radius:12px;background:color-mix(in srgb,var(--blue) 6%,transparent)}
.esg-strip > div{flex:none;display:grid}
.esg-strip small{display:flex;align-items:center;color:var(--muted);font-size:12px}
.esg-strip strong{color:var(--text-strong);font-size:20px;line-height:1.15;font-variant-numeric:tabular-nums}
.esg-strip strong i{color:var(--muted);font-size:13px;font-style:normal;font-weight:500}
.esg-strip p{flex:1;min-width:0;margin:0;padding-left:14px;border-left:1px solid var(--line)}
.esg-hint{display:grid;gap:1px}
.esg-hint span{color:var(--text-strong);font-size:13px;font-weight:600}
.esg-hint small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.esg-list-note{flex:none;padding:6px 6px 0;color:var(--muted);font-size:12px;line-height:1.45}
.esg-blank .card-link{margin-top:4px}
:global(.modal.esg-intro-modal){width:min(600px,calc(100vw - 32px))}
.esg-intro{display:grid;gap:14px;font-size:14px;line-height:1.6;color:var(--text)}
.esg-intro h3{margin:0 0 4px;color:var(--text-strong);font-size:15px}
.esg-intro p{margin:0}
.esg-intro-key{padding:12px 14px;border:1px solid color-mix(in srgb,var(--blue) 24%,transparent);border-radius:14px;background:color-mix(in srgb,var(--blue) 6%,transparent)}
.esg-intro-no{margin-top:6px!important}
.esg-intro ul{margin:2px 0 0;padding-left:18px}
.esg-intro li strong{color:var(--text-strong)}
.esg-intro-try{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.esg-intro-try button{padding:4px 12px;border:1px solid var(--line-strong);border-radius:999px;background:transparent;color:var(--text-strong);font-size:13px;cursor:pointer}
.esg-intro-try button:hover{border-color:var(--blue);color:var(--blue)}
.esg-intro footer{display:flex;align-items:center;gap:12px;padding-top:12px;border-top:1px solid var(--line)}
.esg-intro footer label{display:flex;align-items:center;gap:6px;color:var(--text);font-size:13px;cursor:pointer}
.esg-intro footer input{width:15px;height:15px;margin:0;accent-color:var(--blue)}
.esg-intro footer small{flex:1;color:var(--muted);font-size:12px}
.esg-strip button{flex:none}
.esg-rows{flex:1;min-height:0;display:grid;grid-template-rows:1.3fr .85fr 1.15fr;gap:6px}
.esg-row{--g:#2A78D6;display:grid;grid-template-columns:44px minmax(0,1fr);gap:8px;min-height:0}
.esg-row.is-S{--g:#C76E12}
.esg-row.is-G{--g:#8A4FD0}
:global(body[data-theme="dark"] .esg-row.is-E){--g:#8DB4F5}
:global(body[data-theme="dark"] .esg-row.is-S){--g:#F0B070}
:global(body[data-theme="dark"] .esg-row.is-G){--g:#C7A2F2}
.esg-row > header{display:grid;place-content:center;justify-items:center;border-right:2px solid var(--g)}
.esg-row > header b{color:var(--g);font-size:20px;line-height:1.1}
.esg-row > header small{color:var(--muted);font-size:12px}
.esg-tiles{display:grid;grid-template-columns:repeat(var(--n),minmax(0,1fr));gap:8px;min-height:0}
.esg-tile{display:flex;flex-direction:column;gap:3px;min-width:0;min-height:0;padding:7px 10px;border:1.5px solid var(--pw-small-line);border-radius:12px;background:var(--pw-inner);overflow:hidden;cursor:pointer;transition:border-color .15s}
.esg-tile:hover,.esg-tile:focus-visible{border-color:var(--g);outline:none}
.esg-tile.is-empty{border-style:dashed;background:transparent}
.esg-tile-top{flex:none;display:flex;align-items:center;justify-content:space-between;gap:6px}
.esg-tile h3{display:flex;align-items:center;min-width:0;margin:0;overflow:hidden;color:var(--text-strong);font-size:14px;white-space:nowrap}
.esg-mark{flex:none;padding:0 6px;border-radius:999px;background:color-mix(in srgb,var(--g) 14%,transparent);color:var(--g);font-size:11px;font-weight:800}
.esg-tile dl{margin:0;display:grid;gap:1px}
.esg-row.is-S dl{grid-template-columns:repeat(2,minmax(0,1fr));gap:1px 18px}
.esg-tile-foot{margin-top:auto;display:grid;gap:1px;padding-top:4px;border-top:1px dashed var(--line)}
.esg-tile-foot small{display:block;overflow:hidden;color:var(--text);font-size:12px;line-height:1.35;text-overflow:ellipsis;white-space:nowrap}
.esg-tile-foot b{margin-right:5px;color:var(--muted);font-weight:500}
@media (max-height:680px){.esg-tile-foot small:nth-child(2){display:none}}
.esg-tile dl div{display:flex;align-items:baseline;justify-content:space-between;gap:6px;min-width:0}
.esg-tile dl:has(div:only-child) div{flex-direction:column;align-items:flex-start;gap:0}
.esg-tile dl:has(div:only-child) dd{max-width:100%;font-size:18px}
.esg-tile:not(:has(.esg-tile-foot)) dl:has(div:only-child){margin:auto 0}
.esg-tile dt{flex:none;color:var(--muted);font-size:12px}
.esg-tile dd{min-width:0;margin:0;overflow:hidden;color:var(--text-strong);font-size:14px;font-weight:700;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}
.esg-tile dd small{color:var(--muted);font-size:11px;font-weight:500}
.esg-tile > p{margin:auto 0;color:var(--muted);font-size:13px}
.esg-blank{flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;text-align:center}
.esg-blank-art{width:92px;margin-bottom:6px}
.esg-blank strong{color:var(--text-strong);font-size:15px}
.esg-blank small{color:var(--muted);font-size:13px;line-height:1.45}
.esg-side > header{flex:none;display:flex;align-items:baseline;justify-content:space-between;padding-bottom:6px;border-bottom:1.5px solid #E2C3B5}
.esg-side h2{margin:0;color:var(--text-strong);font-size:17px}
.esg-side > header small{color:var(--muted);font-size:12px}
.esg-list{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.esg-list-head,.esg-list button{display:grid;grid-template-columns:minmax(0,1fr) 38px 38px;align-items:center;gap:4px}
.esg-list-head{flex:none;padding:0 6px 3px;color:var(--muted);font-size:12px;font-weight:700}
.esg-list-head span:not(:first-child){text-align:right}
.esg-list button{flex:1 1 0;max-height:46px;min-height:0;padding:0 6px;border:0;border-bottom:1px solid var(--line);border-radius:0;background:transparent;color:var(--text-strong);font-size:13px;text-align:left;cursor:pointer}
.esg-list button:hover{background:color-mix(in srgb,var(--blue) 6%,transparent)}
.esg-list button.active{background:color-mix(in srgb,var(--blue) 11%,transparent)}
.esg-list button span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.esg-list b{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.esg-list em{grid-column:span 2;color:var(--muted);font-size:12px;font-style:normal;text-align:right}
.esg-side footer{flex:none;display:grid;gap:2px;padding-top:8px;border-top:1px dashed var(--line)}
.esg-side footer strong{color:var(--text-strong);font-size:13px}
.esg-side footer span{color:var(--muted);font-size:12px;line-height:1.5}
.esg-detail{display:grid;gap:0;font-size:14px}
.esg-detail > div{display:flex;justify-content:space-between;gap:16px;padding:8px 0;border-bottom:1px solid var(--line)}
.esg-detail span{color:var(--muted)}
.esg-detail b{max-width:60%;color:var(--text-strong);text-align:right;white-space:pre-line}
.esg-detail b.is-none{color:var(--muted);font-weight:500}
.esg-detail a{justify-self:end;margin-top:10px;color:var(--blue);font-size:13px;font-weight:700}
@media (max-width:1000px){
  .esg-workspace{height:auto}
  .esg-grid{grid-template-columns:1fr}
  .esg-rows{grid-template-rows:none}
  .esg-tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .esg-head,.esg-strip{flex-wrap:wrap}
}
</style>
