<script setup>
import AppIcon from '@/components/AppIcon.vue'
import CardInsights from '@/components/picker/CardInsights.vue'
import { computed } from 'vue'
import { isCompared, isTracked, toggleCompare, toggleTrack } from '@/stores/workspace.js'
import { settings } from '@/stores/ui.js'
import { BUDGET_OPTIONS } from '@/data/preferences.js'

// 選股結果卡片（對應舊版 stockCards()）。
const props = defineProps({
  stock: { type: Object, required: true },
  rank: { type: Number, required: true },
  layout: { type: String, default: 'compact' }, // compact | wide | solo
})
defineEmits(['detail', 'explain', 'advanced'])
// 第一條理由通常是類型標籤，有其他理由時略過；只有一檔時空間夠，多列幾條。
const reasons = computed(() => {
  const all = props.stock.aiReasons || []
  const list = all.length > 1 ? all.slice(1) : all
  return list.slice(0, props.layout === 'solo' ? 3 : 1)
})

// 依偏好問卷的「預估投入」換算一張（1,000 股）大約多少錢；只呈現金額比例，不建議買幾張。
const money = (v) => (v >= 1_000_000 ? `${Math.round(v / 10_000).toLocaleString('zh-TW')} 萬` : v >= 10_000 ? `${(Math.round(v / 1000) / 10).toLocaleString('zh-TW')} 萬` : `${Math.round(v).toLocaleString('zh-TW')} `)
const lot = computed(() => {
  const budget = settings.personalPrefs.budget
  const price = Number(props.stock.price)
  if (!budget || budget === '不想填' || !Number.isFinite(price) || price <= 0) return null
  const cap = BUDGET_OPTIONS.find(([label]) => label === budget)?.[1]
  const cost = price * 1000
  const base = `一張約 ${money(cost)}元`
  if (!cap) return { text: base, title: `一張（1,000 股）約 ${money(cost)}元。`, over: false }
  if (cost > cap) return { text: `${base}，超過你預估的 ${money(cap)}（可買零股）`, title: `一張（1,000 股）約 ${money(cost)}元，超過你預估的 ${money(cap)}元；也可以買零股，1 股約 ${money(price)}元。`, over: true }
  return { text: `${base}，約占你預估上限的 ${Math.max(1, Math.round((cost / cap) * 100))}%`, title: `一張（1,000 股）約 ${money(cost)}元，約占你預估上限 ${money(cap)}元的 ${Math.max(1, Math.round((cost / cap) * 100))}%。`, over: false }
})
</script>

<template>
  <article class="card stock-card smart-stock-card" :class="[`sc-${layout}`, { 'has-hint': layout === 'solo' && !stock.explanation }]">
    <div class="sc-main">
    <div class="smart-stock-head">
      <div class="stock-name">
        <div class="stock-rank">{{ String(rank).padStart(2, '0') }}</div>
        <div class="stock-title-wrap"><strong :title="stock.name">{{ stock.name }}</strong><small :title="`${stock.code} · ${stock.industry}`">{{ stock.code }} · {{ stock.industry }}</small></div>
      </div>
      <button
        class="candidate-toggle"
        :class="{ active: isTracked(stock.code) }"
        type="button"
        :aria-pressed="String(isTracked(stock.code))"
        :title="isTracked(stock.code) ? '取消追蹤' : '加入追蹤'"
        @click="toggleTrack(stock.code, 'picker')"
      >
        <AppIcon name="star" :size="18" /><span>{{ isTracked(stock.code) ? '已追蹤' : '加入追蹤' }}</span>
      </button>
    </div>
    <div class="smart-stock-tags">
      <span class="tag demo">{{ stock.tag }}</span>
      <small class="sc-range">近 6 個月走勢</small>
      <span class="data-state" :title="stock.price != null ? `日收盤 ${stock.price} · ${stock.tradeDate || ''}（非即時）` : ''">
        {{ stock.price != null ? `日收盤 ${Number(stock.price).toLocaleString('zh-TW')} · ${stock.tradeDate || '日期未提供'}` : '官方日資料缺值' }}
      </span>
    </div>
    <CardInsights :code="stock.code" :type="stock.type" :layout="layout" />
    </div>
    <div class="sc-side">
    <template v-if="stock.aiReasons">
      <div class="smart-stock-reason picker-ai-reasons">
        <span class="sc-explain-head"><span>為什麼列入</span><button v-if="stock.explanation && layout === 'compact'" type="button" class="sc-explain-more" @click="$emit('explain', stock)">看完整說明</button></span>
        <ul>
          <li v-for="reason in reasons" :key="reason" :class="{ warning: reason.startsWith('⚠') }">{{ reason }}</li>
        </ul>
      </div>
      <!-- 白話說明在卡片上最多兩行，點「看完整說明」跳出彈窗，頁面高度不變 -->
      <div v-if="stock.explanation && layout !== 'compact'" class="smart-stock-risk picker-ai-explanation">
        <span class="sc-explain-head"><span><AppIcon name="book" :size="16" /> 白話說明</span><button type="button" class="sc-explain-more" @click="$emit('explain', stock)">看完整說明</button></span>
        <p>{{ stock.explanation }}</p>
      </div>
      <div v-if="layout === 'solo' || (layout === 'wide' && !stock.explanation)" class="smart-stock-risk"><span><AppIcon name="shield" :size="16" /> 主要風險</span><p>{{ stock.risk }}</p></div>
    </template>
    <template v-else>
      <div class="smart-stock-reason"><span>為什麼列入</span><strong>{{ stock.reason }}</strong></div>
      <div v-if="layout !== 'compact'" class="smart-stock-risk"><span><AppIcon name="shield" :size="16" /> 主要風險</span><p>{{ stock.risk }}</p></div>
    </template>
    <div v-if="layout === 'solo' && !stock.explanation" class="sc-next">
      <strong>目前只找到這 1 檔</strong>
      <small>想多看幾檔，可以放寬條件再找一次。</small>
      <button class="card-link" type="button" @click="$emit('advanced')">調整進階條件 →</button>
    </div>
    <p v-if="lot" class="sc-lot" :class="{ 'is-over': lot.over }" :title="`${lot.title}依偏好設定的預估投入、以最近日收盤計算，不代表建議買幾張。`">{{ lot.text }}</p>
    <div class="smart-stock-actions">
      <button class="primary-button small stock-detail" type="button" @click="$emit('detail', stock)">查看分析</button>
      <button
        class="outline-button small picker-compare"
        :class="{ active: isCompared(stock.code) }"
        type="button"
        :aria-pressed="String(isCompared(stock.code))"
        @click="toggleCompare(stock.code)"
      >
        {{ isCompared(stock.code) ? '✓ 已選比較' : '＋ 加入比較' }}
      </button>
    </div>
    </div>
  </article>
