import { reactive } from 'vue'
import { tours } from '@/data/tours.js'
import { settings } from './ui.js'

// 互動式導覽狀態（對應舊版 js/tours.js 的 startTour / endTour）；畫面由 TourOverlay.vue 負責。
export const tour = reactive({
  active: false,
  key: '',
  steps: [],
  index: 0,
  origin: null, // 結束後要回到的頁面路徑
})

// 導覽結束後要做的事（例如重新打開「功能教學」抽屜），不放進 reactive。
let afterEnd = null

export function startTour(which = 'full', { restore = false, currentPath = '', onEnd = null } = {}) {
  afterEnd = onEnd
  const steps = which === 'full' ? tours.full.filter((step) => step.page === 'settings' || settings.navVisible[step.page] !== false) : tours[which] || tours.full
  Object.assign(tour, { active: true, key: which, steps, index: 0, origin: restore ? currentPath : null })
}

export function endTour(mark = true) {
  if (tour.key === 'full' && mark) settings.onboardingCompleted = true
  const origin = tour.origin
  Object.assign(tour, { active: false, key: '', steps: [], index: 0, origin: null })
  const done = afterEnd
  afterEnd = null
  if (done) setTimeout(done, 0)
  return origin
}
