<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client.js'
import { usePopularStocks } from '@/composables/popularStocks.js'
import AppModal from '@/components/AppModal.vue'
import HoldingsModal from '@/components/stock/HoldingsModal.vue'
import MetricFlag from '@/components/MetricFlag.vue'
import GgOutline from '@/components/GgOutline.vue'
import { addRecord, track } from '@/stores/footprint.js'
import StockSearch from '@/components/StockSearch.vue'
import AppIcon from '@/components/AppIcon.vue'
import InfoTip from '@/components/InfoTip.vue'
import { workspace, toggleCompare } from '@/stores/workspace.js'
import { openStockDetail } from '@/stores/overlays.js'
import { snapshots, loadSnapshots, quoteText, metricText } from '@/stores/snapshots.js'
import { research, visibleTasks, isCompleted, formatDate, confirmResearch } from '@/stores/research.js'
import { ui } from '@/stores/ui.js'
import { assistant, current as currentConversation, newConversation } from '@/stores/assistant.js'

// 股票比較（對應舊版 js/pages-workspaces.js 的 comparePage）。
const METRIC_TIPS = {
  近半年報酬: '期間內第一個與最後一個交易日收盤價的變化百分比；不含股利，也不代表未來表現。',
  年化波動: '把每日漲跌幅換算成一年的起伏程度。本系統以 25% 以下為較低、45% 以上為較高。',
  最大回撤: '期間內從某個高點跌到之後最低點的最大跌幅，可以感受最壞情況下帳面可能虧多少。',
  平均成交量: '期間內每天平均成交的股數。成交量越大，買賣越容易成交。',
  成份股: 'ETF 持有的股票檔數與最大持股，來自投信官網公開資料。',
  'AI 研究': '顯示這檔最近一次 AI 標的研究；還沒研究過可以直接建立。',
}

const { popular: POPULAR, date: quickDate } = usePopularStocks()

watch(() => [...workspace.compare], (codes) => loadSnapshots(codes), { immediate: true })

const router = useRouter()
watch(() => [...workspace.compare].sort().join(','), (codes) => {
  if (codes.split(',').length < 2) return
  addRecord({ id: `compare_${new Date().toISOString().slice(0, 10)}_${codes}`, kind: 'compare', at: new Date().toISOString(), label: codes.replaceAll(',', '、'), symbols: codes.split(','), status: 'completed', tokens: 0 })
  track('compare', codes)
  if (new Date().getHours() >= 14) track('after_close_compare', '', { once: true })
}, { immediate: true })
const colorOf = (code) => `cp-c${workspace.compare.indexOf(code)}`
const selected = computed(() =>
  workspace.compare.map((code) => ({
    code,
    name: snapshots[code]?.name || POPULAR.value.find(([c]) => c === code)?.[1] || '',
    type: snapshots[code]?.type || (/^00/.test(code) ? 'etf' : 'stock'),
    market: snapshots[code]?.market || '待確認',
  })),
)

const ROWS = [
  ['類型與市場', (s) => `${s.type === 'etf' ? 'ETF' : '個股'} · ${s.market}`],
  ['最近日收盤', (s) => quoteText(s.code)],
  ['近半年報酬', (s) => metricText(s.code, 'period_return_pct', '%')],
  ['年化波動', (s) => metricText(s.code, 'annualized_volatility_pct', '%')],
  ['最大回撤', (s) => metricText(s.code, 'max_drawdown_pct', '%')],
  ['平均成交量', (s) => metricText(s.code, 'average_volume_shares', '股')],
  ['成份股', (s) => holdingText(s)],
  ['AI 研究', () => ''],
]
const WARN_FIELDS = { 近半年報酬: 'period_return_pct', 年化波動: 'annualized_volatility_pct', 最大回撤: 'max_drawdown_pct' }

