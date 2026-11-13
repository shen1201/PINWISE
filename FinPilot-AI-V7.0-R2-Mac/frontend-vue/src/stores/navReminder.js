import { reactive } from 'vue'
import { settings, toast } from './ui.js'
import { navMeta } from '@/data/nav.js'

// 加入「比較／追蹤」時，若對應頁面已從側邊欄隱藏，提醒使用者入口被關閉。
// 「今天不再提醒」以頁面為單位記錄日期（存在 settings，跟著本機設定保存）。
export const navReminder = reactive({ key: '' })

const today = () => new Date().toLocaleDateString('sv-SE') // YYYY-MM-DD（本地時間）

export function ensureNavVisible(key) {
  if (settings.navVisible?.[key] !== false) return
  if (settings.navReminderSnooze?.[key] === today()) return
  navReminder.key = key
}

export function showNav(key) {
  settings.navVisible[key] = true
  toast(`已在側邊欄顯示「${navMeta[key]?.[1] || key}」`)
  navReminder.key = ''
}

export function dismissNavReminder(key, snoozeToday) {
  if (snoozeToday) settings.navReminderSnooze = { ...(settings.navReminderSnooze || {}), [key]: today() }
  navReminder.key = ''
}
