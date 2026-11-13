<script setup>
import { useRouter } from 'vue-router'
import { overlays } from '@/stores/overlays.js'
import { account, logout } from '@/stores/account.js'
import { toast } from '@/stores/ui.js'

// 帳戶與個人設定選單（對應舊版 renderProfileDropdown）。
const router = useRouter()

function action(key) {
  overlays.profile = false
  if (key === 'logout') {
    toast('正在登出…')
    logout()
  } else if (key === 'login' || key === 'create') overlays.account = key
  else router.push(`/settings/${key}`)
}
</script>

<template>
  <div class="profile-backdrop" :hidden="!overlays.profile" @click="overlays.profile = false"></div>
  <section class="profile-dropdown" role="dialog" aria-modal="true" aria-labelledby="profileDialogTitle" :hidden="!overlays.profile">
    <header class="profile-dialog-head">
      <div><span class="eyebrow">PINWISE 帳戶</span><h2 id="profileDialogTitle">帳戶與個人設定</h2></div>
      <button class="icon-button" type="button" aria-label="關閉帳戶視窗" @click="overlays.profile = false">✕</button>
    </header>
    <div class="profile-dialog-body">
      <div class="account-status">
        <template v-if="account.user"><strong>{{ account.user.username }}</strong><small>已登入 · 帳號由後端資料庫管理</small></template>
        <template v-else><strong>訪客投資者</strong><small>訪客模式 · 資料保存在此瀏覽器</small></template>
      </div>
      <div class="separator"></div>
      <template v-if="!account.user">
        <button type="button" @click="action('create')">建立帳戶 <span>→</span></button>
        <button type="button" @click="action('login')">登入 <span>→</span></button>
      </template>
      <button type="button" @click="action('preferences')">個人化偏好 <span>→</span></button>
      <button type="button" @click="action('notifications')">通知設定 <span>→</span></button>
      <button type="button" @click="action('appearance')">設定 <span>→</span></button>
      <button v-if="account.user" type="button" @click="action('logout')">登出 <span>→</span></button>
    </div>
  </section>
</template>
