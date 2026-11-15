<script setup>
import FeedbackBar from '@/components/FeedbackBar.vue'
import PrefsBadge from '@/components/PrefsBadge.vue'
import MetricFlag from '@/components/MetricFlag.vue'
import { computed, ref } from 'vue'
import { toast } from '@/stores/ui.js'
import { formatDate, failureText, symbolName } from '@/stores/research.js'
import { isCompared, isTracked, toggleCompare, toggleTrack, trackWatchItems } from '@/stores/workspace.js'
import ResearchMetricChart from './ResearchMetricChart.vue'
import ResearchCoverageMatrix from './ResearchCoverageMatrix.vue'
import AppModal from '@/components/AppModal.vue'
import InfoTip from '@/components/InfoTip.vue'

// 研究結果四個分頁（對應舊版 resultTabBody：summary / risk / evidence / trace）。
const props = defineProps({
  task: { type: Object, required: true },
  section: { type: String, required: true },
  inline: { type: Boolean, default: false }, // 直接顯示在研究頁下方（不是彈窗）
})
defineEmits(['navigate'])

const t = computed(() => props.task)
const ended = computed(() => ['completed', 'failed', 'cancelled'].includes(t.value.status))
// 觀察條件連同標的加入追蹤（對應舊版 trackWatchItems）。
function trackWatch(items) {
  const saved = trackWatchItems(items, t.value.id)
  toast(saved ? `已加入追蹤，並保存 ${saved} 個觀察條件` : '這些觀察條件沒有對應的個別標的')
}

// ── 研究摘要 ───────────────────────────────────────────
const candidates = computed(() => (t.value.candidates || []).map((code) => ({ code, name: symbolName(t.value, code) })))

function insight(code) {
  const m = t.value.metrics?.[code]
  if (m) {
    const parts = []
    if (Number.isFinite(m.observations)) parts.push(`${m.observations} 筆日資料`)
    if (m.period_start && m.period_end) parts.push(`${m.period_start} ～ ${m.period_end}`)
    if (Number.isFinite(m.period_return_pct)) parts.push(`期間報酬 ${m.period_return_pct}%`)
    if (Number.isFinite(m.annualized_volatility_pct)) parts.push(`年化波動 ${m.annualized_volatility_pct}%`)
    if (Number.isFinite(m.revenue_yoy_pct)) parts.push(`${m.revenue_month || '最新'} 月營收年增 ${m.revenue_yoy_pct}%`)
    if (Number.isFinite(m.eps_ytd)) parts.push(`${m.eps_period || '累計'} EPS ${m.eps_ytd} 元`)
    if (Number.isFinite(m.pe_ratio)) parts.push(`本益比 ${m.pe_ratio} 倍`)
    if (Number.isFinite(m.dividend_yield_pct)) parts.push(`殖利率 ${m.dividend_yield_pct}%`)
    if (parts.length) return `${t.value.dataMode === 'fixture' ? '隔離計算' : '已取得並計算'}：${parts.join('、')}。`
  }
  return ended.value ? '已納入本次後端研究；詳細數據與缺漏請查看資料與來源。' : '資料取得與計算中，完成後顯示程式計算結果。'
}

const nameMap = computed(() => Object.fromEntries(candidates.value.map((s) => [s.code, s.name])))

// 資料限制改寫成長度相近（約 26～32 字）、可單獨讀懂的完整句子，不需要再開完整說明
const LIMIT_SHORT = [
  [/產業代碼|產業分類/, () => '交易所產業分類範圍較廣，個別公司的產品關聯仍需逐一核對。'],
  [/財務資料為官方|完整財報/, () => '財務只含本益比、殖利率、月營收與累計 EPS，未含完整財報細項。'],
  [/綜合損益|EPS|獲利能力|營業利益率/, () => '部分公司的 EPS 或營業利益率資料不完整，獲利比較僅供參考。'],
  [/重大訊息|法說/, () => '部分公司本期間沒有重大訊息或法說會資料，質化分析可能不足。'],
  [/模型輸出.*?(\d+)\s*句/, (m) => `AI 回答中有 ${m[1]} 句數字無法與資料對證，已自動排除不顯示。`],
  [/歷史日價|歷史行情/, () => '部分公司的歷史日價資料不足，未計算區間報酬與波動指標。'],
  [/未取得|無法取得|缺漏/, () => '部分資料來源本次未能取得，相關結論只使用成功取得的資料。'],
]
const shortLimit = (text) => {
  for (const [re, make] of LIMIT_SHORT) {
    const m = String(text).match(re)
    if (m) return make(m)
  }
  return String(text).split(/[；;。]/)[0]
}
// 資料限制：逐項「代號 資料集：原因」已由覆蓋矩陣呈現，這裡只保留通用說明並去除重複句。
const limitationList = computed(() => {
  const inMatrix = new Set(records.value.filter((r) => r.subjects?.length === 1).map((r) => r.source))
  const seen = new Set()
  return (t.value.limitations || []).filter((text) => {
    const head = String(text).split('：')[0]
    if (inMatrix.has(head)) return false
    const norm = String(text).replace(/[\s，。；、,.;]/g, '')
    if (seen.has(norm)) return false
    seen.add(norm)
    return true
  })
})

const trustTitle = computed(() => {
  const task = t.value
  if (task.dataMode === 'fixture') return '隔離測試結果'
  if (task.verificationStatus === 'sourced') return '已取得預定證據，仍有能力限制'
  if (task.dataMode === 'unverified' || !task.dataMode) return '舊紀錄／尚未驗證'
  return '有限度分析，資料尚不完整'
})
const coverage = computed(() => t.value.metrics?.coverage)
const trustNote = computed(() => (t.value.dataMode === 'fixture'
  ? '此結果使用 Fixture，不代表真實 Gemini 或市場 API 已連線。'
  : '完成研究流程不等於全部結論已驗證；請對照「資料與來源」及風險中的資料限制。')
  + (coverage.value ? `\n覆蓋率＝已取得的真實／快取證據 ÷ 本次預定項目（${coverage.value.available_sources}/${coverage.value.total_sources}）；Gemini 不計入，較舊資料 ${coverage.value.stale_sources || 0} 項另行標記。` : ''))

