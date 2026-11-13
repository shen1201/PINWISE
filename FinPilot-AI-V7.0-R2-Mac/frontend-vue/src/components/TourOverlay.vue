<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { tour, endTour } from '@/stores/tour.js'

// 導覽畫面：切到步驟所在頁面，高亮目標元素並放置說明框（對應舊版 goTourStep / positionTour）。
const router = useRouter()
const tooltip = ref(null)
const nextButton = ref(null)
const hi = reactive({ left: 0, top: 0, width: 0, height: 0, visible: false })
const tt = reactive({ left: 0, top: 0, width: 300, placement: 'right', visible: false })
let token = 0
// 往前或往後；optional 步驟找不到目標時沿同一方向跳過（例如還沒選股時略過「結果卡片」）。
let direction = 1

const step = computed(() => tour.steps[tour.index])
const isLast = computed(() => tour.index >= tour.steps.length - 1)
const frame = () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))

const visible = (el) => {
  if (!el) return false
  const r = el.getBoundingClientRect()
  return r.width > 24 && r.height > 16 && getComputedStyle(el).visibility !== 'hidden'
}

// 步驟是否適用目前畫面：onlyIfMissing 是「某元素不存在時才顯示」的替代說明（例如沒有公告時）。
const applies = (s) => !s.onlyIfMissing || !document.querySelector(s.onlyIfMissing)

function findTarget(s) {
  if (!applies(s)) return null
  const raw = document.querySelector(s.selector)
  if (visible(raw)) return raw
  if (s.optional) return null
  const heading = document.querySelector('#pageHost .page-banner, #pageHost .picker-dashboard-head, #pageHost .research-landing-heading')
  if (visible(heading)) return heading
  return document.querySelector(`#sidebar .nav-item[data-page="${s.page}"]`)
}

// 說明框位置：依右、左、下、上順序挑不超出畫面、不遮住目標的一側。
function placement(rect, width, height, sidebarTarget) {
  const gap = 14, edge = 12
  const sidebar = document.querySelector('#sidebar')
  const minLeft = innerWidth > 900 && sidebar ? Math.max(edge, sidebar.getBoundingClientRect().right + edge) : edge
  const maxLeft = Math.max(edge, innerWidth - width - edge), maxTop = Math.max(edge, innerHeight - height - edge)
  const candidates = sidebarTarget
    ? [{ side: 'right', left: rect.right + gap, top: rect.top + rect.height / 2 - height / 2 }, { side: 'bottom', left: rect.left, top: rect.bottom + gap }, { side: 'top', left: rect.left, top: rect.top - height - gap }]
    : [
        { side: 'right', left: rect.right + gap, top: rect.top + rect.height / 2 - height / 2 },
        { side: 'left', left: rect.left - width - gap, top: rect.top + rect.height / 2 - height / 2 },
        { side: 'bottom', left: rect.left + rect.width / 2 - width / 2, top: rect.bottom + gap },
        { side: 'top', left: rect.left + rect.width / 2 - width / 2, top: rect.top - height - gap },
      ]
  const overflow = (p) => Math.max(0, minLeft - p.left) + Math.max(0, p.left + width - (innerWidth - edge)) + Math.max(0, edge - p.top) + Math.max(0, p.top + height - (innerHeight - edge))
  const overlaps = (l, t) => l < rect.right + 4 && l + width > rect.left - 4 && t < rect.bottom + 4 && t + height > rect.top - 4
  return candidates
    .map((c, i) => {
      const left = Math.max(minLeft, Math.min(c.left, maxLeft)), top = Math.max(edge, Math.min(c.top, maxTop))
      return { ...c, left, top, score: overflow(c) * 100 + (overlaps(left, top) ? 10000 : 0) + i }
    })
    .sort((a, b) => a.score - b.score)[0]
}

