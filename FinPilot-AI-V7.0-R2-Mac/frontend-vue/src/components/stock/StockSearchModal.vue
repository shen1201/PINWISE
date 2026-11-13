<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import AppModal from '@/components/AppModal.vue'
import { api } from '@/api/client.js'
import { overlays, openStockDetail } from '@/stores/overlays.js'
import { storageKey } from '@/api/runtime.js'

// 右上角「搜尋股票」（對應舊版 openStockSearch）：輸入兩個字以上自動搜尋，選取後開啟個股詳情。
// Enter／搜尋按鈕：有代號或名稱完全相符、或只有一筆結果時直接開啟；↑↓ 可選擇結果。
const query = ref('')
const results = ref([])
const state = ref('idle')
const error = ref('')
const input = ref(null)
const active = ref(-1)
let timer = 0
let lastSearched = ''

// 最近搜尋：只存在此瀏覽器，新的在前，最多 6 筆。
const HISTORY_KEY = storageKey('pinwise_vue_stock_search_history')
const HISTORY_LIMIT = 6
function loadHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]')
    return Array.isArray(saved) ? saved.filter((s) => s?.code).slice(0, HISTORY_LIMIT) : []
  } catch {
    return []
  }
}
const history = ref(loadHistory())
function saveHistory() {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value))
  } catch {
    // 瀏覽器不允許儲存時，歷史只保留到重新整理為止。
  }
}
function remember(stock) {
  history.value = [stock, ...history.value.filter((s) => s.code !== stock.code)].slice(0, HISTORY_LIMIT)
  saveHistory()
}
function clearHistory() {
  history.value = []
  active.value = -1
  saveHistory()
  input.value?.focus()
}
// 上下鍵與 Enter 操作的清單：還沒輸入時是最近搜尋，否則是搜尋結果。
const rows = computed(() => (state.value === 'idle' ? history.value : results.value))

async function run() {
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
      market: item.market || '',
    }))
    lastSearched = q
    active.value = -1
    state.value = 'done'
  } catch (e) {
    error.value = e.message || '後端未回應'
    state.value = 'failed'
  }
}

watch(query, (value) => {
  clearTimeout(timer)
  if (value.trim().length >= 2) timer = setTimeout(run, 450)
  else {
    // 刪到少於兩個字（含全部清空）時收起舊結果，回到初始說明。
    results.value = []
    active.value = -1
    lastSearched = ''
    state.value = 'idle'
  }
})
// 每次開啟都從空白開始（清掉上次的文字與結果），並把游標放進輸入框。
watch(() => overlays.stockSearch, (open) => {
  if (!open) return
  clearTimeout(timer)
  query.value = ''
  active.value = -1
  nextTick(() => input.value?.focus())
})

function bestMatch() {
  const q = query.value.trim().toLowerCase()
  if (active.value >= 0) return results.value[active.value]
  return results.value.find((s) => s.code.toLowerCase() === q || (s.name || '').toLowerCase() === q)
    || (results.value.length === 1 ? results.value[0] : null)
}

async function submit() {
  clearTimeout(timer)
  if (state.value === 'idle' && !query.value.trim()) {
    if (active.value >= 0) pick(history.value[active.value])
    return
  }
  if (state.value !== 'done' || lastSearched !== query.value.trim()) await run()
  const match = state.value === 'done' && bestMatch()
  if (match) pick(match)
}

function move(step) {
  if (!rows.value.length) return
  active.value = (active.value + step + rows.value.length) % rows.value.length
}

function pick(stock) {
  remember(stock)
  overlays.stockSearch = false
  openStockDetail(stock.code, '股票詳情')
}
</script>

<template>
  <AppModal :open="overlays.stockSearch" title="搜尋股票" modal-class="stock-search-modal" @close="overlays.stockSearch = false">
    <form class="stock-search-form" @submit.prevent="submit">
      <input
        ref="input"
        v-model="query"
        type="search"
        placeholder="輸入代號或名稱，例如 2330、台積電、0050"
        autocomplete="off"
        aria-label="股票代號或名稱"
        @keydown.down.prevent="move(1)"
        @keydown.up.prevent="move(-1)"
      />
      <button class="primary-button" type="submit">搜尋</button>
    </form>
    <div class="stock-search-results">
      <section v-if="state === 'idle' && history.length" class="ss-history" aria-label="最近搜尋">
        <div class="ss-history-head"><h3>最近搜尋</h3><button type="button" class="card-link" @click="clearHistory">清除</button></div>
        <button
          v-for="(s, i) in history"
          :key="s.code"
          type="button"
          class="stock-search-row"
          :class="{ 'is-active': i === active }"
          @click="pick(s)"
          @mouseenter="active = i"
        >
          <strong>{{ s.code }} {{ s.name }}</strong>
          <small>{{ s.type === 'etf' ? 'ETF' : '股票' }}{{ s.market ? ` · ${s.market}` : '' }}</small>
          <b aria-hidden="true">→</b>
        </button>
      </section>
      <p v-if="state === 'idle'" class="hint">找到後可查看最近收盤、K 線與財務資料，並加入「我的追蹤」。想用條件找股票，請到「智慧選股」用一句話描述。</p>
      <div v-else-if="state === 'loading'" class="empty-state">搜尋中…</div>
      <div v-else-if="state === 'failed'" class="notice"><strong>搜尋失敗</strong><span>{{ error }}</span></div>
      <template v-else>
        <button
          v-for="(s, i) in results"
          :key="s.code"
          type="button"
          class="stock-search-row"
          :class="{ 'is-active': i === active }"
          @click="pick(s)"
          @mouseenter="active = i"
        >
          <strong>{{ s.code }} {{ s.name }}</strong>
          <small>{{ s.type === 'etf' ? 'ETF' : '股票' }}{{ s.market ? ` · ${s.market}` : '' }}</small>
          <b aria-hidden="true">→</b>
        </button>
        <div v-if="!results.length" class="empty-state">找不到符合的股票，請改用代號或完整名稱。</div>
      </template>
    </div>
  </AppModal>
</template>

<style scoped>
.ss-history{display:grid;gap:6px;margin-bottom:10px}
.ss-history-head{display:flex;align-items:center;justify-content:space-between}
.ss-history-head h3{margin:0;color:var(--muted);font-size:13px;font-weight:700}
.stock-search-row.is-active{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 7%,transparent)}
/* 只留一個捲軸：外框不捲動（外框捲軸也會蓋掉右側圓角），標題固定，結果區自己捲動。 */
:global(.modal.stock-search-modal){display:flex;flex-direction:column;overflow:hidden}
:global(.modal.stock-search-modal > .modal-header){flex:none}
:global(.modal.stock-search-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto}
</style>
