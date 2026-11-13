import { reactive } from 'vue'
import { api } from '@/api/client.js'
import { settings } from './ui.js'

// 帳號登入（對應舊版 js/api.js 的 Account）。需要後端設定 DATABASE_URL；
// token 存在與舊版相同的 localStorage 鍵，由 api/client.js 帶入 X-FinPilot-Session。
const TOKEN_KEY = 'finpilot_account_session'

export const account = reactive({ enabled: false, user: null, loaded: false })

const setToken = (value) => {
  try {
    value ? localStorage.setItem(TOKEN_KEY, value) : localStorage.removeItem(TOKEN_KEY)
  } catch {}
}
const hasToken = () => {
  try {
    return Boolean(localStorage.getItem(TOKEN_KEY))
  } catch {
    return false
  }
}

export async function loadAccount() {
  try {
    const data = await api.accountMe()
    account.enabled = Boolean(data.enabled)
    account.user = data.user || null
  } catch (error) {
    console.warn('[PINWISE] 無法讀取帳號狀態', error)
  } finally {
    account.loaded = true
  }
  // 登入已過期：清掉 token，以訪客身分繼續。
  if (hasToken() && !account.user) setToken('')
}

export async function submitAccount(kind, username, password) {
  const data = await api.accountSubmit(kind, username, password)
  setToken(data.token)
  account.user = data.user
  if (kind === 'register' && settings.nickname === '訪客投資者') settings.nickname = data.user.username
  location.reload()
}

export async function logout() {
  try {
    await api.accountLogout()
  } catch (error) {
    console.warn('[PINWISE] 登出請求失敗', error)
  }
  setToken('')
  location.reload()
}