async function position() {
  const current = ++token
  hi.visible = tt.visible = false
  const s = step.value
  if (!s) return
  if (router.currentRoute.value.name !== s.page) await router.push(`/${s.page}`)
  await nextTick()
  await frame()
  // 步驟需要先切換分頁時（投資足跡的歷程、徽章），先點那個分頁。
  if (s.click) {
    document.querySelector(s.click)?.click()
    await nextTick()
    await frame()
  }
  if (current !== token) return
  const el = findTarget(s)
  if (!el) {
    const nextIndex = tour.index + direction
    if (nextIndex < 0 || nextIndex >= tour.steps.length) return direction > 0 ? finish(true) : (direction = 1, position())
    tour.index = nextIndex
    return position()
  }
  el.scrollIntoView({ block: 'nearest', behavior: 'auto' })
  await frame()
  if (current !== token || !el.isConnected) return
  const r = el.getBoundingClientRect(), sidebarTarget = Boolean(el.closest('#sidebar')), pad = sidebarTarget ? 1 : 6
  Object.assign(hi, { left: r.left - pad, top: r.top - pad, width: r.width + pad * 2, height: r.height + pad * 2, visible: true })
  const sidebar = document.querySelector('#sidebar')
  const safeLeft = innerWidth > 900 && sidebar ? sidebar.getBoundingClientRect().right + 12 : 12
  tt.width = Math.min(330, Math.max(240, innerWidth - safeLeft - 12))
  await nextTick()
  const p = placement(r, tt.width, tooltip.value?.offsetHeight || 180, sidebarTarget)
  Object.assign(tt, { left: Math.round(p.left), top: Math.round(p.top), placement: p.side, visible: true })
  nextButton.value?.focus({ preventScroll: true })
}

function finish(mark = true) {
  token++
  // 導覽途中切換過分頁時，結束後回到第一步的分頁（例如投資足跡回到「總覽」）。
  const resetTab = tour.steps[0]?.click
  if (resetTab) document.querySelector(resetTab)?.click()
  const origin = endTour(mark)
  if (origin) router.push(origin)
}
const next = () => (isLast.value ? finish() : ((direction = 1), tour.index++, position()))
const back = () => tour.index > 0 && ((direction = -1), tour.index--, position())

// 單頁的功能教學：先切到那一頁，把目前畫面沒有的 optional 步驟拿掉，「第幾步／共幾步」才準。
// 需要切換分頁的步驟（click）保留，到時再找。
async function trimSteps() {
  const pages = new Set(tour.steps.map((s) => s.page))
  if (pages.size !== 1) return
  const [page] = pages
  if (router.currentRoute.value.name !== page) await router.push(`/${page}`)
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 350))
  const kept = tour.steps.filter((s) => s.click || (!s.optional ? true : applies(s) && visible(document.querySelector(s.selector))))
  if (kept.length) tour.steps = kept
}
watch(() => tour.active && tour.key, async (active) => {
  if (!active) return
  direction = 1
  await trimSteps()
  position()
})
const onResize = () => tour.active && position()
const onKeydown = (e) => tour.active && e.key === 'Escape' && finish(true)
onMounted(() => {
  addEventListener('resize', onResize)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  removeEventListener('resize', onResize)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="tour-overlay" :hidden="!tour.active">
    <div
      class="tour-highlight"
      :style="{ left: `${hi.left}px`, top: `${hi.top}px`, width: `${hi.width}px`, height: `${hi.height}px`, opacity: hi.visible ? 1 : 0 }"
    ></div>
    <div
      ref="tooltip"
      class="tour-tooltip"
      :data-placement="tt.placement"
      :style="{ left: `${tt.left}px`, top: `${tt.top}px`, width: `${tt.width}px`, opacity: tt.visible ? 1 : 0, pointerEvents: tt.visible ? 'auto' : 'none' }"
    >
      <span class="eyebrow">互動式新手導覽</span>
      <h3>{{ step?.title }}</h3>
      <p>{{ step?.text }}</p>
      <div class="tour-options"><button class="text-button" type="button" @click="finish(true)">跳過導覽</button></div>
      <div class="tour-controls">
        <button class="soft-button" type="button" :disabled="tour.index === 0" @click="back">上一步</button>
        <span>{{ tour.index + 1 }} / {{ tour.steps.length }}</span>
        <button ref="nextButton" class="primary-button small" type="button" @click="next">{{ isLast ? '完成' : '下一步' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 導覽進行中擋住背景，只能操作說明框；highlight 只是標示位置，不能點 */
.tour-overlay:not([hidden]){pointer-events:auto}
</style>
