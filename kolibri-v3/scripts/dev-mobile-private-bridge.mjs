#!/usr/bin/env node

// Expo's web server listens on 4104. This bridge is intentionally bound to a
// non-public loopback alias, so `localhost:4103` can never become a competing
// browser origin. Only the 3103 gateway reaches it.
import http from "node:http";
import net from "node:net";
import { existsSync, unlinkSync } from "node:fs";
import path from "node:path";

const socketPath = process.env.KOLIBRI_V3_MOBILE_INTERNAL_SOCKET || path.resolve("var/mobile-web.sock");
const upstreamHost = process.env.KOLIBRI_V3_MOBILE_UPSTREAM_HOST || "127.0.0.1";
const upstreamPort = Number(process.env.KOLIBRI_V3_MOBILE_UPSTREAM_PORT || "4104");
function headers(request) { return { ...request.headers, host: `${upstreamHost}:${upstreamPort}` }; }
function proxy(request, response) {
  const upstream = http.request({ hostname: upstreamHost, port: upstreamPort, path: request.url, method: request.method, headers: headers(request) }, (upstreamResponse) => {
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.statusMessage, upstreamResponse.headers);
    upstreamResponse.pipe(response);
  });
  upstream.once("error", () => { if (!response.headersSent) response.writeHead(502).end(); else response.destroy(); });
  request.pipe(upstream);
}
function upgrade(request, socket, head) {
  const upstream = net.connect(upstreamPort, upstreamHost, () => {
    const serialized = Object.entries(headers(request)).flatMap(([name, value]) => Array.isArray(value) ? value.map((entry) => `${name}: ${entry}`) : value == null ? [] : [`${name}: ${value}`]).join("\r\n");
    upstream.write(`${request.method} ${request.url} HTTP/1.1\r\n${serialized}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  upstream.once("error", () => socket.destroy());
  socket.once("error", () => upstream.destroy());
}
const server = http.createServer(proxy);
server.on("upgrade", upgrade);
if (existsSync(socketPath)) unlinkSync(socketPath);
server.listen(socketPath, () => console.log(`[dev:mobile-bridge] private ${socketPath} -> ${upstreamHost}:${upstreamPort}`));
function shutdown(signal) { server.close(() => { if (existsSync(socketPath)) unlinkSync(socketPath); process.exit(signal === "SIGINT" ? 130 : 0); }); server.closeAllConnections?.(); }
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
