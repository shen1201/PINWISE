<script setup>
import V7FieldPreview from './V7FieldPreview.vue'

// 「閱讀這個工作區」說明卡（對應舊版 js/workspace.js 的 v7Context）。
defineProps({
  title: { type: String, required: true },
  copy: { type: String, required: true },
  fields: { type: Array, required: true },
})
</script>

<template>
  <aside class="v7-context">
    <span class="eyebrow">閱讀這個工作區</span>
    <h2>{{ title }}</h2>
    <p>{{ copy }}</p>
    <V7FieldPreview :fields="fields" />
  </aside>
</template>