// 成份股：只有 ETF 需要查，查過就留著。
const holdingsOf = reactive({})
async function loadHoldings(code) {
  if (!/^00/.test(code) || holdingsOf[code]) return
  holdingsOf[code] = { loading: true }
  try {
    const data = await api.etfHoldings(code)
    holdingsOf[code] = data.available ? { rows: data.holdings, data } : { missing: true }
  } catch {
    holdingsOf[code] = { missing: true }
  }
}
watch(() => [...workspace.compare], (codes) => codes.forEach(loadHoldings), { immediate: true })
function holdingText(stock) {
  if (stock.type !== 'etf') return '個股，沒有成份股'
  const data = holdingsOf[stock.code]
  if (!data || data.loading) return '讀取中…'
  if (data.missing) return /[LR]$/.test(stock.code) ? '槓桿／反向型不適用' : '未取得持股資料'
  return `${data.rows.length} 檔，最大 ${data.rows[0].name} ${data.rows[0].weight.toFixed(2)}% →`
}

// 各投信的代號格式不同（AAPL.US、AMD_US），比對時只看市場後綴之前的部分。
const holdingKey = (code) => String(code).split(/[.\s_]/)[0].toUpperCase()
const etfHoldings = computed(() =>
  selected.value.filter((s) => holdingsOf[s.code]?.rows).map((s) => ({
    code: s.code,
    map: new Map(holdingsOf[s.code].rows.map((row) => [holdingKey(row.code), row])),
  })),
)
const overlapPairs = computed(() => {
  const pairs = []
  etfHoldings.value.forEach((a, i) => etfHoldings.value.slice(i + 1).forEach((b) => {
    let count = 0, weight = 0
    a.map.forEach((row, key) => {
      const other = b.map.get(key)
      if (other) (count++, (weight += Math.min(row.weight, other.weight)))
    })
    pairs.push({ a: a.code, b: b.code, count, weight })
  }))
  return pairs
})
const sharedHoldings = computed(() => {
  const keys = new Set(etfHoldings.value.flatMap((etf) => [...etf.map.keys()]))
  return [...keys]
    .map((key) => {
      const held = etfHoldings.value.map((etf) => etf.map.get(key))
      const names = held.filter(Boolean).map((row) => row.name).sort((x, y) => x.length - y.length)
      return { key, name: names[0], weights: held.map((row) => row?.weight ?? null), count: names.length, total: held.reduce((sum, row) => sum + (row?.weight || 0), 0) }
    })
    .filter((row) => row.count >= 2)
    .sort((x, y) => y.count - x.count || y.total - x.total)
})
const showOverlap = ref(false)
watch(showOverlap, (open) => open && overlapPairs.value.some((pair) => pair.weight >= 50) && track('overlap_50', '', { once: true }))
const holdingsCode = ref('')
function askAssistant() {
  // 只放代號：代號和名稱連著寫時，助手可能認不出其中一檔。
  const codes = selected.value.map((s) => s.code).join('、')
  if (currentConversation.value?.messages.length) newConversation()
  assistant.view = 'chat'
  ui.assistantOpen = true
  ui.assistantDraft = `請比較 ${codes} 的近半年報酬、波動和最大回撤，這些差異代表什麼？新手要注意哪些風險？`
}

// AI 研究：顯示這檔最新一份研究，沒有就可以直接建立。
function researchOf(code) {
  return visibleTasks.value.find((task) => (task.requestedSymbols || []).includes(code) || (task.candidates || []).some((item) => (item?.symbol || item) === code))
}
function researchLabel(code) {
  const task = researchOf(code)
  if (task && isCompleted(task)) return `${formatDate(task.completedAt || task.createdAt)} 完成，查看結果 →`
  return task?.running ? '研究進行中，查看進度 →' : '建立 AI 研究 →'
}
async function openResearch(stock) {
  const task = researchOf(stock.code)
  if (task && (isCompleted(task) || task.running)) {
    research.activeId = task.id
    return router.push('/research')
  }
  const created = await confirmResearch(`研究 ${stock.code} ${stock.name} ${stock.type === 'etf' ? '的表現與風險' : '的產業位置、主要成長動能與風險'}`, {
    requestedSymbols: [stock.code], researchType: 'single_company',
    inputUnderstanding: { candidates: [{ symbol: stock.code, name: stock.name }] },
  })
  if (created) router.push('/research')
}
// 資料還沒回來時顯示讀取中，不要先出現「資料不足」。
const valueOf = (getValue, stock) => (snapshots[stock.code] ? getValue(stock) : '讀取中…')

