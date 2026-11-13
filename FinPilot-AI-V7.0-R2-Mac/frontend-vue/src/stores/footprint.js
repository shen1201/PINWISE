import { reactive, watch } from 'vue'
import { api } from '@/api/client.js'
import { storageKey } from '@/api/runtime.js'
import { toast } from './ui.js'

// 我的投資足跡：使用紀錄、評價與徽章進度。
// 內容可以刪，但已經發生的累計數字保留；只存在這個瀏覽器，匿名評價另外送回後端。
const STORE_KEY = storageKey('pinwise_vue_footprint')
const RECORD_LIMIT = 500
const ASK_PER_DAY = 2
// 每枚徽章每天最多累計的次數：徽章記的是長期習慣，避免一天刷完或為了徽章多耗 Token。
export const BADGE_PER_DAY = 3

function load() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') || {}
  } catch {
    return {}
  }
}
const saved = load()
export const footprint = reactive({
  records: Array.isArray(saved.records) ? saved.records : [],
  counters: saved.counters || {},
  seen: saved.seen || {},
  visitWeeks: Array.isArray(saved.visitWeeks) ? saved.visitWeeks : [],
  ask: saved.ask || { day: '', count: 0 },
  tally: saved.tally || { day: '', counts: {}, notified: false },
  monthly: saved.monthly || {},
})
watch(footprint, (value) => {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(value))
  } catch {
    // 瀏覽器不允許儲存時，紀錄只保留到重新整理為止。
  }
}, { deep: true })

// 每月次數獨立累計：明細有筆數上限，刪除內容也不影響，一年後仍查得到。
const monthOf = (at) => String(at || '').slice(0, 7)
function buildMonthly() {
  const months = {}
  footprint.records.forEach((row) => {
    const key = monthOf(localIso(row.at))
    if (key) months[key] = (months[key] || 0) + 1
  })
  return months
}
function localIso(at) {
  const date = new Date(at)
  return Number.isNaN(date.getTime()) ? '' : localDay(date)
}
const localDay = (date = new Date()) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
if (!saved.monthly) footprint.monthly = buildMonthly()

export function weekStart(date = new Date()) {
  const monday = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7))
  return localDay(monday)
}
export const tokensOf = (usage) => Number(usage?.total_token_count ?? usage?.total_tokens) || 0

export function addRecord(record) {
  const existing = footprint.records.find((row) => row.id === record.id)
  if (existing) {
    if (!existing.deleted) Object.assign(existing, record, { rating: existing.rating, reason: existing.reason })
    return
  }
  footprint.records.unshift({ rating: null, reason: null, deleted: false, ...record })
  const month = monthOf(localIso(record.at))
  if (month) footprint.monthly[month] = (footprint.monthly[month] || 0) + 1
  footprint.records.sort((a, b) => String(b.at).localeCompare(String(a.at)))
  footprint.records.splice(RECORD_LIMIT)
}

// 內容刪除後只留類型、時間與統計數字。
export function markDeleted(id) {
  const record = footprint.records.find((row) => row.id === id)
  if (record) Object.assign(record, { deleted: true, label: '', symbols: [], conversationId: null })
}

// rating 傳 null 代表取消評價。
export function rate(id, feature, rating, reason = null) {
  const record = footprint.records.find((row) => row.id === id)
  if (record) {
    const added = rating && !record.rating
    // 改評價不換日期，避免同一則評價換一天又多算一次。
    Object.assign(record, { rating, reason, ratedDay: !rating ? null : record.rating ? ratedDayOf(record) : localDay() })
    if (added && ratedPerDay()[localDay()] > BADGE_PER_DAY) remindOnce()
  }
  api.sendFeedback({ feature, rating: rating || 'cleared', reason, item_id: id }).catch(() => {})
}
export const ratingOf = (id) => footprint.records.find((row) => row.id === id) || null

// 評價可以取消，所以由目前的紀錄算出，每天最多算 BADGE_PER_DAY 則。
const ratedDayOf = (row) => row.ratedDay || localIso(row.at)
function ratedPerDay() {
  const days = {}
  footprint.records.forEach((row) => {
    if (row.rating) days[ratedDayOf(row)] = (days[ratedDayOf(row)] || 0) + 1
  })
  return days
}
export const ratedTotal = () => Object.values(ratedPerDay()).reduce((sum, count) => sum + Math.min(count, BADGE_PER_DAY), 0)

function todayTally() {
  const day = localDay()
  if (footprint.tally.day !== day) footprint.tally = { day, counts: {}, notified: false }
  return footprint.tally
}
// 一天只提醒一次，而且只在使用者真的超過時才出現。
function remindOnce() {
  const tally = todayTally()
  if (tally.notified) return
  tally.notified = true
  toast('今天的徽章進度累積滿了，明天回來再繼續。功能都照常，不用為了徽章多做。', 4600)
}

// 同一件事同一天只算一次；once 代表整個紀錄只算一次（例如不同的 ETF）。
export function track(counter, key = '', { once = false } = {}) {
  const seenKey = `${counter}|${key}|${once ? '' : localDay()}`
  if (footprint.seen[seenKey]) return
  const tally = todayTally()
  if ((tally.counts[counter] || 0) >= BADGE_PER_DAY) return remindOnce() // 不記 seen，改天再做同一件事仍算數。
  tally.counts[counter] = (tally.counts[counter] || 0) + 1
  footprint.seen[seenKey] = 1
  footprint.counters[counter] = (footprint.counters[counter] || 0) + 1
}

export function recordVisit() {
  const week = weekStart()
  if (!footprint.visitWeeks.includes(week)) footprint.visitWeeks.push(week)
}
export function weekStreak() {
  const weeks = new Set(footprint.visitWeeks)
  let streak = 0
  const cursor = new Date(`${weekStart()}T12:00:00`)
  while (weeks.has(weekStart(cursor))) {
    streak++
    cursor.setDate(cursor.getDate() - 7)
  }
  return streak
}

// 主動詢問：回答完才「偶爾」問，不在每一則下面放評價按鈕。
// 資料不足的回答一定問（最需要知道哪裡不好）；其他回答約 1/3 機率；每天最多 2 次。
const ASK_CHANCE = 0.35
export function shouldAskFeedback(answered, verification) {
  const today = localDay()
  if (footprint.ask.day !== today) footprint.ask = { day: today, count: 0 }
  if (footprint.ask.count >= ASK_PER_DAY || answered < 1) return false
  if (verification !== 'source_missing' && Math.random() >= ASK_CHANCE) return false
  footprint.ask.count++
  return true
}

// 使用者自己打的回饋：存在足跡（「歷程」看得到），也匿名送給團隊改進服務；
// 後端存檔前會再遮掉 email、電話與身分證字號。
export const COMMENT_LIMIT = 300
export function saveComment(id, feature, text) {
  const record = footprint.records.find((row) => row.id === id)
  const comment = String(text || '').trim().slice(0, COMMENT_LIMIT) || null
  if (!record || !comment) return
  record.comment = comment
  api.sendFeedback({ feature, rating: record.rating || 'cleared', reason: record.reason, item_id: id, comment }).catch(() => {})
}
