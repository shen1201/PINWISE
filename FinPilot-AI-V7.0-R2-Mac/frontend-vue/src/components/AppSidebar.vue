<script setup>
import { computed, ref, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from './AppIcon.vue'
import { navMeta, navGroups } from '@/data/nav.js'
import { ui, settings } from '@/stores/ui.js'
import { overlays } from '@/stores/overlays.js'
import { account } from '@/stores/account.js'
import { tour } from '@/stores/tour.js'
import mark from '@root/assets/pinwise-mark.png'

const route = useRoute()
const router = useRouter()
const isActive = (key) => route.name === key
// 導覽進行中時標出目前步驟所在的頁面（對應舊版 .tour-current）。
const tourPage = computed(() => (tour.active ? tour.steps[tour.index]?.page : ''))

// 依設定頁的側邊欄管理決定顯示哪些項目與順序（對應舊版 renderNav）。
const groups = computed(() =>
  navGroups
    .map(([label, keys]) => [
      label,
      keys.filter((key) => settings.navVisible[key] !== false).sort((a, b) => settings.navOrder.indexOf(a) - settings.navOrder.indexOf(b)),
    ])
    .filter(([, keys]) => keys.length),
)

// 沿用舊版的 <button> 結構，CSS 才會套用一致。
function go(key) {
  ui.mobileNavOpen = false
  router.push(`/${key}`)
}

// 捲軸只在滾動時顯示，停止約 0.8 秒後淡出。
const scrolling = ref(false)
let scrollTimer = 0
function onNavScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => (scrolling.value = false), 800)
}
onBeforeUnmount(() => clearTimeout(scrollTimer))

function openAssistant() {
  ui.mobileNavOpen = false
  ui.assistantOpen = true
}
</script>

<template>
  <aside class="sidebar" id="sidebar" :class="{ open: ui.mobileNavOpen, 'tour-active': tour.active }">
    <button class="brand" type="button" aria-label="回首頁" @click="go('home')">
      <img class="brand-logo" :src="mark" alt="" aria-hidden="true" width="40" height="48" />
      <span class="brand-text"><strong>PINWISE</strong><small>智慧投資夥伴</small></span>
    </button>

    <nav class="sidebar-nav" :class="{ 'is-scrolling': scrolling }" aria-label="主要導覽" @scroll.passive="onNavScroll">
      <div v-for="[label, keys] in groups" :key="label" class="nav-group">
        <span class="nav-group-label">{{ label }}</span>
        <button
          v-for="key in keys"
          :key="key"
          type="button"
          class="nav-item"
          :class="{ active: isActive(key), 'tour-current': tourPage === key }"
          :data-page="key"
          :aria-label="navMeta[key][1]"
          @click="go(key)"
        >
          <span class="nav-icon"><AppIcon :name="navMeta[key][0]" /></span>
          <span class="nav-label">{{ navMeta[key][1] }}</span>
        </button>
      </div>
      <div class="nav-settings">
        <button
          type="button"
          class="nav-item"
          :class="{ active: isActive('settings'), 'tour-current': tourPage === 'settings' }"
          data-page="settings"
          aria-label="設定"
          @click="go('settings')"
        >
          <span class="nav-icon"><AppIcon name="settings" /></span>
          <span class="nav-label">設定</span>
        </button>
      </div>
    </nav>

    <div class="sidebar-spacer"></div>
    <div class="sb-dock">
    <div class="sidebar-account">
      <button class="profile-btn" type="button" :aria-expanded="String(overlays.profile)" @click.stop="overlays.profile = !overlays.profile">
        <span class="avatar" aria-hidden="true">
          <svg viewBox="0 0 40 40" fill="none">
            <circle cx="20" cy="15" r="6" fill="currentColor" />
            <path d="M8.5 32c.7-6 5.1-9.5 11.5-9.5s10.8 3.5 11.5 9.5" fill="currentColor" />
          </svg>
        </span>
        <span class="profile-copy"><strong>{{ account.user?.username || settings.nickname }}</strong></span>
        <span class="chevron">⌄</span>
      </button>
    </div>
    <button
      class="assistant-dock"
      type="button"
      aria-label="開啟 PINWISE 助手：自由對話與股票知識問答"
      title="自由對話與股票知識問答"
      @click="openAssistant"
    >
      <img :src="mark" alt="" />
      <span class="assistant-dock-copy"><strong>PINWISE 助手</strong><small>即時問答</small></span>
    </button>
    </div>
    <div class="sidebar-footer">
      <p>小小的投資知識<br />也能累積大大的未來</p>
      <span>Better Insights<br />A Brighter Tomorrow</span>
      <small>PINWISE V7.0 R2 · Vue</small>
    </div>
  </aside>
</template>