const SLOT_LABELS = ['第一檔', '第二檔', '第三檔（可選）']
const slots = computed(() => SLOT_LABELS.map((label, i) => ({ label, stock: selected.value[i] || null })))
const headline = computed(() => {
  const n = selected.value.length
  if (!n) return ['先加入兩檔想了解的標的', '從上方搜尋或點常用標的，最多三檔，加入後這張表會用同一組標準填上數字。']
  if (n === 1) return ['再選一檔就能開始比較', '第一檔的資料已經填入，點代號可以查看完整股票詳情。']
  return [`${n} 檔標的比較`, '數值由日資料計算，反映過去表現，不代表未來；點代號可以查看完整股票詳情。']
})

const focusSearch = () => document.querySelector('.comparison-search-card input')?.focus()

function addStock(stock) {
  if (!workspace.compare.includes(stock.code)) toggleCompare(stock.code)
}
const showDetail = (stock) => openStockDetail(stock.code, '比較標的詳情')
</script>

<template>
  <div class="page with-top-space compare-page">
    <div class="workspace compare-workspace">
      <section class="page-banner">
        <h1>股票比較</h1>
        <p>搜尋一檔看完整資料結構，加入 2～3 檔後再用同一組標準比較差異。</p>
      </section>

      <section class="card comparison-search-card surface-solid">
        <h2 class="cp-search-title">加入比較標的<InfoTip text="加入後會取得最近官方日資料；取得失敗會顯示原因，不會改用固定價格。最多同時比較三檔。" label="加入比較標的" /></h2>
        <StockSearch
          :selected="workspace.compare" action-label="加入比較" done-label="已選擇" history-key="compare"
          :full="workspace.compare.length >= 3" full-text="比較清單已有 3 檔。先在下方移除一檔，輸入的字會保留，回到搜尋欄就能直接加入。"
          @pick="addStock"
        />
        <div class="comparison-popular">
          <span :title="quickDate ? `依成交金額排序的個股，資料日 ${quickDate}` : ''">常用標的</span>
          <button v-for="[code, name] in POPULAR" :key="code" type="button" :title="`${code} ${name}`" :disabled="workspace.compare.includes(code)" @click="addStock({ code })">{{ code }} {{ name }}</button>
        </div>
      </section>

      <!-- 0～3 檔都用同一張表：已選的欄位顯示資料，其餘保留空欄 -->
      <section class="card cp-empty">
        <header class="cp-head">
          <span class="cp-symbol"><AppIcon name="compare" :size="22" /></span>
          <div><h2>{{ headline[0] }}</h2><p>{{ headline[1] }}</p></div>
          <div v-if="selected.length >= 2" class="cp-actions">
            <button v-if="etfHoldings.length >= 2" class="outline-button small" type="button" @click="showOverlap = true">成份股比較</button>
            <button class="primary-button small" type="button" @click="askAssistant">詢問助手</button>
          </div>
        </header>
        <div class="cp-table" role="table" aria-label="股票比較表">
          <div class="cp-row" role="row">
            <span class="cp-cell cp-label is-head" role="columnheader">比較面向</span>
            <div v-for="(slot, i) in slots" :key="i" class="cp-cell is-head" role="columnheader">
              <div v-if="slot.stock" class="cp-stock" :class="`cp-c${i}`">
                <button class="cp-stock-name" type="button" title="查看股票詳情" @click="showDetail(slot.stock)"><b>{{ slot.stock.code }}</b><span>{{ slot.stock.name }}</span></button>
                <button class="cp-remove" type="button" :aria-label="`從比較移除 ${slot.stock.code} ${slot.stock.name}`" @click="toggleCompare(slot.stock.code)">×</button>
              </div>
              <button v-else type="button" class="cp-slot" @click="focusSearch"><b aria-hidden="true">{{ i + 1 }}</b>{{ slot.label }}</button>
            </div>
          </div>
          <div v-for="([label, getValue], r) in ROWS" :key="label" class="cp-row" role="row">
            <span class="cp-cell cp-label" :class="{ 'is-last': r === ROWS.length - 1 }" role="rowheader" :title="METRIC_TIPS[label]">{{ label }}</span>
            <div v-for="(slot, i) in slots" :key="i" class="cp-cell" :class="{ 'is-last': r === ROWS.length - 1 }" role="cell">
              <button v-if="slot.stock && label === 'AI 研究'" class="cp-research" type="button" @click="openResearch(slot.stock)">{{ researchLabel(slot.stock.code) }}</button>
              <button v-else-if="slot.stock && label === '成份股' && holdingsOf[slot.stock.code]?.rows" class="cp-research" type="button" title="查看完整成份股" @click="holdingsCode = slot.stock.code">{{ holdingText(slot.stock) }}</button>
              <span v-else-if="slot.stock" class="cp-value" :title="valueOf(getValue, slot.stock)">{{ valueOf(getValue, slot.stock) }}</span>
              <MetricFlag v-if="slot.stock && WARN_FIELDS[label]" :metrics="snapshots[slot.stock.code]?.metrics" :field="WARN_FIELDS[label]" />
              <i v-else-if="!slot.stock" aria-hidden="true"></i>
            </div>
          </div>
          <div v-if="!selected.length" class="cp-blank">
            <div class="cp-blank-art"><GgOutline kind="guji" /></div>
            <strong>這裡還是空的</strong>
            <span>從上方加入兩檔，表格就會填上數字</span>
          </div>
          <div v-if="selected.length === 1" class="cp-need" aria-hidden="true">
            <strong>再選一檔標的開始比較</strong>
          </div>
        </div>
      </section>
    </div>
    <HoldingsModal :open="Boolean(holdingsCode)" :code="holdingsCode" :holdings="holdingsOf[holdingsCode]?.data || null" @close="holdingsCode = ''" />
    <AppModal :open="showOverlap" title="成份股比較" modal-class="cp-overlap-modal" @close="showOverlap = false">
      <div class="cp-overlap">
        <ul>
          <li v-for="pair in overlapPairs" :key="pair.a + pair.b"><span><b :class="colorOf(pair.a)">{{ pair.a }}</b> × <b :class="colorOf(pair.b)">{{ pair.b }}</b></span><strong>重疊 {{ pair.weight.toFixed(1) }}%</strong><small>共同持股 {{ pair.count }} 檔</small></li>
        </ul>
        <p class="cp-overlap-note">重疊比重是每檔共同持股取兩邊較低的權重後加總，數字越高，兩檔 ETF 的內容越相似。</p>
        <table v-if="sharedHoldings.length">
          <thead><tr><th>代號</th><th>名稱</th><th v-for="etf in etfHoldings" :key="etf.code" class="is-num"><b :class="colorOf(etf.code)">{{ etf.code }}</b></th></tr></thead>
          <tbody>
            <tr v-for="row in sharedHoldings" :key="row.key">
              <td><b>{{ row.key }}</b></td>
              <td :title="row.name">{{ row.name }}</td>
              <td v-for="(weight, i) in row.weights" :key="i" class="is-num">{{ weight == null ? '—' : `${weight.toFixed(2)}%` }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="cp-overlap-note">這幾檔 ETF 沒有共同持股。</p>
      </div>
    </AppModal>
  </div>
</template>

<style scoped>
/* 上方：標題與搜尋同一列，常用標的獨立一列 */
.compare-page .comparison-search-card{flex:none;position:relative;z-index:6;display:grid!important;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:10px 18px;padding:12px 18px;overflow:visible!important}
.cp-search-title{display:flex;align-items:center;gap:4px;margin:0;color:var(--text-strong);font-size:18px;white-space:nowrap}
.stock-search-box,:deep(.stock-search-box){position:relative;min-width:0}
.compare-page .comparison-search-card :deep(.comparison-search-shell){min-height:50px;margin:0;border:2px solid #6C98F0;border-radius:14px;background:#fff;box-shadow:0 6px 16px rgba(60,110,210,.16)}
.compare-page .comparison-search-card :deep(.comparison-search-shell:focus-within){border-color:#3B6FE0}
.compare-page .comparison-search-card :deep(.comparison-search-results){position:absolute;z-index:20;top:calc(100% + 6px);left:0;right:0;margin:0}
.compare-page .comparison-search-card :deep(.comparison-search-results:empty){display:none}
.compare-page .comparison-popular{grid-column:1/-1;display:flex;flex-wrap:nowrap;align-items:center;gap:8px;margin:0;overflow:visible}
.compare-page .comparison-popular > span{flex:none;color:var(--muted);font-weight:700}
.compare-page .comparison-popular button{flex:0 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
:global(body[data-theme="dark"][data-page="compare"] .page-host .page.compare-page .comparison-search-shell){border:2px solid #7FA8F2!important;background:#22314D!important}
:global(body[data-theme="dark"] .compare-page .comparison-search-results){background:#2B3C5C!important}

/* 比較表：0～3 檔同一個版面，不捲動 */
.cp-empty{flex:1;min-height:0;display:flex;flex-direction:column;gap:10px;margin:0;padding:12px 18px;overflow:hidden}
.cp-head{flex:none;display:flex;align-items:center;gap:12px}
.cp-symbol{flex:none;display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue)}
.cp-head > div:first-of-type{flex:1;min-width:0}
.cp-actions{flex:none;display:flex;gap:8px}
.cp-c0{--cp:#2F6FDE}
.cp-c1{--cp:#C2701C}
.cp-c2{--cp:#8A4FD0}
:global(body[data-theme="dark"] .cp-c0){--cp:#8DB4F5}
:global(body[data-theme="dark"] .cp-c1){--cp:#F0B070}
:global(body[data-theme="dark"] .cp-c2){--cp:#C7A2F2}
.cp-head h2{margin:0;color:var(--text-strong);font-size:18px}
.cp-head p{margin:2px 0 0;color:var(--muted);font-size:13px}
.cp-table{position:relative;flex:1;min-height:0;display:grid;grid-template-columns:128px repeat(3,minmax(0,1fr));grid-template-rows:auto repeat(8,minmax(0,1fr));padding:0 14px 2px;border:1.5px solid #E2C3B5;border-radius:14px;background:var(--pw-inner)}
.cp-row{display:contents}
.cp-cell{display:flex;align-items:center;min-width:0;min-height:0;padding:0 14px;border-bottom:1px solid var(--line);border-right:1px solid var(--line);font-size:14px;color:var(--text)}
.cp-cell:first-child{padding-left:0}
.cp-cell:last-child{padding-right:0;border-right:0}
.cp-cell.is-last{border-bottom:0}
.cp-cell.is-head{padding-top:7px;padding-bottom:7px}
.cp-label{color:var(--text);font-size:13px;font-weight:700}
.cp-label.is-head{color:var(--muted);font-size:12px}
.cp-cell > i{display:block;width:100%;height:8px;border-radius:5px;background:color-mix(in srgb,var(--blue) 11%,transparent)}
.cp-value{overflow:hidden;color:var(--text-strong);text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}
.cp-stock{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;min-height:38px;padding:0 4px 0 10px;border:1.5px solid var(--cp);border-radius:10px;background:color-mix(in srgb,var(--cp) 10%,transparent)}
.cp-stock-name{display:flex;align-items:baseline;gap:6px;min-width:0;padding:0;border:0;background:transparent;cursor:pointer}
.cp-stock-name b{color:var(--cp);font-size:16px}
.cp-research{padding:0;border:0;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
.cp-research:hover,.cp-research:focus-visible{text-decoration:underline}
:global(.modal.cp-overlap-modal){display:flex;flex-direction:column;overflow:hidden;width:min(680px,calc(100vw - 32px))}
:global(.modal.cp-overlap-modal > .modal-header){flex:none}
:global(.modal.cp-overlap-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto;padding:14px 24px 20px}
.cp-overlap ul{display:grid;gap:6px;margin:0;padding:0;list-style:none}
.cp-overlap li{display:grid;grid-template-columns:minmax(0,1fr) auto 110px;align-items:center;gap:12px;padding:8px 12px;border-radius:10px;background:var(--pw-inner)}
.cp-overlap li strong{color:var(--text-strong)}
.cp-overlap li small{color:var(--muted);text-align:right}
.cp-overlap b{color:var(--text-strong)}
.cp-overlap b[class^="cp-c"]{color:var(--cp)}
.cp-overlap-note{margin:8px 0 10px;color:var(--muted);font-size:13px}
.cp-overlap table{width:100%;border-collapse:separate;border-spacing:0;font-size:14px;color:var(--text)}
.cp-overlap th{padding:8px 6px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;font-weight:600;text-align:left}
.cp-overlap td{max-width:220px;padding:7px 6px;overflow:hidden;border-bottom:1px solid color-mix(in srgb,var(--line) 55%,transparent);text-overflow:ellipsis;white-space:nowrap}
.cp-overlap .is-num{text-align:right;font-variant-numeric:tabular-nums}
.cp-stock-name span{overflow:hidden;color:var(--muted);font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.cp-stock-name:hover b,.cp-stock-name:focus-visible b{color:var(--blue);text-decoration:underline}
.cp-remove{flex:none;width:26px;height:26px;border:0;border-radius:50%;background:transparent;color:var(--muted);font-size:17px;line-height:1;cursor:pointer}
.cp-remove:hover,.cp-remove:focus-visible{background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
.cp-slot{display:flex;align-items:center;justify-content:center;gap:6px;width:100%;min-height:38px;border:1.5px dashed #D8B7A6;border-radius:10px;background:rgba(255,255,255,.6);color:var(--blue);font-size:13px;font-weight:700;cursor:pointer}
.cp-slot:hover,.cp-slot:focus-visible{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 7%,transparent)}
.cp-slot b{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:color-mix(in srgb,var(--blue) 14%,transparent);font-size:12px}
/* 空資料提示：蓋在表格下半部中間，用漸層淡掉後面的占位條，不佔表格位置 */
.cp-blank{position:absolute;inset:0;grid-column:3 / span 1;grid-row:2 / span 8;display:grid;align-content:center;justify-items:center;gap:2px;background:radial-gradient(ellipse 48% 42% at 50% 50%,var(--pw-inner) 78%,transparent);text-align:center;white-space:nowrap;pointer-events:none}
.cp-blank-art{width:92px;margin-bottom:4px}
.cp-blank strong{color:var(--text-strong);font-size:15px}
.cp-blank span{padding:0 10px;background:var(--pw-inner);color:var(--muted);font-size:13px}
/* 用絕對定位蓋在第二、三欄上，不佔表格位置，欄位才不會被擠開 */
.cp-need{position:absolute;top:50%;left:calc(142px + (100% - 156px) * 2 / 3);transform:translate(-50%,-30%);display:grid;gap:3px;padding:14px 26px;border:1.5px solid #E2C3B5;border-radius:14px;background:var(--surface-solid,#fff);box-shadow:0 8px 20px rgba(70,50,90,.12);text-align:center;white-space:nowrap}
.cp-need strong{color:var(--text-strong);font-size:16px}
:global(body[data-theme="dark"] .cp-slot){background:transparent}
:global(body[data-theme="dark"] .cp-need){background:#2B3C5C}
@media (max-width:900px){
  .compare-page .comparison-search-card{grid-template-columns:1fr}
  .compare-page .comparison-popular{flex-wrap:wrap}
  .cp-empty{flex:none}
  .cp-table{overflow-x:auto;grid-template-columns:96px repeat(3,minmax(110px,1fr));grid-template-rows:none;grid-auto-rows:minmax(38px,auto)}
}
</style>
