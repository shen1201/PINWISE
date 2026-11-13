<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import AppIcon from './AppIcon.vue'
import { api } from '@/api/client.js'
import { storageKey } from '@/api/runtime.js'

// 以代號或名稱搜尋上市櫃股票與 ETF，邏輯與右上角「搜尋股票」相同：
// 輸入兩個字以上自動搜尋；Enter 直接選完全相符或唯一的結果；↑↓ 可選擇結果。
// historyKey：有值時記住最近選過的 3 檔，點空白搜尋欄就列出，打字時符合的排在最前面。
// full：清單已滿時不清空輸入，直接在結果上方說明原因，移除一檔後就能點同一筆加入。
const props = defineProps({
  selected: { type: Array, default: () => [] }, // 已加入的代號，按鈕會停用
  actionLabel: { type: String, default: '加入' },
  doneLabel: { type: String, default: '已加入' },
  historyKey: { type: String, default: '' },
  full: { type: Boolean, default: false },
  fullText: { type: String, default: '清單已滿，請先移除一檔' },
  placeholder: { type: String, default: '例如：2330／台積電／環球晶' },
})
const emit = defineEmits(['pick'])

const HISTORY_LIMIT = 3
const query = ref('')
const results = ref([])
const state = ref('idle') // idle | loading | done | failed
const error = ref('')
const active = ref(-1)
const focused = ref(false)
let timer = 0
let lastSearched = ''

// 最近搜尋：只存在這個瀏覽器。
const historyStore = props.historyKey ? storageKey(`pinwise_vue_search_history_${props.historyKey}`) : ''
function loadHistory() {
  if (!historyStore) return []
  try {
    const list = JSON.parse(localStorage.getItem(historyStore) || '[]')
    return Array.isArray(list) ? list.filter((s) => s && s.code).slice(0, HISTORY_LIMIT) : []
  } catch {
    return []
  }
}
const history = ref(loadHistory())
function remember(stock) {
  if (!historyStore) return
  const { code, name, type, market } = stock
  history.value = [{ code, name, type, market }, ...history.value.filter((s) => s.code !== code)].slice(0, HISTORY_LIMIT)
  try {
    localStorage.setItem(historyStore, JSON.stringify(history.value))
  } catch {
    // 瀏覽器不允許儲存時，只在這次使用中記住。
  }
}
// 搜尋欄空白時顯示最近 3 筆；打字時把符合的最近紀錄排在最前面（最多 3 筆）。
const recent = computed(() => {
  if (!historyStore || !focused.value) return []
  const q = query.value.trim().toLowerCase()
  if (!q) return state.value === 'idle' ? history.value : []
  return history.value.filter((s) => s.code.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q))
})
const listed = computed(() => {
  const codes = new Set(recent.value.map((s) => s.code))
  return [...recent.value.map((s) => ({ ...s, recent: true })), ...results.value.filter((s) => !codes.has(s.code))]
})

async function search() {
  const q = query.value.trim()
  if (!q) return
  state.value = 'loading'
  try {
    const response = await api.searchStocks(q)
    if (query.value.trim() !== q) return
    results.value = (response.items || []).map((item) => ({
      code: item.symbol,
      name: item.name,
      type: item.product_type || (/^00/.test(item.symbol) ? 'etf' : 'stock'),
      market: item.market,
    }))
    lastSearched = q
    active.value = -1
    state.value = 'done'
  } catch (e) {
    error.value = e.message || '搜尋失敗'
    state.value = 'failed'
  }
}

watch(query, (value) => {
  clearTimeout(timer)
  if (value.trim().length >= 2) timer = setTimeout(search, 450)
  else closeResults()
})
function bestMatch() {
  const q = query.value.trim().toLowerCase()
  if (active.value >= 0) return listed.value[active.value]
  return listed.value.find((s) => s.code.toLowerCase() === q || (s.name || '').toLowerCase() === q)
    || (results.value.length === 1 ? results.value[0] : null)
}
async function submit() {
  clearTimeout(timer)
  if (!query.value.trim()) return
  if (state.value !== 'done' || lastSearched !== query.value.trim()) await search()
  const match = state.value === 'done' && bestMatch()
  if (match && !props.selected.includes(match.code)) choose(match)
}
function move(step) {
  if (listed.value.length) active.value = (active.value + step + listed.value.length) % listed.value.length
}

