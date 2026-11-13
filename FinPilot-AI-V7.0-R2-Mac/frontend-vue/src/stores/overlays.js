import { reactive } from 'vue'

// 全域彈窗與抽屜的開關狀態；各元件掛在 App.vue，任何頁面都能開啟。
export const overlays = reactive({
  stockDetail: null, // { code, title }
  stockSearch: false,
  notifications: false,
  profile: false,
  account: null, // 'login' | 'create'
  help: null, // { tab: 'faq' | 'glossary', term?, article? }
  featureGuide: false,
  onboarding: null, // 'welcome' | 'preferences' | 'tourOffer'
})

export const openStockDetail = (code, title = '標的詳情') => (overlays.stockDetail = { code, title })
export const openHelp = (tab = 'faq') => (overlays.help = { tab })
export const openTerm = (term) => (overlays.help = { tab: 'glossary', term })
export const openArticle = (article) => (overlays.help = { tab: 'article', article })
