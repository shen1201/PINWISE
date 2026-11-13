<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PreferenceForm from '@/components/PreferenceForm.vue'
import AppIcon from '@/components/AppIcon.vue'
import { navMeta, navGroups } from '@/data/nav.js'
import { PREFERENCE_LABELS } from '@/data/preferences.js'
import { settings, ui, toast, SCENES, NAV_ORDER, APPEARANCE_DEFAULTS, resolvedTheme, sceneCss } from '@/stores/ui.js'
import { overlays, openHelp } from '@/stores/overlays.js'
import { newConversation } from '@/stores/assistant.js'
import { formatDate } from '@/stores/research.js'
import { startTour } from '@/stores/tour.js'
import { workspace } from '@/stores/workspace.js'
import { sourceHealth, refreshSourceHealth, checkSource, engineMode, HEALTH_LABELS, CONFIG_LABELS } from '@/stores/sourceHealth.js'

// 設定（對應舊版 js/settings.js 的 settingsPage 與各分頁）。網址 #/settings/<分頁>。
const route = useRoute()
const router = useRouter()
const TABS = [['appearance', '外觀與版面'], ['notifications', '通知設定'], ['monitoring', '監控規則'], ['connections', '資料連線'], ['preferences', '個人化偏好'], ['accountPrivacy', '帳戶與隱私'], ['help', '教學與幫助']]
const tab = computed(() => (TABS.some(([key]) => key === route.params.tab) ? route.params.tab : 'appearance'))
const go = (key) => router.replace(`/settings/${key}`)

// ready：網頁開著時已會檢查並通知；月營收尚未接上。
const MONITOR_RULES = [['disclosure', '重大公告 / 法說', '追蹤股票近 3 天的新公告', true], ['price', '價格波動', '單日漲跌超過 7%，或距半年高點回落超過「風險觀察」的提醒線', true], ['revenue', '月營收', '尚未接上每月營收公布', false]]

// ── 外觀 ──
const MODES = [['light', '柔和淺色'], ['white', '純白'], ['dark', '深色'], ['classic', 'PINWISE 原色'], ['system', '跟隨系統']]
const FONT_PRESETS = [[92, '小'], [100, '標準'], [110, '大'], [120, '特大']]
const SLIDERS = [['背景亮度', 'brightness', 50, 150, '%'], ['背景模糊', 'blur', 0, 20, ' px'], ['背景遮罩', 'overlay', 0, 50, '%'], ['卡片透明度', 'cardOpacity', 72, 100, '%']]
const activeFont = computed(() => FONT_PRESETS.reduce((best, x) => (Math.abs(x[0] - settings.fontScale) < Math.abs(best[0] - settings.fontScale) ? x : best), FONT_PRESETS[1])[0])
const previewStyle = computed(() => ({
  '--preview-scene': sceneCss(),
  '--preview-brightness': `${settings.brightness}%`,
  '--preview-blur': `${settings.blur}px`,
  '--preview-overlay': settings.overlay / 100,
  '--preview-opacity': settings.cardOpacity / 100,
}))
function resetAppearance() {
  Object.assign(settings, APPEARANCE_DEFAULTS)
  toast('已還原外觀預設值')
}

// ── 側邊欄管理 ──
// 與左側側邊欄相同：依分組顯示，組內照 navOrder 排序；上下移只在同一組裡交換。
const navSorted = (keys) => [...keys].sort((a, b) => settings.navOrder.indexOf(a) - settings.navOrder.indexOf(b))
const navConfigGroups = computed(() => navGroups.map(([title, keys]) => [title, navSorted(keys)]))
function moveNav(key, delta) {
  const group = navConfigGroups.value.find(([, keys]) => keys.includes(key))?.[1] || []
  const neighbor = group[group.indexOf(key) + delta]
  if (!neighbor) return
  const order = settings.navOrder, from = order.indexOf(key), to = order.indexOf(neighbor)
  ;[order[from], order[to]] = [order[to], order[from]]
}
function toggleNav(key) {
  if (key === 'home') return
  settings.navVisible[key] = !settings.navVisible[key]
  toast(`${navMeta[key][1]}已${settings.navVisible[key] ? '顯示' : '從側邊欄隱藏'}`)
}
function resetSidebar() {
  settings.navOrder = [...NAV_ORDER]
  settings.navVisible = Object.fromEntries(NAV_ORDER.map((key) => [key, true]))
  toast('已恢復建議側邊欄配置')
}