// 研究摘要：第一句當結論，完整內容放彈窗
const conclusion = computed(() => {
  const text = String(t.value.summary || '')
  const first = text.split(/(?<=。)/)[0] || text
  return first.length > 120 ? `${first.slice(0, 118)}…` : first
})
const subModal = ref('') // summary | charts
// 問題寫了檔數但報告標的數不同（修正前產生的舊報告會發生）時提示
const askedCount = computed(() => {
  const m = String(t.value.query || '').match(/(\d{1,2}|[一二三四五六七八九十兩]{1,3})\s*(?:檔|家|支|隻)/)
  if (!m) return null
  const map = { 一: 1, 二: 2, 兩: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 }
  return Number(m[1]) || map[m[1]] || null
})
const countMismatch = computed(() => askedCount.value && candidates.value.length && askedCount.value !== candidates.value.length)
// 重點表格：每欄最高／最低標色
// [欄位, 標題, 單位, 顯示正負號, 評比門檻 { good, watch }, 說明]
// 只有明顯超出一般範圍才標示：👍 表現突出、⚠ 值得留意；多數格子不標，僅供參考。
const COLS = [
  ['period_return_pct', '期間報酬', '%', true, { good: (v) => v >= 20, watch: (v) => v <= -15 },
    '本次研究期間內的股價漲跌，不含股利。\n漲超過 20% 標 👍、跌超過 15% 標 ⚠。\n過去表現不代表未來，短期大漲也可能伴隨較高風險。'],
  ['annualized_volatility_pct', '年化波動', '%', false, { good: (v) => v < 20, watch: (v) => v >= 80 },
    '股價一年內常見的起伏幅度。\n低於 20% 標 👍（相當平穩）、80% 以上標 ⚠（起伏非常大）。\n波動大不一定不好，但持有時帳面變化會比較劇烈，請評估自己能承受的程度。'],
  ['revenue_yoy_pct', '月營收年增', '%', true, { good: (v) => v >= 80, watch: (v) => v <= -10 },
    '最新月營收和去年同月相比。\n成長 80% 以上標 👍、衰退超過 10% 標 ⚠。\n單月數字可能受季節或一次性因素影響，建議連續觀察幾個月。'],
  ['pe_ratio', '本益比', ' 倍', false, { good: (v) => v <= 12, watch: (v) => v >= 60 },
    '股價 ÷ 每股盈餘，反映市場願意為每 1 元獲利付多少錢。\n12 倍以下標 👍（評價相對保守）、60 倍以上標 ⚠（評價明顯偏高）。\n高本益比常見於市場看好成長的公司；低本益比也可能是市場預期獲利下滑，請搭配營收與產業狀況判斷。'],
]
const tableRows = computed(() => candidates.value.map((s) => ({ ...s, m: t.value.metrics?.[s.code] || {} })))
// 依門檻評比：超過「突出」門檻標 good（👍）、超過「留意」門檻標 watch（⚠），其餘不標
const verdict = (key, v) => {
  if (!Number.isFinite(v)) return ''
  const rule = COLS.find(([k]) => k === key)?.[4]
  if (rule?.good(v)) return 'good'
  if (rule?.watch(v)) return 'watch'
  return ''
}
// 單一標的的大數字卡：只列有資料的指標；ETF 沒有營收與本益比，不留空格。
const TILES = [
  ['period_return_pct', '期間報酬', '%', true, () => '期間股價變化，不含股利'],
  ['annualized_volatility_pct', '年化波動', '%', false, () => '一年內常見的起伏幅度'],
  ['max_drawdown_pct', '最大回撤', '%', false, () => '從高點跌到低點的最大跌幅'],
  ['revenue_yoy_pct', '月營收年增', '%', true, (m) => `${m.revenue_month || '最新'} 月，與去年同月相比`],
  ['revenue_ytd_yoy_pct', '累計營收年增', '%', true, () => '今年累計，與去年同期相比'],
  ['pe_ratio', '本益比', ' 倍', false, () => '股價是每股盈餘的幾倍'],
  ['pb_ratio', '股價淨值比', ' 倍', false, () => '股價是每股淨值的幾倍'],
  ['dividend_yield_pct', '殖利率', '%', false, () => '以目前股價計算的現金股利'],
  ['eps_ytd', '累計 EPS', ' 元', true, (m) => m.eps_period || '今年累計每股盈餘'],
  ['period_high', '區間最高收盤', ' 元', false, () => '本次研究期間的最高收盤'],
  ['period_low', '區間最低收盤', ' 元', false, () => '本次研究期間的最低收盤'],
  ['average_volume_shares', '平均成交量', '', false, () => '期間每日平均成交張數'],
]
const TILE_LIMIT = 6
const singleInline = computed(() => props.inline && candidates.value.length === 1)
const singleTiles = computed(() => {
  const m = t.value.metrics?.[candidates.value[0]?.code] || {}
  return TILES.filter(([key]) => Number.isFinite(m[key])).slice(0, TILE_LIMIT).map(([key, label, unit, signed, note]) => ({
    key, label,
    text: key === 'average_volume_shares' ? `${Math.round(m[key] / 1000).toLocaleString('zh-TW')} 張` : fmtCell(m[key], unit, signed),
    note: note(m),
    tip: COLS.find(([k]) => k === key)?.[5] || '',
    flag: verdict(key, m[key]),
    tone: key === 'period_return_pct' ? (m[key] > 0 ? 'price-up' : m[key] < 0 ? 'price-down' : '') : '',
  }))
})
const cellClass = (key, v) => (verdict(key, v) ? `is-${verdict(key, v)}` : '')
const fmtCell = (v, unit, signed) => (Number.isFinite(v) ? `${signed && v > 0 ? '+' : ''}${Math.round(v * 100) / 100}${unit}` : '—')
const periodNote = computed(() => {
  const m = t.value.metrics?.[candidates.value[0]?.code] || {}
  return `${m.period_start ? `資料期間 ${m.period_start} ～ ${m.period_end}，約 ${m.observations || 0} 筆日資料；營收為 ${m.revenue_month || '最新'} 月。\n` : ''}👍 代表該指標超過「表現突出」的參考門檻，⚠ 代表值得留意；各欄門檻請看欄名旁的 ⓘ。標示只是參考，請搭配自己的投資目標判斷。`
})

