import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const API_PROXY = process.env.VITE_API_PROXY || 'http://127.0.0.1:8000'
const WS_PROXY = API_PROXY.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')

export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_ACTIONS ? '/kolibri-ai-platform/' : '/',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': API_PROXY,
      '/v1': API_PROXY,
      '/ws': {
        target: WS_PROXY,
        ws: true,
      },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          minSize: 20_000,
          groups: [
            { name: 'react', test: /node_modules\/(react|react-dom|scheduler)\// },
            { name: 'motion', test: /node_modules\/(framer-motion|motion-dom|motion-utils)\// },
            { name: 'markdown', test: /node_modules\/(react-markdown|remark-|rehype-|unified|micromark|mdast-|unist-)\// },
            { name: 'icons', test: /node_modules\/lucide-react\// },
          ],
        },
      },
    },
  },
})
