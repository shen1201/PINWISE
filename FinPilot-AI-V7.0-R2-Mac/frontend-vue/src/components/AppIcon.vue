<script setup>
import { ICON_PATHS } from '@/data/nav.js'

defineProps({ name: { type: String, required: true }, size: { type: Number, default: 20 } })
</script>

<template>
  <!-- 圖示路徑是固定常數，不含使用者輸入，可安全使用 v-html。 -->
  <svg
    class="ui-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="ICON_PATHS[name] || ICON_PATHS.info"
  />
</template>
