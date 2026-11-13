import { reactive, computed, ref } from 'vue'
import { api } from '@/api/client.js'
import { addRecord, markDeleted, tokensOf } from './footprint.js'
import { toast, settings, notify, preferencesPayload } from './ui.js'
import { notifyQuota, isQuotaError } from './alerts.js'
import { storageKey } from '../api/runtime.js'

// 對應舊版 js/data.js 的 ResearchStore 與 js/research.js 的 requestBackendResearch。
// 只保留後端研究模式（舊版的示範動畫模式已不使用）；資料存在獨立的 localStorage 鍵。
const STORE_KEY = storageKey('pinwise_vue_research')
const RECENT_MS = 7 * 24 * 60 * 60 * 1000
// 每秒查一次進度：訪客模式每人每分鐘有 API 呼叫上限，太密會把額度用在輪詢上。
const POLL_MS = 1000
const POLL_RETRY_MS = 4000
const POLL_MAX_MISSES = 6
const TERMINAL = ['completed', 'failed', 'cancelled']

export const PHASES = [
  { key: 'understanding', label: '理解問題與條件' },
  { key: 'planning', label: '規劃任務' },
  { key: 'tools', label: '選擇資料工具' },
  { key: 'data', label: '取得與核對資料' },
  { key: 'verification', label: '資料缺漏與替代處理' },
  { key: 'metrics', label: '計算指標' },
  { key: 'analysis', label: 'Gemini 分析' },
  { key: 'validation', label: '輸出檢核' },
  { key: 'persistence', label: '保存報告及證據' },
]

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || '[]')
    return Array.isArray(saved) ? saved : []
  } catch {
    return []
  }
}

export const research = reactive({
  tasks: load(), // 新的在前
  activeId: '',
  // 送出研究前的確認視窗：{ kind: 'ambiguous' | 'redirect', query, result }
  dialog: null,
})
research.activeId = research.tasks.find((t) => !t.deletedAt)?.id || ''

// 每秒更新一次，讓「已執行時間」持續跳動。
export const clock = ref(Date.now())
setInterval(() => (clock.value = Date.now()), 1000)

let saveTimer = 0
function save() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(research.tasks.slice(0, 50)))
    } catch {}
  }, 200)
}

export const visibleTasks = computed(() => research.tasks.filter((t) => !t.deletedAt))
export const activeTask = computed(() => visibleTasks.value.find((t) => t.id === research.activeId) || null)
export const recentTasks = computed(() => {
  const now = clock.value
  return visibleTasks.value.filter((t) => now - Date.parse(t.createdAt) < RECENT_MS)
})

export const isCompleted = (task) => task?.status === 'completed' || task?.progress >= 100

export function statusLabel(task) {
  return ({
    completed: '已完成', failed: '失敗', cancelled: '已取消', paused: '已暫停',
    pause_requested: '等待安全暫停', cancel_requested: '等待安全取消',
  })[task.status] || '研究中'
}

export function elapsedMs(task) {
  if (!task?.createdAt) return 0
  const start = Date.parse(task.activeStartedAt)
  const live = task.running && Number.isFinite(start) ? Math.max(0, clock.value - start) : 0
  return Math.max(0, (task.activeElapsedMs || 0) + live)
}

export function durationText(task) {
  if (!task?.createdAt) return '尚未開始'
  const backend = Number(task.backendDurationMs)
  const elapsed = TERMINAL.includes(task.status) && task.backendDurationMs != null && backend >= 0 ? backend : elapsedMs(task)
  if (elapsed < 1000) return '< 1 秒'
  const s = Math.ceil(elapsed / 1000)
  if (s >= 86400) return `${Math.floor(s / 86400)} 天 ${Math.floor((s % 86400) / 3600)} 小時`
  if (s >= 3600) return `${Math.floor(s / 3600)} 小時 ${Math.floor((s % 3600) / 60)} 分`
  return `${Math.floor(s / 60)} 分 ${String(s % 60).padStart(2, '0')} 秒`
}

