<script setup>
import { watch, onBeforeUnmount } from 'vue'

// 沿用舊版 #modal 的結構與 class；modalClass 對應舊版 showModal 後加上的 class。
const props = defineProps({
  open: Boolean,
  title: { type: String, default: '' },
  status: { type: String, default: '' },
  modalClass: { type: [String, Array], default: '' },
  backdropClass: { type: String, default: '' },
  // false 時不顯示右上角 ✕（仍會發出 close，由使用端決定要不要關）。
  closable: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}
watch(
  () => props.open,
  (open) => {
    document.body.classList.toggle('modal-open', open)
    document[open ? 'addEventListener' : 'removeEventListener']('keydown', onKeydown)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  document.body.classList.remove('modal-open')
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <!-- 關閉時不渲染：舊版 CSS 對部分 modal class 設了 display，會蓋過 hidden 屬性。 -->
    <template v-if="open">
      <div class="modal-backdrop" :class="backdropClass" @click="emit('close')"></div>
      <section class="modal" :class="modalClass" role="dialog" aria-modal="true" :aria-label="title">
        <header class="modal-header">
          <div><span class="eyebrow">PINWISE</span><h2>{{ title }}</h2></div>
          <span v-if="status" class="demo-badge modal-status">{{ status }}</span>
          <button v-if="closable" class="icon-button" type="button" aria-label="關閉視窗" @click="emit('close')">✕</button>
        </header>
        <div class="modal-body">
          <slot />
        </div>
      </section>
    </template>
  </Teleport>
</template>
