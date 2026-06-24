import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

const apiTarget = process.env.KOLIBRI_BACKEND_URL || process.env.VITE_KOLIBRI_BACKEND_URL || "http://127.0.0.1:8000"

function configureOfflineFallback(proxy) {
  proxy.on("error", (error, _request, response) => {
    if (!response || response.headersSent || typeof response.writeHead !== "function") return
    response.writeHead(502, { "Content-Type": "application/json" })
    response.end(JSON.stringify({
      code: "backend_offline",
      message: "Kolibri backend is offline in local dev mode",
      target: apiTarget,
      error: error.code || error.message,
    }))
  })
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5177,
    strictPort: true,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
        configure: configureOfflineFallback,
      },
      "/v1": {
        target: apiTarget,
        changeOrigin: true,
        configure: configureOfflineFallback,
      },
      "/ws": {
        target: apiTarget,
        changeOrigin: true,
        ws: true,
        configure: configureOfflineFallback,
      },
    },
  },
})
