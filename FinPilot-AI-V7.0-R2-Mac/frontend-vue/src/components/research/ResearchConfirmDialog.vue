<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import AppModal from '@/components/AppModal.vue'
import { research, createTask, isEtfCode, typoOf } from '@/stores/research.js'

// 研究範圍確認：送出前先讓使用者看到 Agent 的理解，可調整標的、重點與期間，按下確認才開始。
const dialog = computed(() => (research.dialog?.kind === 'confirm' ? research.dialog : null))
const options = computed(() => dialog.value?.options || {})
const understanding = computed(() => options.value.inputUnderstanding || {})

const FOCUS = [
  ['', '全面研究', '成長、獲利與風險都看'],
  ['股價與成交量', '股價與成交量', '近期走勢與量能變化'],
  ['財報與基本面', '財報與基本面', '營收、獲利與估值'],
  ['重大訊息與事件', '重大訊息與事件', '公告與法說會'],
]
const DATASETS = ['市場日行情', '歷史日價', '公司基本資料', '重大訊息', '法說會', '估值與財務']
const isEtf = computed(() => symbols.value.some(isEtfCode))
// ETF 沒有財報，不提供這個面向。
const focusOptions = computed(() => (isEtf.value ? FOCUS.filter(([value]) => value !== '財報與基本面') : FOCUS))
const PERIODS = [['近 3 個月', 3], ['近 6 個月', 6], ['近 1 年', 12]]

const removed = ref([])
const focus = ref('')
const months = ref(null)

const originalLabel = computed(() => options.value.horizon || understanding.value.historical_period?.label || '預設近 6 個月')
function monthsOf(label) {
  const text = String(label)
  if (/半年/.test(text)) return 6
  if (/一年/.test(text)) return 12
  const m = text.match(/(\d+)\s*(個月|年)/)
  return m ? Number(m[1]) * (m[2] === '年' ? 12 : 1) : null
}
const originalMonths = computed(() => monthsOf(originalLabel.value))
// 問題本身寫了特定年份或區間時，後端會以問題為準，這裡只顯示不提供切換。
const periodLocked = computed(() => {
  const kind = understanding.value.historical_period?.kind
  return Boolean(kind && kind !== 'relative') || /\d\s*[-–—~～到至]\s*\d+\s*(個月|月|年)/.test(dialog.value?.query || '') || originalMonths.value === null
})

watch(dialog, () => {
  removed.value = []
  focus.value = ''
  months.value = originalMonths.value
}, { immediate: true })

const nameOf = (code) => understanding.value.candidates?.find((c) => c.symbol === code)?.name || ''
const symbols = computed(() => options.value.requestedSymbols || [])
const kept = computed(() => symbols.value.filter((code) => !removed.value.includes(code)))
const scopeNote = computed(() => {
  const topic = options.value.researchTopic
  return topic ? `依「${topic}」由官方產業分類挑選標的` : '依你的問題由官方資料挑選標的'
})
const typo = computed(() => (dialog.value ? typoOf(dialog.value.query, understanding.value, symbols.value[0]) : null))
const finalQuery = computed(() => typo.value?.corrected || dialog.value?.query || '')
// 逐區出現：第一區打字機打出問題，接著第二區研究標的，最後第三區其他資訊；點一下可跳過。
const chars = computed(() => Array.from(finalQuery.value))
const typed = ref(0)
const stage = ref(2) // 0 打字中｜1 顯示研究標的｜2 全部顯示
const typedText = computed(() => chars.value.slice(0, typed.value).join(''))
const animating = computed(() => stage.value < 2)
let typer = 0
let timers = []
function stopAnimation() {
  clearInterval(typer)
  timers.forEach(clearTimeout)
  timers = []
}
function skipAnimation() {
  stopAnimation()
  typed.value = chars.value.length
  stage.value = 2
}
function playAnimation() {
  stopAnimation()
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return skipAnimation()
  typed.value = 0
  stage.value = 0
  // 長短題目的打字時間都控制在 1 秒內
  const step = Math.max(14, Math.min(36, 900 / Math.max(chars.value.length, 1)))
  typer = setInterval(() => {
    typed.value += 1
    if (typed.value < chars.value.length) return
    clearInterval(typer)
    timers.push(setTimeout(() => (stage.value = 1), 180))
    timers.push(setTimeout(() => (stage.value = 2), 620))
  }, step)
}
watch(dialog, (value) => (value ? playAnimation() : stopAnimation()), { immediate: true })
onBeforeUnmount(stopAnimation)