export function formatDate(iso) {
  const d = new Date(iso)
  if (!Number.isFinite(d.getTime())) return '—'
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// 舊版紀錄的每日額度錯誤，改成較清楚的說明。
export function failureText(task) {
  return String(task?.failureMessage || '')
    .replace('此訪客的 Gemini 每日 token 預算不足，本次未送出', 'PINWISE 設定的本工作階段 Gemini 每日 token 預算不足；本次未送出，限制於下一個 UTC 日重置')
    .replace('此訪客的 Gemini 每日呼叫上限已達，本次未送出', 'PINWISE 設定的本工作階段 Gemini 每日呼叫上限已達；本次未送出，限制於下一個 UTC 日重置')
}

// 股票代號 → 名稱：來自輸入理解的候選與市場日行情證據。
export function symbolName(task, code) {
  const fromInput = task.inputUnderstanding?.candidates?.find((c) => c.symbol === code)?.name
  if (fromInput) return fromInput
  for (const record of task.sourceRecords || [])
    for (const item of record.data || []) if (item?.symbol === code && item.name) return item.name
  return ''
}

function applyJob(task, job) {
  const terminal = TERMINAL.includes(job.status)
  Object.assign(task, {
    jobId: job.id,
    status: job.status,
    progress: Number(job.progress) || 0,
    currentStage: job.current_phase || 'understanding',
    running: !terminal && !['paused'].includes(job.status),
    failed: job.status === 'failed',
    failureMessage: job.error?.message || null,
    failureCode: job.error?.code || null,
    failureRetryable: job.error?.retryable !== false,
    backendModel: job.model,
    agentTrace: job.events || [],
    sourceRecords: job.evidence?.length ? job.evidence : task.sourceRecords,
    metrics: job.metrics || task.metrics,
    backendDurationMs: job.duration_ms ?? null,
    usage: job.usage || task.usage || {},
    updatedAt: new Date().toISOString(),
  })
  const result = job.result
  if (result) {
    Object.assign(task, {
      summary: result.summary,
      risks: result.risks || [],
      invalidationConditions: result.invalidation_conditions || [],
      watchItems: result.watch_items || [],
      limitations: result.limitations || [],
      sourceRecords: result.evidence || [],
      metrics: result.metrics || {},
      candidates: result.candidates || [],
      backendModel: result.model,
      backendDurationMs: result.duration_ms,
      dataMode: result.data_mode,
      verificationStatus: result.verification_status || 'unverified',
    })
  }
  if (terminal || job.status === 'paused') {
    task.activeElapsedMs = elapsedMs(task)
    task.activeStartedAt = null
  }
  if (job.status === 'completed') {
    task.progress = 100
    task.completedAt = task.completedAt || new Date().toISOString()
  }
  recordResearch(task)
  save()
}

// 研究通知：完成或失敗時留下通知（不在研究頁或頁面在背景時才增加未讀）。
// id 規則：完成 research_<研究id>（同一份研究只通知一次）；
// 失敗 research_failed_<研究id>_<這次執行的工作編號>（重試後再失敗會再通知一次）。
const shorten = (text, max = 48) => (text && text.length > max ? `${text.slice(0, max)}…` : text || '')
function notifyResearch(task, outcome, message = '') {
  // 停在研究頁也通知：研究常要等一兩分鐘，使用者可能在看別的東西。
  if (outcome !== 'completed' && isQuotaError(`${task.failureCode || ''} ${message}`)) notifyQuota(failureText(task) || message)
  if (!settings.notificationPrefs.research) return
  const topic = shorten(task.query, 30)
  if (outcome === 'completed') {
    const parts = []
    const count = task.candidates?.length
    if (count) parts.push(`共 ${count} 檔`)
    const coverage = task.metrics?.coverage?.completeness_pct
    if (Number.isFinite(coverage)) parts.push(`資料覆蓋 ${coverage}%`)
    const risk = task.risks?.[0]
    notify({
      id: `research_${task.id}`, type: 'research', taskId: task.id, title: 'AI 標的研究已完成',
      body: `「${topic}」${parts.length ? `：${parts.join('、')}` : '已完成'}${risk ? `。主要風險：${shorten(risk)}` : ''}`,
    })
  } else {
    notify({
      id: `research_failed_${task.id}_${task.jobId || Date.now()}`, type: 'research', taskId: task.id,
      title: 'AI 標的研究失敗', body: `「${topic}」${shorten(message, 60) || '未完成'}${task.failureRetryable === false ? '' : '。可到研究頁重試。'}`,
    })
  }
}

const polling = new Set()
async function poll(task) {
  if (polling.has(task.id) || TERMINAL.includes(task.status)) return
  polling.add(task.id)
  try {
    let job = task.jobId ? await api.researchJob(task.jobId) : await api.createResearchJob(task)
    applyJob(task, job)
    // 單次查詢進度失敗（網路抖動、訪客每分鐘呼叫上限）不直接判定研究失敗：放慢後再查，連續失敗多次才放棄。
    let misses = 0
    while (!TERMINAL.includes(job.status) && job.status !== 'paused' && !task.deletedAt) {
      await new Promise((resolve) => setTimeout(resolve, misses ? POLL_RETRY_MS : POLL_MS))
      try {
        job = await api.researchJob(job.id)
        misses = 0
      } catch (error) {
        if (++misses >= POLL_MAX_MISSES) throw error
        continue
      }
      applyJob(task, job)
    }
    if (job.status === 'completed') {
      toast('AI 標的研究已完成，可以前往查看結果囉！', 4200)
      notifyResearch(task, 'completed')
    }
    else if (job.status === 'failed') {
      toast(`研究失敗：${job.error?.message || '請檢查資料來源與設定'}`)
      notifyResearch(task, 'failed', job.error?.message || '請檢查資料來源與設定')
    }
    else if (job.status === 'cancelled') toast('研究已在安全工作邊界取消')
  } catch (error) {
    Object.assign(task, {
      status: 'failed', failed: true, running: false, failureCode: 'network_error', failureRetryable: true,
      failureMessage: error.message || '後端研究失敗', activeElapsedMs: elapsedMs(task), activeStartedAt: null,
    })
    save()
    toast(`研究失敗：${error.message || '請檢查後端連線與設定'}`)
    notifyResearch(task, 'failed', error.message || '請檢查後端連線與設定')
  } finally {
    polling.delete(task.id)
  }
}

// 重新整理頁面後，接續仍在進行中的研究。
research.tasks.filter((t) => t.jobId && !TERMINAL.includes(t.status) && !t.deletedAt).forEach(poll)

// 沒有後端工作編號、也不在送出中的未完成研究（送出途中頁面被重新整理或關閉）：改成可重試的失敗，避免畫面永遠停在 0%。
function failOrphans() {
  let changed = false
  for (const task of research.tasks) {
    if (task.jobId || task.deletedAt || TERMINAL.includes(task.status) || polling.has(task.id)) continue
    Object.assign(task, {
      status: 'failed', failed: true, running: false, failureCode: 'not_submitted', failureRetryable: true,
      failureMessage: '研究沒有成功送到後端（可能送出時頁面被重新整理），請按重試再送一次',
      activeElapsedMs: elapsedMs(task), activeStartedAt: null,
    })
    changed = true
  }
  if (changed) save()
}
failOrphans()
setInterval(failOrphans, 15000)

// 問卷的「波動感受」換算成研究的風險設定；未完成問卷時不假設（對應舊版 createResearchTask）。
const RISK_BY_TOLERANCE = { 較難接受: '低', 可接受小幅波動: '中等', 可接受明顯波動: '中高', 能承受較大波動: '高' }
const riskFromPreferences = () => (settings.personalPrefs.completed && RISK_BY_TOLERANCE[settings.personalPrefs.riskTolerance]) || '未指定'

export function createTask(query, opts = {}) {
  const now = new Date().toISOString()
  const task = {
    id: `research_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    query: query.trim(),
    requestedSymbols: opts.requestedSymbols || [],
    horizon: opts.horizon || null,
    researchType: opts.researchType || 'unknown',
    researchTopic: opts.researchTopic || null,
    riskPreference: riskFromPreferences(),
    preferences: {
      ...preferencesPayload(),
      ...(opts.focusLabel ? { researchFocus: opts.focusLabel } : {}),
      ...(opts.excludedSymbols?.length ? { excludedSymbols: opts.excludedSymbols } : {}),
    },
    focusLabel: opts.focusLabel || '',
    inputUnderstanding: opts.inputUnderstanding || null,
    status: 'queued', progress: 0, running: true, failed: false,
    failureMessage: null, failureCode: null, failureRetryable: true,
    currentStage: 'understanding', jobId: null,
    summary: null, risks: [], invalidationConditions: [], watchItems: [], limitations: [],
    candidates: opts.requestedSymbols || [], sourceRecords: [], metrics: {}, agentTrace: [],
    createdAt: now, updatedAt: now, completedAt: null, activeElapsedMs: 0, activeStartedAt: now,
  }
  research.tasks.unshift(task)
  research.activeId = task.id
  save()
  // 必須使用 reactive 代理物件，輪詢更新才會反映到畫面。
  const proxy = research.tasks[0]
  poll(proxy)
  return proxy
}

// 針對單一標的建立研究（對應舊版 startStockResearch），追蹤頁「重新評估」使用。
export function researchSymbol(code, name = '') {
  return createTask(`研究 ${code}${name ? ' ' + name : ''} ${isEtfCode(code) ? '的表現與風險' : '的產業位置、主要成長動能與風險'}`, { requestedSymbols: [code], researchType: isEtfCode(code) ? 'etf' : 'single_company' })
}

export async function pause(task) {
  try {
    applyJob(task, await api.pauseResearchJob(task.jobId))
    toast(task.status === 'pause_requested' ? '已要求暫停；進行中的 API 呼叫完成後生效' : '研究已暫停')
    if (task.status === 'pause_requested') poll(task)
  } catch (error) {
    toast(`無法暫停：${error.message}`)
  }
}

export async function resume(task) {
  try {
    applyJob(task, await api.resumeResearchJob(task.jobId))
    task.activeStartedAt = new Date().toISOString()
    poll(task)
  } catch (error) {
    toast(`無法繼續：${error.message}`)
  }
}

export async function cancel(task) {
  try {
    applyJob(task, await api.cancelResearchJob(task.jobId))
    toast(task.status === 'cancel_requested' ? '已要求取消；進行中的 API 呼叫完成後停止' : '研究已取消')
    if (task.status === 'cancel_requested') poll(task)
  } catch (error) {
    toast(`無法取消：${error.message}`)
  }
}

// 失敗後重試：以同一個問題重新建立後端任務。
export function retry(task) {
  Object.assign(task, {
    status: 'queued', failed: false, running: true, failureMessage: null, failureCode: null, jobId: null,
    progress: 0, activeStartedAt: new Date().toISOString(), agentTrace: [],
  })
  poll(task)
}

export function toggle(task) {
  if (task.failed) retry(task)
  else if (['paused', 'pause_requested'].includes(task.status)) resume(task)
  else pause(task)
}

// 足跡只留統計數字；研究題目與報告從瀏覽器和後端一起刪除。
function recordResearch(task) {
  if (task.status !== 'completed' && task.status !== 'failed') return
  const coverage = task.metrics?.coverage || {}
  addRecord({
    id: task.id, kind: 'research', at: task.completedAt || task.updatedAt || task.createdAt, label: task.query,
    symbols: task.requestedSymbols || [], status: task.status, tokens: tokensOf(task.usage),
    coverage: coverage.completeness_pct ?? null, sources: coverage.available_sources || 0, missing: coverage.missing_sources || 0,
    rejected: task.metrics?.output_validation?.rejected_sentence_count || 0, durationMs: task.backendDurationMs ?? null,
  })
}

export function removeTask(id) {
  const task = research.tasks.find((t) => t.id === id)
  if (!task) return
  task.deletedAt = new Date().toISOString() // 讓進行中的輪詢停止
  recordResearch(task)
  markDeleted(id)
  research.tasks = research.tasks.filter((t) => t.id !== id)
  if (research.activeId === id) research.activeId = visibleTasks.value[0]?.id || ''
  save()
  if (task.jobId) api.deleteResearchJob(task.jobId).catch(() => toast('這個瀏覽器的紀錄已刪除，但伺服器副本刪除失敗，請稍後再試。', 4200))
}

// 對應舊版 prepareResearchInput：先由後端理解輸入，再決定建立研究、確認標的或導向其他功能。
export async function beginResearch(query, context = 'research') {
  let result
  try {
    result = await api.understandInput(query, context)
  } catch (error) {
    toast(`後端理解服務無法連線：${error.message}。原問題尚未建立研究。`, 4200)
    return null
  }
  if (result.target_status === 'recognized' || result.target_status === 'not_required') {
    return confirmResearch(query, optionsFromUnderstanding(result))
  }
  research.dialog = {
    kind: result.target_status === 'ambiguous' ? 'ambiguous' : 'redirect',
    reason: /etf/i.test(query) ? 'etf' : '',
    codes: [], query, result,
  }
  return null
}

// 台股 ETF 代號都以 00 開頭，一般股票不會。
export const isEtfCode = (code) => /^00/.test(String(code || ''))

// 標的研究一次只研究一檔（股票或 ETF）：多檔、產業主題與觀念問題改導向適合的功能。
function blockedReason({ requestedSymbols = [], researchType, inputUnderstanding }) {
  if (researchType === 'knowledge' || inputUnderstanding?.intent === 'explain') return 'concept'
  if (requestedSymbols.length > 1) return 'multi'
  if (!requestedSymbols.length) return researchType === 'etf' ? 'etf' : 'theme'
  return ''
}

// 開啟研究範圍確認視窗；使用者確認後回傳建立的研究，取消或被導向其他功能時回傳 null。
export function confirmResearch(query, options) {
  const reason = blockedReason(options)
  if (reason) {
    research.dialog = { kind: 'redirect', reason, query, codes: options.requestedSymbols || [], result: options.inputUnderstanding || {} }
    return Promise.resolve(null)
  }
  const single = options.requestedSymbols[0]
  const confirmed = isEtfCode(single) ? { ...options, researchType: 'etf' } : options
  return new Promise((resolve) => {
    research.dialog = { kind: 'confirm', query, options: confirmed, resolve }
  })
}

// 使用者打錯名稱但系統認得時（國劇 → 國巨），把題目裡的錯字換成正確名稱；沒有錯字回傳 null。
export function typoOf(query, understanding, symbol) {
  const item = understanding?.candidates?.find((c) => c.symbol === symbol)
  if (!item || !['phonetic', 'approximate'].includes(item.match_kind)) return null
  const typed = item.typed_text
  if (!typed || typed === item.matched_text || !query.includes(typed)) return null
  return { typed, name: item.matched_text, corrected: query.replace(typed, item.matched_text) }
}

export function optionsFromUnderstanding(result, symbol = result.selected_symbol) {
  const resolved = (result.resolved_symbols || []).filter(Boolean)
  return {
    requestedSymbols: symbol ? [symbol] : resolved,
    horizon: result.historical_period?.label || null,
    researchType: result.research_type || 'unknown',
    researchTopic: result.research_topic || null,
    inputUnderstanding: result,
  }
}

// 舊版只標記刪除；載入時補進足跡並清掉內容，已完成的研究也補上紀錄。
research.tasks.forEach(recordResearch)
research.tasks.filter((t) => t.deletedAt).forEach((t) => removeTask(t.id))

// Token 用量一直存在後端，早期的研究只是沒帶回瀏覽器；載入時補一次。
async function backfillUsage() {
  const missing = research.tasks.filter((t) => t.jobId && t.status === 'completed' && !t.usage)
  for (const task of missing) {
    try {
      task.usage = (await api.researchJob(task.jobId)).usage || {}
    } catch {
      task.usage = {}
    }
    recordResearch(task)
  }
  if (missing.length) save()
}
backfillUsage()
