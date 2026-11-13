<script setup>
import { ref, computed, watch } from 'vue'
import AppModal from '@/components/AppModal.vue'
import { overlays } from '@/stores/overlays.js'
import { account, submitAccount } from '@/stores/account.js'
import { toast } from '@/stores/ui.js'
import mark from '@root/assets/pinwise-mark.png'

// 登入／建立帳戶（對應舊版 showAccountUnavailable 與 accountFormHtml）。
// 後端未設定資料庫時，只顯示預定的第三方登入方式與訪客入口。
const kind = computed(() => overlays.account)
const login = computed(() => kind.value === 'login')
const title = computed(() => (login.value ? '登入 PINWISE' : '建立 PINWISE 帳戶'))

const username = ref('')
const password = ref('')
const confirm = ref('')
const error = ref('')
const submitting = ref(false)

watch(kind, () => {
  username.value = password.value = confirm.value = error.value = ''
  submitting.value = false
})

async function submit() {
  const name = username.value.trim()
  if (!/^[A-Za-z0-9_.-]{3,32}$/.test(name)) return (error.value = '帳號需為 3–32 個英文字母、數字或 _ . -')
  if (password.value.length < 8) return (error.value = '密碼至少需要 8 個字元')
  if (!login.value && password.value !== confirm.value) return (error.value = '兩次輸入的密碼不一致')
  error.value = ''
  submitting.value = true
  try {
    await submitAccount(login.value ? 'login' : 'register', name, password.value)
  } catch (failure) {
    error.value = failure.message || '無法連線後端，請稍後再試'
    submitting.value = false
  }
}

const close = () => (overlays.account = null)
const switchKind = () => (overlays.account = login.value ? 'create' : 'login')
</script>

<template>
  <AppModal :open="Boolean(kind)" :title="title" modal-class="login-design-modal" @close="close">
    <div class="login-design">
      <aside class="login-visual" aria-hidden="true">
        <div class="login-visual-shine"></div>
        <div class="login-visual-brand"><img class="brand-logo" :src="mark" alt="" /><strong>PINWISE</strong></div>
        <p>讓 AI 成為<br />你研究投資的最佳夥伴</p>
      </aside>
      <div class="login-main">
        <button type="button" class="login-close" aria-label="關閉登入視窗" @click="close">×</button>
        <div class="login-main-inner">
          <h2>{{ title }}</h2>
          <p class="login-subtitle">保存研究紀錄與個人偏好</p>

          <form v-if="account.enabled" class="account-form" novalidate @submit.prevent="submit">
            <div class="field"><label for="accountUsername">帳號</label><input id="accountUsername" v-model="username" autocomplete="username" maxlength="32" spellcheck="false" /></div>
            <div class="field"><label for="accountPassword">密碼</label><input id="accountPassword" v-model="password" type="password" :autocomplete="login ? 'current-password' : 'new-password'" maxlength="128" /></div>
            <template v-if="!login">
              <div class="field"><label for="accountPasswordConfirm">再次輸入密碼</label><input id="accountPasswordConfirm" v-model="confirm" type="password" autocomplete="new-password" maxlength="128" /></div>
              <p class="account-form-hint">帳號 3–32 字（英文字母、數字或 _ . -），密碼至少 8 字。</p>
            </template>
            <p class="account-form-error" role="alert">{{ error }}</p>
            <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? (login ? '登入中…' : '建立中…') : login ? '登入' : '建立帳戶' }}</button>
            <button type="button" class="text-button account-form-switch" @click="switchKind">{{ login ? '還沒有帳號？建立帳戶' : '已有帳號？登入' }}</button>
          </form>
          <div v-else class="login-provider-list" aria-label="預定登入方式">
            <button v-for="[provider, markText, cls] in [['Google', 'G', 'google'], ['Apple', '', 'apple'], ['Facebook', 'f', 'facebook']]" :key="provider" class="login-provider" type="button" @click="toast(`${provider} 登入尚未開放，可先以訪客身分使用`)">
              <span class="login-provider-mark" :class="cls" aria-hidden="true">{{ markText }}</span><strong>使用 {{ provider }} 繼續</strong>
            </button>
          </div>

          <div class="login-divider"><span>或</span></div>
          <button type="button" class="login-guest" @click="close">繼續以訪客身分使用 <span aria-hidden="true">→</span></button>
          <p class="login-footnote">
            {{ account.enabled ? '帳號資料存放在 PINWISE 後端資料庫，密碼僅以雜湊保存。' : '登入服務需要後端設定 PostgreSQL（DATABASE_URL）；目前可先以訪客模式使用。' }}
          </p>
        </div>
      </div>
    </div>
  </AppModal>
</template>
