import assert from 'node:assert/strict'

import viteConfig, {
  createProxyRoutes,
  resolveApiProxy,
  resolveCanonicalApiProxy,
} from '../vite.config.js'

assert.equal(resolveApiProxy(undefined), null)
assert.equal(resolveApiProxy('  https://example.test/  '), 'https://example.test')
assert.equal(resolveApiProxy('http://127.0.0.1:9010'), 'http://127.0.0.1:9010')
assert.throws(() => resolveApiProxy('ftp://example.test'), /HTTP or HTTPS/)
assert.throws(() => resolveApiProxy('https://user:secret@example.test'), /credential-free origin/)
assert.throws(() => resolveApiProxy('https://example.test/legacy'), /credential-free origin/)
assert.throws(() => resolveApiProxy('https://example.test?token=secret'), /credential-free origin/)
assert.equal(resolveCanonicalApiProxy(' KolibriAI.ru\n'), 'https://kolibriai.ru')
assert.equal(resolveCanonicalApiProxy('localhost'), null)
assert.equal(resolveCanonicalApiProxy('example.test/path'), null)

const routes = createProxyRoutes('https://example.test')
assert.deepEqual(Object.keys(routes), ['/api', '/v1', '/ws'])
assert.equal(routes['/api'].target, 'https://example.test')
assert.equal(routes['/v1'].target, 'https://example.test')
assert.equal(routes['/ws'].target, 'wss://example.test')
assert.equal(routes['/v1'].changeOrigin, true)
assert.equal(routes['/v1'].secure, true)
assert.equal(routes['/v1'].headers.Origin, 'https://example.test')
assert.equal(routes['/ws'].ws, true)

const previous = process.env.VITE_API_PROXY
delete process.env.VITE_API_PROXY
const unconfigured = viteConfig({ command: 'serve', mode: 'development' })
assert.equal(unconfigured.server.proxy['/v1'].target, 'https://kolibriai.ru')
assert.equal(unconfigured.preview.proxy['/v1'].target, 'https://kolibriai.ru')
assert.equal(unconfigured.server.host, '127.0.0.1')
assert.equal(unconfigured.server.port, 5174)
assert.equal(unconfigured.server.strictPort, true)
process.env.VITE_API_PROXY = 'https://example.test'
const configured = viteConfig({ command: 'serve', mode: 'development' })
assert.equal(configured.server.proxy['/v1'].target, 'https://example.test')
if (previous === undefined) delete process.env.VITE_API_PROXY
else process.env.VITE_API_PROXY = previous

console.log('Kolibri explicit local API proxy contract passed')
