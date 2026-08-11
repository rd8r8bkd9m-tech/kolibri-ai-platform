#!/usr/bin/env node

// Regression gate for the single public UI origin (3103).
//
// - Desktop User-Agent must reach the Next desktop UI.
// - Mobile User-Agent must reach the Expo web UI through the private bridge;
//   a 502 here means the bridge cannot connect to Expo (for example after a
//   loopback-family mismatch between `--host localhost` and the bridge).
//
// Requires the dev stack (`npm run dev` / `npm run dev:persistent`) to be
// running. It is intentionally not part of `npm run verify` because the
// offline gates must not depend on a live stack.

import http from "node:http";

const gateway = process.env.KOLIBRI_V3_UI_URL || "http://127.0.0.1:3103";
const DESKTOP_UA =
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36";
const MOBILE_UA =
	"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148";

function get(url, headers = {}) {
	return new Promise((resolve, reject) => {
		const request = http.get(url, { headers }, (response) => {
			let body = "";
			response.setEncoding("utf8");
			response.on("data", (chunk) => {
				if (body.length < 64 * 1024) body += chunk;
			});
			response.on("end", () =>
				resolve({
					status: response.statusCode || 0,
					headers: response.headers,
					body,
				}),
			);
		});
		request.setTimeout(20_000, () => {
			request.destroy(new Error(`timeout: ${url}`));
		});
		request.on("error", reject);
	});
}

function fail(message) {
	console.error(`[check-ui-gateway] FAIL: ${message}`);
	process.exit(1);
}

async function main() {
	const desktop = await get(`${gateway}/`, {
		"User-Agent": DESKTOP_UA,
		Accept: "text/html",
	});
	if (desktop.status !== 200) {
		fail(`desktop route returned ${desktop.status}`);
	}
	if (!desktop.body.includes("<!DOCTYPE html")) {
		fail("desktop route did not return an HTML document");
	}

	const mobile = await get(`${gateway}/app`, {
		"User-Agent": MOBILE_UA,
		Accept: "text/html",
	});
	if (mobile.status !== 200) {
		fail(`mobile route returned ${mobile.status}`);
	}
	if (mobile.headers["x-kolibri-ui-target"] !== "mobile") {
		fail("mobile route was not routed to the Expo target");
	}
	if (!/expo|react-native|__EXPO/i.test(mobile.body)) {
		fail("mobile route did not return Expo web content");
	}

	const desktopApp = await get(`${gateway}/app`, {
		"User-Agent": DESKTOP_UA,
		Accept: "text/html",
	});
	if (desktopApp.status !== 200) {
		fail(`desktop /app returned ${desktopApp.status}`);
	}
	if (desktopApp.headers["x-kolibri-ui-target"] !== "desktop") {
		fail("desktop /app was not routed to the Next target");
	}

	console.log(
		"[check-ui-gateway] OK: desktop 200, mobile 200 (Expo via private bridge)",
	);
}

main().catch((error) => fail(error instanceof Error ? error.message : String(error)));