// ── 資料與來源 ─────────────────────────────────────────
const SOURCES = [
  ['M', 'MOPS', '公司基本資料／每日公告'],
  ['T', 'TWSE', '上市日行情'],
  ['P', 'TPEx', '上櫃日行情'],
  ['F', 'FinMind', '歷史日價'],
  ['N', '新聞', '交易所市場新聞'],
  ['法', '法說會', '每日法說公告'],
]

function sourceGroup(record = {}) {
  const text = `${record.source || ''} ${record.title || ''}`
  const provider = record.provider || record.data?.[0]?.metadata?.source || ''
  if (/法說/.test(text)) return '法說會'
  if (/新聞|RSS/.test(text + ' ' + provider)) return '新聞'
  if (/公司基本|重大訊息|MOPS/.test(text)) return 'MOPS'
  if (/歷史日?行情|FinMind/.test(text + ' ' + provider)) return 'FinMind'
  if (/TPEx/.test(provider)) return 'TPEx'
  if (/TWSE/.test(provider) || (record.missing && /市場日?行情/.test(text))) return 'TWSE'
  return ''
}

const records = computed(() => (Array.isArray(t.value.sourceRecords) ? t.value.sourceRecords : []))
const groups = computed(() => {
  const rows = SOURCES.map(([icon, name, desc]) => {
    const items = records.value.filter((r) => sourceGroup(r) === name)
    const available = items.some((r) => !r.missing && ['real', 'cache'].includes(r.data_status))
    const fixture = items.some((r) => r.data_status === 'fixture')
    const state = !items.length ? 'missing' : available ? 'connected' : fixture ? 'queued' : 'missing'
    const status = !items.length ? '未取得' : available ? '已取得' : fixture ? '隔離資料' : '資料缺漏／未驗證'
    return { icon, name, desc, status, state, items }
  })
  const other = records.value.filter((r) => !sourceGroup(r))
  if (other.length) rows.push({ icon: '＋', name: '其他來源', desc: '補充核對項目', status: '已取得', state: 'connected', items: other })
  return rows
})
const selectedSource = ref(0)

const urlSafe = (r) => /^https?:\/\//i.test(r?.url || '') && !/\.invalid(?:[/:]|$)/i.test(r.url)
const verified = (r) => !r?.missing && ['real', 'cache'].includes(r?.data_status) && !/^gemini$/i.test(r.provider || r.source || '') && urlSafe(r)
const DATA_STATUS = { real: '即時取得', cache: '快取', fixture: '隔離資料，非市場證據', missing: '缺失', unverified: '尚未驗證' }


// ── Agent 執行紀錄 ────────────────────────────────────
const traceStatus = computed(() => ({
  completed: '已完成', failed: '失敗', cancelled: '已取消', pause_requested: '等待安全暫停',
  paused: '已暫停', cancel_requested: '等待安全取消',
})[t.value.status] || '進行中')

// 同時只展開一個步驟。
// 執行紀錄合併成 7 個階段；每階段一行摘要，點開才看細項（原始事件全部保留）。
const STAGES = [
  ['understanding', '理解問題', ['understanding']],
  ['planning', '規劃任務', ['planning']],
  ['tools', '選擇工具', ['tools']],
  ['data', '取得資料', ['data', 'verification']],
  ['metrics', '計算指標', ['metrics']],
  ['analysis', 'Gemini 分析', ['analysis']],
  ['validation', '檢核與保存', ['validation', 'persistence']],
]
const stages = computed(() => {
  const events = t.value.agentTrace || []
  return STAGES.map(([key, label, phases]) => {
    const list = events.filter((e) => phases.includes(e.phase))
    // 同一動作有「開始」又有「完成」時只留完成那筆
    const done = new Set(list.filter((e) => e.status !== 'started').map((e) => e.action))
    const items = list.filter((e) => e.status !== 'started' || !done.has(e.action))
    const failed = items.filter((e) => e.status === 'failed').length
    const running = items.some((e) => e.status === 'started') && !ended.value
    const ms = items.reduce((sum, e) => sum + (Number(e.duration_ms) || 0), 0)
    let summary = items.filter((e) => e.status !== 'started').at(-1)?.detail || ''
    if (key === 'data' && items.length) {
      const fetched = items.filter((e) => e.phase === 'data' && e.status === 'completed')
      const withData = fetched.filter((e) => (e.metadata?.record_count ?? 1) > 0).length
      summary = `${fetched.length} 項資料：${withData} 項取得、${fetched.length - withData} 項本期間無資料${failed ? `、${failed} 項失敗` : ''}`
    }
    if (key === 'planning' && items[0]?.metadata?.symbols?.length) summary = `研究 ${items[0].metadata.symbols.length} 檔：${items[0].metadata.symbols.join('、')}`
    const status = !items.length ? (ended.value ? 'skipped' : 'waiting') : failed ? 'failed' : running ? 'running' : 'completed'
    return { key, label, items, status, summary, seconds: ms ? (ms / 1000).toFixed(ms < 1000 ? 2 : 1) : '' }
  })
})
// 取得資料成功但 0 筆（例如本期間沒有法說會）：標「!」而不是打勾
const isEmptyFetch = (e) => e.phase === 'data' && e.status === 'completed' && e.metadata?.record_count === 0
const STAGE_STATUS = { completed: '已完成', failed: '有失敗', running: '進行中', waiting: '等待中', skipped: '未執行' }
const openTrace = ref('')
function onToggle(event, key) {
  if (event.target.open) openTrace.value = key
  else if (openTrace.value === key) openTrace.value = ''
}
</script>

