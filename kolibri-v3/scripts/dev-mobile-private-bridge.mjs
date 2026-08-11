#!/usr/bin/env node

// Expo's web server listens on 4104. This bridge is intentionally bound to a
// non-public loopback alias, so `localhost:4103` can never become a competing
// browser origin. Only the 3103 gateway reaches it.
//
// Expo binds `--host localhost` to the first loopback address the OS resolves,
// which is `::1` on some machines and `127.0.0.1` on others. The bridge must
// therefore try both loopback families instead of hardcoding one address;
// otherwise the mobile route returns 502 `ui_upstream_unavailable`.
import http from "node:http";
import net from "node:net";
import { existsSync, unlinkSync } from "node:fs";
import path from "node:path";

const socketPath =
	process.env.KOLIBRI_V3_MOBILE_INTERNAL_SOCKET ||
	path.resolve("var/mobile-web.sock");
const upstreamPort = Number(
	process.env.KOLIBRI_V3_MOBILE_UPSTREAM_PORT || "4104",
);
const configuredHost = process.env.KOLIBRI_V3_MOBILE_UPSTREAM_HOST || "127.0.0.1";
const upstreamHosts = [...new Set([configuredHost, "127.0.0.1", "::1"])];

function hostHeader(host) {
	return `${host.includes(":") && !host.startsWith("[") ? `[${host}]` : host}:${upstreamPort}`;
}

function requestHeaders(request, host) {
	return {
		...request.headers,
		host: hostHeader(host),
	};
}

function tryHttpCandidate(request, response, hostIndex) {
	if (hostIndex >= upstreamHosts.length) {
		if (!response.headersSent) {
			response.writeHead(502).end();
		} else {
			response.destroy();
		}
		return;
	}
	const host = upstreamHosts[hostIndex];
	const upstream = http.request(
		{
			hostname: host,
			port: upstreamPort,
			path: request.url,
			method: request.method,
			headers: requestHeaders(request, host),
		},
		(upstreamResponse) => {
			response.writeHead(
				upstreamResponse.statusCode || 502,
				upstreamResponse.statusMessage,
				upstreamResponse.headers,
			);
			upstreamResponse.pipe(response);
		},
	);
	upstream.once("error", (error) => {
		if (error && (error.code === "ECONNREFUSED" || error.code === "ENOTFOUND")) {
			tryHttpCandidate(request, response, hostIndex + 1);
			return;
		}
		if (!response.headersSent) {
			response.writeHead(502).end();
		} else {
			response.destroy();
		}
	});
	request.pipe(upstream);
}

function tryUpgradeCandidate(request, socket, head, hostIndex) {
	if (hostIndex >= upstreamHosts.length) {
		socket.destroy();
		return;
	}
	const host = upstreamHosts[hostIndex];
	const upstream = net.connect(
		upstreamPort,
		host,
		() => {
			const serialized = Object.entries(requestHeaders(request, host))
				.flatMap(([name, value]) =>
					Array.isArray(value)
						? value.map((entry) => `${name}: ${entry}`)
						: value == null
							? []
							: [`${name}: ${value}`],
				)
				.join("\r\n");
			upstream.write(
				`${request.method} ${request.url} HTTP/1.1\r\n${serialized}\r\n\r\n`,
			);
			if (head.length) upstream.write(head);
			socket.pipe(upstream).pipe(socket);
		},
	);
	const fallback = () => {
		upstream.removeAllListeners();
		socket.removeAllListeners();
		tryUpgradeCandidate(request, socket, head, hostIndex + 1);
	};
	upstream.once("error", (error) => {
		if (error && (error.code === "ECONNREFUSED" || error.code === "ENOTFOUND")) {
			fallback();
			return;
		}
		socket.destroy();
		upstream.destroy();
	});
	socket.once("error", () => upstream.destroy());
}

const server = http.createServer((request, response) => {
	tryHttpCandidate(request, response, 0);
});
server.on("upgrade", (request, socket, head) => {
	tryUpgradeCandidate(request, socket, head, 0);
});

if (existsSync(socketPath)) unlinkSync(socketPath);
server.listen(socketPath, () =>
	console.log(
		`[dev:mobile-bridge] private ${socketPath} -> ${upstreamHosts.join(", ")}:${upstreamPort}`,
	),
);

function shutdown(signal) {
	server.close(() => {
		if (existsSync(socketPath)) unlinkSync(socketPath);
		process.exit(signal === "SIGINT" ? 130 : 0);
	});
	server.closeAllConnections?.();
}
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
