<script setup>
import { ref, nextTick, onBeforeUnmount } from 'vue'

// 名詞說明提示：滑鼠移入、鍵盤聚焦或點擊都會顯示（瀏覽器內建 title 要停留約 1 秒且觸控無法使用）。
// 提示框 Teleport 到 body 並以 fixed 定位，不會被 modal 的捲動區域裁切。
const props = defineProps({
  text: { type: String, required: true },
  label: { type: String, default: '說明' },
  // warning：紅色警告樣式；觸發按鈕內容可用 slot 自訂（預設 ⓘ）。
  variant: { type: String, default: '' },
})

const open = ref(false)
const pinned = ref(false)
const anchor = ref(null)
const bubble = ref(null)
const pos = ref({ left: 0, top: 0, below: false })
const id = `info-tip-${Math.random().toString(36).slice(2, 8)}`

async function show() {
  open.value = true
  await nextTick()
  const a = anchor.value?.getBoundingClientRect()
  const b = bubble.value?.getBoundingClientRect()
  if (!a || !b) return
  const margin = 10
  const left = Math.min(Math.max(a.left + a.width / 2 - b.width / 2, margin), window.innerWidth - b.width - margin)
  const below = a.top - b.height - 8 < margin
  pos.value = { left, top: below ? a.bottom + 8 : a.top - b.height - 8, below }
}
function hide() {
  if (!pinned.value) open.value = false
}
function toggle() {
  pinned.value = !pinned.value
  pinned.value ? show() : (open.value = false)
}
function onOutside(event) {
  if (pinned.value && !anchor.value?.contains(event.target)) {
    pinned.value = false
    open.value = false
  }
}
// 捲動時提示框位置會跑掉，直接收起。
function onScroll() {
  if (!open.value) return
  pinned.value = false
  open.value = false
}
document.addEventListener('pointerdown', onOutside)
window.addEventListener('scroll', onScroll, true)
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onOutside)
  window.removeEventListener('scroll', onScroll, true)
})
</script>

<template>
  <button
    ref="anchor"
    type="button"
    class="info-tip"
    :class="variant ? `info-tip--${variant}` : ''"
    :aria-label="`${label}說明`"
    :aria-describedby="open ? id : undefined"
    :aria-expanded="String(open)"
    @mouseenter="show"
    @mouseleave="hide"
    @focus="show"
    @blur="pinned = false; open = false"
    @click.stop="toggle"
    @keydown.esc="pinned = false; open = false"
  ><slot>ⓘ</slot></button>
  <Teleport to="body">
    <div
      v-if="open"
      :id="id"
      ref="bubble"
      role="tooltip"
      class="info-tip-bubble"
      :style="{ left: `${pos.left}px`, top: `${pos.top}px` }"
    >{{ props.text }}</div>
  </Teleport>
</template>

<style scoped>
.info-tip{display:inline-grid;place-items:center;width:20px;height:20px;margin-left:2px;padding:0;border:0;border-radius:50%;background:transparent;color:#4779ba;font-size:14px;line-height:1;cursor:help;vertical-align:middle}
.info-tip:hover,.info-tip:focus-visible,.info-tip[aria-expanded="true"]{background:rgba(51,127,244,.12);outline:none}
.info-tip--warning{width:auto;height:auto;gap:6px;padding:4px 12px 4px 6px;border:1px solid color-mix(in srgb,var(--red) 35%,transparent);border-radius:999px;background:color-mix(in srgb,var(--red) 9%,transparent);color:var(--red);font-size:13px;font-weight:700;cursor:help;display:inline-flex;align-items:center}
.info-tip--warning:hover,.info-tip--warning:focus-visible,.info-tip--warning[aria-expanded="true"]{background:color-mix(in srgb,var(--red) 15%,transparent)}
.info-tip-bubble{position:fixed;z-index:400;width:max-content;max-width:min(300px,calc(100vw - 20px));padding:10px 12px;border-radius:11px;background:var(--tooltip-bg,#0f2e58);color:var(--tooltip-text,#fff);font-size:13px;font-weight:500;line-height:1.6;white-space:pre-line;box-shadow:0 10px 32px rgba(0,0,0,.22);pointer-events:none}
</style>
