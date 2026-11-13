import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import favicon from '@root/assets/pinwise-favicon.png'

// 先沿用舊版五層 CSS（順序不可更動，見 css/README.md），畫面才會一致。
import '@root/css/base.css'
import '@root/css/layout.css'
import '@root/css/theme.css'
import '@root/css/components.css'
import '@root/css/pages.css'

import AccessGate from './components/AccessGate.vue'
import { needsAccessGate } from './api/runtime.js'

document.getElementById('favicon').href = favicon

const mountApp = () => createApp(App).use(router).mount('#app')

// 線上預覽 / 訪客模式要先取得後端存取權，主程式才掛載（主程式一啟動就會呼叫後端）。
if (needsAccessGate()) {
  const host = document.body.appendChild(document.createElement('div'))
  const gate = createApp(AccessGate, {
    onReady() {
      gate.unmount()
      host.remove()
      mountApp()
    },
  })
  gate.mount(host)
} else {
  mountApp()
}
