<script setup>
// 窄螢幕的區塊切換標籤（對應舊版 r2AddSectionTabs 產生的 nav）；寬螢幕由 CSS 隱藏。
defineProps({ labels: { type: Array, required: true } })
const current = defineModel({ type: Number, default: 0 })
</script>

<template>
  <nav class="r2-section-tabs" aria-label="切換目前畫面的區塊">
    <button
      v-for="(label, index) in labels"
      :key="label + index"
      type="button"
      :class="{ active: index === current }"
      :aria-pressed="String(index === current)"
      @click="current = index"
    >{{ label }}</button>
  </nav>
</template>
