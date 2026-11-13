<script setup>
import PrefsBadge from '@/components/PrefsBadge.vue'
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '@/components/AppIcon.vue'
import AppModal from '@/components/AppModal.vue'
import StockCard from '@/components/picker/StockCard.vue'
import PresetTiles from '@/components/picker/PresetTiles.vue'
import V7Context from '@/components/v7/V7Context.vue'
import R2SectionTabs from '@/components/v7/R2SectionTabs.vue'
import { useSectionTabs, useMedia } from '@/composables/r2Layout.js'
import { workspace, isCompared, isTracked, toggleCompare, toggleTrack } from '@/stores/workspace.js'
import { openStockDetail } from '@/stores/overlays.js'
import { settings } from '@/stores/ui.js'
import InfoTip from '@/components/InfoTip.vue'
import {
  picker, conditions, requestSummary, draftDirty, advancedCount, clearDraftAdvanced, filterHelp, PRESETS, conditionText, viewRecord, rerunRecord, removeRecord, backToHistory,
  TYPE_OPTIONS, INDUSTRY_OPTIONS, PERIOD_OPTIONS, RISK_OPTIONS, normalizeConditions,
  submitDraft, applyPreset, removeCondition, reset, applyPatch, applyAdvanced,
} from '@/stores/picker.js'

const router = useRouter()
const loading = computed(() => picker.state === 'loading')
const list = computed(() => (picker.analyzed ? picker.results : []))
const ai = computed(() => (picker.state === 'completed' ? picker.ai : null))
const aiNotes = computed(() => [...(ai.value?.plan?.unsupported || []), ...(ai.value?.plan?.relaxed ? [ai.value.plan.relaxed] : [])])

const modal = ref('') // advanced | method | all | guide
const advanced = reactive({ type: 'all', industry: 'all', period: 'all', risk: 'all' })
// 欄位：[key, 標題, 選項, 說明, 停用條件]；互相限制的規則在 stores/picker.js 的 normalizeConditions。
const ADVANCED_FIELDS = [
  ['type', '產品類型', TYPE_OPTIONS, '選擇產業時只篩選台股個股。', () => advanced.industry !== 'all'],
  ['industry', '產業主題', INDUSTRY_OPTIONS, '依交易所產業分類近似，結果仍需逐一核對；ETF 不分產業。', () => advanced.type === 'etf'],
  ['risk', '波動程度', RISK_OPTIONS, '以年化波動篩選，代表股價起伏大小，不代表實際損失上限。', () => false],
  ['period', '波動計算期間', PERIOD_OPTIONS, '用多長的歷史日價計算波動；先選波動程度才能設定。', () => advanced.risk === 'all'],
]
// 選項變動時即時套用相同規則，畫面上就看得到連動結果。
watch(advanced, () => Object.assign(advanced, normalizeConditions(advanced)), { deep: true })

// 打開時帶入「已套用的條件」，方便在原本的結果上微調；輸入框的數字只算還沒送出的新條件。
function openAdvanced() {
  Object.assign(advanced, normalizeConditions(advancedCount(picker.draft) || !picker.analyzed ? picker.draft : picker.applied))
  modal.value = 'advanced'
}
function submitAdvanced() {
  modal.value = ''
  applyAdvanced({ ...advanced })
}
// 清除會立刻生效：就算之後按「取消」或關閉視窗，輸入框旁也不會再顯示數字。
function clearAdvanced() {
  Object.assign(advanced, { type: 'all', industry: 'all', period: 'all', risk: 'all' })
  clearDraftAdvanced()
}

function showDetail(stock) {
  modal.value = ''
  openStockDetail(stock.code, '選股分析')
}

