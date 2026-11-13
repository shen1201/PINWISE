<script setup>
import { computed } from 'vue'
import InfoTip from '@/components/InfoTip.vue'

// 頁首右側的「更新」按鈕，旁邊 ⓘ 顯示上次更新時間與資料更新節奏。
const props = defineProps({
  loading: Boolean,
  updatedAt: { type: [Date, Number], default: null },
  details: { type: String, default: '' },
})
defineEmits(['refresh'])

const tip = computed(() => {
  const when = props.updatedAt ? new Date(props.updatedAt) : null
  const text = when ? when.toLocaleString('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '尚未取得'
  return `上次更新：${text}${props.details ? `\n${props.details}` : ''}`
})
</script>

<template>
  <div class="rf">
    <button class="rf-btn" type="button" :disabled="loading" :aria-busy="String(loading)" @click="$emit('refresh')">
      <span class="rf-icon" :class="{ spin: loading }" aria-hidden="true">↻</span>{{ loading ? '更新中' : '更新' }}
    </button>
    <InfoTip :text="tip" label="資料更新時間" />
  </div>
</template>

<style scoped>
.rf{position:absolute;z-index:5;top:50%;right:192px;transform:translateY(-50%);display:flex;align-items:center;gap:2px;min-height:44px}
.rf-btn{display:inline-flex;align-items:center;gap:6px;min-height:40px;padding:0 14px;border:1px solid color-mix(in srgb,var(--blue) 35%,transparent);border-radius:999px;background:linear-gradient(115deg,#eaf2ff,#f1eaff);color:#2b5fc4;font-size:14px;font-weight:800;text-shadow:none;cursor:pointer}
.rf-btn:hover:not(:disabled){border-color:var(--blue)}
.rf-btn:disabled{cursor:wait;opacity:.75}
.rf-icon{display:inline-block;font-size:16px;line-height:1}
.rf-icon.spin{animation:rf-spin .8s linear infinite}
@keyframes rf-spin{to{transform:rotate(360deg)}}
:global(body[data-theme="dark"] .rf-btn){background:#1c3355;color:#cfe0ff}
@media (max-width:1100px){.rf{position:static;margin-top:8px;transform:none}}
@media (prefers-reduced-motion:reduce){.rf-icon.spin{animation:none}}
</style>
