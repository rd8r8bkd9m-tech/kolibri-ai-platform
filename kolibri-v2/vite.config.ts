import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  // BrowserRouter deep links (for example /chat/:id and /developers) must
  // always load the same root-scoped hashed assets after a hard reload.
  base: '/',
  plugins: [react()],
  server: {
    port: 3000,
    allowedHosts: ['kolibriai.ru', 'www.kolibriai.ru'],
    proxy: {
      '/api': {
        target: process.env.KOLIBRI_API_PROXY ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
