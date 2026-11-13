<script setup>
import { onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './components/AppSidebar.vue'
import AssistantPanel from './components/AssistantPanel.vue'
import AppIcon from './components/AppIcon.vue'
import ResearchDialogs from './components/research/ResearchDialogs.vue'
import StockDetailModal from './components/stock/StockDetailModal.vue'
import StockSearchModal from './components/stock/StockSearchModal.vue'
import NotificationDrawer from './components/NotificationDrawer.vue'
import ProfileDialog from './components/account/ProfileDialog.vue'
import AccountModal from './components/account/AccountModal.vue'
import HelpCenter from './components/help/HelpCenter.vue'
import FeatureGuide from './components/help/FeatureGuide.vue'
import Onboarding from './components/help/Onboarding.vue'
import TourOverlay from './components/TourOverlay.vue'
import NavHiddenPrompt from './components/NavHiddenPrompt.vue'
import { ui, settings, unreadCount, applySettings } from './stores/ui.js'
import { overlays } from './stores/overlays.js'
import { loadAccount } from './stores/account.js'
import { recordVisit } from './stores/footprint.js'
import { startAlerts } from './stores/alerts.js'

applySettings()
loadAccount()

// 舊版 CSS 大量依賴 body[data-page]（對應舊版 renderPage 的 document.body.dataset.page）。
const route = useRoute()
watch(() => route.name, (name) => (document.body.dataset.page = name || 'home'), { immediate: true })

// 右上角「搜尋股票／通知」要和頁首卡片右緣對齊；內容區右側保留的捲軸寬度依系統而不同，
// 量出實際寬度存成 --pw-gutter，給樣式計算位置用。
function measureGutter() {
  const host = document.getElementById('pageHost')
  const gutter = host ? Math.max(0, host.offsetWidth - host.clientWidth) : 0
  document.documentElement.style.setProperty('--pw-gutter', `${gutter}px`)
  // 右上角按鈕（高 44px）對齊頁首卡片的垂直中線；各頁頁首高度略有不同，所以用量的。
  const banner = document.querySelector('#pageHost :is(.page-banner, .picker-dashboard-head)')
  if (banner) {
    const rect = banner.getBoundingClientRect()
    document.documentElement.style.setProperty('--pw-fa-top', `${Math.round(rect.top + (rect.height - 44) / 2)}px`)
  }
}
// 頁首高度在字型或樣式載入後可能改變，所以持續觀察，高度一變就重新對齊。
let bannerObserver = null
function observeBanner() {
  bannerObserver?.disconnect()
  const banner = document.querySelector('#pageHost :is(.page-banner, .picker-dashboard-head)')
  if (banner && typeof ResizeObserver !== 'undefined') {
    bannerObserver = new ResizeObserver(measureGutter)
    bannerObserver.observe(banner)
  }
  measureGutter()
}
watch(() => route.name, () => nextTick(() => requestAnimationFrame(observeBanner)))
onMounted(() => {
  recordVisit()
  startAlerts()
  observeBanner()
  window.addEventListener('resize', measureGutter)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', measureGutter)
  bannerObserver?.disconnect()
})

// 依頁面區高度切換緊湊版面（對應舊版 applyR2Layout 的 r2-compact-height / r2-short-height）。
let hostObserver = null
function observeHostHeight() {
  const host = document.querySelector('#pageHost')
  if (!host || typeof ResizeObserver === 'undefined') return
  hostObserver = new ResizeObserver(() => {
    document.body.classList.toggle('r2-compact-height', host.clientHeight < 790)
    document.body.classList.toggle('r2-short-height', host.clientHeight < 690)
  })
  hostObserver.observe(host)
}

function onKeydown(event) {
  if (event.key !== 'Escape') return
  if (overlays.profile) overlays.profile = false
  else if (ui.mobileNavOpen) ui.mobileNavOpen = false
  else if (ui.assistantOpen) ui.assistantOpen = false
}
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  observeHostHeight()
  // 第一次使用時顯示歡迎畫面（對應舊版 initGlobal 的 showWelcomeOnboarding）。
  if (!settings.onboardingCompleted) setTimeout(() => (overlays.onboarding = 'welcome'), 650)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  hostObserver?.disconnect()
})
</script>

