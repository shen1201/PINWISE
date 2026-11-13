<script setup>
// 空資料用：股怪或股吉的虛線剪影，像從畫面上割開、還沒填進東西的位置。
defineProps({ kind: { type: String, default: 'guguai' } })
const HEAD = {
  guguai: 'M70 96L60 50Q58 42 66 46L96 68Q104 64 110 66L114 50L122 65L131 52L134 67Q140 65 146 68L174 46Q182 42 180 50L170 96Q178 108 176 122L186 128L173 134L177 148L162 145Q144 162 120 162Q96 162 78 145L63 148L67 134L54 128L64 122Q62 108 70 96Z',
  guji: 'M70 96L62 54Q60 46 68 49L97 69Q106 64 112 66L108 50L120 62L132 48L129 66Q135 65 143 69L172 49Q180 46 178 54L170 96Q180 108 177 124L186 131L174 136L175 148L162 146Q144 162 120 162Q96 162 78 146L65 148L66 136L54 131L63 124Q60 108 70 96Z',
}
</script>

<template>
  <svg class="gg-outline" viewBox="46 36 148 182" aria-hidden="true">
    <path class="fill" :d="HEAD[kind]" />
    <path class="fill" d="M98 162Q84 176 84 214H156Q156 176 142 162Q131 166 120 166Q109 166 98 162Z" />
    <path class="thin" d="M73 86L69 59L91 73Q79 77 73 86ZM167 86L171 59L149 73Q161 77 167 86Z" />
    <template v-if="kind === 'guji'">
      <ellipse class="thin" cx="98" cy="113" rx="14" ry="15.5" /><ellipse class="thin" cx="142" cy="113" rx="14" ry="15.5" />
      <path class="thin" d="M108 137Q120 150 132 137" />
    </template>
    <template v-else>
      <ellipse class="thin" cx="98" cy="113" rx="14" ry="12.5" /><ellipse class="thin" cx="142" cy="113" rx="14" ry="12.5" />
      <path class="thin" d="M111 138Q115.5 145 120 138Q124.5 145 129 138" />
    </template>
    <path class="thin" d="M116 171H124L122 178L128 200L120 211L112 200L118 178Z" />
  </svg>
</template>

<style scoped>
.gg-outline{display:block;width:100%;height:auto;overflow:visible}
.gg-outline path,.gg-outline ellipse{fill:none;stroke:color-mix(in srgb,var(--muted) 70%,transparent);stroke-linecap:round;stroke-linejoin:round}
.gg-outline .fill{fill:color-mix(in srgb,var(--muted) 7%,transparent);stroke-width:2.8;stroke-dasharray:8 7}
.gg-outline .thin{stroke-width:2;stroke-dasharray:4 5}
</style>