</template>

<style scoped>
.sc-lot{flex:none;margin:0;overflow:hidden;color:var(--muted);font-size:12px;line-height:1.4;text-overflow:ellipsis;white-space:nowrap}
.sc-lot.is-over{color:var(--text)}
@media (min-width:1001px) and (min-height:601px){@container (max-height:300px){.sc-compact .sc-lot{display:none}}}
/* 資料標籤與日收盤合併成一行（收盤靠右、字體較小），卡片少一行高度 */
.smart-stock-card .smart-stock-tags{display:flex!important;flex-wrap:nowrap!important;align-items:center;gap:8px}
.smart-stock-card{min-width:0}
/* 理由與風險文字最多兩行，超過以「…」截斷（完整內容在「查看分析」），讓卡片在固定頁面內放得下 */
.smart-stock-card :deep(.picker-ai-reasons li),.smart-stock-card :deep(.smart-stock-risk:not(.picker-ai-explanation) p),.smart-stock-card :deep(.smart-stock-reason strong){display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* 截斷後瀏覽器不再畫項目符號，改用 ::before 補上 */
.smart-stock-card :deep(.picker-ai-reasons ul){list-style:none;padding-left:0}
.smart-stock-card :deep(.picker-ai-reasons li){position:relative;padding-left:16px}
.smart-stock-card :deep(.picker-ai-reasons li)::before{content:"•";position:absolute;left:3px;top:0}
.smart-stock-card .smart-stock-tags{min-width:0}
.smart-stock-card .smart-stock-tags .tag{flex:none}
/* 空間不夠時日收盤以「…」截斷，不把卡片撐寬（滑鼠移上去可看完整文字） */
.smart-stock-card .smart-stock-tags .data-state{flex:1 1 auto;min-width:0;margin-left:auto!important;overflow:hidden;text-overflow:ellipsis;font-size:12px;white-space:nowrap;text-align:right}
.sc-explain-head{display:flex!important;align-items:center;justify-content:space-between;gap:8px}
.sc-explain-head > span{display:inline-flex!important;align-items:center;gap:4px;white-space:nowrap}
.sc-explain-more{padding:0;border:0;background:transparent;color:var(--blue);font-size:12px;font-weight:700;cursor:pointer;white-space:nowrap}
.sc-explain-more:hover{text-decoration:underline}
/* 主區放資料、會長高；側區放理由與按鈕，高度跟內容走 */
.sc-main,.sc-side{display:flex;flex-direction:column;gap:7px;min-width:0;min-height:0}
/* 高度不夠時由側區的文字讓位，主區的指標數字不壓縮 */
.sc-main{flex:1 0 auto}
.sc-side{flex:0 1 auto;overflow:hidden}
.sc-side > :not(.smart-stock-actions){flex:0 1 auto;min-height:0;overflow:hidden}
.sc-side > .smart-stock-actions{flex:none}
.sc-side .smart-stock-actions{width:100%;grid-template-columns:1fr 1fr!important;justify-content:stretch!important;margin-top:auto}
.smart-stock-card .smart-stock-tags :deep(.tag),.smart-stock-card .smart-stock-tags .tag{padding:2px 7px}
.sc-range{flex:none;color:var(--muted);font-size:12px}
.sc-side .smart-stock-risk:not(.picker-ai-explanation){--sc-lines:1}
.sc-side :deep(.smart-stock-reason){min-height:0;padding:7px 10px}
.sc-side :deep(.smart-stock-reason strong),.sc-side :deep(.smart-stock-risk p),.sc-side :deep(.picker-ai-reasons li){display:-webkit-box!important;overflow:hidden!important;-webkit-box-orient:vertical;-webkit-line-clamp:var(--sc-lines,2)!important}
.sc-compact{--sc-lines:2}
/* 代號與產業放在名稱旁邊，省下一行給走勢圖；寬度不夠時先截短產業 */
.smart-stock-card .smart-stock-head{align-items:center}
.smart-stock-card .smart-stock-head .stock-title-wrap{display:flex;align-items:baseline;gap:8px;min-width:0}
.smart-stock-card .smart-stock-head .stock-title-wrap strong{flex:0 0 auto;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.smart-stock-card .smart-stock-head .stock-title-wrap small{flex:0 1 auto;min-width:0;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sc-compact .sc-side :deep(.smart-stock-reason){gap:2px;padding:5px 10px}
.sc-wide .sc-side :deep(.picker-ai-reasons li),.sc-wide .sc-side :deep(.smart-stock-reason strong){-webkit-line-clamp:1!important}
/* 卡片變矮時（真實理由較長、多了提示列）依序收起次要文字，走勢圖與指標數字永遠完整 */
@media (min-width:1001px) and (min-height:601px){
  .smart-stock-card{container-type:size}
  @container (max-height:350px){
    .sc-wide .smart-stock-tags{display:none}
    .sc-solo .sc-side :deep(.picker-ai-reasons li){-webkit-line-clamp:1!important}
  }
  @container (max-height:335px){.sc-compact .sc-side :deep(.picker-ai-reasons li),.sc-compact .sc-side :deep(.smart-stock-reason strong){-webkit-line-clamp:1!important}}
  @container (max-height:325px){
    .sc-wide .sc-side :deep(.picker-ai-explanation p){-webkit-line-clamp:1!important}
    .sc-solo .sc-side :deep(.picker-ai-explanation){display:none}
  }
  @container (max-height:345px){.sc-compact .smart-stock-tags{display:none}}
  @container (max-height:300px){.sc-solo .sc-side :deep(.smart-stock-risk){display:none}}
  @container (max-height:245px){.sc-compact .sc-side > :not(.smart-stock-actions),.sc-wide .sc-side > :not(.smart-stock-actions){display:none}}
  @container (max-height:282px){.sc-compact .sc-side :deep(.smart-stock-reason),.sc-wide .sc-side :deep(.smart-stock-reason){display:none}}
}
.sc-compact .sc-range{display:none}
.sc-wide .sc-side{gap:4px}
.sc-wide .sc-side :deep(.smart-stock-reason){gap:2px;padding:5px 10px}
.sc-next{flex:1 1 0;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;border:1px dashed var(--line-strong);border-radius:12px;text-align:center}
.sc-next strong{color:var(--text-strong);font-size:14px}
.sc-next small{color:var(--muted);font-size:13px}
.sc-next .card-link{min-height:0;margin-top:4px;padding:0;font-size:13px}
/* 只有一檔：左邊資料、右邊理由，中間用線分開 */
.smart-stock-card.sc-solo{gap:16px!important;--sc-lines:4}
.sc-solo .sc-side :deep(.picker-ai-reasons li),.sc-solo .sc-side :deep(.smart-stock-reason strong){-webkit-line-clamp:2!important}
.sc-solo .sc-side .smart-stock-risk:not(.picker-ai-explanation){--sc-lines:2}
.smart-stock-card.sc-solo > .sc-main{flex:1.9 1 0}
.smart-stock-card.sc-solo > .sc-side{flex:1 1 0;padding-left:16px;border-left:1px solid var(--line)}
.sc-solo .sc-side :deep(.smart-stock-reason){flex:1 1 auto;min-height:0;align-content:start;padding:10px 12px;overflow:hidden}
.sc-solo .sc-side :deep(.smart-stock-risk){flex:none}
@media (max-width:1000px){.smart-stock-card.sc-solo{flex-direction:column!important}.smart-stock-card.sc-solo > .sc-side{padding-left:0;border-left:0}}
</style>
