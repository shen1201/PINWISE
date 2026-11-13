<script setup>
// 尚未設計圖案的徽章：以形狀區分類型（圓形累計、六角形連續、盾形隱藏）。
defineProps({ shape: { type: String, default: 'circle' } })
const SHAPES = {
  hex: 'M50 5L89 27V73L50 95L11 73V27Z',
  shield: 'M50 5Q70 14 88 13V50Q88 78 50 96Q12 78 12 50V13Q30 14 50 5Z',
}
</script>

<template>
  <svg class="slot" viewBox="0 0 100 100" aria-hidden="true">
    <circle v-if="shape === 'circle'" cx="50" cy="50" r="44" /><path v-else :d="SHAPES[shape]" />
    <circle v-if="shape === 'circle'" cx="50" cy="50" r="35" class="inner" />
    <text v-if="shape === 'shield'" x="50" y="62" text-anchor="middle">?</text>
  </svg>
</template>

<style scoped>
.slot{display:block;width:100%;height:100%}
.slot circle,.slot path{fill:color-mix(in srgb,var(--muted) 9%,transparent);stroke:color-mix(in srgb,var(--muted) 55%,transparent);stroke-width:2.4}
.slot .inner{fill:none;stroke-width:1.4}
.slot text{fill:var(--muted);font-size:34px;font-weight:800}
</style>
