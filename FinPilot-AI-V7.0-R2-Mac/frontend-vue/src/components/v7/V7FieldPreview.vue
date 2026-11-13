<script setup>
// 「加入後，這裡會整理」欄位預覽（對應舊版 js/workspace.js 的 v7FieldPreview）。
defineProps({ fields: { type: Array, required: true } }) // [[標題, 說明], ...]
</script>

<template>
  <div class="v7-field-preview" aria-label="加入資料後的內容">
    <span class="v7-preview-label">加入後，這裡會整理</span>
    <div v-for="[title, copy] in fields" :key="title">
      <span class="v7-field-dot" aria-hidden="true"></span><strong>{{ title }}</strong><small>{{ copy }}</small>
    </div>
  </div>
</template>
