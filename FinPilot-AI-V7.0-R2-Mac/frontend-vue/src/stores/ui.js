import { reactive, watch, watchEffect, computed } from 'vue'
import sunset from '@root/assets/hero-taipei-sunset.png'
import courtyard from '@root/assets/scene-courtyard-day.jpg'
import garden from '@root/assets/scene-garden-terrace.jpg'
import library from '@root/assets/scene-library-warm.png'
import { storageKey } from '../api/runtime.js'

// 使用者設定與全域 UI 狀態（對應舊版 state 中的外觀、側欄、通知、個人偏好）。
// 設定存在 localStorage 的 pinwise_vue_settings；開關面板等暫時狀態不保存。
const STORE_KEY = storageKey('pinwise_vue_settings')

export const SCENES = {
  sunset: { name: '台北日落', url: sunset },
  morning: { name: '晴光庭院', url: courtyard },
  night: { name: '綠意露台', url: garden },
  interior: { name: '暖光書房', url: library },
}

export const NAV_ORDER = ['home', 'picker', 'research', 'candidates', 'market', 'compare', 'tracking', 'scorecard', 'learning', 'esg', 'evidence']

const DEFAULTS = {
  nickname: '訪客投資者',
  displayMode: 'light', // light | white | dark | classic | system
  scene: 'sunset',
  brightness: 100,
  blur: 0,
  cardOpacity: 93,
  fontScale: 100,
  overlay: 12,
  motion: true,
  navOrder: [...NAV_ORDER],
  navVisible: Object.fromEntries(NAV_ORDER.map((key) => [key, true])),
  // 通知分類與通知中心分頁一一對應：研究／追蹤／系統（market、learning 已停用，舊資料保留不影響）。
  notificationPrefs: { research: true, tracking: true, system: true },
  personalPrefs: { completed: false, updatedAt: null, explanationStyle: '', horizon: '', riskTolerance: '', objective: '', liquidity: '', budget: '', market: '台股' },
  onboardingCompleted: false,
  // 側邊欄隱藏頁面的提醒：{ 頁面 key: 'YYYY-MM-DD' } 代表當天不再提醒。
  navReminderSnooze: {},
  // ESG 專區進入時的說明視窗：snoozeDay＝當天不再顯示；off＝永久關閉（設定 → 側邊欄管理）。
  esgIntro: { snoozeDay: '', off: false },
  notifications: [],
}
export const APPEARANCE_DEFAULTS = { displayMode: 'light', scene: 'sunset', brightness: 100, blur: 0, overlay: 12, cardOpacity: 93, fontScale: 100, motion: true }

function load() {
  let saved = {}
  try {
    saved = JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {}
  } catch {}
  const merged = { ...structuredClone(DEFAULTS), ...saved }
  merged.navVisible = { ...DEFAULTS.navVisible, ...saved.navVisible, home: true }
  merged.navOrder = [...new Set([...(saved.navOrder || []).filter((k) => NAV_ORDER.includes(k)), ...NAV_ORDER])]
  // 版本 2：智慧選股移到標的研究前面；只調整一次，之後使用者在設定裡自訂的順序不受影響。
  if ((saved.navOrderVersion || 0) < 2) {
    const order = merged.navOrder.filter((k) => k !== 'picker')
    order.splice(order.indexOf('research'), 0, 'picker')
    merged.navOrder = order
  }
  // 版本 3：市場總覽移到股票比較前面；同樣只調整一次。
  if ((saved.navOrderVersion || 0) < 3) {
    const order = merged.navOrder.filter((k) => k !== 'market')
    order.splice(order.indexOf('compare'), 0, 'market')
    merged.navOrder = order
  }
  if ((saved.navOrderVersion || 0) < 4) {
    const order = merged.navOrder.filter((k) => k !== 'esg')
    order.splice(order.indexOf('learning') + 1, 0, 'esg')
    merged.navOrder = order
  }
  merged.navOrderVersion = 4
  merged.notificationPrefs = { ...DEFAULTS.notificationPrefs, ...saved.notificationPrefs }
  merged.personalPrefs = { ...DEFAULTS.personalPrefs, ...saved.personalPrefs }
  merged.esgIntro = { ...DEFAULTS.esgIntro, ...saved.esgIntro }
  if (!SCENES[merged.scene]) merged.scene = 'sunset'
  return merged
}

export const settings = reactive(load())
watch(settings, (value) => {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(value))
  } catch {}
}, { deep: true })

// 暫時性的 UI 狀態。
export const ui = reactive({
  assistantOpen: false,
  assistantDraft: '', // 其他頁面帶入輸入框的問題（不自動送出）
  mobileNavOpen: false,
  toasts: [],
})

let toastId = 0
export function toast(message, duration = 2600) {
  const id = ++toastId
  ui.toasts.push({ id, message })
  setTimeout(() => {
    const index = ui.toasts.findIndex((item) => item.id === id)
    if (index >= 0) ui.toasts.splice(index, 1)
  }, duration)
}

// 個人偏好完成時才送給後端；未完成時不替使用者假設條件。
export const preferencesPayload = () => (settings.personalPrefs.completed ? { ...settings.personalPrefs } : {})

export const unreadCount = computed(() => settings.notifications.filter((n) => !n.read).length)
// code：點通知時打開該股票詳情；link：點通知時前往的頁面。
export function notify({ id, type, title, body, taskId = null, code = null, link = null }) {
  if (settings.notifications.some((n) => n.id === id)) return
  settings.notifications.unshift({ id, type, title, body, taskId, code, link, time: new Date().toLocaleString('zh-TW'), read: false })
  settings.notifications = settings.notifications.slice(0, 50)
}

const systemDark = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null
export const resolvedTheme = () => (settings.displayMode === 'system' ? (systemDark?.matches ? 'dark' : 'light') : settings.displayMode)
export const sceneCss = (key = settings.scene) => `url("${(SCENES[key] || SCENES.sunset).url}"), url("${sunset}")`

// 對應舊版 applySettings()：把設定寫成 body 屬性與 CSS 變數。
// 圖片由 Vite 匯入，網址是絕對路徑，不會被 css/ 的位置影響。
export function applySettings() {
  const themeTick = reactive({ n: 0 })
  systemDark?.addEventListener?.('change', () => themeTick.n++)
  watchEffect(() => {
    themeTick.n
    const root = document.documentElement
    document.body.dataset.theme = resolvedTheme()
    document.body.dataset.displayMode = settings.displayMode
    root.dataset.motion = settings.motion ? 'full' : 'reduced'
    root.style.setProperty('--scene', sceneCss())
    root.style.setProperty('--bg-brightness', `${settings.brightness}%`)
    root.style.setProperty('--bg-blur', `${settings.blur}px`)
    root.style.setProperty('--surface-alpha', settings.cardOpacity / 100)
    root.style.setProperty('--font-scale', settings.fontScale / 100)
    root.style.setProperty('--overlay-strength', settings.overlay / 100)
    root.style.setProperty('--motion', settings.motion ? 1 : 0)
  })
}
