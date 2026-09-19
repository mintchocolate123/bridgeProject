import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 開發時 /api 轉給本機的平台,前端和平台看起來是同一個網址,不會有 CORS 問題。
// 正式部署時 build 出來的 dist/ 直接由平台提供,也是同一個網址。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