// ── 通知 ──
// 與通知中心分頁一一對應；ready=false 代表尚未產生通知，顯示「即將推出」且不能切換。
const NOTIFY_ITEMS = [
  ['research', 'AI 標的研究', '研究完成或失敗時提醒。', true],
  ['tracking', '追蹤股票', '單日漲跌超過 7%、距半年高點回落超過提醒線、有新公告；可在「監控規則」選擇要哪幾種。', true],
  ['system', '系統狀態', '官方資料連不上、AI 每日額度用完。', true],
]

// ── 資料連線 ──
watch(tab, (value) => value === 'connections' && !sourceHealth.checked && refreshSourceHealth(), { immediate: true })
const engine = computed(() => engineMode())

// ── 個人化偏好 ──
const editingPrefs = ref(false)

// ── 帳戶與隱私 ──
const nickname = ref(settings.nickname)
function saveNickname() {
  settings.nickname = nickname.value.trim() || '訪客投資者'
  toast('已儲存本機暱稱')
}
function openNewConversation() {
  newConversation()
  ui.assistantOpen = true
}

// ── 教學與幫助 ──
const HELP_ITEMS = [['新手快速導覽', '重新啟動實際畫面高亮教學', 'tour'], ['常見問題', '開啟可搜尋、分類與展開的完整問題中心', 'faq'], ['投資名詞', '查詢 P/E、EPS、ROE、ETF、最大回撤等', 'glossary'], ['功能教學', '依頁面啟動對應互動導覽', 'feature']]
function openHelpItem(kind) {
  if (kind === 'tour') startTour('full', { restore: true, currentPath: route.fullPath })
  else if (kind === 'feature') overlays.featureGuide = true
  else openHelp(kind)
}
</script>

