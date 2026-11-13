import { reactive, computed, watch } from 'vue'
import { api } from '@/api/client.js'
import { settings, toast, preferencesPayload } from './ui.js'
import { storageKey } from '../api/runtime.js'
import { addRecord, markDeleted, shouldAskFeedback, tokensOf } from './footprint.js'
import { notifyQuota, isQuotaError } from './alerts.js'

// 對應舊版 js/ui.js 的 assistantAsk 與 js/state.js 的對話保存。
// 使用獨立的 localStorage 鍵，不會動到舊版前端的資料。
const CONV_KEY = storageKey('pinwise_vue_conversations')
const SESSION_KEY = 'pinwise_vue_current_conversation'

function emptyMemory() {
  return {
    version: 2, confirmed_symbol: null, recent_symbols: [], active_symbols: [], comparison_symbols: [],
    last_intent: null, hypotheses: [], constraints: [], historical_period: null, last_tool_results: [],
    last_verified_claims: [], last_answer_reference: null, as_of: null, expires_at: null, updated_at: null,
    structured_summary: {},
  }
}

const uid = (prefix) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
const now = () => new Date().toISOString()

function makeConversation() {
  const at = now()
  return { id: uid('conversation'), title: '新對話', createdAt: at, updatedAt: at, messages: [], pinned: false, memory: emptyMemory() }
}

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(CONV_KEY) || '[]')
    return Array.isArray(saved) ? saved.filter((c) => Array.isArray(c.messages)) : []
  } catch {
    return []
  }
}

export const assistant = reactive({
  conversations: load(),
  currentId: '',
  view: 'chat', // chat | history | confirmClear
  streams: {}, // conversationId -> { controller, userStopped }
  freshId: '', // 剛收到回答的訊息，只有它會播放淡入
})

// 重新整理時，中斷中的回答標成「已停止」，避免永遠顯示「正在產生」。
assistant.conversations.forEach((c) =>
  c.messages.forEach((m) => {
    if (m.pending) Object.assign(m, { pending: false, stopped: true, completionState: 'stopped', status: '' })
  }),
)

function ensureCurrent() {
  const saved = sessionStorage.getItem(SESSION_KEY)
  const found = assistant.conversations.find((c) => c.id === saved) || assistant.conversations.find((c) => !c.messages.length)
  if (found) assistant.currentId = found.id
  else {
    const c = makeConversation()
    assistant.conversations.unshift(c)
    assistant.currentId = c.id
  }
}
ensureCurrent()

let saveTimer = 0
function save() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(CONV_KEY, JSON.stringify(assistant.conversations))
    } catch {}
  }, 150)
}
watch(() => assistant.currentId, (id) => sessionStorage.setItem(SESSION_KEY, id), { immediate: true })

export const current = computed(() => assistant.conversations.find((c) => c.id === assistant.currentId))
export const isStreaming = computed(() => Boolean(current.value && assistant.streams[current.value.id]))

export function completionLabel(message) {
  if (message.pending) return message.status || '正在準備回答…'
  if (message.completionState === 'stopped') return '已由你停止 · 回答可能不完整'
  if (message.completionState === 'failed' || message.error) return message.partial ? '中途失敗 · 已保留部分回答' : '回答失敗'
  if (message.completionState === 'clarification') return '需要你的確認'
  if (message.completionState === 'completed' && message.verification === 'source_missing') return '部分資料缺漏'
  if (message.completionState === 'completed') return ''
  return message.status || ''
}

// 回答核對完才會送達，收到就整段顯示；淡入由畫面的 CSS 負責。
function markFresh(message) {
  if (!settings.motion) return
  assistant.freshId = message.id
  clearTimeout(freshTimer)
  freshTimer = setTimeout(() => (assistant.freshId = ''), 1500)
}
let freshTimer = 0

// 分段送達的回答先累積，到齊才一次顯示；否則每段都會讓淡入重播。
function createWriter(message) {
  let buffered = ''
  return {
    enqueue(text) {
      buffered += text || ''
    },
    flush() {
      if (!buffered) return
      markFresh(message)
      message.text += buffered
      buffered = ''
      save()
    },
  }
}

