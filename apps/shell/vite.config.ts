import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.KOLIBRI_API_URL || 'http://127.0.0.1:8191'
const proxy = {
  '/v1': { target: apiTarget, changeOrigin: true, ws: true },
  '/api': { target: apiTarget, changeOrigin: true },
}

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom' },
  build: { target: 'es2022', sourcemap: true },
  server: { proxy },
  preview: { proxy, allowedHosts: ['kolibri.test'] },
})