const isPreset = computed(() => PERIODS.some(([, value]) => value === originalMonths.value))

function cancel() {
  const current = dialog.value
  research.dialog = null
  current?.resolve?.(null)
}
function start() {
  const current = dialog.value
  const preset = PERIODS.find(([, value]) => value === months.value)
  const horizon = periodLocked.value || months.value === originalMonths.value ? originalLabel.value : preset?.[0] || originalLabel.value
  const task = createTask(finalQuery.value, {
    ...options.value,
    requestedSymbols: kept.value,
    horizon,
    focusLabel: focus.value,
    excludedSymbols: [...removed.value],
  })
  research.dialog = null
  current.resolve?.(task)
}
</script>

<template>
  <AppModal :open="Boolean(dialog)" title="確認研究範圍" modal-class="rc-modal" backdrop-class="rc-backdrop" @close="cancel">
    <div v-if="dialog" class="rc" @click="animating && skipAnimation()">
      <p class="rc-query"><small>我理解你想研究</small><strong class="rc-typing"><span class="rc-ghost">{{ finalQuery }}</span><span class="rc-typed" aria-hidden="true">{{ typedText }}<i v-if="stage === 0" class="rc-caret"></i></span></strong></p>

      <!-- 第二區：研究標的 -->
      <section class="rc-zone" :class="{ 'is-in': stage >= 1 }">
        <p v-if="typo" class="rc-typo" role="status">你輸入的是「{{ typo.typed }}」，我找到的是 <b>{{ symbols[0] }} {{ nameOf(symbols[0]) }}</b>，是這一檔嗎？</p>
        <div v-if="!typo" class="rc-field">
          <h3>研究標的</h3>
        <div v-if="symbols.length" class="rc-chips">
          <span v-for="code in kept" :key="code" class="rc-chip">
            <b>{{ code }}</b> {{ nameOf(code) }}
            <button v-if="kept.length > 1" type="button" :aria-label="`移除 ${code}`" @click="removed.push(code)">×</button>
          </span>
        </div>
        <p v-else class="rc-note">{{ scopeNote }}</p>
      </div>

      </section>

      <!-- 第三區：其他資訊 -->
      <section class="rc-zone rc-rest" :class="{ 'is-in': stage >= 2 }">
      <div class="rc-field">
        <h3>想先看哪個面向？</h3>
        <div class="rc-focus">
          <button v-for="[value, label, hint] in focusOptions" :key="label" type="button" :class="{ active: focus === value }" :aria-pressed="String(focus === value)" @click="focus = value">
            <strong>{{ label }}</strong><small>{{ hint }}</small>
          </button>
        </div>
      </div>

      <div class="rc-field">
        <h3>歷史資料期間</h3>
        <div v-if="!periodLocked" class="rc-periods">
          <button v-if="!isPreset" type="button" :class="{ active: months === originalMonths }" @click="months = originalMonths">{{ originalLabel }}</button>
          <button v-for="[label, value] in PERIODS" :key="value" type="button" :class="{ active: months === value }" :aria-pressed="String(months === value)" @click="months = value">{{ label }}</button>
        </div>
        <p v-else class="rc-note">{{ originalLabel }}（依你的問題）</p>
      </div>

      <div class="rc-plan">
        <h3>接下來 Agent 會做</h3>
        <p>查詢{{ DATASETS.join('、') }} → 程式計算指標 → Gemini 分析 1 次 → 逐句核對數字</p>
        <p v-if="isEtf" class="rc-assume">ETF 沒有營收、EPS 與本益比；成份股、費用率與配息目前也查不到，報告會以價格、波動與公告為主。</p>
        <p v-for="a in understanding.assumptions || []" :key="a" class="rc-assume">{{ a }}</p>
      </div>

      <div class="rc-actions">
        <button class="outline-button" type="button" @click="cancel">{{ typo ? '不是，重新輸入' : '取消' }}</button>
        <button class="primary-button" type="button" @click="start">{{ typo ? '是，開始研究 →' : '確認，開始研究 →' }}</button>
      </div>
      </section>
    </div>
  </AppModal>