function recordReply(conversation, reply, query) {
  addRecord({ id: reply.id, kind: 'assistant', at: reply.at, label: query.slice(0, 60), conversationId: conversation.id, status: 'completed', tokens: tokensOf(reply.usage) })
}
const forgetReplies = (conversation) => conversation.messages.forEach((m) => m.role === 'assistant' && markDeleted(m.id))

const appendLine = (message, text) => (message.text += (message.text ? '\n\n' : '') + text)

export async function ask(query, { retryOf = null, onResearchHandoff } = {}) {
  const c = current.value
  if (!c) return false
  if (assistant.streams[c.id]) {
    toast('這個對話仍在回答；可先停止生成，或等待完成。')
    return false
  }
  const history = c.messages
    .filter((m) => m.text && !m.pending && !m.error && !m.stopped)
    .slice(-12)
    .map((m) => ({ role: m.role, text: m.text }))
  c.messages.push({ id: uid('assistant_user'), role: 'user', text: query, at: now(), retryOf })
  if (c.title === '新對話') c.title = query.slice(0, 28) + (query.length > 28 ? '…' : '')
  c.messages.push({
    id: uid('assistant_reply'), role: 'assistant', text: '', status: '正在理解問題…', pending: true,
    completionState: 'pending', retryQuery: query, retryOf, at: now(),
  })
  // 必須取回 reactive 代理物件，之後的修改才會觸發畫面更新。
  const reply = c.messages.at(-1)
  c.updatedAt = now()
  save()

  const controller = new AbortController()
  const active = reactive({ controller, userStopped: false })
  assistant.streams[c.id] = active
  const writer = createWriter(reply)
  let terminal = null, errorEvent = null, handoff = null

  try {
    await api.streamAssistant(
      { conversation_id: c.id, message: query, history, memory: c.memory || {}, preferences: preferencesPayload() },
      (event) => {
        switch (event.type) {
          case 'start': reply.model = event.model; reply.status = '正在理解問題與條件…'; break
          case 'understanding': reply.understanding = event.data; reply.status = '正在選擇資料工具…'; break
          case 'tool_plan': reply.status = event.data?.calls?.length ? '正在依對話條件取得資料…' : '正在整理對話上下文…'; break
          case 'tool':
            reply.status = event.status === 'completed'
              ? `已取得 ${event.symbol ? event.symbol + ' ' : ''}${event.name} 資料`
              : event.message || `${event.name} 取得失敗`
            break
          case 'memory': c.memory = event.memory || c.memory; break
          case 'verification': reply.status = event.message || '正在核對數字與來源…'; break
          case 'delta': writer.enqueue(event.text); reply.status = '正在產生回答…'; break
          case 'clarification': writer.enqueue(event.message); reply.candidates = event.candidates || []; terminal = 'clarification'; break
          case 'research_handoff':
            writer.enqueue('已將明確的完整研究要求交給既有研究工作流；進度、工具與結果會在 AI 標的研究頁顯示。')
            terminal = 'research_handoff'
            handoff = event
            break
          case 'done':
            c.memory = event.memory || c.memory
            // notes：資料日期、缺口與核對結果，顯示在回答下方，不寫進回答本文。
            Object.assign(reply, { usage: event.usage || {}, model: event.model, verification: event.verification, notes: event.notes || [] })
            terminal = 'completed'
            break
          case 'error': errorEvent = event; terminal = 'failed'; break
        }
        c.updatedAt = now()
      },
      { signal: controller.signal },
    )
    writer.flush()
    if (active.userStopped) Object.assign(reply, { stopped: true, partial: Boolean(reply.text), completionState: 'stopped' })
    else if (errorEvent) {
      if (isQuotaError(`${errorEvent.code || ''} ${errorEvent.message || ''}`)) notifyQuota(errorEvent.message)
      Object.assign(reply, { error: true, partial: Boolean(reply.text), completionState: 'failed' })
      appendLine(reply, errorEvent.message)
    } else if (terminal === 'clarification') reply.completionState = 'clarification'
    else if (terminal === 'research_handoff') {
      reply.completionState = 'completed'
      onResearchHandoff?.(handoff)
    } else if (terminal === 'completed') {
      reply.completionState = 'completed'
      recordReply(c, reply, query)
      reply.askFeedback = shouldAskFeedback(c.messages.filter((m) => m.role === 'assistant' && m.completionState === 'completed').length, reply.verification)
    }
    else {
      Object.assign(reply, { error: true, completionState: 'failed' })
      appendLine(reply, '助手串流已結束，但沒有收到完成訊號。沒有改用示範回答。')
    }
  } catch (error) {
    writer.flush()
    if (active.userStopped || error.name === 'AbortError') {
      Object.assign(reply, { stopped: true, partial: Boolean(reply.text), completionState: 'stopped' })
      if (!reply.text) reply.text = '尚未收到回答內容。'
    } else {
      Object.assign(reply, { error: true, partial: Boolean(reply.text), completionState: 'failed' })
      appendLine(reply, `助手請求失敗：${error.message}。沒有改用示範回答。`)
    }
  } finally {
    Object.assign(reply, { pending: false, status: '' })
    delete assistant.streams[c.id]
    c.updatedAt = now()
    save()
  }
  return true
}