<template>
  <div class="app-shell" id="appShell" :inert="overlays.onboarding === 'welcome' || overlays.onboarding === 'preferences' || undefined">
    <div class="mobile-nav-backdrop" :hidden="!ui.mobileNavOpen" @click="ui.mobileNavOpen = false"></div>
    <AppSidebar />
    <ProfileDialog />

    <main class="main-shell">
      <div class="floating-actions">
        <button
          class="mobile-menu-button"
          type="button"
          :aria-label="ui.mobileNavOpen ? '關閉主選單' : '開啟主選單'"
          :aria-expanded="String(ui.mobileNavOpen)"
          @click="ui.mobileNavOpen = !ui.mobileNavOpen"
        >☰</button>
        <button class="top-search-button" type="button" aria-label="搜尋股票" @click="overlays.stockSearch = true">
          <AppIcon name="search" /><span>搜尋股票</span>
        </button>
        <button class="top-icon notification-bell" type="button" aria-label="通知" @click="overlays.notifications = true">
          <AppIcon name="bell" :size="22" />
          <span class="notification-badge" :hidden="!unreadCount">{{ unreadCount }}</span>
        </button>
      </div>
      <section class="page-host" id="pageHost">
        <RouterView />
      </section>
    </main>
  </div>

  <AssistantPanel />
  <ResearchDialogs />
  <StockDetailModal />
  <StockSearchModal />
  <NotificationDrawer />
  <AccountModal />
  <HelpCenter />
  <FeatureGuide />
  <Onboarding />
  <TourOverlay />
  <NavHiddenPrompt />

  <div class="toast-stack" aria-live="polite">
    <div v-for="t in ui.toasts" :key="t.id" class="toast" role="status">{{ t.message }}</div>
  </div>
</template>

