import http from 'node:http';
import https from 'node:https';

const QWEN_HOST = 'chat.qwen.ai';
const KOLIBRI_HOST = '127.0.0.1';
const KOLIBRI_PORT = 8002;
const PORT = Number(process.env.PORT || 8082);
const JWT = process.env.QWEN_JWT || '';

if (!JWT) {
  console.error('⚠️  QWEN_JWT не задан');
  process.exit(1);
}

// Чат-запросы идут на Qwen, остальное — на kolibri backend
const QWEN_CHAT_RE = /\/v1\/(chat\/completions|chat\/stream|completions)([/?]|$)/i;

const CORS = (req) => ({
  'access-control-allow-origin': req.headers.origin || '*',
  'access-control-allow-headers':
    req.headers['access-control-request-headers'] ||
    'authorization,content-type,accept',
  'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
  'access-control-max-age': '86400',
});

const HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
  'host',
  'origin',
  'referer',
  'accept-encoding',
]);

const fwdHeaders = (req, targetHost, addJwt = false) => {
  const out = {};
  for (const [key, value] of Object.entries(req.headers)) {
    const lk = key.toLowerCase();
    if (HOP.has(lk) || lk === 'authorization') continue;
    out[key] = value;
  }
  out['host'] = targetHost;
  if (addJwt) out['authorization'] = `Bearer ${JWT}`;
  out['accept-encoding'] = 'identity';
  return out;
};

const server = http.createServer((req, res) => {
  const cors = CORS(req);
  if (req.method === 'OPTIONS') {
    res.writeHead(204, cors);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host}`);
  const path = url.pathname;

  // Роутинг: чат → Qwen, остальное → kolibri
  const isQwen = QWEN_CHAT_RE.test(path);
  const targetHost = isQwen ? QWEN_HOST : KOLIBRI_HOST;
  const targetPort = isQwen ? 443 : KOLIBRI_PORT;
  const useHttps = isQwen;

  const headers = fwdHeaders(req, targetHost, isQwen);

  const doForward = (body) => {
    if (body !== undefined) {
      headers['content-length'] = Buffer.byteLength(body);
    }
    const proxyReq = (useHttps ? https : http).request(
      {
        method: req.method,
        hostname: targetHost,
        port: targetPort,
        path: url.pathname + url.search,
        headers,
      },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode || 502, {
          ...proxyRes.headers,
          ...cors,
        });
        proxyRes.pipe(res, { end: true });
      },
    );
    proxyReq.on('error', (err) => {
      console.error(`[proxy] ${targetHost}${path}:`, err.message);
      if (!res.headersSent) res.writeHead(502, cors);
      res.end(`proxy error: ${err.message}`);
    });
    if (body !== undefined) proxyReq.end(body);
    else req.pipe(proxyReq, { end: true });
  };

  if (isQwen && ['POST', 'PUT', 'PATCH'].includes(req.method)) {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      let body = Buffer.concat(chunks);
      try {
        const json = JSON.parse(body.toString('utf8'));
        if (json && typeof json === 'object') {
          for (const key of [
            'chat_id', 'chatId',
            'session_id', 'sessionId',
            'parent_id', 'parentId',
            'conversation_id', 'conversationId',
          ]) {
            delete json[key];
          }
          body = Buffer.from(JSON.stringify(json));
        }
      } catch {
        // не JSON
      }
      console.log(`→ Qwen ${req.method} ${path}`);
      doForward(body);
    });
    return;
  }

  console.log(`→ ${isQwen ? 'Qwen' : 'kolibri'} ${req.method} ${path}`);
  doForward();
});

server.listen(PORT, () => {
  console.log(`✅ Universal proxy on :${PORT}`);
  console.log(`   Chat → https://${QWEN_HOST}`);
  console.log(`   Auth/Threads/Models/Billing → http://${KOLIBRI_HOST}:${KOLIBRI_PORT}`);
  console.log(`   JWT: ${JWT.slice(0, 8)}…${JWT.slice(-4)}`);
});
