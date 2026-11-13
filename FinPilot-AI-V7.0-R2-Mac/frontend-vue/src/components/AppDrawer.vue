<script setup>
import { watch, onBeforeUnmount } from 'vue'

// 沿用舊版 #drawer 的結構與 class（對應舊版 openDrawer / closeDrawer）。
const props = defineProps({
  open: Boolean,
  title: { type: String, default: '' },
  eyebrow: { type: String, default: 'PINWISE' },
  size: { type: String, default: 'large' }, // small | medium | large
})
const emit = defineEmits(['close'])

const onKeydown = (event) => event.key === 'Escape' && emit('close')
watch(() => props.open, (open) => document[open ? 'addEventListener' : 'removeEventListener']('keydown', onKeydown), { immediate: true })
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Teleport to="body">
    <div class="drawer-backdrop" :hidden="!open" @click="emit('close')"></div>
    <aside class="drawer" :class="[`drawer-${size}`, { open }]" :aria-hidden="String(!open)">
      <header class="drawer-header">
        <div><span class="eyebrow">{{ eyebrow }}</span><h2>{{ title }}</h2></div>
        <button class="icon-button" type="button" aria-label="關閉" @click="emit('close')">✕</button>
      </header>
      <div class="drawer-body"><slot v-if="open" /></div>
    </aside>
  </Teleport>
</template>