<style>
/* 搜尋股票：香檳金，和藍紫色的主按鈕區隔；淺色底要配深色字才看得清楚 */
.floating-actions .top-search-button{border-color:transparent;background:linear-gradient(115deg,#FFF3C4,#FFDC82);color:#3A2600;box-shadow:0 8px 20px rgba(230,170,40,.34)}
.floating-actions .top-search-button:hover,.floating-actions .top-search-button:focus-visible{border-color:transparent;color:#3A2600;filter:brightness(1.05);box-shadow:0 10px 24px rgba(230,170,40,.52)}

/* 通知鈴鐺：比搜尋股票更淡的金色，同色系但不搶主按鈕 */
html body .app-shell .floating-actions .notification-bell,html body .floating-actions button.notification-bell{border:1px solid #F0D48C!important;background:linear-gradient(135deg,#FFFBEF,#FFF0CC)!important;color:#7A5410!important;box-shadow:0 6px 14px rgba(230,170,40,.22)}

/* 每頁最上方的標題卡：全站同一個底色（蓋過原本各頁不同的色調），比內容卡略有色但不搶眼 */
body[data-page] .page-host .page :is(.page-banner,.picker-dashboard-head){background:linear-gradient(100deg,#FBF0DF 0%,#F7EEF4 55%,#EDF2FC 100%)!important}
body[data-theme="dark"][data-page] .page-host .page :is(.page-banner,.picker-dashboard-head){background:linear-gradient(100deg,#2B2A4A 0%,#21294A 55%,#1A2C48 100%)!important}

/* 首頁搜尋欄：和側邊欄卡片同樣的金邊 */
body[data-page="home"] .home-page .hero-query{border:1.5px solid #C9A25A!important}

/* 設定頁左側選單：選取樣式和主側邊欄一致 */
body .settings-menu .settings-tab.active{background:linear-gradient(98deg,#D9E9FF 0%,#E9E5FF 100%)!important;color:#143E89!important;font-weight:800;outline:2px solid #86AEF0;outline-offset:-2px}
body[data-theme="dark"] .settings-menu .settings-tab.active{background:linear-gradient(98deg,#3A5C94,#4A4B8E)!important;color:#fff!important}

/* 深色模式分層：越上層越亮（卡片亮於背景與側邊欄、卡片內區塊再亮一階、輸入框凹陷較暗），不再整頁同一個深色 */
body[data-theme="dark"]{--pw-d1:#2B3C5C;--pw-d2:#374A6E;--pw-d-well:#22314D}
body[data-theme="dark"][data-page] .page-host .page :is(.card,.wl-card,.wl-kpis article,.mk-card,.mk-tile,.rp-bottom,.rp-locked,.scorecard-empty-status){background:var(--pw-d1)!important}
body[data-theme="dark"][data-page] .page-host .page :is(.smart-stock-card,.kpi-card,.research-landing-feature,.learning-tile,.recommend-card,.learning-path-label,.pk-what,.pk-chips button,.pk-presets button,.tr-cell,.ev-source,.ev-empty li,.wl-ways button,.cp-table,.rs-box:not(.rs-risk),.rp-pv-box,.pk-record:not(.pk-record-slot),.empty-state,.display-mode-option,.scene-scroll,.theme-card,.font-size-preset:not(.active),.appearance-preview,.sidebar-config-item,.mk-table th){background:var(--pw-d2)!important}
body[data-theme="dark"][data-page] .page-host .page :is(table th){background:var(--pw-d2)!important}
body[data-theme="dark"][data-page] .page-host .page :is(table td){background:transparent!important}
body[data-theme="dark"][data-page] .page-host .page :is(.picker-input-shell,.comparison-search-shell,.research-empty-form>div){background:var(--pw-d-well)!important;border-color:rgba(205,221,248,.3)!important}
body[data-theme="dark"][data-page] .page-host .page .research-empty-form input{color:#F2F6FF!important}
body[data-theme="dark"][data-page] .page-host .page .research-landing-topics button{background:var(--pw-d2)!important;border-color:rgba(205,221,248,.3)!important;color:#EAF1FF!important}
body[data-theme="dark"][data-page="home"] .home-page :is(.hero-query,.topic-chip,.summary-card){background:rgba(43,60,92,.94)!important}

/* 深色模式：台股紅漲綠跌（共用樣式把上漲設成綠色），並補足深色卡片上的文字對比 */
/* 共用樣式只替「漲」加粗，漲跌要看起來一樣重。 */
.price-down{font-weight:800}
body[data-theme="dark"] .price-up,body[data-theme="dark"] .page-host .price-up{color:#FF9A9A!important}
body[data-theme="dark"] .price-down,body[data-theme="dark"] .page-host .price-down{color:#6FE3B4!important}
body[data-theme="dark"][data-page] .page-host .page{--blue:#A9CEFF}
body[data-theme="dark"][data-page] .page-host .page :is(.info-tip,.card-link,.picker-preference-note button,.pk-try button,.picker-advanced-link){color:#A9CEFF!important}
body[data-theme="dark"][data-page] .page-host .page :is(.eyebrow,.drag-handle,.research-landing-topics>span){color:#C8D5EA!important}
body[data-theme="dark"][data-page] .page-host .page :is(.sidebar-config-item strong,.empty-state strong){color:#F2F6FF!important}
body[data-theme="dark"][data-page] .page-host .page .empty-state span{color:#DCE6F7!important}
body[data-theme="dark"][data-page] .page-host .page .picker-input-shell{border-radius:14px;overflow:hidden}
body[data-theme="dark"][data-page] .page-host .page :is(.mk-range button.active,.wl-sort button.active){background:#337FF4!important;border-color:#337FF4!important;color:#fff!important}

/* 深色模式的彈窗標題與關閉鈕 */
body[data-theme="dark"] .modal .modal-header h2,body[data-theme="dark"] .modal .modal-header .icon-button{color:#F2F6FF!important}

/* 深色首頁：背景圖維持原樣，標題靠文字本身的陰影維持可讀性 */
body[data-theme="dark"][data-page="home"] .home-title{color:#fff!important;text-shadow:0 2px 3px rgba(8,14,30,.8),0 4px 24px rgba(8,14,30,.75)!important}
body[data-theme="dark"][data-page="home"] .home-title em{color:#A9CEFF!important;text-shadow:0 2px 3px rgba(8,14,30,.8),0 4px 24px rgba(8,14,30,.75)!important}
body[data-theme="dark"][data-page="home"] .home-subtitle{color:#F4F7FF!important;text-shadow:0 1px 3px rgba(8,14,30,.9),0 2px 14px rgba(8,14,30,.8)!important}

/* 全站卡片分三層，寫在這裡讓各頁一致：
   主要大卡＝柔和藍紫漸層框；KPI／小卡＝淺藍紫單色框；卡片內區塊＝淡藍底不加框。
   漸層框用 ::after 畫，不必覆蓋卡片原本的底色。 */
:root{--pw-frame-a:#F2C4A0;--pw-frame-b:#EBB4CF;--pw-frame-w:1.5px;--pw-small-line:#EFD9D2;--pw-inner:#F7F8FD}
body[data-theme="dark"]{--pw-frame-a:#A9805F;--pw-frame-b:#9C6C8C;--pw-small-line:#4A5470;--pw-inner:#374A6E}
body .page-host :is(.page-banner,.picker-dashboard-head,.card:not(.kpi-card,.smart-stock-card,.card .card),.wl-card,.mk-card,.rp-bottom,.rp-locked,.scorecard-empty-status,.evidence-source-dashboard){position:relative;border-width:0!important;box-shadow:0 12px 30px rgba(70,50,90,.13)!important}
body .page-host :is(.page-banner,.picker-dashboard-head,.card:not(.kpi-card,.smart-stock-card,.card .card),.wl-card,.mk-card,.rp-bottom,.rp-locked,.scorecard-empty-status,.evidence-source-dashboard)::after{content:"";position:absolute;inset:0;width:auto;height:auto;padding:var(--pw-frame-w);border-radius:inherit;background:linear-gradient(120deg,var(--pw-frame-a),var(--pw-frame-b));opacity:1;filter:none;transform:none;pointer-events:none;-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude}
body .page-host :is(.wl-kpis article,.mk-tile,.kpi-card,.research-landing-feature,.smart-stock-card,.learning-tile,.summary-card){border:1.5px solid var(--pw-small-line)!important;box-shadow:0 6px 16px rgba(30,60,120,.1)}
body .page-host :is(.rs-inline .rs-box:not(.rs-risk),.rp-pv-box,.pk-record:not(.pk-record-slot)){border-color:transparent!important;background:var(--pw-inner)!important}
/* 右上角按鈕：非首頁時與頁首卡片右緣切齊，並在卡片圓角內側留 16px，不壓到圓弧。
   首頁沒有頁首卡片，維持原位置。 */
body:not([data-page="home"]) .floating-actions{right:calc(var(--r2-pad, 12px) + var(--pw-gutter, 0px) + 16px)!important}
@media (min-width:901px){body:not([data-page="home"]) .floating-actions{top:var(--pw-fa-top, calc(var(--r2-pad, 12px) + 8px))!important}}
/* 頁首說明文字讓出右上角按鈕的位置，避免文字跑到按鈕底下 */
@media (min-width:901px){body:not([data-page="home"]) .page-banner{padding-right:240px}}
</style>
