import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发时(npm run dev)把接口和 WebSocket 转给本地的 Python 服务
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