<template>
  <div class="research-section-content" :class="{ 'rs-inline': inline }" :data-section="section">
    <!-- 研究摘要 -->
    <template v-if="section === 'summary'">
      <div :class="{ 'rs-inline-head': inline }">
        <h2 v-if="inline">研究摘要</h2>
        <div class="rs-trust">
          <strong>{{ trustTitle }}</strong>
          <InfoTip :text="trustNote" label="資料完整度" />
        </div>
        <small v-if="inline && coverage">已驗證證據 {{ coverage.completeness_pct }}%（{{ coverage.available_sources }}/{{ coverage.total_sources }} 項）</small>
        <FeedbackBar v-if="inline" class="rs-feedback" :item-id="t.id" feature="research" prompt="這份研究有幫助嗎？" />
      </div>
      <PrefsBadge v-if="t.summary" class="rs-prefs" :prefs="t.preferences" label="這份研究參考了你的偏好" />
      <section v-if="!t.summary" class="card surface-solid">
        <div class="card-body">
          <div class="empty-state research-waiting">
            <template v-if="t.status === 'failed' || t.status === 'cancelled'">
              <strong>沒有可顯示的研究摘要</strong>
              <small>{{ failureText(t) || '任務未完成，系統不會用示範內容取代真實結果。' }}</small>
            </template>
            <template v-else>
              <strong>等待 Gemini 依已取得資料完成分析。</strong>
              <small>目前進度 {{ Math.round(t.progress) }}%，內容會隨這份研究的進度更新。</small>
            </template>
          </div>
        </div>
      </section>
      <div v-else class="rs-summary">
        <!-- 一句話結論 -->
        <section class="rs-box rs-conclusion">
          <p v-if="countMismatch" class="rs-mismatch">⚠ 你要求 {{ askedCount }} 檔，這份較早產生的報告含 {{ candidates.length }} 檔，結論可能只描述其中幾檔；重新研究即可依檔數產生。</p>
          <span>研究結論</span>
          <p>{{ conclusion }}</p>
          <button class="card-link" type="button" @click="subModal = 'summary'">看完整說明 ›</button>
        </section>

        <!-- 重點表格 -->
        <!-- 單一標的：直接用大數字呈現，不用只有一列的表格 -->
        <section v-if="singleInline" class="rs-box rs-table-box rs-tiles-box">
          <div class="rs-box-head">
            <h3>重點指標<InfoTip :text="periodNote" label="重點指標說明" /></h3>
            <div class="rs-tiles-actions">
              <button class="card-link" type="button" @click="toggleTrack(candidates[0].code, 'research')">{{ isTracked(candidates[0].code) ? '✓ 已追蹤' : '＋ 追蹤' }}</button>
              <button class="card-link" type="button" @click="toggleCompare(candidates[0].code)">{{ isCompared(candidates[0].code) ? '✓ 比較中' : '比較' }}</button>
              <button class="card-link" type="button" @click="subModal = 'charts'">查看各指標圖表 ›</button>
            </div>
          </div>
          <div class="rs-tiles" :class="`n-${singleTiles.length}`">
            <article v-for="tile in singleTiles" :key="tile.key">
              <span>{{ tile.label }}<InfoTip v-if="tile.tip" :text="tile.tip" :label="tile.label" /><MetricFlag :metrics="t.metrics?.[candidates[0]?.code]" :field="tile.key" /></span>
              <strong :class="tile.tone">{{ tile.text }}</strong>
              <small :title="tile.note"><b v-if="tile.flag" :class="`is-${tile.flag}`">{{ tile.flag === 'good' ? '表現突出' : '值得留意' }}</b>{{ tile.note }}</small>
            </article>
          </div>
        </section>
        <section v-else class="rs-box rs-table-box">
          <div class="rs-box-head">
            <h3>{{ candidates.length > 1 ? `${candidates.length} 檔重點比較` : '重點指標' }}<InfoTip :text="periodNote" label="表格說明" /></h3>
            <button v-if="candidates.length" class="card-link" type="button" @click="subModal = 'charts'">查看各指標圖表 ›</button>
          </div>
          <table class="rs-table">
            <thead><tr><th>標的</th><th v-for="[key, label, , , , tip] in COLS" :key="key" class="num"><span class="rs-th">{{ label }}<InfoTip :text="tip" :label="label" /></span></th><th class="act"></th></tr></thead>
            <tbody>
              <tr v-for="r in tableRows" :key="r.code">
                <td><strong>{{ r.code }}</strong> {{ r.name }}</td>
                <td v-for="[key, , unit, signed] in COLS" :key="key" class="num" :class="cellClass(key, r.m[key])"><i v-if="verdict(key, r.m[key])" class="rs-thumb" :aria-label="verdict(key, r.m[key]) === 'good' ? '表現突出' : '值得留意'">{{ verdict(key, r.m[key]) === 'good' ? '👍' : '⚠' }}</i>{{ fmtCell(r.m[key], unit, signed) }}</td>
                <td class="act">
                  <button class="card-link" type="button" @click="toggleTrack(r.code, 'research')">{{ isTracked(r.code) ? '✓ 已追蹤' : '＋ 追蹤' }}</button>
                  <button class="card-link" type="button" @click="toggleCompare(r.code)">{{ isCompared(r.code) ? '✓ 比較中' : '比較' }}</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="!candidates.length" class="empty-state">尚無符合這項提問的標的；可調整研究問題。</div>
        </section>

        <!-- 右欄：主要風險＋觀察條件 -->
        <aside class="rs-side">
          <section class="rs-box rs-risk">
            <span>主要待核對風險</span>
            <p>{{ t.risks?.[0] || '請核對資料來源與風險。' }}</p>
          </section>
          <section v-if="t.watchItems?.length" class="rs-box rs-watch">
            <div class="rs-box-head">
              <h3>後續觀察條件<InfoTip text="觀察條件由 AI 依本次證據提出並經數字檢核；加入追蹤後會顯示在「我的追蹤」與「公告與事件」。" label="觀察條件" /></h3>
              <button v-if="t.watchItems.some((w) => w.symbol)" class="card-link" type="button" @click="trackWatch(t.watchItems)">全部追蹤</button>
            </div>
            <ul>
              <li v-for="(w, i) in t.watchItems" :key="i">
                <b>{{ w.symbol || '—' }}</b>
                <span :title="w.item">{{ w.item }}</span>
                <InfoTip :text="w.why ? `${w.item}\n${w.why}` : w.item" label="觀察條件" />
                <button v-if="w.symbol" class="card-link" type="button" @click="trackWatch([w])">{{ isTracked(w.symbol) ? '✓ 已追蹤' : '追蹤' }}</button>
              </li>
            </ul>
          </section>
        </aside>
      </div>

      <AppModal :open="subModal === 'summary'" title="完整研究說明" modal-class="rs-sub-modal" backdrop-class="rs-sub-backdrop" @close="subModal = ''">
        <p class="rs-sub-text">{{ t.summary }}</p>
        <small class="rs-sub-note">Gemini 分析不是獨立來源；已核對的證據只列在「資料與來源」。</small>
      </AppModal>
      <AppModal :open="subModal === 'charts'" title="各指標圖表" modal-class="rs-sub-modal rs-sub-wide" backdrop-class="rs-sub-backdrop" @close="subModal = ''">
        <ResearchMetricChart :stocks="candidates" :metrics="t.metrics" />
      </AppModal>
    </template>

    <!-- 風險與反方證據 -->
    <template v-else-if="section === 'risk'">
      <section v-if="!t.risks?.length" class="card surface-solid">
        <div class="card-body">
          <div class="empty-state research-waiting">
            <template v-if="t.status === 'failed' || t.status === 'cancelled'">
              <strong>沒有可顯示的風險分析</strong>
              <small>{{ t.failureMessage || '任務未完成，系統不會用示範風險取代真實分析。' }}</small>
            </template>
            <template v-else>
              <strong>等待分析完成；實際模式以研究結果標記為準。</strong>
              <small>目前進度 {{ Math.round(t.progress) }}%，內容會隨這份研究的進度更新。</small>
            </template>
          </div>
        </div>
      </section>
      <div v-else class="rs-risk-grid">
        <!-- 左：判斷用的內容 -->
        <div class="rs-col">
          <section class="rs-box">
            <div class="rs-box-head">
              <h3>主要風險</h3>
              <span class="tag" :class="t.dataMode === 'live' ? 'good' : 'demo'">{{ t.dataMode === 'fixture' ? '隔離分析' : t.dataMode === 'live' ? 'Gemini 分析（非來源）' : '尚未驗證' }}</span>
            </div>
            <div class="rs-risk-list">
              <article v-for="(risk, i) in t.risks" :key="i"><b>{{ i + 1 }}</b><p>{{ risk }}</p></article>
            </div>
          </section>
          <section class="rs-box">
            <div class="rs-box-head">
              <h3>可能讓原判斷失效的條件<InfoTip text="當已核對資料觸發這些條件時，建立新任務重新取得資料，不覆蓋舊報告。" label="重新評估時機" /></h3>
            </div>
            <ul class="rs-cond-list">
              <li v-for="(r, i) in t.invalidationConditions?.length ? t.invalidationConditions : t.risks" :key="i">{{ r }}</li>
            </ul>
          </section>
        </div>
        <!-- 右：資料完整度 -->
        <div class="rs-col">
          <ResearchCoverageMatrix :records="records" :names="nameMap" />
          <section v-if="limitationList.length" class="rs-box rs-limits">
            <div class="rs-box-head"><h3>⚠ {{ limitationList.length }} 項資料限制</h3></div>
            <ol>
              <li v-for="(text, i) in limitationList" :key="i">{{ shortLimit(text) }}</li>
            </ol>
          </section>
        </div>
      </div>
    </template>

    <!-- 資料與來源 -->
    <template v-else-if="section === 'evidence'">
      <div class="rs-ev-grid">
        <!-- 左：來源清單（點選切換右側明細） -->
        <section class="rs-box">
          <div class="rs-box-head"><h3>{{ records.length ? '資料來源' : '預計核對的來源' }}</h3><small class="rs-muted">點選查看明細</small></div>
          <div class="rs-src-list" role="listbox" aria-label="資料來源">
            <button
              v-for="(row, i) in groups"
              :key="row.name"
              type="button"
              class="rs-src"
              :class="[`is-${row.state}`, { 'is-selected': selectedSource === i }]"
              :aria-selected="String(selectedSource === i)"
              @click="selectedSource = i"
            >
              <i aria-hidden="true"></i>
              <span><b>{{ row.name }}</b><small>{{ row.desc }}</small></span>
              <em>{{ row.items.filter((r) => !r.missing).length }}／{{ row.items.length }}</em>
            </button>
          </div>
        </section>
        <!-- 右：KPI＋所選來源明細 -->
        <div class="rs-col">
          <section class="rs-ev-kpis">
            <span><small>已取得</small><b>{{ records.filter(verified).length }}</b></span>
            <span><small>本期間無資料</small><b>{{ records.filter((r) => r.missing).length }}</b></span>
            <span><small>預定項目</small><b>{{ records.length }}</b></span>
          </section>
          <section v-if="groups[selectedSource]" class="rs-box" aria-live="polite">
            <div class="rs-box-head">
              <h3>{{ groups[selectedSource].name }}<span class="rs-src-state">{{ groups[selectedSource].status }}</span></h3>
              <InfoTip text="來源網址、取得時間、資料期間及缺漏狀態由後端保留；摘要仍需自行核對原文。" label="資料保存" />
            </div>
            <table class="rs-ev-table">
              <tbody>
                <tr v-for="(r, i) in groups[selectedSource].items.filter((x) => !x.missing)" :key="i">
                  <td><b>{{ r.subjects?.join('、') || '全市場' }}</b> <small>{{ String(r.source || '').replace(/^\d{4,6}\s*/, '') }}</small></td>
                  <td>{{ r.latest_data_at ? `資料日 ${r.latest_data_at}` : (r.period_end || '—') }}</td>
                  <td><small>{{ DATA_STATUS[r.data_status || 'unverified'] }}</small></td>
                  <td class="act"><small>{{ r.provider || '' }}</small></td>
                </tr>
              </tbody>
            </table>
            <p v-if="groups[selectedSource].items.some((x) => x.missing)" class="rs-ev-missing">
              本期間無資料：{{ groups[selectedSource].items.filter((x) => x.missing).map((x) => x.source || x.subjects?.join('、')).join('、') }}
            </p>
            <p v-if="!groups[selectedSource].items.length" class="rs-muted">這項來源目前沒有資料。</p>
          </section>
          <details class="rs-task-id"><summary>任務編號與建立時間</summary><code>{{ t.jobId || t.id }}</code> · {{ formatDate(t.createdAt) }}</details>
        </div>
      </div>
    </template>

    <!-- Agent 執行紀錄：7 個階段 -->
    <template v-else>
      <section class="card surface-solid agent-operation-card rs-stage-card">
        <div class="rs-stage-head">
          <strong>{{ t.query }}</strong>
          <span>{{ traceStatus }} · 共 {{ t.agentTrace?.length || 0 }} 筆原始紀錄，依 7 個階段整理</span>
        </div>
        <ol class="rs-stages">
          <li v-for="(st, i) in stages" :key="st.key" class="rs-stage" :class="`is-${st.status}`">
            <details :open="openTrace === st.key" @toggle="onToggle($event, st.key)">
              <summary>
                <span class="rs-stage-no">{{ i + 1 }}</span>
                <span class="rs-stage-name">{{ st.label }}</span>
                <span class="rs-stage-status">{{ STAGE_STATUS[st.status] }}</span>
                <span class="rs-stage-summary" :title="st.summary">{{ st.summary }}</span>
                <span class="rs-stage-time">{{ st.seconds ? `${st.seconds} 秒` : '' }}</span>
                <span v-if="st.items.length" class="rs-stage-more" aria-hidden="true"></span>
              </summary>
              <ul class="rs-stage-items">
                <li v-for="(e, j) in st.items" :key="e.id || j" :class="{ 'is-empty': isEmptyFetch(e) }">
                  <b :class="isEmptyFetch(e) ? 'is-empty' : `is-${e.status}`" :title="isEmptyFetch(e) ? '本期間沒有這類資料（不是錯誤）' : ''">{{ e.status === 'failed' ? '✕' : e.status === 'started' ? '…' : isEmptyFetch(e) ? '!' : '✓' }}</b>
                  <span>{{ e.action || e.message }}</span>
                  <small>{{ isEmptyFetch(e) ? '本期間無資料' : e.detail }}</small>
                </li>
              </ul>
            </details>
          </li>
        </ol>
      </section>
    </template>
  </div>
