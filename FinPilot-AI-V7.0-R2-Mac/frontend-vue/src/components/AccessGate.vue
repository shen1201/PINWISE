<script setup>
// 線上預覽 / 競賽展示的存取入口（對應舊版 js/preview-access.js 的 ensureAccess 畫面）。
// 取得存取權後發出 ready，由 main.js 卸下入口並掛載主程式。
import { computed, onMounted, ref } from 'vue'
import mark from '@root/assets/pinwise-mark.png'
import { config, accessMode, configError, currentToken, verifyToken, issueSession, clearAccess } from '../api/runtime.js'

const emit = defineEmits(['ready'])

// form：輸入權杖或邀請碼；connect：自動建立訪客工作階段，失敗時顯示重新連線按鈕。
const kind = accessMode === 'demo-session' ? (config.inviteRequired ? 'invite' : 'auto') : 'token'
const copy = {
  token: {
    title: 'PINWISE 隔離預覽',
    text: '請輸入分享者提供的預覽權杖。權杖只保存在這個分頁，不會寫入網址或專案檔案。',
    label: '預覽權杖',
    button: '進入預覽',
  },
  invite: {
    title: 'PINWISE 測試入口',
    text: '請輸入分享者提供的測試邀請碼。這不是 Gemini API Key；工作階段會自動到期。',
    label: '測試邀請碼',
    button: '進入測試',
  },
  auto: {
    title: 'PINWISE 競賽展示',
    text: '正在建立隔離的短期訪客工作階段，不需要輸入權杖。',
    label: '',
    button: '重新連線',
  },
}[kind]

const value = ref('')
const error = ref(configError)
const busy = ref(!configError)
const input = ref(null)
const showInput = computed(() => kind !== 'auto')

// 已保存的權杖先驗證；失效就清掉，回到輸入或重新申請。
async function reuseToken() {
  if (!currentToken()) return false
  try {
    await verifyToken(currentToken())
    return true
  } catch {
    clearAccess()
    return false
  }
}

async function connect() {
  busy.value = true
  error.value = '正在連接安全後端…'
  try {
    if (!(await reuseToken())) await issueSession()
    emit('ready')
  } catch (exc) {
    error.value = exc.message
    busy.value = false
  }
}

async function submit() {
  const entered = value.value.trim()
  if (!entered) return
  busy.value = true
  error.value = kind === 'token' ? '正在驗證後端存取權…' : ''
  try {
    if (kind === 'token') await verifyToken(entered)
    else await issueSession(entered)
    value.value = ''
    emit('ready')
  } catch (exc) {
    clearAccess()
    error.value = exc.message
    busy.value = false
  }
}

onMounted(async () => {
  if (configError) return
  if (kind === 'auto') return connect()
  if (await reuseToken()) return emit('ready')
  error.value = ''
  busy.value = false
  input.value?.focus()
})
</script>

<template>
  <section class="preview-access-gate" role="dialog" aria-modal="true" aria-labelledby="previewAccessTitle">
    <form class="preview-access-card" @submit.prevent="kind === 'auto' ? connect() : submit()">
      <img :src="mark" alt="" />
      <h1 id="previewAccessTitle">{{ copy.title }}</h1>
      <p>{{ copy.text }}</p>
      <template v-if="showInput">
        <label for="previewAccessToken">{{ copy.label }}</label>
        <input
          id="previewAccessToken"
          ref="input"
          v-model="value"
          type="password"
          autocomplete="off"
          required
          :minlength="kind === 'token' ? 16 : undefined"
        />
      </template>
      <button class="primary-button" type="submit" :disabled="busy || Boolean(configError)">{{ copy.button }}</button>
      <small id="previewAccessError" role="alert">{{ error }}</small>
    </form>
  </section>
</template>
