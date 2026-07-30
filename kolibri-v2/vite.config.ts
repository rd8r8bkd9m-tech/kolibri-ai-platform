import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const publicBase = process.env.KOLIBRI_PUBLIC_BASE_PATH ?? '/'
if (publicBase !== '/' && !/^\/__canary\/[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\/$/.test(publicBase)) {
  throw new Error('KOLIBRI_PUBLIC_BASE_PATH must be / or /__canary/<release_id>/')
}

// https://vite.dev/config/
export default defineConfig({
  // BrowserRouter deep links (for example /chat/:id and /developers) must
  // always load the same root-scoped hashed assets after a hard reload.
  base: publicBase,
  plugins: [react()],
  server: {
    port: 3000,
    allowedHosts: [
      'kolibriai.ru',
      'www.kolibriai.ru',
      'localhost',
      '127.0.0.1',
      ...(process.env.KOLIBRI_DEV_ALLOWED_HOST ? [process.env.KOLIBRI_DEV_ALLOWED_HOST] : []),
    ],
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