</template>

<style scoped>
.rs-stage-card{padding:16px 18px}
.rs-stage-head{display:grid;gap:2px;margin-bottom:12px}
.rs-stage-head strong{color:var(--text-strong);font-size:17px}
.rs-stage-head span{color:var(--muted);font-size:13px}
.rs-stages{margin:0;padding:0;list-style:none;display:grid;gap:8px}
.rs-stage details{border:1px solid var(--line);border-radius:14px;background:color-mix(in srgb,var(--blue) 3%,transparent)}
.rs-stage summary{display:grid;grid-template-columns:30px 110px 70px minmax(0,1fr) 64px 18px;align-items:center;gap:10px;padding:12px 14px;list-style:none;cursor:pointer}
.rs-stage summary::-webkit-details-marker{display:none}
.rs-stage-no{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue);font-weight:800;font-size:13px}
.rs-stage-name{color:var(--text-strong);font-weight:800}
.rs-stage-status{justify-self:start;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;background:color-mix(in srgb,var(--green) 13%,transparent);color:var(--green)}
.is-failed .rs-stage-status{background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
.is-running .rs-stage-status{background:color-mix(in srgb,var(--orange) 15%,transparent);color:#b06a12}
.is-waiting .rs-stage-status,.is-skipped .rs-stage-status{background:color-mix(in srgb,var(--muted) 15%,transparent);color:var(--muted)}
.rs-stage-summary{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text);font-size:14px}
.rs-stage-time{text-align:right;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.rs-stage-more::before{content:"▾";color:var(--muted)}
.rs-stage details[open] .rs-stage-more::before{content:"▴"}
.rs-stage-items{margin:0;padding:4px 14px 12px 54px;list-style:none;display:grid;gap:4px;max-height:180px;overflow:auto}
.rs-stage-items li{display:grid;grid-template-columns:18px minmax(0,220px) minmax(0,1fr);gap:8px;font-size:13px;color:var(--text)}
.rs-stage-items b{color:var(--green)}
.rs-stage-items b.is-failed{color:var(--red)}
.rs-stage-items b.is-empty{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;background:color-mix(in srgb,var(--orange) 18%,transparent);color:#b06a12;font-size:11px}
.rs-stage-items li.is-empty small{color:#b06a12}
.rs-stage-items small{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-trust{display:inline-flex;align-items:center;gap:4px;margin-bottom:8px;padding:4px 12px;border-radius:999px;background:color-mix(in srgb,var(--blue) 9%,transparent);color:var(--blue);font-size:13px}
.rs-summary{display:grid;grid-template-columns:minmax(0,1fr) 320px;grid-template-areas:"c c" "t s";gap:10px}
.rs-conclusion{grid-area:c}
.rs-table-box{grid-area:t}
.rs-side{grid-area:s;display:grid;gap:12px;align-content:start}
.rs-box{padding:14px 16px;border:1px solid var(--line);border-radius:16px;background:var(--surface-solid,rgba(255,255,255,.96))}
.rs-box > span{display:block;margin-bottom:4px;color:var(--muted);font-size:12px;font-weight:700}
.rs-box-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
.rs-box-head h3{display:flex;align-items:center;margin:0;color:var(--text-strong);font-size:17px}
.rs-box-head .card-link{font-size:14px}
.rs-mismatch{margin:0 0 8px!important;padding:6px 10px;border-radius:8px;background:color-mix(in srgb,var(--orange) 12%,transparent);color:#8a4f0a!important;font-size:13px!important;font-weight:600!important}
.rs-conclusion p{margin:0 0 4px;color:var(--text-strong);font-size:16px;font-weight:700;line-height:1.6}
.rs-table{width:100%;border-collapse:collapse;font-size:14px}
.rs-table th{padding:6px 6px;border-bottom:1px solid var(--line);color:var(--muted);font-size:12px;text-align:left;white-space:nowrap}
.rs-table td,.rs-table th{overflow:visible!important;text-overflow:clip!important;max-width:none!important}
.rs-table td{padding:7px 6px;border-bottom:1px solid var(--line);color:var(--text);white-space:nowrap}
.rs-table tr:last-child td{border-bottom:0}
.rs-table .num{text-align:right;font-variant-numeric:tabular-nums}
.rs-table .act{text-align:right}
.rs-table .act .card-link{margin-left:10px;font-size:13px}
.rs-table td.is-good{color:#13795b;font-weight:800;background:color-mix(in srgb,var(--green) 10%,transparent)}
.rs-table td.is-watch{color:#a85f0c;font-weight:800;background:color-mix(in srgb,var(--orange) 11%,transparent)}
.rs-thumb{margin-right:4px;font-style:normal;font-size:13px}
.rs-th{display:inline-flex;align-items:center;gap:2px}
.rs-th b{margin-left:2px;color:var(--blue);font-size:12px}
.rs-th :deep(.info-tip){width:16px;height:16px;font-size:12px}
.rs-risk p{margin:0;color:var(--text);font-size:14px;line-height:1.6}
.rs-risk{border-color:color-mix(in srgb,var(--red) 25%,transparent);background:color-mix(in srgb,var(--red) 5%,transparent)}
.rs-watch ul{margin:0;padding:0;list-style:none;display:grid;gap:6px}
/* 固定四欄：代號｜條件｜ⓘ｜追蹤，ⓘ 位置不隨文字長短跳動 */
.rs-watch li{display:grid;grid-template-columns:42px minmax(0,1fr) 22px 56px;align-items:center;gap:6px;font-size:14px;line-height:1.5;color:var(--text)}
.rs-watch li b{color:var(--text-strong);font-variant-numeric:tabular-nums}
.rs-watch li span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rs-watch li .card-link{justify-self:end;font-size:13px;white-space:nowrap}
.rs-sub-text{margin:0;line-height:1.8;color:var(--text)}
.rs-sub-note{display:block;margin-top:10px;color:var(--muted)}
:global(.modal.rs-sub-modal){width:min(640px,calc(100vw - 32px));z-index:130}
:global(.modal-backdrop.rs-sub-backdrop){z-index:120}
:global(.modal.rs-sub-wide){width:min(960px,calc(100vw - 32px))}
/* 直接顯示在研究頁下方：壓縮間距，整塊放進固定高度 */
.rs-inline{display:flex;flex-direction:column;height:100%;min-height:0}
.rs-inline-head{flex:none;display:flex;align-items:center;gap:10px;margin-bottom:6px}
.rs-inline-head .rs-feedback{margin-left:auto}
.rs-inline-head h2{margin:0;color:var(--text-strong);font-size:17px}
.rs-inline-head .rs-trust{margin:0;padding:2px 10px}
.rs-inline-head small{color:var(--muted);font-size:12px}
.rs-inline .rs-summary{flex:1;min-height:0;grid-template-rows:auto minmax(0,1fr);grid-template-columns:minmax(0,1fr) 330px;gap:8px}
.rs-inline .rs-box{min-height:0;padding:8px 12px;border-radius:13px}
.rs-inline .rs-box-head{margin-bottom:2px}
.rs-inline .rs-conclusion > span{display:none}
.rs-inline .rs-conclusion{display:flex;flex-wrap:wrap;align-items:baseline;gap:0 10px}
.rs-inline .rs-conclusion p{margin:0;font-size:17px;line-height:1.55}
.rs-inline .rs-table-box{overflow:auto}
.rs-tiles-box{display:flex;flex-direction:column}
.rs-tiles-box .rs-box-head h3{font-size:18px}
.rs-tiles-actions{display:flex;gap:14px}
.rs-tiles-actions .card-link{min-height:0;padding:0;font-size:14.5px;white-space:nowrap}
.rs-tiles{flex:1;min-height:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:minmax(0,1fr);gap:8px}
.rs-tiles.n-4{grid-template-columns:repeat(2,minmax(0,1fr))}
.rs-tiles.n-1,.rs-tiles.n-2{grid-template-columns:repeat(2,minmax(0,1fr))}
.rs-tiles article{display:flex;flex-direction:column;justify-content:center;gap:3px;min-width:0;min-height:0;padding:6px 14px;border-radius:12px;background:var(--surface-solid,#fff);box-shadow:0 2px 8px rgba(30,60,120,.07)}
.rs-tiles span{display:flex;align-items:center;color:var(--muted);font-size:13px;font-weight:700}
.rs-tiles span :deep(.info-tip){width:16px;height:16px;font-size:11px}
.rs-tiles strong:not(.price-up):not(.price-down){color:var(--text-strong)}
.rs-tiles strong{font-size:27px;font-weight:800;line-height:1.15;font-variant-numeric:tabular-nums}
.rs-tiles small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
/* 格子高度不夠時依序縮小：先縮數字，再收小字（滑鼠移上去仍看得到），不讓最後一行被切掉 */
.rs-tiles article{container-type:size}
.rs-tiles article > *{flex:none}
/* 高度是格子內容區（不含上下 6px 內距）：27px 數字需要約 70px，23px 約 64px */
@container (max-height:70px){
  .rs-tiles strong{font-size:23px;line-height:1.1}
}
@container (max-height:62px){
  .rs-tiles strong{font-size:21px}
  .rs-tiles small{display:none}
}
.rs-tiles small b{margin-right:6px;font-weight:800}
.rs-tiles small b.is-good{color:#13795B}
.rs-tiles small b.is-watch{color:#A85F0C}
:global(body[data-theme="dark"] .rs-tiles article){background:#2B3C5C}
:global(body[data-theme="dark"] .rs-tiles small b.is-good){color:#7FE6BE}
:global(body[data-theme="dark"] .rs-tiles small b.is-watch){color:#FFD9A0}
.rs-inline .rs-table{font-size:13px}
.rs-inline .rs-table td,.rs-inline .rs-table th{padding:3px 4px;line-height:1.35}
.rs-inline .rs-table .card-link,.rs-inline .rs-watch .card-link{min-height:0;padding:0;font-size:12px;line-height:1.35}
.rs-inline .rs-table .act .card-link{margin-left:6px}
.rs-inline .rs-table :deep(.info-tip){width:15px;height:15px;font-size:11px}
.rs-inline .rs-side{min-height:0;grid-template-rows:auto minmax(0,1fr);gap:8px}
.rs-inline .rs-risk > span{margin-bottom:2px}
.rs-inline .rs-risk p{display:-webkit-box;overflow:hidden;font-size:14px;line-height:1.55;-webkit-line-clamp:4;-webkit-box-orient:vertical}
.rs-inline .rs-watch{display:flex;flex-direction:column}
.rs-inline .rs-watch ul{flex:1;min-height:0;overflow-y:auto;gap:2px;grid-auto-rows:minmax(24px,1fr);align-content:stretch}
.rs-inline .rs-watch li{grid-template-columns:40px minmax(0,1fr) 18px 50px;font-size:13px;line-height:1.35}
.rs-inline .rs-watch li :deep(.info-tip){width:16px;height:16px;font-size:11px}
@media (max-width:900px){.rs-summary,.rs-inline .rs-summary{grid-template-columns:1fr;grid-template-rows:none;grid-template-areas:"c" "t" "s"}.rs-inline{height:auto}}
/* 手機版高度改成依內容撐開：標題列可換行，指標格子不再用固定高度（container-type:size 會讓格子高度變 0、文字疊在一起） */
@media (max-width:900px){
  .rs-inline-head{flex-wrap:wrap;row-gap:6px}
  .rs-inline-head h2{flex:none;white-space:nowrap}
  .rs-inline-head .rs-feedback{margin-left:0;flex-basis:100%}
  .rs-tiles-box .rs-box-head{flex-wrap:wrap;row-gap:6px}
  .rs-tiles-box .rs-box-head h3{white-space:nowrap}
  .rs-tiles-actions{flex-wrap:wrap;gap:6px 14px}
  .rs-tiles,.rs-tiles.n-4,.rs-tiles.n-1,.rs-tiles.n-2{flex:none;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:auto}
  .rs-tiles article{container-type:normal;min-height:76px;padding:10px 12px}
  .rs-tiles strong{font-size:22px;overflow-wrap:anywhere}
  .rs-tiles span{flex-wrap:wrap;line-height:1.35}
}
/* 風險與來源頁：內容延伸填滿視窗高度，底部只留呼吸空間 */
.research-section-content[data-section="risk"],.research-section-content[data-section="evidence"]{display:flex;flex-direction:column;min-height:calc(min(100dvh - 36px, 760px) - 105px)!important}
.rs-risk-grid{flex:1;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;align-items:stretch}
.rs-col{display:flex;flex-direction:column;gap:12px}
.rs-col > :last-child{flex:1}
.rs-col > .rs-task-id:last-child{flex:none}
.rs-col :deep(.coverage-matrix){margin-top:0}
.rs-limits{border-color:color-mix(in srgb,var(--orange) 35%,transparent);background:color-mix(in srgb,var(--orange) 6%,transparent)}
.rs-limits h3{color:#a85f0c}
.rs-limits ol{margin:0;padding:0;list-style:none;counter-reset:lim;display:grid;gap:8px;font-size:14px;line-height:1.6;color:var(--text)}
.rs-limits li{counter-increment:lim;display:grid;grid-template-columns:22px 1fr;align-items:start;line-height:1.5}
.rs-limits li::before{margin-top:2px;content:counter(lim);display:grid;place-items:center;width:18px;height:18px;border-radius:50%;background:color-mix(in srgb,var(--orange) 20%,transparent);color:#a85f0c;font-size:11px;font-weight:800}
.rs-risk-list{display:grid;gap:8px}
.rs-risk-list article{display:grid;grid-template-columns:24px 1fr;gap:8px;padding:10px 12px;border-left:3px solid var(--red);border-radius:10px;background:color-mix(in srgb,var(--red) 6%,transparent)}
.rs-risk-list b{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--red);color:#fff;font-size:12px}
.rs-risk-list p{margin:0;font-size:14px;line-height:1.6;color:var(--text)}
.rs-cond-list{margin:0;padding-left:18px;display:grid;gap:6px;font-size:14px;line-height:1.6;color:var(--text)}
.rs-limit-btn{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;width:100%;padding:10px 14px;border:1px solid color-mix(in srgb,var(--orange) 35%,transparent);border-radius:12px;background:color-mix(in srgb,var(--orange) 9%,transparent);color:var(--text);text-align:left;cursor:pointer}
.rs-limit-btn span{font-weight:800;color:#a85f0c;white-space:nowrap}
.rs-limit-btn small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.rs-limit-btn b{color:var(--blue);white-space:nowrap}
@media (max-width:900px){.rs-risk-grid{grid-template-columns:1fr}}
.rs-muted{color:var(--muted);font-size:12px}
.rs-ev-grid{flex:1;display:grid;grid-template-columns:320px minmax(0,1fr);gap:12px;align-items:stretch}
.rs-src-list{display:grid;gap:6px}
.rs-src{display:grid;grid-template-columns:10px 1fr auto;align-items:center;gap:10px;padding:9px 12px;border:1px solid var(--line);border-radius:12px;background:transparent;text-align:left;cursor:pointer}
.rs-src:hover{background:color-mix(in srgb,var(--blue) 4%,transparent)}
.rs-src.is-selected{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 7%,transparent)}
.rs-src i{width:10px;height:10px;border-radius:50%;background:var(--green)}
.rs-src.is-missing i{background:var(--red)}
.rs-src.is-queued i{background:var(--orange)}
.rs-src span{display:grid}
.rs-src b{color:var(--text-strong);font-size:14px}
.rs-src small{color:var(--muted);font-size:12px}
.rs-src em{font-style:normal;font-weight:800;color:var(--text-strong);font-variant-numeric:tabular-nums}
.rs-ev-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.rs-ev-kpis span{display:grid;gap:2px;padding:10px 14px;border:1px solid var(--line);border-radius:14px;background:var(--surface-solid,rgba(255,255,255,.96))}
.rs-ev-kpis small{color:var(--muted);font-size:12px}
.rs-ev-kpis b{color:var(--text-strong);font-size:22px}
.rs-src-state{margin-left:8px;padding:1px 8px;border-radius:999px;background:color-mix(in srgb,var(--blue) 9%,transparent);color:var(--blue);font-size:12px;font-weight:700}
.rs-ev-table{width:100%;border-collapse:collapse;font-size:13px}
.rs-ev-table td small{color:var(--muted)}
.rs-ev-table td{padding:7px 6px;border-bottom:1px solid var(--line);color:var(--text);white-space:nowrap}
.rs-ev-table tr:last-child td{border-bottom:0}
.rs-ev-table .act{text-align:right}
.rs-ev-table a{color:var(--blue);font-weight:700}
.rs-ev-missing{margin:8px 0 0;padding:8px 10px;border-radius:10px;background:color-mix(in srgb,var(--red) 6%,transparent);color:var(--text);font-size:13px}
.rs-task-id{color:var(--muted);font-size:12px}
.rs-task-id summary{cursor:pointer}
@media (max-width:900px){.rs-ev-grid{grid-template-columns:1fr}}
</style>
