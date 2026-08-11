#!/usr/bin/env node

// Renders the mobile PWA at a phone viewport and asserts the Expo app shell
// boots (session restoration or auth screen). Requires the dev stack running.

import { chromium } from "@playwright/test";

const baseURL = process.env.KOLIBRI_V3_UI_URL || "http://127.0.0.1:3103";
const target = `${baseURL}/app?client=mobile`;

const browser = await chromium.launch();
const page = await browser.newPage({
	viewport: { width: 390, height: 844 },
	userAgent:
		"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
});
const consoleErrors = [];
page.on("console", (message) => {
	if (message.type() === "error") consoleErrors.push(message.text());
});

try {
	await page.goto(target, { waitUntil: "domcontentloaded", timeout: 30_000 });
	await page.waitForTimeout(8_000);
	const url = page.url();
	if (url.includes("client=desktop")) {
		throw new Error(`mobile PWA redirected to desktop: ${url}`);
	}
	const body = await page.evaluate(() => document.body?.innerText ?? "");
	if (!/Восстановление сессии|Войти|Личный кабинет|Kolibri/i.test(body)) {
		throw new Error(`mobile app shell did not boot; body: ${body.slice(0, 200)}`);
	}
	console.log(
		`[check-mobile-app] OK: mobile PWA booted at ${url} (shell text present)`,
	);
	if (consoleErrors.length) {
		console.warn(
			`[check-mobile-app] console errors:\n${consoleErrors.join("\n")}`,
		);
	}
} finally {
	await browser.close();
}
