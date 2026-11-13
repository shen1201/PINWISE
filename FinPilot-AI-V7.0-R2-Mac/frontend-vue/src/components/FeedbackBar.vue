<script setup>
import { computed, ref } from 'vue'
import { footprint, rate } from '@/stores/footprint.js'

// 三段回饋：有用／還好／很糟；很糟時多問一個固定選項的原因。
const props = defineProps({
  itemId: { type: String, required: true },
  feature: { type: String, required: true },
  prompt: { type: String, default: '' },
  compact: { type: Boolean, default: false },
})
const OPTIONS = [['useful', '有用'], ['ok', '還好'], ['bad', '很糟']]
const REASONS = [['data_wrong', '資料有錯'], ['hard_to_read', '看不懂'], ['too_slow', '太慢'], ['off_topic', '沒回答到問題']]
const record = computed(() => footprint.records.find((row) => row.id === props.itemId))
const asking = ref(false)
// 再點一次同一個選項就是取消。
function choose(value) {
  const next = record.value.rating === value ? null : value
  rate(props.itemId, props.feature, next)
  asking.value = next === 'bad'
}
function giveReason(reason) {
  rate(props.itemId, props.feature, 'bad', reason)
  asking.value = false
}
</script>

<template>
  <div v-if="record && !record.deleted" class="fb" :class="{ 'is-compact': compact }">
    <span v-if="prompt && !record.rating" class="fb-prompt">{{ prompt }}</span>
    <div class="fb-options" role="group" aria-label="這次的評價">
      <button v-for="[value, label] in OPTIONS" :key="value" type="button" :class="[`is-${value}`, { active: record.rating === value }]" :aria-pressed="String(record.rating === value)" @click="choose(value)">{{ label }}</button>
    </div>
    <div v-if="asking" class="fb-reasons" role="group" aria-label="哪裡不好">
      <button v-for="[value, label] in REASONS" :key="value" type="button" @click="giveReason(value)">{{ label }}</button>
    </div>
  </div>
</template>

<style scoped>
.fb{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.fb-prompt{color:var(--text);font-size:12px;font-weight:600}
.fb-options,.fb-reasons{display:flex;gap:3px}
.fb button{padding:2px 9px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);font-size:12px;cursor:pointer;white-space:nowrap}
.fb button:hover,.fb button:focus-visible{border-color:var(--blue);color:var(--blue)}
.fb-options .active.is-useful{border-color:var(--blue);background:color-mix(in srgb,var(--blue) 14%,transparent);color:var(--blue);font-weight:700}
.fb-options .active.is-ok{border-color:var(--muted);background:color-mix(in srgb,var(--muted) 16%,transparent);color:var(--text-strong);font-weight:700}
.fb-options .active.is-bad{border-color:var(--red);background:color-mix(in srgb,var(--red) 13%,transparent);color:var(--red);font-weight:700}
.fb.is-compact button{padding:1px 7px}
</style>
