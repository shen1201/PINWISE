<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import AppModal from '@/components/AppModal.vue'
import ResearchConfirmDialog from './ResearchConfirmDialog.vue'
import { ui } from '@/stores/ui.js'
import { ask } from '@/stores/assistant.js'
import { research, createTask, optionsFromUnderstanding, typoOf } from '@/stores/research.js'
import { isCompared, toggleCompare } from '@/stores/workspace.js'
import { analyzeQuery } from '@/stores/picker.js'

// 送出研究前的確認視窗：研究範圍、標的歧義與功能導引（對應舊版 prepareResearchInput 與 showResearchRedirect）。
const router = useRouter()
const dialog = computed(() => research.dialog)
const period = computed(() => dialog.value?.result.historical_period?.label || '期間未辨識')
const reason = computed(() => dialog.value?.reason || '')
const screening = computed(() => {
  const d = dialog.value
  return d && (['theme', 'etf'].includes(d.reason) || d.result.research_type === 'stock_screen' || /找|挑|推薦|篩|適合|哪些|有什麼/.test(d.query))
})
const redirectOptions = computed(() => {
  const options = [
    ['picker', '到智慧選股，依條件找股票', '會帶入你的句子，由 AI 轉成條件後篩選官方資料。'],
    ['assistant', '問 PINWISE 助手', '適合問觀念或一般問題，例如「什麼是殖利率」。'],
  ]
  if (reason.value === 'multi') return [['compare', '到股票比較，並排看差異', `把 ${dialog.value.codes.join('、')} 加入比較清單。`], options[1]]
  return screening.value ? options : [...options].reverse()
})
const redirectTitle = computed(() => ({ multi: '標的研究一次研究一檔', theme: '先找出想研究的標的', etf: '請先指定一檔 ETF', concept: '這是觀念問題' })[reason.value] || '需要確認關鍵資訊')
const redirectLead = computed(() => ({
  multi: '你提到了多檔標的',
  theme: '還沒有指定標的',
  etf: '還沒有指定是哪一檔',
  concept: 'PINWISE 助手更適合回答',
})[reason.value] || 'AI 標的研究需要明確的標的')
const redirectBody = computed(() => {
  const query = dialog.value?.query
  return ({
    multi: `AI 標的研究一次深入一檔。想看「${query}」的差異，可以用股票比較；也可以改輸入其中一檔。`,
    theme: `「${query}」是產業或主題。先用智慧選股找出候選標的，再挑一檔深入研究。`,
    concept: `「${query}」不需要建立研究，問 PINWISE 助手就能得到解釋。`,
    etf: `「${query}」沒有指定代號。可以直接輸入 ETF 代號（例如 0050），或先用智慧選股找出想看的 ETF。`,
  })[reason.value] || `例如「2330」「台積電」「0050」。你輸入的「${query}」看起來比較像${screening.value ? '選股條件' : '一個問題'}，適合用下面的功能：`
})

const close = () => (research.dialog = null)

function confirmSymbol(symbol) {
  const { query, result } = dialog.value
  close()
  createTask(typoOf(query, result, symbol)?.corrected || query, optionsFromUnderstanding(result, symbol))
  router.push('/research')
}

function redirect(key) {
  const { query, codes } = dialog.value
  close()
  if (key === 'compare') {
    codes.filter((code) => !isCompared(code)).forEach(toggleCompare)
    router.push('/compare')
  } else if (key === 'picker') {
    analyzeQuery(query)
    router.push('/picker')
  } else {
    ui.assistantOpen = true
    ask(query)
  }
}
</script>

<template>
  <ResearchConfirmDialog />

  <AppModal
    :open="dialog?.kind === 'ambiguous'"
    title="請確認研究標的"
    @close="close"
  >
    <div v-if="dialog" class="input-understanding-dialog">
      <p>{{ dialog.result.message }}</p>
      <small>原問題：{{ dialog.query }}</small>
      <small>
        歷史觀察期間：{{ period }}
        <template v-if="dialog.result.outlook_period"><br />未來展望：{{ dialog.result.outlook_period.label }}</template>
      </small>
      <div class="input-candidate-list">
        <button v-for="item in dialog.result.candidates" :key="item.symbol" class="outline-button" type="button" @click="confirmSymbol(item.symbol)">
          <strong>{{ item.symbol }} {{ item.name }}</strong>
          <small>{{ item.market }} · 相似度 {{ Math.round(Number(item.confidence || 0) * 100) }}%</small>
        </button>
      </div>
      <p class="hint">候選按鈕只是捷徑；也可以關閉視窗，直接修改原問題後重新送出。</p>
    </div>
  </AppModal>

  <AppModal
    :open="dialog?.kind === 'redirect'"
    :title="redirectTitle"
    @close="close"
  >
    <template v-if="dialog">
      <div class="notice">
        <strong>{{ redirectLead }}：</strong>
        <span>{{ redirectBody }}</span>
      </div>
      <div class="research-redirect-actions">
        <button
          v-for="([key, label, hint], i) in redirectOptions"
          :key="key"
          type="button"
          :class="i ? 'outline-button' : 'primary-button'"
          @click="redirect(key)"
        >
          <strong>{{ label }}</strong><small>{{ hint }}</small>
        </button>
      </div>
      <p class="hint">也可以改輸入一檔股票或 ETF 的代號或名稱，再按「開始研究」。本次沒有建立研究，也不會消耗 Gemini 額度。</p>
    </template>
  </AppModal>
</template>