export function stop(conversationId = assistant.currentId) {
  const active = assistant.streams[conversationId]
  if (!active || active.userStopped) return
  active.userStopped = true
  const reply = assistant.conversations.find((c) => c.id === conversationId)?.messages.at(-1)
  if (reply?.pending) reply.status = '正在停止生成…'
  active.controller.abort()
}

export function retry(message) {
  if (message.retryQuery) ask(message.retryQuery, { retryOf: message.id })
}

export function confirmCandidate(message, candidate) {
  const c = current.value
  if (!c) return
  c.memory = c.memory || emptyMemory()
  c.memory.confirmed_symbol = candidate.symbol
  c.memory.recent_symbols = [candidate.symbol, ...(c.memory.recent_symbols || []).filter((code) => code !== candidate.symbol)].slice(0, 3)
  message.confirmedSymbol = candidate.symbol
  message.text = `已確認為 ${candidate.symbol} ${candidate.name}，正在接續原問題。`
  save()
  ask(`我確認標的是 ${candidate.symbol} ${candidate.name}，請接續回答上一個問題。`)
}

export function newConversation() {
  assistant.view = 'chat'
  if (current.value && !current.value.messages.length) return toast('目前已是空白對話')
  const c = assistant.conversations.find((x) => !x.messages.length) || makeConversation()
  if (!assistant.conversations.includes(c)) assistant.conversations.unshift(c)
  assistant.currentId = c.id
  save()
  toast('已開啟新對話')
}

export function clearCurrent() {
  const c = current.value
  if (c) {
    stop(c.id)
    forgetReplies(c)
    Object.assign(c, { messages: [], memory: emptyMemory(), title: '新對話', updatedAt: now() })
    save()
    toast('已清除目前對話')
  }
  assistant.view = 'chat'
}

export function openConversation(id) {
  assistant.currentId = id
  assistant.view = 'chat'
}

export function deleteConversation(id) {
  stop(id)
  const removed = assistant.conversations.find((c) => c.id === id)
  if (removed) forgetReplies(removed)
  assistant.conversations = assistant.conversations.filter((c) => c.id !== id)
  if (assistant.currentId === id) ensureCurrent()
  save()
}

export function togglePin(conversation) {
  conversation.pinned = !conversation.pinned
  save()
}

// 這個功能上線前的對話也補進足跡。
assistant.conversations.forEach((c) => c.messages.forEach((m, i) => {
  if (m.role === 'assistant' && m.completionState === 'completed') recordReply(c, m, c.messages[i - 1]?.text || '')
}))
