<script setup>
import { computed } from 'vue'
import InfoTip from './InfoTip.vue'
import { metricWarning } from '@/stores/snapshots.js'
import { track } from '@/stores/footprint.js'

// 指標數字旁的「！」：數字誇張或疑似失真時才出現，滑鼠移上去說明可能原因。
const props = defineProps({ metrics: { type: Object, default: null }, field: { type: String, required: true } })
const text = computed(() => metricWarning(props.metrics, props.field))
</script>

<template>
  <span v-if="text" class="metric-flag" @pointerenter="metrics?.suspected_split_dates?.length && track('split_flag', '', { once: true })"><InfoTip :text="text" label="數字異常">！</InfoTip></span>
</template>

<style scoped>
.metric-flag{display:inline-flex;flex:none;vertical-align:middle}
.metric-flag :deep(.info-tip){width:18px;height:18px;margin-left:5px;background:color-mix(in srgb,var(--orange) 18%,transparent);color:var(--orange);font-size:12px;font-weight:800}
</style>
