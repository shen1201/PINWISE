<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { settings } from '@/stores/ui.js'

// 「已參考你的偏好」小標籤：讓使用者看得到個人化偏好真的有傳給 AI。
// 只列這個功能實際會用到的欄位；沒有完成偏好時不顯示。
const props = defineProps({
  fields: { type: Array, default: () => ['explanationStyle', 'riskTolerance', 'objective'] },
  label: { type: String, default: '已參考你的偏好' },
  // 研究與選股傳入當時送出的偏好快照；沒傳就用目前的設定（例如助手的下一則回答）。
  prefs: { type: Object, default: null },
})
const router = useRouter()
const values = computed(() => {
  const prefs = props.prefs || settings.personalPrefs
  if (!prefs.completed) return []
  return props.fields.map((key) => (key === 'budget' && prefs.budget && prefs.budget !== '不想填' ? `預估投入 ${prefs.budget}` : key === 'budget' ? '' : prefs[key])).filter(Boolean)
})
</script>

<template>
  <p v-if="values.length" class="prefs-badge">
    <span class="prefs-dot" aria-hidden="true"></span>
    <span class="prefs-text" :title="`${label}：${values.join('・')}`">{{ label }}：{{ values.join('・') }}</span>
    <button type="button" @click="router.push('/settings/preferences')">修改</button>
  </p>
</template>

<style scoped>
.prefs-badge{display:inline-flex;align-items:center;gap:6px;width:fit-content;max-width:100%;min-width:0;margin:0;padding:2px 4px 2px 10px;border:1px solid color-mix(in srgb,var(--blue) 24%,transparent);border-radius:999px;background:color-mix(in srgb,var(--blue) 7%,transparent);color:var(--text);font-size:12px;line-height:1.5}
.prefs-dot{flex:none;width:6px;height:6px;border-radius:50%;background:var(--blue)}
.prefs-text{overflow:hidden;min-width:0;text-overflow:ellipsis;white-space:nowrap}
.prefs-badge button{flex:none;padding:0 8px;border:0;border-radius:999px;background:transparent;color:var(--blue);font-size:12px;font-weight:700;cursor:pointer}
.prefs-badge button:hover{background:color-mix(in srgb,var(--blue) 12%,transparent)}
</style>
