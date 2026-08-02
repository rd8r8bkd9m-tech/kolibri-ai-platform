#!/usr/bin/env node

import { createReadStream, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";

const host = process.env.KOLIBRI_V3_MOBILE_HOST || "127.0.0.1";
const port = Number(process.env.KOLIBRI_V3_MOBILE_PORT || "4103");
const root = path.resolve(process.env.KOLIBRI_V3_MOBILE_ROOT || "");

if (!process.env.KOLIBRI_V3_MOBILE_ROOT || !Number.isInteger(port)) {
	throw new Error("KOLIBRI_V3_MOBILE_ROOT and a valid mobile port are required");
}

const contentTypes = new Map([
	[".css", "text/css; charset=utf-8"],
	[".html", "text/html; charset=utf-8"],
	[".ico", "image/x-icon"],
	[".js", "text/javascript; charset=utf-8"],
	[".json", "application/json; charset=utf-8"],
	[".png", "image/png"],
	[".svg", "image/svg+xml"],
	[".webp", "image/webp"],
]);

function candidateFor(requestUrl) {
	let pathname;
	try {
		pathname = decodeURIComponent(new URL(requestUrl || "/", "http://mobile").pathname);
	} catch {
		return null;
	}
	if (pathname.includes("\0") || pathname.split("/").includes("..")) return null;
	const relative = pathname === "/" ? "index.html" : pathname.slice(1);
	const candidates = path.extname(relative)
		? [relative]
		: [`${relative}.html`, path.join(relative, "index.html")];
	for (const candidate of candidates) {
		const resolved = path.resolve(root, candidate);
		if (!resolved.startsWith(`${root}${path.sep}`)) continue;
		try {
			if (statSync(resolved).isFile()) return resolved;
		} catch {
			// Try the next bounded static-route candidate.
		}
	}
	return null;
}

const server = http.createServer((request, response) => {
	if (request.method !== "GET" && request.method !== "HEAD") {
		response.writeHead(405, { allow: "GET, HEAD" });
		response.end();
		return;
	}
	const candidate = candidateFor(request.url);
	if (!candidate) {
		response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
		response.end("Not found");
		return;
	}
	const extension = path.extname(candidate).toLowerCase();
	response.writeHead(200, {
		"cache-control":
			extension === ".html"
					? "no-store"
					: "public, max-age=31536000, immutable",
		"content-type": contentTypes.get(extension) || "application/octet-stream",
		"x-content-type-options": "nosniff",
	});
	if (request.method === "HEAD") {
		response.end();
		return;
	}
	createReadStream(candidate).pipe(response);
});

server.listen(port, host, () => {
	console.log(`[mobile:static] http://${host}:${port} root=${root}`);
});

function shutdown() {
	server.close(() => process.exit(0));
	server.closeAllConnections?.();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
