<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import FeedbackBar from '@/components/FeedbackBar.vue'
import { footprint } from '@/stores/footprint.js'
import { research } from '@/stores/research.js'
import { openConversation } from '@/stores/assistant.js'
import { ui } from '@/stores/ui.js'

const router = useRouter()
const FILTERS = [['all', '全部'], ['research', '研究'], ['assistant', '助手'], ['picker', '選股'], ['compare', '比較']]
// 依評價篩選：點「有用」就列出所有評為有用的操作；「有文字」是自己打過回饋的紀錄。
const RATING_FILTERS = [['all', '全部評價'], ['useful', '有用'], ['ok', '還好'], ['bad', '很糟'], ['comment', '有文字回饋']]
const rating = defineModel('rating', { default: 'all' })
const REASON_TEXT = { data_wrong: '資料有錯', hard_to_read: '看不懂', too_slow: '太慢', off_topic: '沒回答到問題' }
const KIND = { research: 'AI 研究', assistant: '助手', picker: '智慧選股', compare: '股票比較' }
const PAGE_SIZE = 9
const kind = ref('all')
const query = ref('')
const page = ref(0)
const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  const okRating = (r) => rating.value === 'all' || (rating.value === 'comment' ? Boolean(r.comment) : r.rating === rating.value)
  return footprint.records.filter((r) => (kind.value === 'all' || r.kind === kind.value) && okRating(r) && (!q || `${r.label || ''} ${r.comment || ''}`.toLowerCase().includes(q)))
})
const pages = computed(() => Math.max(1, Math.ceil(rows.value.length / PAGE_SIZE)))
const shown = computed(() => rows.value.slice(page.value * PAGE_SIZE, (page.value + 1) * PAGE_SIZE))
watch([kind, query, rating], () => (page.value = 0))
const emptyText = computed(() => (!footprint.records.length ? '還沒有使用紀錄' : rating.value === 'comment' ? '還沒有打過文字回饋' : rating.value !== 'all' ? `還沒有評為「${RATING_FILTERS.find(([k]) => k === rating.value)[1]}」的紀錄` : '沒有符合的紀錄'))
const when = (at) => {
  const d = new Date(at)
  return Number.isNaN(d.getTime()) ? '—' : `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
const detail = (r) => [r.coverage != null ? `覆蓋 ${r.coverage}%` : '', r.count != null ? `${r.count} 檔` : '', r.tokens ? `${r.tokens.toLocaleString('zh-TW')} Token` : ''].filter(Boolean).join(' · ') || '—'
const canOpen = (r) => !r.deleted && (r.kind !== 'research' || research.tasks.some((t) => t.id === r.id))
function open(r) {
  if (r.kind === 'research') {
    research.activeId = r.id
    router.push('/research')
  } else if (r.kind === 'assistant') {
    openConversation(r.conversationId)
    ui.assistantOpen = true
  } else router.push(r.kind === 'picker' ? '/picker' : '/compare')
}
</script>

<template>
  <section class="card surface-solid fp-card fp-grow">
    <header data-tour="fp-history-filters">
      <div class="fp-chips" role="group" aria-label="篩選類型"><button v-for="[key, label] in FILTERS" :key="key" type="button" :class="{ active: kind === key }" @click="kind = key">{{ label }}</button></div>
      <div class="fp-chips hs-rating" role="group" aria-label="篩選評價"><button v-for="[key, label] in RATING_FILTERS" :key="key" type="button" :class="[`is-${key}`, { active: rating === key }]" @click="rating = key">{{ label }}</button></div>
      <input v-model="query" class="hs-search" type="search" placeholder="搜尋紀錄" aria-label="搜尋紀錄" />
    </header>
    <div v-if="shown.length" class="fp-table hs-table">
      <div v-for="r in shown" :key="r.id" class="hs-row">
        <time>{{ when(r.at) }}</time>
        <span class="fp-tag">{{ KIND[r.kind] }}</span>
        <div v-if="!r.deleted" class="hs-label">
          <strong :title="r.label">{{ r.label || '（無標題）' }}</strong>
          <q v-if="r.comment || r.reason" :title="r.comment || ''">{{ [r.reason && REASON_TEXT[r.reason], r.comment].filter(Boolean).join('：') }}</q>
        </div>
        <em v-else>內容已刪除（紀錄保留）</em>
        <small>{{ r.status === 'failed' ? '研究失敗' : detail(r) }}</small>
        <FeedbackBar v-if="r.kind !== 'compare' && r.status !== 'failed'" compact :item-id="r.id" :feature="r.kind" />
        <i v-else></i>
        <button v-if="canOpen(r)" class="fp-link" type="button" @click="open(r)">查看 →</button>
        <i v-else></i>
      </div>
    </div>
    <div v-else class="fp-empty"><strong>{{ emptyText }}</strong></div>
    <footer class="hs-pager">
      <small>共 {{ rows.length }} 筆</small>
      <div><button class="fp-link" type="button" :disabled="page === 0" @click="page--">← 上一頁</button><span>{{ page + 1 }} / {{ pages }}</span><button class="fp-link" type="button" :disabled="page >= pages - 1" @click="page++">下一頁 →</button></div>
    </footer>
  </section>
</template>

<style scoped>
.hs-search{width:220px;height:32px;padding:0 12px;border:1px solid var(--pw-small-line);border-radius:10px;background:var(--pw-inner);color:var(--text-strong);font-size:13px}
.hs-table{display:grid;grid-template-rows:repeat(9,minmax(0,1fr));padding:0 14px}
.hs-row{display:grid;grid-template-columns:82px 74px minmax(0,1fr) 170px 150px 50px;align-items:center;gap:10px;min-height:0;font-size:13px;color:var(--text)}
.hs-row + .hs-row{border-top:1px solid var(--line)}
.hs-table{overflow:visible}
.hs-row :deep(.fb){position:relative;flex-wrap:nowrap}
.hs-row :deep(.fb-reasons){position:absolute;top:calc(100% + 3px);right:0;z-index:5;padding:5px;border:1px solid var(--line);border-radius:12px;background:var(--surface-solid,#fff);box-shadow:0 8px 20px rgba(30,60,120,.2)}
.hs-row time{color:var(--muted);font-variant-numeric:tabular-nums}
.hs-row .fp-tag{justify-self:start}
.hs-row strong{overflow:hidden;color:var(--text-strong);font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.hs-label{display:grid;gap:1px;min-width:0}
.hs-label q{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap;quotes:"「" "」"}
.hs-rating{margin-left:auto}
.hs-rating button.is-useful.active{background:var(--blue)!important;border-color:var(--blue)!important;color:#fff!important}
.hs-rating button.is-bad.active{background:var(--red)!important;border-color:var(--red)!important;color:#fff!important}
.hs-row em{color:var(--muted);font-style:italic}
.hs-row small{overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.hs-pager{flex:none;display:flex;align-items:center;justify-content:space-between}
.hs-pager small{color:var(--muted);font-size:12px}
.hs-pager div{display:flex;align-items:center;gap:12px;color:var(--text);font-size:12px}
.hs-pager button:disabled{opacity:.4;cursor:default}
@media (max-width:900px){.hs-table{grid-template-rows:none}.hs-row{grid-template-columns:1fr auto;padding:8px 0}.hs-row small{display:none}}
</style>