<style scoped>
/* 側邊欄分三區：底色為白金大理石，上方品牌與下方帳號、助手各自用白金色加金色細框；中間的頁面清單自成一框，捲軸只出現在框內。 */
.sidebar{background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='340' height='1000'%3E%3Cfilter id='m' x='0' y='0' width='100%25' height='100%25'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.005 .014' numOctaves='5' seed='11'/%3E%3CfeColorMatrix values='0 0 0 0 .76 0 0 0 0 .58 0 0 0 0 .2 1.8 0 0 0 -.4'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='table' tableValues='0 0 0 0 0 .85 0 0 0 0 0'/%3E%3C/feComponentTransfer%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3C/svg%3E"),url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='340' height='1000'%3E%3Cfilter id='m' x='0' y='0' width='100%25' height='100%25'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.009 .02' numOctaves='5' seed='37'/%3E%3CfeColorMatrix values='0 0 0 0 .62 0 0 0 0 .6 0 0 0 0 .58 1.8 0 0 0 -.4'/%3E%3CfeComponentTransfer%3E%3CfeFuncA type='table' tableValues='0 0 0 0 0 .5 0 0 0 0 0'/%3E%3C/feComponentTransfer%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3C/svg%3E"),linear-gradient(160deg,#FFFDF6 0%,#F7EFDC 45%,#FCF7EA 75%,#F3E8CF 100%)!important;background-size:cover,cover,auto!important;background-repeat:no-repeat!important}
.sidebar > .brand,.sb-dock{--sb-panel:linear-gradient(125deg,#FFFFFF 0%,#EEF0F4 100%);border:1.5px solid #C9A25A;box-shadow:0 8px 20px rgba(150,115,50,.24);background:var(--sb-panel);border-radius:16px}
.sidebar > .brand{position:relative;flex:none;padding:10px 12px!important}
.sidebar-nav{flex:1 1 auto;min-height:0;margin:8px 0;padding:8px 2px 8px 6px!important;border:1.5px solid #9C8CEB;border-radius:16px;background:rgba(255,255,255,.84);overflow-y:auto;scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:transparent transparent}
.sidebar-nav.is-scrolling{scrollbar-color:#9DB4E6 transparent}
.sidebar-nav::-webkit-scrollbar{width:6px}
.sidebar-nav::-webkit-scrollbar-track{margin:12px 0;background:transparent}
.sidebar-nav::-webkit-scrollbar-thumb{background:transparent;border-radius:99px}
.sidebar-nav.is-scrolling::-webkit-scrollbar-thumb{background:#9DB4E6}
.sb-dock{position:relative;flex:none;display:grid;gap:8px;padding:0;background:none;border:0;box-shadow:none}
.sb-dock .sidebar-account,.sb-dock .assistant-dock{margin:0!important}
.sb-dock .sidebar-account{padding:0!important;border-top:0!important}
.sb-dock .profile-btn{background:linear-gradient(125deg,#FFFFFF 0%,#EEF0F4 100%)!important;border:1.5px solid #C9A25A!important}
/* 頭像中心與名字起點，對齊下方助手 Logo 與文字（淺色、深色共用） */
.sb-dock .profile-btn{padding-left:16.5px!important;gap:15.5px!important}
.sb-dock .profile-btn strong,.sb-dock .profile-btn .chevron{color:#10284F!important}
.sb-dock .profile-btn .avatar{background:#F3E2BC!important;color:#7A5A22!important}
.sb-dock .assistant-dock{background:linear-gradient(125deg,#FFFFFF 0%,#EEF0F4 100%)!important;border:1.5px solid #C9A25A!important}
.sb-dock .assistant-dock img{align-self:center}
.sb-dock .assistant-dock strong{color:#10284F!important}
.sb-dock .assistant-dock small{color:#3F4E6B!important}
/* 目前頁面只用底色標示；鍵盤焦點框畫在按鈕內側，避免被清單框裁掉 */
.sidebar .sidebar-nav .nav-item.active{box-shadow:none!important;outline:2px solid #86AEF0;outline-offset:-2px}
body .sidebar .sidebar-nav .nav-item:focus-visible{outline:2px solid #78a7ea!important;outline-offset:-2px!important}
.sidebar > .brand strong{color:#10284F}
:global(body[data-theme="dark"] .sb-dock .profile-btn),:global(body[data-theme="dark"] .sb-dock .assistant-dock){background:linear-gradient(125deg,#16243F 0%,#22304F 100%)!important;border:1.5px solid #C9A25A!important}
:global(body[data-theme="dark"] .sb-dock .profile-btn .avatar){background:#F3E2BC!important}
:global(body[data-theme="dark"] .sb-dock .profile-btn strong),:global(body[data-theme="dark"] .sb-dock .profile-btn .chevron){color:#F2F6FF!important}
:global(body[data-theme="dark"] .sb-dock .assistant-dock strong){color:#F2F6FF!important}
:global(body[data-theme="dark"] .sb-dock .assistant-dock small){color:#DCE6F7!important}
:global(body[data-theme="dark"] .sidebar > .brand strong){color:#F2F6FF!important}
:global(body[data-theme="dark"] .sidebar){background:linear-gradient(160deg,#17243C 0%,#1E2540 100%)!important}
:global(body[data-theme="dark"] .sidebar > .brand),:global(body[data-theme="dark"] .sb-dock){--sb-panel:linear-gradient(125deg,#16243F 0%,#22304F 100%)}
:global(body[data-theme="dark"] .sidebar-nav){border-color:#33507A;background:rgba(255,255,255,.03)}
</style>
