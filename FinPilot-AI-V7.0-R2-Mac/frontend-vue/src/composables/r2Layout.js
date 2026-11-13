import { ref, reactive, computed, toValue, onMounted, onBeforeUnmount } from 'vue'

// 窄螢幕的區塊切換（對應舊版 js/workspace.js 的 r2AddSectionTabs）。
// 標籤列一律渲染，是否顯示由 CSS 決定；窄螢幕時只顯示目前選擇的區塊。
export const NARROW = '(max-width: 900px), (max-height: 560px)'

// 各頁上次選擇的區塊，切頁回來時保留（對應舊版 r2SectionChoice）。
const choices = reactive({})

export function useMedia(query) {
  const media = typeof matchMedia === 'function' ? matchMedia(query) : null
  const matches = ref(Boolean(media?.matches))
  const onChange = (event) => (matches.value = event.matches)
  onMounted(() => media?.addEventListener('change', onChange))
  onBeforeUnmount(() => media?.removeEventListener('change', onChange))
  return matches
}

// key：頁面識別；count：區塊數（數字或 ref）；narrow：自訂的窄螢幕條件（ref）。
export function useSectionTabs(key, count, { narrow, initial = 0 } = {}) {
  const isNarrow = narrow || useMedia(NARROW)
  if (choices[key] === undefined) choices[key] = initial
  const current = computed({
    get: () => Math.min(choices[key], Math.max(0, toValue(count) - 1)),
    set: (value) => (choices[key] = value),
  })
  const hidden = (index) => isNarrow.value && index !== current.value
  return { isNarrow, current, hidden }
}
