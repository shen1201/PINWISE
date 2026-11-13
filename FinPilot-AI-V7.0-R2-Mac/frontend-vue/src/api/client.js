// 對應舊版 js/api.js 的 FinPilotAPI；API 網址與存取權杖由 runtime.js 依 runtime-config.js 決定。
import { config, accessMode, apiUrl, accessHeaders, clearAccess, renewAccess, TUNNEL_HEADERS } from './runtime.js'

const TIMEOUT_MS = 45000
const ASSISTANT_TIMEOUT_MS = Number(config.assistantTimeoutMs) || 105000
const ACCOUNT_TOKEN_KEY = 'finpilot_account_session'

function headers(extra = {}) {
  let account = ''
  try {
    account = localStorage.getItem(ACCOUNT_TOKEN_KEY) || ''
  } catch {}
  return { 'Content-Type': 'application/json', ...TUNNEL_HEADERS, ...accessHeaders(), ...(account ? { 'X-FinPilot-Session': account } : {}), ...extra }
}

// 送出請求；訪客工作階段過期（401）時自動重新申請一次，權杖被拒（401/403）時清掉本分頁保存的權杖。
async function send(path, init) {
  // cache: 'no-store'：不使用瀏覽器快取，避免拿到之前暫時失敗（例如沒有 K 線）的舊回應。
  const perform = () => fetch(apiUrl(path), { cache: 'no-store', ...init, credentials: 'omit', headers: headers(init.headers) })
  let response = await perform()
  if (response.status === 401 && accessMode === 'demo-session') {
    await renewAccess()
    response = await perform()
  }
  if (response.status === 401 || response.status === 403) clearAccess()
  return response
}

// 合併外部 signal 與逾時，回傳 { signal, timedOut(), cleanup() }。
function withTimeout(external, ms) {
  const controller = new AbortController()
  let timedOut = false
  const onAbort = () => controller.abort()
  if (external?.aborted) controller.abort()
  else external?.addEventListener('abort', onAbort, { once: true })
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, ms)
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    cleanup() {
      clearTimeout(timer)
      external?.removeEventListener('abort', onAbort)
    },
  }
}

async function request(path, { timeoutMs = TIMEOUT_MS, signal, ...options } = {}) {
  const guard = withTimeout(signal, timeoutMs)
  try {
    const response = await send(path, { ...options, signal: guard.signal })
    const isJson = (response.headers.get('content-type') || '').includes('json')
    // 成功狀態卻不是 JSON（例如被通道服務的警告頁攔下）時明確報錯，不當成「成功但沒有資料」。
    if (response.ok && response.status !== 204 && !isJson) throw new Error('收到的不是 API 資料（可能被通道警告頁攔截），請重新整理再試')
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || payload.message || `後端回傳 HTTP ${response.status}`)
    return payload
  } catch (error) {
    if (error.name === 'AbortError' && guard.timedOut()) throw new Error('後端請求逾時')
    throw error
  } finally {
    guard.cleanup()
  }
}

// 讀取 SSE：每個以空行分隔的區塊取 `data: ` 那一行解析成 JSON。
async function streamAssistant(payload, onEvent, { signal } = {}) {
  const guard = withTimeout(signal, ASSISTANT_TIMEOUT_MS)
  const emit = (block) => {
    const line = block.split('\n').find((item) => item.startsWith('data: '))
    if (line) onEvent(JSON.parse(line.slice(6)))
  }
  try {
    const response = await send('/api/assistant/stream', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal: guard.signal,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(error.detail || `助手後端回傳 HTTP ${response.status}`)
    }
    if (!response.body) throw new Error('瀏覽器無法讀取助手串流')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() || ''
      blocks.forEach(emit)
      if (done) break
    }
    if (buffer.trim()) emit(buffer)
  } catch (error) {
    if (error.name === 'AbortError' && guard.timedOut()) throw new Error('助手串流逾時；已保留收到的文字')
    throw error
  } finally {
    guard.cleanup()
  }
}

// 研究任務請求內容（對應舊版 researchPayload）。
function researchPayload(task) {
  return {
    query: task.query,
    symbols: task.requestedSymbols || [],
    research_type: task.researchType || 'unknown',
    research_topic: task.researchTopic || null,
    horizon: task.horizon || null,
    risk_preference: task.riskPreference || null,
    preferences: task.preferences || {},
  }
}

const job = (id, suffix = '') => `/api/research/jobs/${encodeURIComponent(id)}${suffix}`

export const api = {
  health: () => request('/api/health'),
  twseNews: (limit = 20) => request(`/api/news/rss?limit=${limit}`, { timeoutMs: 20000 }),
  marketIndexHistory: () => request('/api/market/index-history', { timeoutMs: 20000 }),
  marketOverview: (refresh = false) => request(`/api/market/overview${refresh ? '?refresh=true' : ''}`, { timeoutMs: 30000 }),
  understandInput: (text, context = 'research') =>
    request('/api/input/understand', { method: 'POST', body: JSON.stringify({ text, context, default_history_months: 6 }) }),
  streamAssistant,
  createResearchJob: (task) => request('/api/research/jobs', { method: 'POST', body: JSON.stringify(researchPayload(task)) }),
  researchJob: (id) => request(job(id)),
  pauseResearchJob: (id) => request(job(id, '/pause'), { method: 'POST' }),
  resumeResearchJob: (id) => request(job(id, '/resume'), { method: 'POST' }),
  cancelResearchJob: (id) => request(job(id), { method: 'DELETE' }),
  deleteResearchJob: (id) => request(job(id, '/record'), { method: 'DELETE' }),
  sendFeedback: (entry) => request('/api/feedback', { method: 'POST', body: JSON.stringify(entry) }),
  selectStocks: (conditions) => request('/api/stocks/select', { method: 'POST', body: JSON.stringify(conditions) }),
  aiSelectStocks: (payload) => request('/api/stocks/ai-select', { method: 'POST', body: JSON.stringify(payload), timeoutMs: 90000 }),
  stockOverview: (code, months = 6) => request(`/api/stocks/${encodeURIComponent(code)}/overview?months=${months}`, { timeoutMs: 30000 }),
  esg: (code) => request(`/api/esg/${encodeURIComponent(code)}`, { timeoutMs: 25000 }),
  esgSummaries: (codes) => request(`/api/esg?symbols=${encodeURIComponent(codes.join(','))}`, { timeoutMs: 25000 }),
  etfHoldings: (code) => request(`/api/etf/${encodeURIComponent(code)}/holdings`, { timeoutMs: 20000 }),
  sourceStatus: () => request('/api/sources/status'),
  sourceHealth: (source) => request(`/api/sources/health?source=${encodeURIComponent(source)}`),
  accountMe: () => request('/api/auth/me', { timeoutMs: 5000 }),
  accountSubmit: (kind, username, password) => request(`/api/auth/${kind}`, { method: 'POST', body: JSON.stringify({ username, password }) }),
  accountLogout: () => request('/api/auth/logout', { method: 'POST' }),
  stockSnapshots: (symbols) => request('/api/stocks/snapshots', { method: 'POST', body: JSON.stringify({ symbols }) }),
  // 以代號、名稱搜尋上市櫃股票與 ETF（對應舊版 searchComparisonBackend）。
  searchStocks: (query) =>
    request('/api/stocks/select', {
      method: 'POST',
      body: JSON.stringify({ query, product_type: 'all', market: 'all', industry: null, period: null, risk: null, limit: 8 }),
    }),
}