<template>
  <div class="page with-top-space settings-page">
    <div class="workspace settings-workspace">
      <section class="page-banner"><h1>設定</h1><p>集中管理個人化偏好、介面、通知與資料。</p></section>
      <div class="settings-layout">
        <aside class="card settings-menu surface-solid">
          <div class="settings-menu-nav settings-menu-flat">
            <button v-for="[key, label] in TABS" :key="key" type="button" class="settings-tab" :class="{ active: tab === key }" @click="go(key)">{{ label }}</button>
          </div>
        </aside>

        <section class="card settings-section surface-solid">
          <!-- 捲動放內層：外框線才會固定在卡片邊緣，不會跟著內容捲走 -->
          <div class="settings-scroll">
          <!-- 外觀與版面 -->
          <template v-if="tab === 'appearance'">
            <h2>外觀與介面</h2>
            <p>調整背景時，右側預覽會立即顯示畫面效果。</p>
            <div class="appearance-layout">
              <div class="appearance-controls">
                <div class="setting-row setting-mode-row">
                  <div><strong>顯示模式</strong><small>柔和淺色、純白、深色；原色保留既有風格，跟隨系統依裝置外觀切換。</small></div>
                  <div class="display-mode-options" role="radiogroup" aria-label="顯示模式">
                    <button v-for="[key, label] in MODES" :key="key" type="button" class="display-mode-option" :class="{ active: settings.displayMode === key }" role="radio" :aria-checked="String(settings.displayMode === key)" @click="settings.displayMode = key">
                      <span>{{ settings.displayMode === key ? '●' : '○' }}</span>{{ label }}
                    </button>
                  </div>
                </div>
                <h3 class="setting-subtitle">背景與主題</h3>
                <p class="scene-picker-hint">在下方框內捲動，選擇不同場景。</p>
                <div class="scene-scroll" role="group" aria-label="選擇背景場景">
                  <div class="theme-cards">
                    <button v-for="(scene, key) in SCENES" :key="key" type="button" class="theme-card" :class="{ active: settings.scene === key }" :aria-pressed="String(settings.scene === key)" @click="settings.scene = key">
                      <div class="theme-thumb" :style="{ backgroundImage: `url('${scene.url}')` }"></div>
                      <span>{{ scene.name }}</span>
                    </button>
                  </div>
                </div>
                <div v-for="[label, key, min, max, suffix] in SLIDERS" :key="key" class="slider-row">
                  <label :for="`slider-${key}`">{{ label }}</label>
                  <input :id="`slider-${key}`" v-model.number="settings[key]" type="range" :min="min" :max="max" />
                  <output class="slider-value" :for="`slider-${key}`">{{ settings[key] }}{{ suffix }}</output>
                </div>
                <div class="setting-row typography-setting-row">
                  <div><strong>文字大小</strong><small>全站同步調整，預覽中的範例文字也會跟著改變。</small></div>
                  <div class="font-size-presets" role="radiogroup" aria-label="文字大小">
                    <button v-for="[value, label] in FONT_PRESETS" :key="value" type="button" class="font-size-preset" :class="{ active: activeFont === value }" role="radio" :aria-checked="String(activeFont === value)" @click="settings.fontScale = value">
                      <span>{{ label }}</span><small>{{ value }}%</small>
                    </button>
                  </div>
                </div>
                <div class="setting-row">
                  <div>
                    <strong title="開啟後會縮短頁面切換、彈窗、提示、進度條、FAQ 與教學導覽的移動效果。">減少動態效果 ⓘ</strong>
                    <small>適合偏好穩定畫面，或容易受到移動效果影響時使用。</small>
                  </div>
                  <button class="switch" :class="{ on: !settings.motion }" type="button" aria-label="減少動態效果" :aria-pressed="String(!settings.motion)" @click="settings.motion = !settings.motion"></button>
                </div>
              </div>
              <aside class="appearance-preview" aria-label="背景與介面即時預覽" :data-theme="resolvedTheme()" :style="previewStyle">
                <div class="appearance-preview-head"><div><strong>即時預覽</strong><small>拖動左側滑桿即可看到變化</small></div></div>
                <div class="appearance-preview-stage">
                  <div class="appearance-preview-photo"></div>
                  <div class="appearance-preview-shade"></div>
                  <div class="appearance-preview-ui">
                    <div class="preview-bar"><b>PINWISE</b><span>◌</span></div>
                    <div class="preview-content">
                      <small>智慧投資研究</small><strong>讓每一步都更清楚</strong>
                      <div class="preview-sample-card"><b>研究摘要</b><span>範例卡片會跟著透明度調整</span><i></i><i></i></div>
                    </div>
                  </div>
                </div>
                <div class="appearance-preview-foot">
                  <strong>{{ SCENES[settings.scene].name }}</strong>
                  <small>亮度 {{ settings.brightness }}% · 模糊 {{ settings.blur }}px · 遮罩 {{ settings.overlay }}% · 卡片 {{ settings.cardOpacity }}%</small>
                  <button class="card-link" type="button" @click="resetAppearance">還原外觀預設</button>
                </div>
              </aside>
            </div>
            <details class="settings-inline-section">
              <summary>側邊欄管理</summary>
              <h2>側邊欄管理</h2>
              <p>順序與左側側邊欄相同，上下移只在同一組內調整。隱藏只會移除左側入口，不會停用功能；仍可從其他頁面的連結開啟。</p>
              <div class="sidebar-config">
                <template v-for="[title, keys] in navConfigGroups" :key="title">
                  <h3 class="st-nav-group">{{ title }}</h3>
                  <div v-for="(key, i) in keys" :key="key" class="sidebar-config-item">
                    <span class="drag-handle" aria-hidden="true">☰</span>
                    <div>
                      <strong>{{ navMeta[key][1] }}</strong>
                      <label v-if="key === 'esg'" class="st-esg-intro"><input v-model="settings.esgIntro.off" type="checkbox" />不再顯示進入時的說明視窗</label>
                    </div>
                    <div class="sidebar-order-actions">
                      <button type="button" :aria-label="`上移 ${navMeta[key][1]}`" :disabled="i === 0" @click="moveNav(key, -1)">↑</button>
                      <button type="button" :aria-label="`下移 ${navMeta[key][1]}`" :disabled="i === keys.length - 1" @click="moveNav(key, 1)">↓</button>
                    </div>
                    <button class="switch" :class="{ on: settings.navVisible[key] }" type="button" :aria-pressed="String(settings.navVisible[key])" :aria-label="`${navMeta[key][1]}顯示開關`" :disabled="key === 'home'" @click="toggleNav(key)"></button>
                  </div>
                </template>
                <h3 class="st-nav-group">固定</h3>
                <div class="sidebar-config-item is-fixed">
                  <span class="drag-handle" aria-hidden="true">☰</span>
                  <div><strong>設定</strong><small>永遠顯示在最下方</small></div>
                </div>
              </div>
              <button class="outline-button" type="button" style="margin-top: 13px" @click="resetSidebar">恢復建議配置</button>
            </details>
          </template>

          <!-- 通知 -->
          <template v-else-if="tab === 'monitoring'">
            <div class="card-header"><h2>監控規則</h2><span class="tag medium">網頁開著時檢查</span></div>
            <div class="card-body">
              <p class="hint">網頁開著時每 10 分鐘檢查追蹤股票一次，符合就在右上角鈴鐺通知；網頁關閉時不會通知，行情為收盤日資料。</p>
              <div v-for="[key, label, desc, ready] in MONITOR_RULES" :key="key" class="setting-row">
                <div><strong>{{ label }}<span v-if="!ready" class="tag demo notify-soon">即將推出</span></strong><small>{{ desc }}</small></div>
                <button
                  class="switch"
                  :class="{ on: ready && workspace.monitorRules[key] }"
                  type="button"
                  :aria-label="label"
                  :aria-pressed="String(workspace.monitorRules[key])"
                  :disabled="!ready"
                  @click="workspace.monitorRules[key] = !workspace.monitorRules[key]"
                ></button>
              </div>
            </div>
          </template>

          <template v-else-if="tab === 'notifications'">
            <h2>通知</h2>
            <p>選項會保存在本機；通知只在此瀏覽器、網頁開啟時產生。</p>
            <div v-for="[key, label, desc, ready] in NOTIFY_ITEMS" :key="key" class="setting-row">
              <div>
                <strong>{{ label }}<span v-if="!ready" class="tag demo notify-soon">即將推出</span></strong>
                <small>{{ desc }}</small>
              </div>
              <button
                class="switch"
                :class="{ on: ready && settings.notificationPrefs[key] }"
                type="button"
                :aria-label="label"
                :aria-pressed="String(ready && settings.notificationPrefs[key])"
                :disabled="!ready"
                @click="settings.notificationPrefs[key] = !settings.notificationPrefs[key]"
              ></button>
            </div>
          </template>

          <!-- 資料連線 -->
          <template v-else-if="tab === 'connections'">
            <div class="settings-heading-actions">
              <div>
                <h2>外部 API 與資料連線</h2>
                <p>設定狀態由 Python 後端提供，不會把任何金鑰送到瀏覽器。只有你按下單一服務的檢查按鈕時，才會嘗試連線該來源。</p>
              </div>
              <button class="outline-button small" type="button" :disabled="sourceHealth.loading" @click="refreshSourceHealth">{{ sourceHealth.loading ? '更新中…' : '更新設定狀態' }}</button>
            </div>
            <div class="notice engine-mode-status"><strong>{{ engine.title }}</strong><span>{{ engine.text }}</span></div>
            <div aria-live="polite">
              <div v-if="sourceHealth.loading && !sourceHealth.checked" class="empty-state">正在讀取後端設定狀態…</div>
              <div v-else-if="sourceHealth.error" class="notice"><strong>無法取得後端狀態</strong><span>{{ sourceHealth.error }}</span></div>
              <div v-else class="source-connection-grid">
                <article v-for="row in sourceHealth.rows" :key="row.source" class="source-connection-card" :data-source-state="row.status">
                  <div class="source-connection-head">
                    <div><strong>{{ row.source }}</strong><small>{{ row.purpose }}</small></div>
                    <span class="tag" :class="row.status === 'healthy' ? 'good' : row.status === 'error' ? 'bad' : 'demo'">{{ HEALTH_LABELS[row.status] || row.status }}</span>
                  </div>
                  <dl>
                    <div><dt>API Key</dt><dd>{{ row.requires_api_key ? '需要' : row.api_key_optional ? '選填' : '不需要' }}</dd></div>
                    <div><dt>設定狀態</dt><dd>{{ CONFIG_LABELS[row.configuration_status] || row.configuration_status || '未知' }}</dd></div>
                    <div><dt>實際連線</dt><dd>{{ HEALTH_LABELS[row.status] || row.status }}</dd></div>
                    <div><dt>最近檢查</dt><dd>{{ row.checked_at ? formatDate(row.checked_at) : '尚未檢查' }}</dd></div>
                  </dl>
                  <p>{{ row.message }}</p>
                  <small v-if="row.latest_data_at">最新資料：{{ row.latest_data_at }}</small>
                  <small v-if="row.required_settings?.length && row.configuration_status === 'missing'">缺少設定：{{ row.required_settings.join('、') }}</small>
                  <button class="outline-button small" type="button" :disabled="['missing', 'disabled'].includes(row.configuration_status) || row.status === 'checking'" @click="checkSource(row.source)">
                    {{ row.status === 'checking' ? '檢查中…' : '檢查這個服務' }}
                  </button>
                </article>
              </div>
            </div>
            <div class="notice"><strong>資料範圍說明</strong><span>Shioaji 預設關閉；法說會目前涵蓋每日重大訊息中的法說公告，不代表完整歷史資料庫。「已設定」不等於「已驗證連線」。</span></div>
          </template>

          <!-- 個人化偏好 -->
          <template v-else-if="tab === 'preferences'">
            <div class="settings-title-row">
              <div><h2>個人化偏好</h2><p>設定 AI 的說明方式、觀察習慣與風險承受程度。</p></div>
              <span class="preference-status" :class="{ 'is-complete': settings.personalPrefs.completed }">{{ settings.personalPrefs.completed ? '已完成' : '尚未設定' }}</span>
            </div>
            <template v-if="settings.personalPrefs.completed && !editingPrefs">
              <div class="preference-complete-card">
                <div class="preference-complete-mark"><AppIcon name="check" :size="28" /></div>
                <div class="preference-complete-copy">
                  <span class="eyebrow">個人化已啟用</span>
                  <h3>個人化偏好已完成</h3>
                  <p>未來使用智慧選股、AI 標的研究與 PINWISE 助手時，會根據這份個人設定與投資偏好，調整候選建議、風險提醒與分析說明。</p>
                </div>
                <div class="preference-summary-grid">
                  <div v-for="(label, key) in PREFERENCE_LABELS" :key="key"><small>{{ label }}</small><strong>{{ settings.personalPrefs[key] }}</strong></div>
                </div>
                <div class="preference-complete-foot">
                  <small>最後更新：{{ settings.personalPrefs.updatedAt ? formatDate(settings.personalPrefs.updatedAt) : '沿用既有設定' }}</small>
                  <button class="primary-button" type="button" @click="editingPrefs = true">變更偏好</button>
                </div>
              </div>
              <div class="notice personal-impact"><strong>套用原則</strong><span>你在當次問題中明確輸入的條件會優先於已保存的偏好。</span></div>
            </template>
            <template v-else>
              <PreferenceForm @saved="editingPrefs = false" />
              <div class="notice personal-impact"><strong>如何使用這些偏好</strong><span>根據你的個人設定與投資偏好，調整最後提供的候選建議、風險提醒與分析說明。</span></div>
            </template>
          </template>

          <!-- 帳戶與隱私 -->
          <template v-else-if="tab === 'accountPrivacy'">
            <h2>帳戶與隱私</h2>
            <p>管理暱稱、本機紀錄與資料安全。</p>
            <div class="field"><label for="nicknameInput">暱稱</label><input id="nicknameInput" v-model="nickname" /></div>
            <button class="primary-button" type="button" @click="saveNickname">儲存本機暱稱</button>
            <div class="setting-row">
              <div><strong>研究紀錄</strong><small>到 AI 標的研究頁開啟「查看歷史」管理紀錄。</small></div>
              <button class="soft-button" type="button" @click="router.push('/research')">管理紀錄</button>
            </div>
            <div class="setting-row">
              <div><strong>PINWISE 助手</strong><small>開啟空白對話；歷史紀錄可從助手上方切換管理。</small></div>
              <button class="soft-button" type="button" @click="openNewConversation">開啟新對話</button>
            </div>
            <div class="notice">訪客模式請勿輸入密碼、API Key 或券商憑證。</div>
          </template>

          <!-- 教學與幫助 -->
          <template v-else>
            <h2>教學與幫助</h2>
            <p>操作教學、常見問題、投資名詞與產品說明集中在這裡。</p>
            <div v-for="[title, desc, kind] in HELP_ITEMS" :key="kind" class="setting-row">
              <div><strong>{{ title }}</strong><small>{{ desc }}</small></div>
              <button class="soft-button learning-open" type="button" @click="openHelpItem(kind)">開啟</button>
            </div>
            <div class="settings-about">
              <span class="eyebrow">ABOUT FINPILOT</span>
              <h3>智慧投資研究與選股 AI Agent</h3>
              <p>協助使用者提出研究問題、尋找台灣上市櫃候選標的、理解風險與來源，並持續追蹤原始投資論點。</p>
              <small>PINWISE 不會自行送出真實買賣委託。</small>
            </div>
          </template>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.notify-soon{margin-left:8px;font-size:11px;vertical-align:middle}
.switch:disabled{opacity:.4;cursor:not-allowed}
:global(body[data-page="settings"] .settings-section){overflow:hidden!important;padding:0!important}
.settings-scroll{height:100%;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;padding:20px 24px 28px}
.settings-scroll > p{margin:0 0 19px;color:var(--muted);font-size:calc(14px * var(--font-scale))}
.st-esg-intro{display:flex;align-items:center;gap:6px;margin-top:3px;color:var(--muted);font-size:12px;font-weight:500;cursor:pointer}
.st-esg-intro input{width:14px;height:14px;margin:0;accent-color:var(--blue)}
.st-nav-group{margin:8px 2px 0;color:var(--muted);font-size:13px;font-weight:700}
.st-nav-group:first-child{margin-top:0}
.sidebar-config-item.is-fixed{opacity:.7}
.sidebar-config-item.is-fixed small{display:block;color:var(--muted);font-size:12px}
</style>