// Gemini 實際有理解需求才算 AI；額度用完或失敗時後端改用關鍵字規則。
const aiUsed = computed(() => picker.ai?.plan?.source === 'gemini')
const aiFallback = computed(() => Boolean(picker.ai) && !aiUsed.value)
const explainStock = ref(null)
const formatAt = (iso) => { const d = new Date(iso); return Number.isFinite(d.getTime()) ? `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : '' }
// 第一次使用（沒有結果也沒有紀錄）才顯示標題與常用條件，避免壓縮結果卡與紀錄的高度。
const firstUse = computed(() => !picker.analyzed)
// 起始畫面：預設看各方向的預覽；從結果按「回到選股紀錄」時看紀錄。
const startView = ref('tiles') // tiles | history
function openHistory() {
  startView.value = 'history'
  backToHistory()
}
watch(() => picker.history.length, (count) => !count && (startView.value = 'tiles'))
const START_VIEWS = computed(() => [['tiles', '常用方向'], ['history', `選股紀錄（${picker.history.length}）`]])
const compared = computed(() => workspace.compare.map((code) => list.value.find((s) => s.code === code) || { code }))

// ── 窄螢幕與內容溢出時的版面（對應舊版 applyR2Layout 的 picker 部分）──
// 寬度或高度不足、或結果放不下時，切成「搜尋條件／結果」兩個區塊，並在 body 加上 r2-picker-focus。
const smallScreen = useMedia('(max-width: 900px), (max-height: 600px)')
const focus = ref(false)
const resultsEl = ref(null)
const gridEl = ref(null)
let measuring = false
async function measure() {
  if (measuring) return
  measuring = true
  focus.value = false // 先以完整版面量測，再決定是否切換
  await nextTick()
  const results = resultsEl.value, grid = gridEl.value
  // 只在螢幕真的太小時才切成分頁；內容放不下時改由結果區自己捲動，
  // 避免畫面上方突然多出「搜尋條件／分析結果」按鈕、把版面往下推。
  void results; void grid
  focus.value = smallScreen.value
  measuring = false
}
watch(focus, (value) => document.body.classList.toggle('r2-picker-focus', value))
let observer = null
onMounted(() => {
  const host = document.querySelector('#pageHost')
  if (host && typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure)
    observer.observe(host)
  }
  measure()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  document.body.classList.remove('r2-picker-focus')
})
watch(() => [picker.analyzed, picker.state, list.value.length, smallScreen.value], () => measure())

// 有尚未送出的變更時先看搜尋條件，否則看結果（對應舊版 r2PickerSectionIndex）。
const { current: tab, hidden: tabHidden } = useSectionTabs('picker', 2, { narrow: focus })
watch(() => [draftDirty.value, picker.state], () => (tab.value = draftDirty.value ? 0 : 1), { immediate: true })

// 窄螢幕時結果卡片一次顯示一張（對應舊版 r2-card-pager）。
const singleCard = useMedia('(max-width: 1000px), (max-height: 600px)')
const cardIndex = ref(0)
const previewCount = computed(() => Math.min(list.value.length, 3))
// 依檔數換版面：1 檔左右雙區、2 檔放大走勢、3 檔精簡。
const cardLayout = computed(() => ({ 1: 'solo', 2: 'wide' })[previewCount.value] || 'compact')
watch(list, () => (cardIndex.value = 0))
</script>

<template>
  <div class="page picker-page picker-page-v3">
    <div class="workspace picker-workspace-v3">
      <header class="picker-dashboard-head">
        <div>
          <h1>智慧選股</h1>
          <p>還沒決定要看哪幾檔？用一句話或條件，找出候選標的與列入原因。</p>
        </div>
      </header>
      <R2SectionTabs v-model="tab" :labels="['搜尋條件', picker.analyzed ? '分析結果' : picker.history.length ? '選股紀錄' : '探索方向']" />

      <section class="card picker-hub picker-command-center" data-tour="picker-controls" :hidden="tabHidden(0)">
        <!-- 標題改放在搜尋欄的提示文字裡，省下一行；label 保留給螢幕閱讀器 -->
        <label class="sr-only" for="pickerSearch">告訴 AI 你想找什麼</label>
        <h2 v-if="firstUse" class="pk-search-title">你想找哪一類標的？</h2>
        <form class="picker-search picker-natural-search picker-ai-query" data-tour="picker-search" @submit.prevent="submitDraft">
          <div class="picker-input-shell">
            <input id="pickerSearch" v-model="picker.draft.search" type="text" :placeholder="firstUse ? '例如：想找適合長期觀察、波動不要太大的半導體公司' : '告訴 AI 你想找什麼，例如：想找適合長期觀察、波動不要太大的半導體公司'" aria-label="告訴 AI 你想找什麼" />
            <button v-if="picker.draft.search" type="button" aria-label="清除需求" @click="picker.draft.search = ''">×</button>
            <!-- 進階條件併入搜尋欄右側，不再單獨佔一行 -->
            <button
              class="picker-advanced-link pk-advanced-inline"
              data-tour="picker-advanced"
              :class="{ 'has-filters': advancedCount(picker.draft) }"
              type="button"
              title="需要指定產品、產業或風險時再使用"
              :disabled="loading"
              @click="openAdvanced"
            >⚙ 進階條件<b v-if="advancedCount(picker.draft)">{{ advancedCount(picker.draft) }}</b></button>
          </div>
          <button id="pickerSearchBtn" :class="{ 'has-pending': draftDirty }" type="submit" :disabled="loading">
            <AppIcon name="bot" :size="18" /><span>交給 AI 分析</span>
          </button>
        </form>
        <!-- 只有尚未完成投資偏好時提醒；已設定（含編輯中未儲存，仍沿用已存設定）不顯示 -->
        <div v-if="!settings.personalPrefs.completed" class="picker-preference-note">
          想讓篩選更貼近你的偏好？可先完成投資偏好設定。
          <button type="button" @click="router.push('/settings/preferences')">前往設定</button>
        </div>
        <div v-if="draftDirty" class="picker-filter-feedback"><span>需求或條件已變更，送出後由 AI 重新整合</span></div>
        <div v-if="loading" class="picker-analysis-status">
          <span class="picker-thinking-spinner" aria-hidden="true"></span>
          <div><strong>AI 正在整理你的需求</strong><small>{{ picker.step }}</small></div>
        </div>
        <div v-if="picker.analyzed && conditions.length" class="picker-understood">
          <!-- 有進階條件時走關鍵字與條件篩選，不經 Gemini，所以不寫「AI 已理解」 -->
          <span>{{ aiUsed ? 'AI 已理解' : picker.ai ? '依關鍵字理解' : '已套用條件' }}</span>
          <div>
            <button v-for="[key, text] in conditions" :key="key" type="button" title="移除條件" @click="removeCondition(key)">{{ text }} <b>×</b></button>
            <button type="button" class="picker-reset-link" @click="reset()">全部清除</button>
          </div>
        </div>
      </section>

      <!-- 尚未分析：探索方向 -->
      <section v-if="!picker.analyzed" ref="resultsEl" class="card picker-results picker-results-empty picker-empty-v2" :class="{ 'pk-first-use': true, 'pk-has-history': startView === 'history' && picker.history.length }" data-tour="picker-results" :hidden="tabHidden(1)">
        <!-- 還沒有紀錄：顯示常用篩選 -->
        <template v-if="startView === 'tiles' || !picker.history.length">
          <PresetTiles @pick="applyPreset" @detail="openStockDetail($event, '選股分析')">
            <template v-if="picker.history.length" #side>
              <div class="pk-switch" role="group" aria-label="切換內容"><button v-for="[key, text] in START_VIEWS" :key="key" type="button" :class="{ active: startView === key }" :aria-pressed="String(startView === key)" @click="startView = key">{{ text }}</button></div>
            </template>
          </PresetTiles>
        </template>

        <!-- 有紀錄：最近的選股紀錄 -->
        <div v-else class="pk-home">
          <section class="pk-history" aria-label="最近的選股紀錄">
            <div class="pk-block-head">
              <h2>最近的選股紀錄</h2>
              <div class="pk-block-side"><small>只保存在此瀏覽器，最多 5 筆</small><div class="pk-switch" role="group" aria-label="切換內容"><button v-for="[key, text] in START_VIEWS" :key="key" type="button" :class="{ active: startView === key }" :aria-pressed="String(startView === key)" @click="startView = key">{{ text }}</button></div></div>
            </div>
            <article v-for="r in picker.history" :key="r.id" class="pk-record">
              <div class="pk-record-copy">
                <strong :title="r.applied.search || conditionText(r.applied)">{{ r.applied.search || conditionText(r.applied) }}</strong>
                <small>{{ r.applied.search ? conditionText(r.applied) + '・' : '' }}找到 {{ r.count }} 檔・{{ formatAt(r.at) }}</small>
                <small v-if="r.results?.length" class="pk-record-top">{{ r.results.slice(0, 3).map((x) => x.name || x.code).join('、') }}{{ r.count > 3 ? '…' : '' }}</small>
              </div>
              <div class="pk-record-actions">
                <button class="soft-button small" type="button" :disabled="loading" @click="viewRecord(r)">查看結果</button>
                <button class="outline-button small" type="button" :disabled="loading" :title="r.ai ? 'AI 分析會使用 Gemini 額度' : ''" @click="rerunRecord(r)">用最新資料重跑</button>
                <button class="pk-record-remove" type="button" :aria-label="`刪除紀錄：${r.applied.search || conditionText(r.applied)}`" @click="removeRecord(r.id)">×</button>
              </div>
            </article>
            <!-- 未使用的位置排成淡色虛線框，5 格整齊排列 -->
            <div v-for="n in Math.max(0, 5 - picker.history.length)" :key="`slot-${n}`" class="pk-record pk-record-slot" aria-hidden="true">
              下一次篩選會記在這裡
            </div>
          </section>
        </div>
      </section>

      <!-- 分析結果 -->
      <section v-else ref="resultsEl" class="card picker-results" data-tour="picker-results" :hidden="tabHidden(1)">
        <!-- 捲動放在內層：卡片四角維持圓角，捲軸留在圓角卡片裡面 -->
        <div class="pk-scroll" :class="{ 'is-fit': previewCount }">
        <div class="picker-results-head">
          <div class="pk-head-copy">
            <h2>{{ list.length ? `找到 ${list.length} 檔可進一步研究的標的` : '目前沒有完全符合需求的標的' }}</h2>
            <small v-if="list.length">TWSE／TPEx 最近可得日資料・非即時行情・預覽 {{ Math.min(list.length, 3) }}／{{ list.length }} 檔</small>
          </div>
          <!-- AI 無法使用時的警告：滑鼠移入、點擊或聚焦顯示完整說明 -->
          <InfoTip
            v-if="aiFallback"
            variant="warning"
            label="AI 目前無法使用"
            text="可能是今日 AI 額度已用完或連線中斷，本次改用關鍵字規則篩選，範圍可能較寬、結果較粗略。可稍後用「用最新資料重跑」，或改用進階條件指定產業與波動。"
          ><span class="pk-warn-mark" aria-hidden="true">!</span>AI 目前無法使用</InfoTip>
          <div class="picker-results-tools">
            <button v-if="picker.history.length" class="outline-button small" type="button" @click="openHistory">← 回到選股紀錄</button>
            <button v-if="list.length" class="soft-button small" type="button" @click="modal = 'method'">查看整理方式</button>
            <button v-if="list.length > 3" class="outline-button small" type="button" @click="modal = 'all'">查看全部 {{ list.length }} 檔</button>
          </div>
        </div>

        <div v-if="picker.viewingAt" class="pk-viewing">
          <span>這是 {{ formatAt(picker.viewingAt) }} 的篩選結果，價格與指標可能已更新。</span>
          <button class="card-link" type="button" :disabled="loading" @click="rerunRecord({ applied: picker.applied })">用最新資料重跑</button>
        </div>
        <!-- 篩選過程濃縮成一行（不同顏色區分）；名詞解釋、整體說明與聲明移到「查看整理方式」 -->
        <!-- 篩選過程只顯示一行摘要；點「查看篩選過程」跳出彈窗，頁面高度不變 -->
        <div v-if="ai || compared.length" class="pk-status">
        <div v-if="ai" class="pk-ai-line">
          <div class="pk-ai-summary">
            <span class="pk-ai-source"><AppIcon name="bot" :size="14" /> {{ aiUsed ? 'AI 理解' : '依關鍵字' }}</span>
            <span v-if="ai.funnel.length" class="pk-ai-funnel-short">{{ ai.funnel[0].label }} {{ Number(ai.funnel[0].count).toLocaleString('zh-TW') }} 檔 → 篩選後 <em>{{ list.length }}</em> 檔</span>
            <span v-if="aiNotes.length" class="pk-ai-note">⚠ {{ aiNotes.length }} 項說明</span>
            <!-- 偏好只在「交給 AI 分析」時傳給 AI；預估投入用在卡片上的一張金額換算 -->
            <PrefsBadge v-if="ai.prefs" class="pk-prefs" :prefs="ai.prefs" :fields="['explanationStyle', 'riskTolerance', 'budget']" label="參考偏好" />
            <button type="button" class="pk-ai-more" @click="modal = 'funnel'">查看篩選過程</button>
          </div>
        </div>

        <aside v-if="compared.length" class="picker-comparison-tray" aria-label="比較清單">
          <div>
            <span class="comparison-tray-icon"><AppIcon name="compare" :size="17" /></span>
            <div><strong>比較清單</strong><small>{{ compared.length < 2 ? '再選 1 檔即可比較' : `已選 ${compared.length} 檔` }}</small></div>
          </div>
          <div class="comparison-tray-stocks">
            <button v-for="s in compared" :key="s.code" type="button" title="從比較清單移除" @click="toggleCompare(s.code)">{{ s.code }}<b>×</b></button>
          </div>
          <button type="button" class="primary-button small" :disabled="compared.length < 2" @click="router.push('/compare')">
            {{ compared.length < 2 ? '尚未可比較' : '開始比較' }}
          </button>
        </aside>
        </div>

        <div v-if="picker.error" class="notice"><strong>後端篩選失敗</strong><span>{{ picker.error }}</span></div>
        <ul v-if="list.length && filterHelp.details.length" class="pk-help-details pk-help-inline">
          <li v-for="d in filterHelp.details" :key="d">{{ d }}</li>
        </ul>

        <div id="stockGrid" ref="gridEl" class="stock-grid smart-stock-grid" :class="`pk-n${previewCount}`">
          <StockCard
            v-for="(stock, i) in list.slice(0, 3)"
            :key="stock.code"
            :stock="stock"
            :rank="i + 1"
            :layout="cardLayout"
            :hidden="singleCard && i !== cardIndex"
            @detail="showDetail"
            @explain="explainStock = $event; modal = 'explain'"
            @advanced="openAdvanced"
          />
          <div v-if="!list.length && !loading" class="empty-state picker-empty picker-empty-guidance">
            <span class="picker-empty-icon"><AppIcon name="bot" :size="24" /></span>
            <span class="eyebrow">篩選結果</span>
            <strong>目前沒有完全符合需求的標的</strong>
            <p>{{ filterHelp.reason }}</p>
            <ul v-if="filterHelp.details.length" class="pk-help-details">
              <li v-for="d in filterHelp.details" :key="d">{{ d }}</li>
            </ul>
            <div class="picker-empty-actions">
              <button
                v-for="(act, i) in filterHelp.actions"
                :key="act.label"
                :class="i === 0 ? 'primary-button' : 'outline-button'"
                type="button"
                @click="applyPatch(act.patch)"
              >{{ act.label }}</button>
              <button class="outline-button" type="button" @click="openAdvanced">調整進階條件</button>
            </div>
          </div>
        </div>
        <div v-if="previewCount" class="r2-card-pager">
          <button type="button" aria-label="查看上一檔候選預覽" :disabled="cardIndex === 0" @click="cardIndex--">← 上一檔</button>
          <span aria-live="polite">{{ cardIndex + 1 }}／{{ previewCount }} 張預覽</span>
          <button type="button" aria-label="查看下一檔候選預覽" :disabled="cardIndex >= previewCount - 1" @click="cardIndex++">下一檔 →</button>
        </div>
        </div>
      </section>
    </div>
  </div>

  <!-- 進階條件 -->
  <AppModal :open="modal === 'advanced'" title="進階條件" modal-class="picker-advanced-modal" @close="modal = ''">
    <form class="picker-advanced-form" @submit.prevent="submitAdvanced">
      <p>只有需要更精確限制時再選擇；未選擇的項目交由 AI 依你的文字需求判斷。</p>
      <div class="picker-advanced-grid">
        <label v-for="[key, text, options, hint, isDisabled] in ADVANCED_FIELDS" :key="key" :class="{ 'pk-field-disabled': isDisabled() }">
          {{ text }}
          <select v-model="advanced[key]" :disabled="isDisabled()">
            <option v-if="key === 'period' && advanced.risk === 'all'" value="all">—</option>
            <option v-for="[value, optionLabel] in options" :key="value" :value="value">{{ optionLabel }}</option>
          </select>
          <small class="pk-field-hint">{{ hint }}</small>
        </label>
      </div>
      <div class="picker-advanced-summary">
        <span>套用後，AI 會把這些條件與你的原始問題一起整理。</span>
        <button type="button" class="card-link" @click="clearAdvanced">清除進階條件</button>
      </div>
      <div class="candidate-dialog-actions">
        <button class="outline-button" type="button" @click="modal = ''">取消</button>
        <button class="primary-button" type="submit">套用並重新分析</button>
      </div>
    </form>
  </AppModal>

  <!-- 結果說明（窄螢幕的「結果會怎麼呈現？」） -->
  <AppModal :open="modal === 'guide'" title="結果說明" @close="modal = ''">
    <div class="r2-guide-content">
      <V7Context
        title="結果會怎麼呈現？"
        copy="送出需求後，同一區會顯示相符標的；先看理由與風險，再加入追蹤或比較。"
        :fields="[['研究方向', '公司、產業與符合條件的原因'], ['主要風險', '可能影響原本想法的條件'], ['下一步', '查看分析、加入追蹤或比較']]"
      />
    </div>
  </AppModal>

  <!-- 整理方式 -->
  <!-- 篩選過程（AI 理解）彈窗 -->
  <AppModal :open="modal === 'funnel'" title="篩選過程" modal-class="pk-info-modal" @close="modal = ''">
    <div v-if="ai" class="pk-info-body">
      <p class="pk-info-lead"><b>{{ aiUsed ? 'AI 理解你的需求' : '依關鍵字理解需求' }}：</b>{{ ai.plan.interpretation || picker.applied.search }}</p>
      <ol class="pk-info-steps">
        <li v-for="(stage, i) in ai.funnel" :key="i"><span>{{ stage.label }}</span><em>{{ Number(stage.count).toLocaleString('zh-TW') }} 檔</em></li>
      </ol>
      <ul v-if="aiNotes.length" class="pk-info-notes"><li v-for="note in aiNotes" :key="note">⚠ {{ note }}</li></ul>
      <p v-if="ai.overall" class="pk-info-text">{{ ai.overall }}</p>
      <small class="pk-info-small">{{ ai.notice }}</small>
    </div>
  </AppModal>

  <!-- 單一標的的完整白話說明彈窗 -->
  <AppModal :open="modal === 'explain' && Boolean(explainStock)" :title="explainStock ? `${explainStock.code} ${explainStock.name}` : ''" modal-class="pk-info-modal" @close="modal = ''">
    <div v-if="explainStock" class="pk-info-body">
      <h4>白話說明</h4>
      <p class="pk-info-text">{{ explainStock.explanation }}</p>
      <h4>為什麼列入</h4>
      <ul class="pk-info-notes"><li v-for="r in explainStock.aiReasons || []" :key="r">{{ r }}</li></ul>
      <h4>主要風險</h4>
      <p class="pk-info-text">{{ explainStock.risk }}</p>
      <div class="pk-info-actions">
        <button class="primary-button small" type="button" @click="modal = ''; showDetail(explainStock)">查看分析</button>
      </div>
    </div>
  </AppModal>

  <AppModal :open="modal === 'method'" title="選股條件與資料狀態" modal-class="picker-method-modal" @close="modal = ''">
    <div class="picker-method-intro">
      <strong>這份結果如何整理？</strong>
      <p>先把你的文字需求轉成可調整條件，再依條件相符程度與風險說明完整度排列；這裡不使用虛構報價、勝率或保證報酬。</p>
    </div>
    <div class="picker-method-grid">
      <section><span>你的需求</span><strong>{{ picker.applied.search.trim() || '尚未輸入文字需求' }}</strong></section>
      <section><span>目前條件</span><strong>{{ conditions.filter(([k]) => k !== 'search').map(([, t]) => t).join('、') || '不限類型、產業與波動' }}</strong></section>
      <section><span>排列原則</span><strong>條件相符、理由清楚，且能同時說明主要風險</strong></section>
      <section><span>資料狀態</span><strong>TWSE／TPEx 最近可得日資料，非即時行情</strong></section>
    </div>
    <div v-if="ai" class="pk-method-ai">
      <p v-if="ai.plan.interpretation"><strong>需求解讀：</strong>{{ ai.plan.interpretation }}</p>
      <p v-if="ai.overall"><strong>整體說明：</strong>{{ ai.overall }}</p>
      <ul v-if="aiNotes.length"><li v-for="note in aiNotes" :key="note">{{ note }}</li></ul>
      <dl v-if="ai.glossary.length"><template v-for="g in ai.glossary" :key="g.term"><dt>{{ g.term }}</dt><dd>{{ g.explanation }}</dd></template></dl>
      <small>{{ ai.notice }}</small>
    </div>
  </AppModal>

  <!-- 全部結果 -->
  <AppModal :open="modal === 'all'" :title="`全部選股結果（${list.length}）`" modal-class="picker-all-modal" @close="modal = ''">
    <div class="picker-all-note">依目前條件排列；先閱讀理由與風險，再加入追蹤或比較。</div>
    <div class="picker-all-list">
      <article v-for="(s, i) in list" :key="s.code" class="picker-all-row">
        <div class="stock-rank">{{ String(i + 1).padStart(2, '0') }}</div>
        <div class="picker-all-copy">
          <strong>{{ s.code }} {{ s.name }}</strong>
          <small>{{ s.industry }} · {{ s.aiReasons?.slice(1).join('；') || s.reason }}</small>
          <span><AppIcon name="shield" :size="14" /> {{ s.explanation || s.risk }}</span>
        </div>
        <div class="picker-all-actions">
          <button class="candidate-toggle" :class="{ active: isTracked(s.code) }" type="button" @click="toggleTrack(s.code, 'picker')">
            {{ isTracked(s.code) ? '✓ 已追蹤' : '＋ 加入追蹤' }}
          </button>
          <button class="outline-button small" :class="{ active: isCompared(s.code) }" type="button" @click="toggleCompare(s.code)">
            {{ isCompared(s.code) ? '✓ 已選比較' : '＋ 比較' }}
          </button>
          <button class="primary-button small" type="button" @click="showDetail(s)">查看分析</button>
        </div>
      </article>
    </div>
  </AppModal>
</template>

<style scoped>
/* 進階條件按鈕放在搜尋欄右側內緣（輸入框已預留 9rem 右側空間）；
   有清除鈕時，清除鈕排在它左邊 */
.picker-input-shell .pk-advanced-inline{position:absolute;top:50%;right:6px;transform:translateY(-50%);display:inline-flex;align-items:center;gap:6px;height:calc(100% - 12px);margin:0;padding:0 12px;border:1px solid var(--line);border-radius:10px;background:color-mix(in srgb,var(--blue) 6%,transparent);color:var(--blue);font-size:14px;font-weight:700;white-space:nowrap;cursor:pointer}
.picker-input-shell .pk-advanced-inline:hover:not(:disabled){background:color-mix(in srgb,var(--blue) 12%,transparent)}
.picker-input-shell .pk-advanced-inline b{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:var(--blue);color:#fff;font-size:11px}
.picker-input-shell .pk-advanced-inline:disabled{opacity:.5;cursor:not-allowed}
/* 清除鈕原本沒有定位樣式，會被擠到輸入框下一行；改放在輸入框內、進階條件左側 */
.picker-input-shell button[aria-label="清除需求"]{position:absolute;top:50%;right:128px;transform:translateY(-50%);display:grid;place-items:center;width:26px;height:26px;padding:0;border:0;border-radius:50%;background:color-mix(in srgb,var(--muted) 18%,transparent);color:var(--text-strong);font-size:16px;line-height:1;cursor:pointer}
/* 最近的選股紀錄＋追蹤摘要 */
/* 舊版空狀態樣式會把內容垂直置中；有紀錄時改為靠上 */
body[data-page="picker"] .picker-results.pk-has-history{display:flex!important;flex-direction:column!important;align-content:start!important;justify-content:flex-start!important;padding-top:22px!important;padding-bottom:18px!important}
body[data-page="picker"] .picker-results.pk-has-history > .pk-home{flex:1 1 auto}
.pk-home{display:grid;grid-template-columns:minmax(0,1fr);gap:18px}
.pk-search-title{margin:0 0 8px;color:var(--text-strong);font-size:18px}
/* 起始畫面：搜尋與內容併成同一張卡片，接縫的間距、圓角、陰影與框線都收掉 */
:global(body[data-page="picker"] .picker-workspace-v3:has(.pk-first-use)){gap:10px!important}
:global(body[data-page="picker"] .picker-workspace-v3:has(.pk-first-use) .picker-command-center){position:relative;z-index:1;border-bottom-left-radius:0!important;border-bottom-right-radius:0!important;box-shadow:none!important;padding-bottom:4px!important}
:global(body[data-page="picker"] .picker-workspace-v3:has(.pk-first-use) .picker-command-center::after){clip-path:inset(0 0 var(--pw-frame-w) 0)}
:global(body[data-page="picker"] .page-host .picker-workspace-v3 .picker-results.pk-first-use){margin-top:-9px!important;border-top-left-radius:0!important;border-top-right-radius:0!important;padding-top:8px!important}
:global(body[data-page="picker"] .picker-workspace-v3 .picker-results.pk-first-use::after){clip-path:inset(var(--pw-frame-w) 0 0 0)}
.pk-switch{flex:none;display:flex;gap:2px;padding:2px;border:1px solid var(--line);border-radius:999px}
.pk-switch button{padding:3px 12px;border:0;border-radius:999px;background:transparent;color:var(--muted);font-size:13px;font-weight:700;white-space:nowrap;cursor:pointer}
.pk-switch button:hover{color:var(--text-strong)}
.pk-switch button.active{background:var(--blue);color:#fff}
:global(body[data-theme="dark"] .pk-switch button.active){color:#0d2340}
.pk-block-side{display:flex;align-items:center;gap:12px}
/* 紀錄壓成兩行：搜尋卡片多了試試看與提醒列時，5 筆仍放得下 */
.pk-home .pk-history .pk-record{min-height:0;padding-top:7px;padding-bottom:7px}
.pk-home .pk-history .pk-record-copy{display:grid;grid-template-columns:auto minmax(0,1fr);column-gap:10px;align-items:baseline}
.pk-home .pk-history .pk-record-copy strong{grid-column:1/-1}
.pk-home .pk-history .pk-record-copy small{margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pk-block-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:10px}
.pk-block-head h2{margin:0;font-size:18px;color:var(--text-strong)}
.pk-block-head small{color:var(--muted);font-size:12px}
.pk-record{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:14px;background:color-mix(in srgb,var(--blue) 3%,transparent)}
.pk-record + .pk-record{margin-top:8px}
.pk-record-top{color:var(--text)!important;opacity:.75;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pk-record-slot{justify-content:center;min-height:0;flex:1 1 0;border-style:dashed;background:transparent;color:var(--muted);font-size:13px;opacity:.7}
/* 兩欄延伸到區塊底部對齊；紀錄與虛線框平均分配高度 */
.pk-home{min-height:100%;align-items:stretch}
.pk-history{display:flex;flex-direction:column}
.pk-history > .pk-record{flex:1 1 0;min-height:max-content}
.pk-record-copy{flex:1;min-width:0;display:grid;gap:3px}
.pk-record-copy strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-strong);font-size:15px}
.pk-record-copy small{color:var(--muted);font-size:12px}
.pk-record-actions{display:flex;align-items:center;gap:6px;flex:none}
.pk-record-remove{width:26px;height:26px;border:0;border-radius:50%;background:transparent;color:var(--muted);font-size:16px;cursor:pointer}
.pk-record-remove:hover{background:color-mix(in srgb,var(--muted) 15%,transparent)}
.pk-viewing{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 12px;margin-bottom:10px;padding:8px 12px;border-radius:10px;background:color-mix(in srgb,var(--orange) 12%,transparent);color:var(--text);font-size:13px}
@media (max-width:900px){.pk-home{grid-template-columns:1fr}.pk-record{flex-wrap:wrap}}
.picker-command-center .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.pk-warn-mark{display:inline-grid;place-items:center;width:15px;height:15px;border-radius:50%;background:var(--red);color:#fff;font-size:10px;font-weight:900;line-height:1}
.picker-results-head{align-items:center}
.picker-results-head :deep(.info-tip--warning){padding:2px 9px 2px 4px;gap:5px;font-size:12px}
.pk-head-copy h2{margin:0;font-size:24px!important;line-height:1.3}
.pk-head-copy small{display:block;margin-top:2px;color:var(--muted);font-size:12px}
/* 篩選過程一行：來源（藍）→ 漏斗數字（粗體）→ 警示（橘）→ AI 說明（灰，單行截斷） */
.pk-ai-line{margin:4px 0 8px;padding:7px 12px;border:1px solid var(--line);border-radius:12px;background:color-mix(in srgb,var(--blue) 4%,transparent);font-size:13px;color:var(--text)}
.pk-ai-summary{display:flex;flex-wrap:nowrap;align-items:center;gap:14px;white-space:nowrap;overflow:hidden}
.pk-ai-funnel-short{overflow:hidden;text-overflow:ellipsis}
.pk-ai-funnel-short em{padding:0 7px;border-radius:999px;background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue);font-style:normal;font-weight:800}
.pk-ai-more{margin-left:auto;padding:0;border:0;background:transparent;color:var(--blue);font-size:13px;font-weight:700;cursor:pointer}
.pk-ai-more::after{content:" ›"}
:global(.modal.pk-info-modal){width:min(560px,calc(100vw - 32px))}
.pk-info-body{display:grid;gap:10px;font-size:14px;line-height:1.7;color:var(--text)}
.pk-info-body h4{margin:6px 0 0;color:var(--text-strong);font-size:14px}
.pk-info-body p{margin:0}
.pk-info-steps{margin:0;padding-left:20px;display:grid;gap:4px}
.pk-info-steps li{display:flex;justify-content:space-between;gap:12px}
.pk-info-steps em{font-style:normal;font-weight:800;color:var(--blue)}
.pk-info-notes{margin:0;padding-left:18px;color:var(--text)}
.pk-info-small{color:var(--muted);font-size:12px}
.pk-info-actions{display:flex;justify-content:flex-end;margin-top:4px}
.pk-ai-source{display:inline-flex;align-items:center;gap:4px;color:var(--blue);font-weight:700}
.pk-ai-funnel{display:inline-flex;flex-wrap:wrap;align-items:center;gap:6px}
.pk-ai-funnel b{color:var(--muted);font-weight:400}
.pk-ai-funnel em{margin-left:3px;padding:0 7px;border-radius:999px;background:color-mix(in srgb,var(--blue) 12%,transparent);color:var(--blue);font-style:normal;font-weight:800}
.pk-ai-note{color:#b06a12;font-size:12px}
.pk-ai-overall{flex:1 1 240px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.pk-method-ai{display:grid;gap:8px;margin-top:12px;padding-top:12px;border-top:1px solid var(--line);font-size:13px;line-height:1.6;color:var(--text)}
.pk-method-ai p,.pk-method-ai ul,.pk-method-ai dl{margin:0}
.pk-method-ai dt{font-weight:700;color:var(--text-strong)}
.pk-method-ai dd{margin:0 0 6px;color:var(--muted)}
.pk-method-ai small{color:var(--muted)}
.pk-fallback{display:grid;gap:2px;margin-bottom:10px;padding:10px 14px;border-radius:12px;border:1px solid color-mix(in srgb,var(--orange) 35%,transparent);background:color-mix(in srgb,var(--orange) 10%,transparent);font-size:13px;color:var(--text)}
.pk-fallback strong{color:var(--text-strong)}
/* 結果放不下時在結果區內捲動（不再切換成分頁）。外框保持 overflow:hidden 與圓角，
   捲動交給內層 .pk-scroll，捲軸就會留在圓角卡片裡面、不會切出直角。 */
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty)){overflow:hidden!important;display:flex!important;flex-direction:column!important;padding-right:6px!important}
/* 固定頁面：不出現捲軸。只有展開「篩選過程」時才允許捲動。 */
/* 一般情況剛好放滿不會捲動；內容真的放不下時才出現捲軸，避免內容被裁切看不到 */
.pk-scroll{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;overflow-y:auto;scrollbar-width:thin;padding:0 0 10px 0}
.pk-scroll > *{flex-shrink:0}
:global(body.r2-picker-focus) .pk-scroll{overflow:visible;padding-right:0}
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .smart-stock-grid){flex:1 0 auto!important;overflow:visible!important;min-height:max-content!important;grid-template-rows:1fr!important;align-items:stretch!important}
/* 卡片填滿剩餘高度：按鈕固定在卡片底部，內容間距自然拉開；空間不夠時維持內容高度並捲動 */
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .smart-stock-grid > .smart-stock-card){display:flex!important;flex-direction:column!important;height:auto!important;min-height:max-content!important;align-self:stretch!important}
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .smart-stock-grid > .smart-stock-card){justify-content:flex-start!important;gap:10px!important}
/* 內容由上往下排，按鈕固定在卡片底部，不再把少量內容拉開成大片空白 */
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .smart-stock-card .smart-stock-actions){margin-top:auto!important}
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .smart-stock-card > *){width:100%}
:global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .smart-stock-card .smart-stock-actions){display:grid!important;grid-template-columns:1fr 1fr!important;gap:8px!important}
/* 窄螢幕的「搜尋條件」分頁：高度跟著內容，靠上排列，不留大片空白 */
body.r2-picker-focus .picker-command-center{min-height:0!important;height:auto!important;justify-content:flex-start!important;align-content:start!important;flex:none!important}
/* 狀態列：篩選過程與比較清單併成一行，把高度留給卡片 */
.pk-status{display:flex;gap:8px;margin:0 0 8px}
.pk-prefs{flex:0 1 auto;min-width:0}
.pk-status .pk-ai-line{flex:1 1 0;min-width:0;display:grid;align-items:center;margin:0}
.pk-status .picker-comparison-tray{flex:1.2 1 0!important;width:auto!important;min-width:0;margin:0!important}
/* 卡片放得下：結果區不捲動，由卡片吃掉剩餘高度；3 檔、2 檔、1 檔各自決定欄數 */
@media (min-width:1001px) and (min-height:601px){
  .pk-scroll.is-fit{overflow:hidden;padding-bottom:4px}
  .pk-scroll.is-fit .picker-results-head{margin-bottom:6px}
  .pk-scroll.is-fit .pk-head-copy{flex:1 1 0;min-width:0;display:flex;align-items:baseline;gap:10px}
  .pk-scroll.is-fit .pk-head-copy h2{flex:none;font-size:20px!important;white-space:nowrap}
  .pk-scroll.is-fit .pk-head-copy small{flex:0 1 auto;min-width:0;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .pk-scroll.is-fit .picker-results-tools{flex:none}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .pk-scroll.is-fit){padding-right:8px}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .pk-scroll.is-fit > .smart-stock-grid){flex:1 1 0!important;min-height:0!important;overflow:hidden!important;grid-template-rows:minmax(0,1fr)!important;justify-content:stretch!important;gap:10px!important}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results .smart-stock-grid.pk-n1){grid-template-columns:minmax(0,1fr)!important}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results .smart-stock-grid.pk-n2){grid-template-columns:repeat(2,minmax(0,1fr))!important}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results .smart-stock-grid.pk-n3){grid-template-columns:repeat(3,minmax(0,1fr))!important}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .pk-scroll.is-fit > .smart-stock-grid > .smart-stock-card){height:auto!important;min-height:0!important;overflow:hidden;gap:8px!important;padding:12px 14px!important}
  :global(body[data-page="picker"]:not(.r2-picker-focus) .page-host .picker-results:not(.picker-results-empty) .pk-scroll.is-fit > .smart-stock-grid > .smart-stock-card.sc-solo){flex-direction:row!important;gap:16px!important}
}
@media (max-width:1000px){.pk-status{flex-direction:column}}
.pk-help-details{margin:2px 0 6px;padding-left:18px;color:var(--muted);font-size:13px;line-height:1.6;text-align:left}
.pk-help-inline{margin:0 0 10px}
.picker-empty-actions{flex-wrap:wrap}
.pk-field-hint{display:block;margin-top:4px;color:var(--muted);font-size:12px;font-weight:400;line-height:1.5}
.pk-field-disabled{opacity:.55}
.pk-field-disabled select{cursor:not-allowed}
.picker-input-shell button[aria-label="清除需求"]:hover{background:color-mix(in srgb,var(--muted) 30%,transparent)}
</style>
