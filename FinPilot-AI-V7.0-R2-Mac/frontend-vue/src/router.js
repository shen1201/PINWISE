import { createRouter, createWebHashHistory } from 'vue-router'
import HomePage from './pages/HomePage.vue'
import ResearchPage from './pages/ResearchPage.vue'
import PickerPage from './pages/PickerPage.vue'
import CandidatesPage from './pages/CandidatesPage.vue'
import EsgPage from './pages/EsgPage.vue'
import ComparePage from './pages/ComparePage.vue'
import TrackingPage from './pages/TrackingPage.vue'
import FootprintPage from './pages/FootprintPage.vue'
import MarketPage from './pages/MarketPage.vue'
import EvidencePage from './pages/EvidencePage.vue'
import LearningPage from './pages/LearningPage.vue'
import SettingsPage from './pages/SettingsPage.vue'

// 與舊版相同使用 #/頁面 網址；設定頁的分頁放在 #/settings/<分頁>。
export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/home' },
    { path: '/home', name: 'home', component: HomePage },
    { path: '/research', name: 'research', component: ResearchPage },
    { path: '/picker', name: 'picker', component: PickerPage },
    { path: '/candidates', name: 'candidates', component: CandidatesPage },
    { path: '/compare', name: 'compare', component: ComparePage },
    { path: '/tracking', name: 'tracking', component: TrackingPage },
    // 路由名稱沿用 scorecard：共用版面樣式與已保存的側邊欄設定都以這個名稱對應。
    { path: '/scorecard', alias: '/footprint', name: 'scorecard', component: FootprintPage },
    { path: '/market', name: 'market', component: MarketPage },
    { path: '/etf', redirect: '/market' },
    { path: '/evidence', name: 'evidence', component: EvidencePage },
    { path: '/learning', name: 'learning', component: LearningPage },
    { path: '/esg', name: 'esg', component: EsgPage },
    { path: '/settings/:tab?', name: 'settings', component: SettingsPage },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})
