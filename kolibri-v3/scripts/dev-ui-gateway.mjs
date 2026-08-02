#!/usr/bin/env node

/**
 * One local UI origin for Kolibri V3.
 *
 * The desktop Next runtime and the Expo web runtime intentionally remain
 * separate processes, but callers must not need to know about two UI ports.
 * This gateway owns 3103 and selects the upstream from the request's mobile
 * user-agent or the explicit `client=mobile` handoff query parameter.
 */

import http from "node:http";
import net from "node:net";

const listenHost = process.env.KOLIBRI_V3_UI_HOST || "127.0.0.1";
const listenPort = Number(process.env.KOLIBRI_V3_UI_PORT || "3103");
const desktopPort = Number(
	process.env.KOLIBRI_V3_DESKTOP_INTERNAL_PORT || "3104",
);
const mobilePort = Number(
	process.env.KOLIBRI_V3_MOBILE_INTERNAL_PORT || "4103",
);
const mobileHost =
	process.env.KOLIBRI_V3_MOBILE_INTERNAL_HOST || "127.0.0.1";
const mobileUserAgent =
	/(Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile)/i;

function requestUrl(request) {
	return new URL(request.url || "/", `http://${request.headers.host || listenHost}`);
}

function cookieClient(request) {
	const cookies = request.headers.cookie || "";
	const match = cookies.match(/(?:^|;\s*)kolibri_ui_client=(mobile|desktop)(?:;|$)/);
	return match?.[1] || null;
}

function isMobileRequest(request, url = requestUrl(request)) {
	// A direct /app navigation is a new client selection. This lets a desktop
	// browser leave a previous mobile handoff without requiring a stale cookie
	// or query parameter to be cleared manually. Device signals own this entry;
	// static chunks keep using the affinity cookie selected here.
	if (/^\/app(?:\/|$)/.test(url.pathname)) {
		if (request.headers["sec-ch-ua-mobile"] === "?1") return true;
		return mobileUserAgent.test(request.headers["user-agent"] || "");
	}
	const explicitClient = url.searchParams.get("client");
	if (explicitClient === "mobile") return true;
	if (explicitClient === "desktop") return false;
	const affinity = cookieClient(request);
	if (affinity === "mobile") return true;
	if (affinity === "desktop") return false;
	if (request.headers["sec-ch-ua-mobile"] === "?1") return true;
	return mobileUserAgent.test(request.headers["user-agent"] || "");
}

function upstreamPath(url, mobile) {
	if (!mobile) return `${url.pathname}${url.search}`;

	const pathname =
		url.pathname === "/app" || url.pathname === "/app/"
			? "/app"
			: url.pathname.startsWith("/app/")
				? url.pathname.slice("/app".length)
				: url.pathname;
	const search = new URLSearchParams(url.searchParams);
	search.delete("client");
	const query = search.toString();
	return `${pathname || "/"}${query ? `?${query}` : ""}`;
}

function targetFor(request, url = requestUrl(request)) {
	const mobile = isMobileRequest(request, url);
	return {
		mobile,
		host: mobile ? mobileHost : "127.0.0.1",
		port: mobile ? mobilePort : desktopPort,
		path: upstreamPath(url, mobile),
	};
}

function upstreamHeaders(request, port) {
	return {
		...request.headers,
		host: `${listenHost}:${port}`,
		"x-forwarded-host": request.headers.host || `${listenHost}:${listenPort}`,
		"x-forwarded-proto": "http",
	};
}

function unavailable(response, target, error) {
	if (response.headersSent) {
		response.destroy(error);
		return;
	}
	response.writeHead(502, { "content-type": "application/json; charset=utf-8" });
	response.end(
		JSON.stringify({
			code: "ui_upstream_unavailable",
			message: `Kolibri V3 ${target.mobile ? "mobile" : "desktop"} UI is starting.`,
		}),
	);
}

function proxyHttp(request, response) {
	const target = targetFor(request);
	const upstream = http.request(
		{
			hostname: target.host,
			port: target.port,
			path: target.path,
			method: request.method,
			headers: upstreamHeaders(request, target.port),
		},
		(upstreamResponse) => {
			const headers = { ...upstreamResponse.headers };
			const existingCookies = headers["set-cookie"]
				? Array.isArray(headers["set-cookie"])
					? headers["set-cookie"]
					: [headers["set-cookie"]]
				: [];
			const affinityCookie = [
				...existingCookies,
				`kolibri_ui_client=${target.mobile ? "mobile" : "desktop"}; Path=/; SameSite=Lax`,
			];
			delete headers["set-cookie"];
			response.setHeader("set-cookie", affinityCookie);
			response.setHeader(
				"x-kolibri-ui-target",
				target.mobile ? "mobile" : "desktop",
			);
			response.writeHead(
				upstreamResponse.statusCode || 502,
				upstreamResponse.statusMessage,
				headers,
			);
			upstreamResponse.pipe(response);
		},
	);
	upstream.setTimeout(15_000, () => upstream.destroy(new Error("upstream timeout")));
	upstream.once("error", (error) => unavailable(response, target, error));
	request.pipe(upstream);
}

function proxyUpgrade(request, socket, head) {
	const target = targetFor(request);
	const upstream = net.connect(target.port, target.host, () => {
		const headers = Object.entries(upstreamHeaders(request, target.port))
			.flatMap(([name, value]) => {
				if (Array.isArray(value)) return value.map((item) => `${name}: ${item}`);
				if (value == null) return [];
				return [`${name}: ${value}`];
			})
			.join("\r\n");
		upstream.write(`${request.method} ${target.path} HTTP/1.1\r\n${headers}\r\n\r\n`);
		if (head.length) upstream.write(head);
		socket.pipe(upstream).pipe(socket);
	});
	const close = () => {
		socket.destroy();
		upstream.destroy();
	};
	upstream.once("error", close);
	socket.once("error", () => upstream.destroy());
}

const server = http.createServer(proxyHttp);
server.on("upgrade", proxyUpgrade);
server.listen(listenPort, listenHost, () => {
	console.log(
		`[dev:gateway] http://${listenHost}:${listenPort} desktop->${desktopPort} mobile->${mobilePort}`,
	);
});

function shutdown(signal) {
	server.close(() => process.exit(signal === "SIGINT" ? 130 : 0));
	server.closeAllConnections?.();
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
