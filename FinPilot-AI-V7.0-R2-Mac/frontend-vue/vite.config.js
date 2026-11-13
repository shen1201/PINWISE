import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 舊前端的 css/ 與 assets/ 放在上一層，直接共用，不複製。
const projectRoot = fileURLToPath(new URL('..', import.meta.url))
const backend = process.env.FINPILOT_BACKEND_URL || 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@root': projectRoot,
    },
  },
  server: {
    port: 5173,
    fs: { allow: [projectRoot] },
    // 開發時 /api 與 /runtime-config.js 轉給既有 FastAPI 後端。
    proxy: {
      '/api': { target: backend, changeOrigin: false },
      '/runtime-config.js': { target: backend, changeOrigin: false },
    },
  },
})
