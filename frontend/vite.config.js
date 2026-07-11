import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'node:fs'
import path from 'path'
import { fileURLToPath } from 'node:url'

const configDirectory = path.dirname(fileURLToPath(import.meta.url))

export function resolveApiProxy(value = process.env.VITE_API_PROXY) {
  const configured = String(value || '').trim()
  if (!configured) return null

  let target
  try {
    target = new URL(configured)
  } catch {
    throw new Error('VITE_API_PROXY must be an absolute HTTP(S) origin')
  }
  if (!['http:', 'https:'].includes(target.protocol)) {
    throw new Error('VITE_API_PROXY must use HTTP or HTTPS')
  }
  if (
    target.username
    || target.password
    || target.search
    || target.hash
    || !['', '/'].includes(target.pathname)
  ) {
    throw new Error('VITE_API_PROXY must be a credential-free origin without path, query, or fragment')
  }
  return target.origin
}

export function resolveCanonicalApiProxy(cname) {
  const hostname = String(cname || '').trim().toLowerCase()
  if (!/^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/.test(hostname)) {
    return null
  }
  return resolveApiProxy(`https://${hostname}`)
}

function configuredApiProxy() {
  const explicit = resolveApiProxy()
  if (explicit) return explicit
  try {
    return resolveCanonicalApiProxy(
      readFileSync(new URL('./CNAME', import.meta.url), 'utf8'),
    )
  } catch {
    return null
  }
}

export function createProxyRoutes(apiProxy) {
  if (!apiProxy) return undefined
  const wsProxy = apiProxy.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')
  const httpRoute = {
    target: apiProxy,
    changeOrigin: true,
    secure: true,
    // The loopback Vite server is the browser's same-origin facade. Bind the
    // upstream public session to the reviewed API origin, never to a stale
    // localhost origin that production may not allow.
    headers: { Origin: apiProxy },
  }
  return {
    '/api': { ...httpRoute },
    '/v1': { ...httpRoute },
    '/ws': {
      target: wsProxy,
      changeOrigin: true,
      secure: true,
      headers: { Origin: apiProxy },
      ws: true,
    },
  }
}

export default defineConfig(() => {
  const proxy = createProxyRoutes(configuredApiProxy())
  return {
    plugins: [react()],
    base: process.env.GITHUB_ACTIONS ? '/kolibri-ai-platform/' : '/',
    resolve: {
      alias: {
        '@': path.resolve(configDirectory, './src'),
      },
    },
    server: {
      host: '127.0.0.1',
      port: 5174,
      strictPort: true,
      ...(proxy ? { proxy } : {}),
    },
    preview: {
      host: '127.0.0.1',
      strictPort: true,
      ...(proxy ? { proxy } : {}),
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
  }
})
