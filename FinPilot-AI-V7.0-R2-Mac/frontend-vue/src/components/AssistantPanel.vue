<script setup>
import FeedbackPrompt from './FeedbackPrompt.vue'
import PrefsBadge from './PrefsBadge.vue'
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ui, settings, toast } from '@/stores/ui.js'
import {
  assistant, current, isStreaming, completionLabel, ask, stop, retry, confirmCandidate,
  newConversation, clearCurrent, openConversation, deleteConversation, togglePin,
} from '@/stores/assistant.js'
import { confirmResearch } from '@/stores/research.js'
import { ratingOf } from '@/stores/footprint.js'
import { markdown } from '@/utils/markdown.js'
import mark from '@root/assets/pinwise-mark.png'
import InfoTip from './InfoTip.vue'

const router = useRouter()
const RUNTIME_NOTE = '回答由 Python 後端串流取得 Gemini；行情為最近官方日資料，不是即時價。'
const input = ref('')
const box = ref(null)
const nearBottom = ref(true)
const historyQuery = ref('')
// 右側整欄抽屜；需要看長篇回答時可放大成較寬版面。
const expanded = ref(false)
// 空白對話的建議問題：點一下帶入輸入框（不直接送出），使用者可再修改，例如把比較的代號換掉。
const SUGGESTIONS = ['什麼是殖利率？', '0050 和 0056 差在哪？', '台積電最近表現如何？', 'ETF 適合新手嗎？']
const inputEl = ref(null)
function useSuggestion(text) {
  input.value = text
  nextTick(() => {
    inputEl.value?.focus()
    inputEl.value?.setSelectionRange(text.length, text.length)
  })
}

// 點擊抽屜以外的地方自動收起。彈窗、提示訊息與 ⓘ 說明不算外面，
// 避免從助手開啟股票詳情時，點彈窗就把助手關掉。
const panel = ref(null)
const KEEP_OPEN = '.modal, .modal-backdrop, .toast-stack, .info-tip-bubble, [aria-label^="開啟 PINWISE 助手"]'
function onOutsidePointer(event) {
  if (!ui.assistantOpen || panel.value?.contains(event.target)) return
  if (event.target.closest?.(KEEP_OPEN)) return
  close()
}
onMounted(() => document.addEventListener('pointerdown', onOutsidePointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutsidePointer))

const messages = computed(() => current.value?.messages || [])
// 偶爾詢問的回饋小窗：只看最新一則、還沒評價過的回答，正在生成時不出現。
// 出現後記住是哪一則，使用者選了評價也不會馬上消失，才能接著打字。
// 換對話時 askMessage 自然找不到那一則而收起，不需要另外清除（另外清除會和下面的 watch 搶先後順序）。
const promptId = ref('')
watch(
  () => {
    const last = messages.value.at(-1)
    return !isStreaming.value && last?.role === 'assistant' && last.askFeedback && !ratingOf(last.id)?.rating ? last.id : ''
  },
  (id) => id && (promptId.value = id),
  { immediate: true },
)
const askMessage = computed(() => messages.value.find((m) => m.id === promptId.value) || null)
function feedbackDone() {
  if (askMessage.value) askMessage.value.askFeedback = false
  promptId.value = ''
}

const history = computed(() => {
  const q = historyQuery.value.toLowerCase()
  return assistant.conversations
    .filter((c) => c.messages.length && (c.title + c.messages.map((m) => m.text).join(' ')).toLowerCase().includes(q))
    .sort((a, b) => b.pinned - a.pinned || new Date(b.updatedAt) - new Date(a.updatedAt))
})

