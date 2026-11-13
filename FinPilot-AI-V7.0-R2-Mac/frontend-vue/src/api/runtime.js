// 執行環境設定與後端存取權（對應舊版 js/preview-access.js 的 FinPilotRuntime）。
// 設定來自 index.html 先載入的 runtime-config.js：本機由 FastAPI 動態產生，Netlify 由建置腳本寫入。
// 存取模式：
//   local         本機同源，不需權杖
//   shared-token  需輸入分享者提供的預覽權杖
//   demo-session  自動向後端申請短期訪客工作階段（inviteRequired 時需先輸入邀請碼）
export const config = Object.freeze({ ...(window.FINPILOT_CONFIG || {}) })
export const accessMode = String(config.accessMode || (config.requirePreviewToken ? 'shared-token' : 'local'))

const TOKEN_KEY = 'finpilot_preview_token_session'
const SCOPE_KEY = 'finpilot_demo_storage_scope'
const LOCAL_HOST = /^(localhost|127(?:\.\d+){3}|\[::1\])$/i

let token = ''
try {
  token = sessionStorage.getItem(TOKEN_KEY) || ''
} catch {}

// 訪客模式下每個分頁各自一份資料範圍，避免同一台展示電腦的訪客看到彼此的紀錄。
let clientScope = ''
try {
  clientScope = sessionStorage.getItem(SCOPE_KEY) || ''
  if (!clientScope) {
    clientScope = (crypto.randomUUID?.() || `${Date.now()}_${Math.random().toString(36).slice(2)}`)
      .replace(/[^A-Za-z0-9_-]/g, '')
      .slice(0, 48)
    sessionStorage.setItem(SCOPE_KEY, clientScope)
  }
} catch {
  clientScope = Math.random().toString(36).slice(2)
}

function normalizedBase() {
  const raw = String(config.apiBaseUrl || '').trim().replace(/\/$/, '')
  if (!raw) return ''
  const parsed = new URL(raw, location.href)
  if (!LOCAL_HOST.test(location.hostname) && LOCAL_HOST.test(parsed.hostname)) throw new Error('線上預覽的 API 不可指向訪客電腦的 localhost')
  if (location.protocol === 'https:' && parsed.protocol !== 'https:') throw new Error('HTTPS 預覽只能連線 HTTPS API')
  return parsed.origin + parsed.pathname.replace(/\/$/, '')
}

// 設定錯誤（例如 API 指向 localhost）在啟動時就檢查，入口畫面會直接顯示。
export const configError = (() => {
  try {
    normalizedBase()
    return ''
  } catch (error) {
    return error.message
  }
})()

export function apiUrl(path) {
  const base = normalizedBase()
  return base ? new URL(path, base + '/').href : path
}

export const currentToken = () => token
export const accessHeaders = () => (token ? { Authorization: `Bearer ${token}` } : {})

function saveToken(value) {
  token = value
  try {
    value ? sessionStorage.setItem(TOKEN_KEY, value) : sessionStorage.removeItem(TOKEN_KEY)
  } catch {}
}

export const clearAccess = () => saveToken('')

async function errorDetail(response, fallback) {
  const payload = await response.json().catch(() => ({}))
  return new Error(payload.detail || `${fallback}（HTTP ${response.status}）`)
}

// 透過 ngrok 免費網域公開展示時，ngrok 會對瀏覽器的 GET 請求先回一頁警告 HTML（不帶 cookie 的 API 請求永遠過不去）。
// 帶上這個標頭即可略過警告頁；不經過 ngrok 時伺服器會忽略它。
export const TUNNEL_HEADERS = { 'ngrok-skip-browser-warning': '1' }

// 用權杖呼叫 /api/health 確認仍有效；有效才保存。
export async function verifyToken(value) {
  const response = await fetch(apiUrl('/api/health'), {
    headers: { ...TUNNEL_HEADERS, Authorization: `Bearer ${value}` },
    cache: 'no-store',
    credentials: 'omit',
  })
  if (!response.ok) throw await errorDetail(response, 'API 驗證失敗')
  saveToken(value)
  return response.json()
}

// 向後端申請訪客工作階段。
export async function issueSession(invite = '') {
  const response = await fetch(apiUrl('/api/demo/session'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...TUNNEL_HEADERS, ...(invite ? { 'X-FinPilot-Invite': invite } : {}) },
    cache: 'no-store',
    credentials: 'omit',
  })
  if (!response.ok) throw await errorDetail(response, '無法建立訪客工作階段')
  const payload = await response.json()
  if (!payload.access_token) throw new Error('後端未回傳訪客工作階段')
  saveToken(payload.access_token)
  return payload
}

// 請求收到 401 時重新申請工作階段；需要邀請碼的模式無法自動重來，請使用者重新整理。
export async function renewAccess() {
  if (accessMode !== 'demo-session') return false
  clearAccess()
  if (config.inviteRequired) throw new Error('訪客工作階段已到期，請重新整理頁面並輸入邀請碼')
  await issueSession()
  return true
}

// 本機模式啟動時不需要入口畫面。
export const needsAccessGate = () => Boolean(configError) || accessMode === 'demo-session' || Boolean(config.requirePreviewToken)

// localStorage 鍵加上資料範圍：本機模式維持原鍵名（既有資料不受影響）；
// 隔離預覽與訪客模式各自分開，訪客模式再依分頁區分。
export function storageKey(base) {
  const mode = config.dataMode || (config.previewMode ? 'fixture' : 'live')
  if (mode === 'live' && accessMode === 'local') return base
  return `${base}_${mode}${accessMode === 'demo-session' ? '_' + clientScope : ''}`
}
