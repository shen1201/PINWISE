import { reactive } from 'vue'
import { api } from '@/api/client.js'

// 資料來源狀態（對應舊版 js/api.js 的 sourceHealthState / refreshSourceHealth / checkSourceHealth）。
// /api/sources/status 只讀後端設定、不連外；單一來源檢查才實際連線。
export const HEALTH_LABELS = {
  healthy: '已連線', degraded: '有限可用', stale: '資料過期', pending: '待驗證', not_checked: '尚未驗證',
  checking: '檢查中', fixture: '隔離模式', disabled: '已關閉', error: '連線失敗',
}
export const CONFIG_LABELS = {
  configured: '已設定', optional_anonymous: '匿名免費模式', built_in: '公開來源', fixture: '隔離設定', missing: '未設定', disabled: '已關閉',
}

export const sourceHealth = reactive({ loading: false, checked: false, rows: [], error: '', app: null })

export async function refreshSourceHealth() {
  if (sourceHealth.loading) return
  sourceHealth.loading = true
  sourceHealth.error = ''
  try {
    const [rows, app] = await Promise.all([api.sourceStatus(), api.health()])
    sourceHealth.rows = rows.map((row) => ({ ...row, status: row.connection_status || 'not_checked' }))
    sourceHealth.app = app
    sourceHealth.checked = true
  } catch (error) {
    sourceHealth.error = error.message || '後端未啟動或無法連線'
    sourceHealth.rows = []
  } finally {
    sourceHealth.loading = false
  }
}

export async function checkSource(source) {
  const row = sourceHealth.rows.find((item) => item.source === source)
  if (!row) return
  row.status = 'checking'
  try {
    const [result] = await api.sourceHealth(source)
    Object.assign(row, result, { status: result.status, connection_status: result.status })
  } catch (error) {
    Object.assign(row, { status: 'error', connection_status: 'error', checked_at: new Date().toISOString(), message: error.message || '連線檢查失敗' })
  }
}

// AI 回覆引擎狀態說明（對應舊版 assistantEngineModeHtml）。
export function engineMode() {
  const app = sourceHealth.app
  if (!app) return { title: 'AI 回覆引擎', text: '尚未讀取後端運行模式；不以前端狀態推斷 Gemini 已連線。' }
  const mode = app.gemini_mode || 'disabled'
  if (app.preview_fixture_mode || mode === 'fixture')
    return { title: 'AI 回覆引擎：隔離／預覽模式', text: '使用固定替身資料，不會呼叫真實 Gemini 或外部市場 API。' }
  const call = app.gemini_last_call
  if (mode === 'enabled' && call)
    return {
      title: `AI 回覆引擎：${call.http_status === 200 ? '真實 Gemini 生成已驗證' : '真實 Gemini 呼叫失敗'}`,
      text: `${call.model} · HTTP ${call.http_status || '未取得回應'} · ${call.latency_ms} ms。這是最近一次實際生成紀錄，不代表市場資料完整。`,
    }
  if (mode === 'enabled') return { title: 'AI 回覆引擎：Gemini Provider 已啟用', text: '只代表後端已設定供應者；在單項健康檢查成功前，仍屬「尚未驗證連線」。' }
  return { title: 'AI 回覆引擎：未啟用', text: '後端目前不會呼叫 Gemini，且不會回退為示範回答。' }
}
