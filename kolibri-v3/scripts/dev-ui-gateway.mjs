#!/usr/bin/env node

/**
 * The one public browser origin for Kolibri V3.
 *
 * Desktop Next and Expo Web are separate internal runtimes.  This gateway is
 * their only browser-facing entry point: a mobile UA or the explicit
 * `client=mobile` handoff goes to Expo, all other requests go to Next.
 */

import http from "node:http";
import net from "node:net";

const listenHost = process.env.KOLIBRI_V3_UI_HOST || "127.0.0.1";
const listenPort = Number(process.env.KOLIBRI_V3_UI_PORT || "3103");
const desktopPort = Number(process.env.KOLIBRI_V3_DESKTOP_INTERNAL_PORT || "3104");
const mobileSocket = process.env.KOLIBRI_V3_MOBILE_INTERNAL_SOCKET || "";
const mobilePort = Number(process.env.KOLIBRI_V3_MOBILE_INTERNAL_PORT || "4104");
const backendPort = Number(process.env.KOLIBRI_V3_BACKEND_INTERNAL_PORT || "8002");
const mobileUserAgent = /(Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile)/i;

function requestUrl(request) {
  return new URL(request.url || "/", `http://${request.headers.host || listenHost}`);
}

function cookieClient(request) {
  const match = (request.headers.cookie || "").match(/(?:^|;\s*)kolibri_ui_client=(mobile|desktop)(?:;|$)/);
  return match?.[1] || null;
}

function isMobileRequest(request, url = requestUrl(request)) {
  // These are product infrastructure paths, not mobile-screen assets. They
  // must never follow the Expo affinity cookie.
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/_next/")) return false;
  const explicitClient = url.searchParams.get("client");
  // The responsive desktop shell writes this value before reloading. It must
  // win even in a desktop browser with a narrow viewport.
  if (explicitClient === "mobile") return true;
  if (explicitClient === "desktop") return false;
  if (/^\/app(?:\/|$)/.test(url.pathname)) {
    return request.headers["sec-ch-ua-mobile"] === "?1" || mobileUserAgent.test(request.headers["user-agent"] || "");
  }
  // Expo's first bundle requests can race the Set-Cookie from /app. Preserve
  // the explicit mobile handoff from their referring document in that window.
  try {
    if (new URL(request.headers.referer || "", `http://${listenHost}`).searchParams.get("client") === "mobile") return true;
  } catch {
    // An invalid Referer simply falls through to the regular selection.
  }
  const affinity = cookieClient(request);
  if (affinity === "mobile") return true;
  if (affinity === "desktop") return false;
  return request.headers["sec-ch-ua-mobile"] === "?1" || mobileUserAgent.test(request.headers["user-agent"] || "");
}

function upstreamPath(url, mobile) {
  if (!mobile) return `${url.pathname}${url.search}`;
  const pathname = url.pathname === "/app" || url.pathname === "/app/"
    ? "/app"
    : url.pathname.startsWith("/app/") ? url.pathname.slice("/app".length) : url.pathname;
  const search = new URLSearchParams(url.searchParams);
  search.delete("client");
  const query = search.toString();
  return `${pathname || "/"}${query ? `?${query}` : ""}`;
}

function targetFor(request, url = requestUrl(request)) {
  // Product API calls are UI-agnostic and must resolve on the caller's own
  // host (localhost in dev, the LAN address on a phone), otherwise the mobile
  // PWA's baked 127.0.0.1 API base points at the device itself. Only /v1/*
  // belongs to the backend: /api/* are the desktop Next.js BFF routes and
  // must keep going to the desktop upstream.
  if (url.pathname.startsWith("/v1/")) {
    return {
      mobile: false,
      host: "127.0.0.1",
      port: backendPort,
      socketPath: undefined,
      path: `${url.pathname}${url.search}`,
    };
  }
  const mobile = isMobileRequest(request, url);
  return { mobile, host: "127.0.0.1", port: mobile ? mobilePort : desktopPort, socketPath: mobile ? mobileSocket || undefined : undefined, path: upstreamPath(url, mobile) };
}

function upstreamHeaders(request, port) {
  const forwardedProto =
    request.headers["x-forwarded-proto"]?.split(",")[0]?.trim() || "http";
  return {
    ...request.headers,
    host: `${listenHost}:${port}`,
    "x-forwarded-host": request.headers.host || `${listenHost}:${listenPort}`,
    "x-forwarded-proto": forwardedProto,
  };
}

function unavailable(response, target, error) {
  if (response.headersSent) return response.destroy(error);
  response.writeHead(502, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify({ code: "ui_upstream_unavailable", message: `Kolibri V3 ${target.mobile ? "mobile" : "desktop"} UI is starting.` }));
}

function proxyHttp(request, response) {
  const target = targetFor(request);
  const upstream = http.request({ hostname: target.socketPath ? undefined : target.host, port: target.socketPath ? undefined : target.port, socketPath: target.socketPath, path: target.path, method: request.method, headers: upstreamHeaders(request, target.port) }, (upstreamResponse) => {
    const headers = { ...upstreamResponse.headers };
    const existingCookies = headers["set-cookie"] ? (Array.isArray(headers["set-cookie"]) ? headers["set-cookie"] : [headers["set-cookie"]]) : [];
    delete headers["set-cookie"];
    response.setHeader("set-cookie", [...existingCookies, `kolibri_ui_client=${target.mobile ? "mobile" : "desktop"}; Path=/; SameSite=Lax`]);
    response.setHeader("x-kolibri-ui-target", target.mobile ? "mobile" : "desktop");
    response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.statusMessage, headers);
    upstreamResponse.pipe(response);
  });
  upstream.setTimeout(15_000, () => upstream.destroy(new Error("upstream timeout")));
  upstream.once("error", (error) => unavailable(response, target, error));
  request.pipe(upstream);
}

function proxyUpgrade(request, socket, head) {
  const target = targetFor(request);
  const upstream = target.socketPath ? net.connect(target.socketPath, () => {
    const headers = Object.entries(upstreamHeaders(request, target.port)).flatMap(([name, value]) => Array.isArray(value) ? value.map((item) => `${name}: ${item}`) : value == null ? [] : [`${name}: ${value}`]).join("\r\n");
    upstream.write(`${request.method} ${target.path} HTTP/1.1\r\n${headers}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  }) : net.connect(target.port, target.host, () => {
    const headers = Object.entries(upstreamHeaders(request, target.port)).flatMap(([name, value]) => Array.isArray(value) ? value.map((item) => `${name}: ${item}`) : value == null ? [] : [`${name}: ${value}`]).join("\r\n");
    upstream.write(`${request.method} ${target.path} HTTP/1.1\r\n${headers}\r\n\r\n`);
    if (head.length) upstream.write(head);
    socket.pipe(upstream).pipe(socket);
  });
  const close = () => { socket.destroy(); upstream.destroy(); };
  upstream.once("error", close);
  socket.once("error", () => upstream.destroy());
}

const server = http.createServer(proxyHttp);
server.on("upgrade", proxyUpgrade);
server.listen(listenPort, listenHost, () => console.log(`[dev:gateway] http://${listenHost}:${listenPort} desktop->${desktopPort} mobile->${mobileSocket || `127.0.0.1:${mobilePort}`}`));

function shutdown(signal) { server.close(() => process.exit(signal === "SIGINT" ? 130 : 0)); server.closeAllConnections?.(); }
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
