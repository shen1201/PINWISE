import { footprint, ratedTotal, weekStreak } from '@/stores/footprint.js'

// 徽章定義。條件都是對使用者有益的行為，不獎勵交易、報酬、研究份數或 Token 用量。
export const TIERS = [['bronze', '銅'], ['silver', '銀'], ['gold', '金']]
const count = (name) => () => footprint.counters[name] || 0
const honest = () => (footprint.records.some((row) => row.rating === 'bad' && row.reason) ? 1 : 0)

export const BADGES = [
  { id: 'verifier', name: '查證者', group: 'total', shape: 'circle', value: count('source_open'), goals: [5, 20, 50], unit: '次', desc: '打開資料來源，確認數字從哪裡來' },
  { id: 'contrarian', name: '反方思考家', group: 'total', shape: 'circle', value: count('risk_read'), goals: [3, 10, 30], unit: '份', desc: '讀完研究的風險與失效條件' },
  { id: 'comparer', name: '貨比三家', group: 'total', shape: 'circle', value: count('compare'), goals: [3, 10, 30], unit: '次', desc: '把標的放在一起比較' },
  { id: 'etf', name: 'ETF 解剖師', group: 'total', shape: 'circle', value: count('etf_view'), goals: [3, 10, 30], unit: '檔', desc: '查看不同 ETF 的成份股' },
  { id: 'detective', name: '公告偵探', group: 'total', shape: 'circle', value: count('announcement'), goals: [10, 30, 100], unit: '則', desc: '閱讀官方公告與新聞' },
  { id: 'guardian', name: '風險守門人', group: 'total', shape: 'circle', value: count('risk_check'), goals: [3, 10, 30], unit: '次', desc: '點開需要留意的標的查看' },
  { id: 'partner', name: '回饋夥伴', group: 'total', shape: 'circle', value: ratedTotal, goals: [5, 20, 50], unit: '次', desc: '替研究或回答留下評價' },
  { id: 'streak', name: '定期回顧', group: 'streak', shape: 'hex', value: weekStreak, goals: [4, 12, 26], unit: '週', desc: '每週回來檢視一次' },
  { id: 'split', group: 'hidden', shape: 'shield', value: count('split_flag'), goals: [1], name: '分割偵探', hint: '有些數字，不是它看起來的樣子。' },
  { id: 'pause', group: 'hidden', shape: 'shield', value: count('surge_pause'), goals: [1], name: '先停一下', hint: '大家都衝的時候，你停了一下。' },
  { id: 'honest', group: 'hidden', shape: 'shield', value: honest, goals: [1], name: '敢說真話', hint: '說實話比說好話難。' },
  { id: 'night', group: 'hidden', shape: 'shield', value: count('after_close_compare'), goals: [1], name: '收盤研究員', hint: '收盤後才是你的時間。' },
  { id: 'overlap', group: 'hidden', shape: 'shield', value: count('overlap_50'), goals: [1], name: '看穿重疊', hint: '看穿一籃子裡的重疊。' },
  { id: 'goal', group: 'hidden', shape: 'shield', value: count('goal_100'), goals: [1], name: '走到那條線', hint: '那條線，你真的走到了。' },
]

// 現場展示用：部分解鎖，才看得出銅銀金、未解鎖與隱藏徽章的差別。正式上線前改成 false，就會依真實紀錄顯示。
export const DEMO_BADGES = true
const DEMO_VALUES = { verifier: 50, contrarian: 12, comparer: 4, etf: 14, detective: 6, guardian: 1, partner: 8, streak: 2, split: 1, honest: 1 }

export function progressOf(badge) {
  const value = DEMO_BADGES ? DEMO_VALUES[badge.id] || 0 : badge.value()
  const earned = badge.goals.filter((goal) => value >= goal).length
  const next = badge.goals[earned] ?? null
  const from = badge.goals[earned - 1] ?? 0
  return { value, earned, next, pct: next == null ? 100 : Math.min(100, Math.round(((value - from) / (next - from)) * 100)) }
}