// 選取後清空，讓結果清單收起；點外面或按 Esc 也收起（輸入的字保留）。
const root = ref(null)
function closeResults() {
  results.value = []
  active.value = -1
  lastSearched = ''
  state.value = 'idle'
}
function choose(stock) {
  // 清單已滿：保留輸入與結果，只顯示原因。
  if (props.full) return
  emit('pick', stock)
  remember(stock)
  query.value = ''
  closeResults()
}
// 回到搜尋欄時，如果之前打的字還在，就重新列出結果。
function onFocus() {
  focused.value = true
  if (query.value.trim().length >= 2 && state.value === 'idle') search()
}
function onOutside(event) {
  if (root.value && !root.value.contains(event.target)) {
    focused.value = false
    closeResults()
  }
}
const isDisabled = (stock) => props.selected.includes(stock.code) || props.full
const labelOf = (stock) => (props.selected.includes(stock.code) ? props.doneLabel : props.full ? '已滿' : props.actionLabel)
onMounted(() => document.addEventListener('pointerdown', onOutside))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutside))
</script>

<template>
  <div ref="root" class="stock-search-box" @keydown.esc="closeResults(); focused = false">
  <form class="comparison-search-shell" @submit.prevent="submit">
    <span><AppIcon name="search" :size="20" /></span>
    <input v-model="query" type="search" autocomplete="off" :placeholder="placeholder" aria-label="股票名稱或代號" @focus="onFocus" @click="onFocus" @keydown.down.prevent="move(1)" @keydown.up.prevent="move(-1)" />
    <button class="primary-button" type="submit" :disabled="state === 'loading'">{{ state === 'loading' ? '搜尋中…' : '搜尋' }}</button>
  </form>
  <div class="comparison-search-results">
    <div v-if="full && (listed.length || state === 'done')" class="comparison-search-empty ss-full" role="status">{{ fullText }}</div>
    <div v-if="state === 'failed'" class="comparison-search-empty">搜尋失敗：{{ error }}</div>
    <div v-else-if="state === 'done' && !listed.length" class="comparison-search-empty">找不到相符標的，請改用股票代號或完整名稱。</div>
    <div v-if="recent.length && !query.trim()" class="ss-label">最近搜尋</div>
    <button
      v-for="(stock, i) in listed"
      :key="stock.code"
      class="comparison-search-result"
      :class="{ 'is-active': i === active }"
      type="button"
      :disabled="isDisabled(stock)"
      @click="choose(stock)"
    >
      <span><strong>{{ stock.code }} {{ stock.name }}</strong><small>{{ stock.market }} · {{ stock.type === 'etf' ? 'ETF' : '台股個股' }}</small><em v-if="stock.recent && query.trim()" class="ss-tag">最近</em></span>
      <b>{{ labelOf(stock) }}</b>
    </button>
  </div>
  </div>
</template>

<style scoped>
/* 外框已經會變色，輸入框本身不要再出現第二層焦點框 */
.comparison-search-shell input:focus,.comparison-search-shell input:focus-visible{border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important}
/* 搜尋結果：一張卡片、一列一筆，不顯示捲動軸 */
.comparison-search-results{display:grid;gap:2px;max-height:min(380px,60vh);padding:6px;overflow-y:auto;border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 14px 34px rgba(30,60,120,.2);scrollbar-width:none}
.comparison-search-results::-webkit-scrollbar{display:none}
.comparison-search-results:empty{display:none}
.comparison-search-results .comparison-search-result{min-height:44px;padding:0 10px 0 12px;border:0;border-radius:10px;background:transparent;cursor:pointer}
.comparison-search-results .comparison-search-result:hover:not(:disabled),.comparison-search-results .comparison-search-result.is-active{background:color-mix(in srgb,var(--blue) 10%,transparent)}
.comparison-search-results .comparison-search-result span{display:flex;align-items:baseline;gap:10px;min-width:0}
.comparison-search-results .comparison-search-result strong{font-size:15px;white-space:nowrap}
.comparison-search-results .comparison-search-result small{white-space:nowrap}
.comparison-search-results .comparison-search-result b{flex:none;padding:3px 10px;border-radius:999px;background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue);font-size:12px}
.comparison-search-results .comparison-search-empty{padding:10px 12px;color:var(--muted);font-size:13px}
.comparison-search-results .ss-full{margin-bottom:2px;border-radius:10px;background:color-mix(in srgb,#E0A030 14%,transparent);color:var(--text-strong);font-weight:700}
.ss-label{padding:4px 12px 2px;color:var(--muted);font-size:12px;font-weight:700}
.ss-tag{flex:none;padding:0 6px;border-radius:999px;background:color-mix(in srgb,var(--muted) 14%,transparent);color:var(--muted);font-size:11px;font-style:normal}
</style>