const timeOf = (iso) => {
  const d = new Date(iso || Date.now())
  return Number.isFinite(d.getTime()) ? `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : ''
}
const dateOf = (iso) => {
  const d = new Date(iso)
  return Number.isFinite(d.getTime()) ? `${d.getMonth() + 1}/${d.getDate()} ${timeOf(iso)}` : '—'
}

// 停在底部時自動跟隨新內容；往上閱讀時保留位置，只顯示「↓」。
const isNearBottom = () => !box.value || box.value.scrollHeight <= box.value.scrollTop + box.value.clientHeight + 18
function onScroll() {
  nearBottom.value = isNearBottom()
}
function scrollToLatest(smooth = false) {
  if (!box.value) return
  box.value.scrollTo({ top: box.value.scrollHeight, behavior: smooth && settings.motion ? 'smooth' : 'auto' })
  nearBottom.value = true
}
watch(
  () => [assistant.currentId, messages.value.length, messages.value.at(-1)?.text],
  () => {
    const follow = isNearBottom()
    nextTick(() => (follow ? scrollToLatest() : onScroll()))
  },
)
watch(() => ui.assistantOpen, (open) => open && nextTick(() => scrollToLatest()))
watch(() => ui.assistantDraft, (text) => {
  if (!text) return
  ui.assistantDraft = ''
  useSuggestion(text)
})
onMounted(() => scrollToLatest())

function submit() {
  const q = input.value.trim()
  if (!q) return
  if (isStreaming.value) return toast('目前仍在生成；可先停止，輸入內容已保留。')
  input.value = ''
  ask(q, {
    // 助手判斷為完整研究要求時，交給研究工作流（對應舊版 research_handoff 處理）。
    onResearchHandoff: async (event) => {
      const task = await confirmResearch(event.query, {
        requestedSymbols: event.symbols || [],
        horizon: event.horizon,
        researchType: event.research_type || event.understanding?.research_type,
        researchTopic: event.research_topic || event.understanding?.research_topic,
        inputUnderstanding: event.understanding,
      })
      if (task) router.push('/research')
    },
  })
}

function close() {
  ui.assistantOpen = false
  assistant.view = 'chat'
}

function rename(conversation) {
  const name = window.prompt('對話名稱', conversation.title)
  if (name?.trim()) conversation.title = name.trim().slice(0, 40)
}
</script>

<template>
  <div ref="panel" class="assistant-panel pw-drawer" :class="{ open: ui.assistantOpen, 'is-expanded': expanded }" :aria-hidden="String(!ui.assistantOpen)">
    <header class="assistant-header">
      <div class="assistant-title">
        <span><strong>PINWISE 助手</strong><small class="pw-subtitle">繁體中文 · 真實後端<InfoTip :text="RUNTIME_NOTE" label="資料來源" /></small></span>
      </div>
      <div class="pw-header-actions">
        <button
          class="icon-button pw-expand"
          type="button"
          :aria-label="expanded ? '縮小助手視窗' : '放大助手視窗'"
          :aria-pressed="String(expanded)"
          :title="expanded ? '縮小' : '放大'"
          @click="expanded = !expanded"
        >{{ expanded ? '⇥' : '⇤' }}</button>
        <button class="icon-button" type="button" aria-label="關閉助手" @click="close">✕</button>
      </div>
    </header>

    <!-- 歷史紀錄 -->
    <section v-if="assistant.view === 'history'" class="assistant-subview" aria-label="助手對話管理">
      <div class="assistant-subview-head">
        <button type="button" @click="assistant.view = 'chat'">← 返回對話</button>
        <strong>歷史紀錄</strong>
      </div>
      <div class="drawer-toolbar">
        <input v-model="historyQuery" type="search" aria-label="搜尋歷史對話" placeholder="搜尋歷史對話" />
        <button class="primary-button small" type="button" @click="newConversation">＋ 新對話</button>
      </div>
      <p class="assistant-history-note">空白對話在送出第一則訊息後才會加入歷史。</p>
      <div class="conversation-list">
        <article
          v-for="c in history"
          :key="c.id"
          class="conversation-item"
          :class="{ active: c.id === assistant.currentId }"
        >
          <button class="conversation-main" type="button" @click="openConversation(c.id)">
            <strong>{{ c.pinned ? '📌 ' : '' }}{{ c.title }}</strong>
            <small>{{ dateOf(c.updatedAt) }} · {{ c.messages.at(-1)?.text.slice(0, 52) }}</small>
          </button>
          <div class="conversation-actions">
            <button type="button" @click="togglePin(c)">{{ c.pinned ? '取消釘選' : '📌 釘選' }}</button>
            <button type="button" @click="rename(c)">✎ 命名</button>
            <button type="button" @click="deleteConversation(c.id)">⌫ 刪除</button>
          </div>
        </article>
        <div v-if="!history.length" class="empty-state">目前沒有歷史對話。</div>
      </div>
    </section>

    <template v-else>
      <div class="assistant-toolbar">
        <button class="assistant-toolbar-primary" type="button" @click="newConversation">＋ 新對話</button>
        <button type="button" @click="assistant.view = 'history'">歷史紀錄</button>
        <button class="assistant-toolbar-danger" type="button" @click="assistant.view = 'confirmClear'">清除對話</button>
      </div>

      <section v-if="assistant.view === 'confirmClear'" class="assistant-subview" aria-label="清除對話確認">
        <div class="assistant-inline-confirm">
          <strong>清除目前對話？</strong>
          <small>只會清除這段對話，不影響歷史紀錄。</small>
          <div>
            <button class="outline-button small" type="button" @click="assistant.view = 'chat'">取消</button>
            <button class="primary-button small" type="button" @click="clearCurrent">確定清除</button>
          </div>
        </div>
      </section>

      <div ref="box" class="assistant-messages" @scroll="onScroll">
        <PrefsBadge v-if="messages.length" class="pw-prefs" label="回答會參考你的偏好" />
        <div v-for="m in messages" :key="m.id" class="pw-row" :class="m.role === 'user' ? 'is-user' : 'is-bot'">
        <!-- 只有助手顯示 PINWISE 標誌；使用者訊息不加頭像 -->
        <span v-if="m.role !== 'user'" class="pw-avatar pw-avatar-bot" aria-hidden="true"><img :src="mark" alt="" /></span>
        <div
          class="message"
          :class="[m.role === 'user' ? 'user' : 'bot', { 'is-error': m.error, 'is-stopped': m.stopped }]"
        >
          <!-- markdown() 會先跳脫 HTML，再套用有限格式。 -->
          <div v-if="m.role === 'assistant' && m.pending && !m.text" class="assistant-typing" role="status" aria-label="正在回答"><i></i><i></i><i></i></div>
          <div v-else-if="m.role === 'assistant'" class="assistant-message-copy is-markdown" :class="{ 'is-fresh': m.id === assistant.freshId }" v-html="markdown(m.text)"></div>
          <div v-else class="assistant-message-copy">{{ m.text }}</div>
          <small v-if="completionLabel(m)" class="assistant-message-status">{{ completionLabel(m) }}</small>
          <div v-if="m.candidates?.length && !m.confirmedSymbol" class="assistant-candidates">
            <button v-for="item in m.candidates" :key="item.symbol" type="button" @click="confirmCandidate(m, item)">
              {{ item.symbol }} {{ item.name }}
            </button>
          </div>
          <div class="assistant-message-actions">
            <button v-if="m.pending" type="button" @click="stop()">停止生成</button>
            <button v-if="(m.error || m.stopped) && m.retryQuery" type="button" @click="retry(m)">重試</button>
          </div>
          <time class="assistant-message-time" :datetime="m.at">{{ timeOf(m.at) }}</time>
        </div>
        </div>
        <div v-if="!messages.length" class="assistant-empty pw-empty">
          <img :src="mark" alt="" class="pw-empty-mark" />
          <strong>先從一個問題開始</strong>
          <span>自由詢問投資知識、股票與 ETF；正式研究請從首頁開始。</span>
          <div class="pw-suggestions" aria-label="建議問題">
            <button v-for="q in SUGGESTIONS" :key="q" type="button" @click="useSuggestion(q)">{{ q }}</button>
          </div>
        </div>
      </div>
      <button
        v-if="!nearBottom"
        class="assistant-new-content"
        type="button"
        aria-label="回到最新訊息"
        title="回到最新訊息"
        @click="scrollToLatest(true)"
      >↓</button>

      <Transition name="fbp" appear>
        <FeedbackPrompt v-if="askMessage" :key="askMessage.id" :item-id="askMessage.id" feature="assistant" @done="feedbackDone" />
      </Transition>
      <form class="assistant-form" @submit.prevent="submit">
        <input ref="inputEl" v-model="input" placeholder="輸入問題，開始對話⋯" autocomplete="off" />
        <button v-if="isStreaming" class="danger-outline small" type="button" @click="stop()">停止生成</button>
        <button class="primary-button small" type="submit" :disabled="isStreaming">送出</button>
        <small class="assistant-risk">提問內容會傳給 AI 服務處理，回答僅供參考，請自行評估風險。</small>
      </form>
    </template>
  </div>
</template>

<style scoped>
/* 右側整欄抽屜：從畫面頂端到底端，取代原本浮在右下角的視窗。
   class 疊加（.assistant-panel.pw-drawer）提高權重以覆蓋舊版共用 CSS，不修改共用檔案。 */
.assistant-panel.pw-drawer{top:0;right:0;bottom:0;left:auto;width:clamp(400px,32vw,480px);height:100dvh;max-height:none;max-width:100vw;border-radius:22px 0 0 22px;border-right:0;transform:translateX(calc(100% + 24px));transition:transform .25s ease,width .25s ease}
.assistant-panel.pw-drawer.open{transform:translateX(0)}
.assistant-panel.pw-drawer.is-expanded{width:min(880px,calc(100vw - 260px))}
.pw-header-actions{display:flex;align-items:center;gap:4px}
.pw-expand{font-size:18px}
.assistant-form{flex-wrap:wrap}
.assistant-risk{flex:0 0 100%;color:var(--muted);font-size:12px;text-align:center}

/* 偏好標籤放在對話最上方置中 */
.pw-prefs{align-self:center;flex:none}

/* 回饋小窗：回答完稍等一下再從底部淡入 */
.fbp-enter-active{transition:opacity .45s ease .9s,transform .45s ease .9s}
.fbp-leave-active{transition:opacity .25s ease,transform .25s ease}
.fbp-enter-from,.fbp-leave-to{opacity:0;transform:translateY(10px)}
@media (prefers-reduced-motion:reduce){.fbp-enter-active,.fbp-leave-active{transition:none}}

/* 淡色品牌漸層背景（只套用淺色模式；深色模式沿用原本深色設定） */
:global(body:not([data-theme="dark"]) .assistant-panel.pw-drawer){background:linear-gradient(180deg,rgba(236,244,255,.97) 0%,rgba(244,241,255,.97) 55%,rgba(250,244,252,.97) 100%)}
:global(body[data-theme="dark"] .assistant-panel.pw-drawer){background:linear-gradient(180deg,#10233d 0%,#16233f 55%,#1c2240 100%)!important}
:global(body:not([data-theme="dark"]) .assistant-panel.pw-drawer .message.bot){background:rgba(255,255,255,.94);border-color:rgba(48,89,140,.14);box-shadow:0 4px 14px rgba(16,47,86,.06)}

/* 對話列：助手在左（PINWISE 標誌＋泡泡），使用者訊息靠右、不加頭像 */
.pw-row{display:flex;align-items:flex-start;gap:8px;width:100%}
.pw-row.is-user{justify-content:flex-end}
.pw-row .message{max-width:calc(100% - 52px);margin:0}
.pw-avatar{flex:none;display:grid;place-items:center;width:34px;height:34px;border-radius:50%;overflow:hidden;margin-top:2px;box-shadow:0 4px 12px rgba(16,47,86,.12)}
.pw-avatar-bot{background:linear-gradient(145deg,#fff7ec,#f3ecff);border:1px solid rgba(213,154,53,.35)}
.pw-avatar-bot img{width:24px;height:24px;object-fit:contain}
:global(body[data-theme="dark"] .pw-avatar-bot){background:linear-gradient(145deg,#2a2f45,#33294a);border-color:rgba(213,154,53,.4)}
.pw-subtitle{display:inline-flex;align-items:center;gap:2px}

/* 放大時限制閱讀寬度：每行太長眼睛換行容易看錯行，對話置中、最寬約 800px */
.assistant-panel.pw-drawer.is-expanded .assistant-messages > *{width:100%;max-width:800px;margin-left:auto;margin-right:auto}

/* 回答裡的表格（比較數字）：可橫向捲動，數字靠右對齊 */
.pw-drawer :deep(.assistant-message-copy table){display:block;overflow-x:auto;border-collapse:collapse;margin:8px 0;font-size:13px}
.pw-drawer :deep(.assistant-message-copy th),.pw-drawer :deep(.assistant-message-copy td){padding:5px 10px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:left}
.pw-drawer :deep(.assistant-message-copy th){color:var(--muted);font-weight:700}

/* 空白狀態：品牌 logo＋可直接點選的建議問題（取代機器人插圖） */
.pw-empty-mark{width:64px;height:64px;object-fit:contain;margin:0 auto 2px;filter:drop-shadow(0 8px 18px rgba(123,101,238,.2))}
.pw-suggestions{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:10px}
.pw-suggestions button{padding:8px 13px;border:1px solid rgba(51,127,244,.22);border-radius:999px;background:rgba(255,255,255,.85);color:var(--text-strong);font-size:13px;font-weight:600;cursor:pointer;transition:background .15s ease,border-color .15s ease}
.pw-suggestions button:hover:not(:disabled){background:#fff;border-color:var(--blue)}
.pw-suggestions button:disabled{opacity:.5;cursor:not-allowed}
/* 深色模式標題列：舊版共用 CSS 未設定，標題與圖示是深藍色、幾乎看不見 */
:global(body[data-theme="dark"] .assistant-panel.pw-drawer .assistant-title strong),
:global(body[data-theme="dark"] .assistant-panel.pw-drawer .assistant-header .icon-button){color:#edf5ff}
:global(body[data-theme="dark"] .pw-suggestions button){background:rgba(255,255,255,.08);color:#edf5ff;border-color:rgba(205,221,248,.28)}

@media (max-width:640px){
  .assistant-panel.pw-drawer,.assistant-panel.pw-drawer.is-expanded{width:100vw;border-radius:0}
  .pw-expand{display:none}
}
/* 等待回答：三個點依序跳動，像對方正在輸入 */
.assistant-typing{display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 2px}
.assistant-typing i{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:assistant-wave 1.1s ease-in-out infinite}
.assistant-typing i:nth-child(2){animation-delay:.14s}
.assistant-typing i:nth-child(3){animation-delay:.28s}
@keyframes assistant-wave{0%,60%,100%{transform:translateY(0);opacity:.45}30%{transform:translateY(-6px);opacity:1}}
/* 回答一次出現，各段落快速依序淡入（v-html 的內容要用 :deep） */
.assistant-message-copy.is-fresh :deep(> *){animation:assistant-pop .26s ease-out both}
.assistant-message-copy.is-fresh :deep(> *:nth-child(2)){animation-delay:.05s}
.assistant-message-copy.is-fresh :deep(> *:nth-child(3)){animation-delay:.1s}
.assistant-message-copy.is-fresh :deep(> *:nth-child(4)){animation-delay:.15s}
.assistant-message-copy.is-fresh :deep(> *:nth-child(n+5)){animation-delay:.2s}
@keyframes assistant-pop{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.assistant-typing i,.assistant-message-copy.is-fresh :deep(> *){animation:none}}
</style>
