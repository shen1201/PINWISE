<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import { footprint, rate, saveComment, COMMENT_LIMIT } from '@/stores/footprint.js'

// 偶爾出現的回饋小窗：回答完成後從底部淡入，選有用／還好／很糟，可以再打幾句話（選填）。
// 送出或關閉後收起，不會留在每則訊息下面。
const props = defineProps({
  itemId: { type: String, required: true },
  feature: { type: String, required: true },
  question: { type: String, default: '這次的回答對你有幫助嗎？' },
})
const emit = defineEmits(['done'])

const OPTIONS = [['useful', '有用'], ['ok', '還好'], ['bad', '很糟']]
const REASONS = [['data_wrong', '資料有錯'], ['hard_to_read', '看不懂'], ['too_slow', '太慢'], ['off_topic', '沒回答到問題']]
const record = computed(() => footprint.records.find((row) => row.id === props.itemId))
const step = ref('ask') // ask | more | thanks
const rating = ref('')
const reason = ref(null)
const text = ref('')
let timer = 0

function choose(value) {
  rating.value = value
  rate(props.itemId, props.feature, value)
  step.value = 'more'
}
function pickReason(value) {
  reason.value = reason.value === value ? null : value
  rate(props.itemId, props.feature, 'bad', reason.value)
}
function finish(withText) {
  if (withText && text.value.trim()) saveComment(props.itemId, props.feature, text.value)
  step.value = 'thanks'
  timer = setTimeout(() => emit('done'), 1400)
}
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <section v-if="record && !record.deleted" class="fbp" role="dialog" aria-live="polite" aria-label="回饋">
    <button v-if="step !== 'thanks'" class="fbp-close" type="button" aria-label="不用了" title="不用了" @click="emit('done')">×</button>
    <template v-if="step === 'ask'">
      <strong>{{ question }}</strong>
      <div class="fbp-options" role="group" aria-label="這次的評價">
        <button v-for="[value, label] in OPTIONS" :key="value" type="button" :class="`is-${value}`" @click="choose(value)">{{ label }}</button>
      </div>
    </template>
    <template v-else-if="step === 'more'">
      <strong>{{ rating === 'bad' ? '哪裡不好？' : '謝謝！想多說一點嗎？' }}<small>（選填）</small></strong>
      <div v-if="rating === 'bad'" class="fbp-reasons" role="group" aria-label="哪裡不好">
        <button v-for="[value, label] in REASONS" :key="value" type="button" :class="{ active: reason === value }" :aria-pressed="String(reason === value)" @click="pickReason(value)">{{ label }}</button>
      </div>
      <textarea v-model="text" :maxlength="COMMENT_LIMIT" rows="2" placeholder="例如：希望多說明風險、數字看不懂…" aria-label="文字回饋"></textarea>
      <div class="fbp-actions">
        <small>匿名送給 PINWISE 團隊，請勿輸入個人資料・{{ text.length }}/{{ COMMENT_LIMIT }}</small>
        <button class="text-button" type="button" @click="finish(false)">略過</button>
        <button class="primary-button small" type="button" :disabled="!text.trim() && !(rating === 'bad' && reason)" @click="finish(true)">送出</button>
      </div>
    </template>
    <p v-else class="fbp-thanks">已收到，可以在「我的投資足跡 → 歷程」查看你的回饋。</p>
  </section>
</template>

<style scoped>
.fbp{position:relative;display:grid;gap:8px;margin:0 14px 8px;padding:11px 14px;border:1px solid color-mix(in srgb,var(--blue) 26%,var(--line));border-radius:14px;background:var(--surface-solid,#fff);box-shadow:0 10px 26px rgba(16,47,86,.14)}
.fbp strong{padding-right:22px;color:var(--text-strong);font-size:13px}
.fbp strong small{margin-left:4px;color:var(--muted);font-weight:400}
.fbp-close{position:absolute;top:6px;right:8px;width:24px;height:24px;border:0;border-radius:50%;background:transparent;color:var(--muted);font-size:16px;cursor:pointer}
.fbp-close:hover{background:color-mix(in srgb,var(--muted) 14%,transparent)}
.fbp-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.fbp-options button,.fbp-reasons button{padding:6px 8px;border:1px solid var(--line-strong);border-radius:999px;background:transparent;color:var(--text);font-size:13px;font-weight:600;cursor:pointer;transition:border-color .15s,background .15s}
.fbp-options .is-useful:hover{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 10%,transparent);color:var(--blue)}
.fbp-options .is-ok:hover{border-color:var(--muted);background:color-mix(in srgb,var(--muted) 14%,transparent)}
.fbp-options .is-bad:hover{border-color:var(--red);background:color-mix(in srgb,var(--red) 10%,transparent);color:var(--red)}
.fbp-reasons{display:flex;flex-wrap:wrap;gap:5px}
.fbp-reasons button{padding:3px 10px;font-size:12px}
.fbp-reasons button.active{border-color:var(--red);background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
.fbp textarea{width:100%;resize:none;padding:7px 10px;border:1px solid var(--line-strong);border-radius:10px;background:var(--pw-inner,transparent);color:var(--text-strong);font:inherit;font-size:13px}
.fbp-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px}
.fbp-actions small{margin-right:auto;color:var(--muted);font-size:11px}
.fbp-thanks{margin:0;color:var(--text);font-size:13px}
:global(body[data-theme="dark"]) .fbp{background:#17304f;border-color:#35557d}
</style>