</template>

<style scoped>
/* 可能從股票詳情視窗開啟，要疊在它上面 */
:global(.modal-backdrop.rc-backdrop){z-index:125}
:global(.modal.rc-modal){z-index:130;display:flex;flex-direction:column;overflow:hidden}
:global(.modal.rc-modal > .modal-header){flex:none}
:global(.modal.rc-modal > .modal-body){flex:1 1 auto;min-height:0;max-height:none;overflow:auto}
.rc{display:grid;gap:12px}
.rc-zone{visibility:hidden;opacity:0;transform:translateY(8px);transition:opacity .28s ease,transform .28s ease,visibility 0s linear .28s}
.rc-zone.is-in{visibility:visible;opacity:1;transform:none;transition:opacity .28s ease,transform .28s ease}
.rc-rest{display:grid;gap:12px}
.rc-typing{position:relative;display:block}
.rc-ghost{color:transparent}
.rc-typed{position:absolute;inset:0}
.rc-caret{display:inline-block;width:2px;height:1em;margin-left:2px;background:var(--blue);vertical-align:-.12em;animation:rc-blink .7s steps(1) infinite}
@keyframes rc-blink{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){.rc-zone,.rc-zone.is-in{transition:none;transform:none}.rc-caret{animation:none}}
.rc-typo{margin:0;padding:10px 14px;border:1px solid color-mix(in srgb,var(--orange) 40%,transparent);border-radius:12px;background:color-mix(in srgb,var(--orange) 10%,transparent);color:var(--text-strong);font-size:14px;line-height:1.6}
.rc-typo b{color:var(--blue)}
.rc-query{display:grid;gap:2px;margin:0;padding:10px 14px;border-radius:12px;background:color-mix(in srgb,var(--blue) 7%,transparent)}
.rc-query small{color:var(--muted);font-size:12px}
.rc-query strong{color:var(--text-strong);font-size:15px;line-height:1.5}
.rc-field{display:grid;gap:6px}
.rc h3{margin:0;color:var(--muted);font-size:13px;font-weight:700}
.rc-chips,.rc-periods{display:flex;flex-wrap:wrap;gap:6px}
.rc-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid var(--line-strong);border-radius:999px;color:var(--text);font-size:13px}
.rc-chip b{color:var(--text-strong)}
.rc-chip button{width:18px;height:18px;padding:0;border:0;border-radius:50%;background:transparent;color:var(--muted);font-size:14px;line-height:1;cursor:pointer}
.rc-chip button:hover{background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
.rc-note{margin:0;color:var(--text);font-size:13px}
.rc-focus{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.rc-focus button{display:grid;gap:2px;padding:9px 10px;border:1px solid var(--line-strong);border-radius:12px;background:transparent;text-align:left;cursor:pointer}
.rc-focus strong{color:var(--text-strong);font-size:13px}
.rc-focus small{color:var(--muted);font-size:12px;line-height:1.4}
.rc-focus button:hover,.rc-periods button:hover{border-color:var(--blue)}
.rc-focus button.active{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 9%,transparent);box-shadow:inset 0 0 0 1px var(--blue)}
.rc-periods button{padding:5px 14px;border:1px solid var(--line-strong);border-radius:999px;background:transparent;color:var(--text);font-size:13px;cursor:pointer}
.rc-periods button.active{border-color:var(--blue);background:var(--blue);color:#fff}
.rc-plan{display:grid;gap:4px;padding:10px 14px;border:1px dashed var(--line-strong);border-radius:12px}
.rc-plan p{margin:0;color:var(--text);font-size:13px;line-height:1.6}
.rc-plan .rc-assume{color:var(--muted);font-size:12px}
.rc-actions{display:flex;justify-content:flex-end;gap:8px}
@media (max-width:640px){.rc-focus{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
