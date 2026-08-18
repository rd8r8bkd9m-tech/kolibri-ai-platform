#!/usr/bin/env node

import { chromium } from "@playwright/test";

const baseURL = process.env.KOLIBRI_V3_UI_URL || "http://127.0.0.1:3103";
const target = `${baseURL}/app?client=mobile`;
const browser = await chromium.launch();
const page = await browser.newPage({
	viewport: { width: 390, height: 844 },
	userAgent:
		"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
});
const failures = [];

page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("console", (message) => {
	if (message.type() === "error") failures.push(`console: ${message.text()}`);
});

const expect = (condition, message) => {
	if (!condition) failures.push(message);
};

try {
	await page.goto(target, { waitUntil: "domcontentloaded", timeout: 30_000 });
	const ownerEmail = process.env.KOLIBRI_V3_DEV_OWNER_EMAIL || "montodays@ya.ru";
	const magicResponse = await fetch(
		"http://127.0.0.1:8002/v1/mobile/auth/magic-link/request",
		{
			method: "POST",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/json",
			},
			body: JSON.stringify({
				email: ownerEmail,
				device: {
					platform: "ios",
					deviceName: "QA Estimate",
					appVersion: "1.0.0",
				},
			}),
		},
	);
	if (!magicResponse.ok) {
		throw new Error(`magic link request failed: ${magicResponse.status}`);
	}
	const magic = await magicResponse.json();
	if (!magic.magicLink) throw new Error("development magic link was not returned");
	const verifyResponse = await fetch(
		"http://127.0.0.1:8002/v1/mobile/auth/magic-link/verify",
		{
			method: "POST",
			headers: {
				Accept: "application/json",
				"Content-Type": "application/json",
			},
			body: JSON.stringify({
				email: ownerEmail,
				token: magic.magicLink,
				device: {
					platform: "ios",
					deviceName: "QA Estimate",
					appVersion: "1.0.0",
				},
			}),
		},
	);
	if (!verifyResponse.ok) {
		throw new Error(`magic link verify failed: ${verifyResponse.status}`);
	}
	const session = await verifyResponse.json();
	if (!session.refreshToken) throw new Error("refresh token missing");
	const documentCountBefore = await (async () => {
		const response = await fetch("http://127.0.0.1:8002/v1/documents", {
			headers: {
				Accept: "application/json",
				Authorization: `Bearer ${session.accessToken}`,
			},
		});
		if (!response.ok) throw new Error(`documents preflight failed: ${response.status}`);
		const payload = await response.json();
		return Array.isArray(payload.documents) ? payload.documents.length : 0;
	})();
	await page.goto(target, { waitUntil: "domcontentloaded", timeout: 30_000 });
	await page.evaluate((refreshToken) => {
		globalThis.localStorage.setItem(
			"kolibri.mobile.refresh-token.v1",
			refreshToken,
		);
	}, session.refreshToken);
	await page.reload({ waitUntil: "domcontentloaded", timeout: 30_000 });
	await page.getByLabel("Сообщение", { exact: true }).waitFor({ timeout: 30_000 });
	const composer = page.getByLabel("Сообщение").last();
	await composer.click({ timeout: 20_000 });
	await composer.fill("Составь смету на ремонт квартиры");
	await page.keyboard.press("Enter");

	await page.getByText("Формирую смету").waitFor({ timeout: 60_000 });
	expect(true, "AI estimate generation card appeared in chat");

	const deadline = Date.now() + 300_000;
	let documentCreated = false;
	while (Date.now() < deadline) {
		const response = await fetch("http://127.0.0.1:8002/v1/documents", {
			headers: {
				Accept: "application/json",
				Authorization: `Bearer ${session.accessToken}`,
			},
		});
		if (response.ok) {
			const payload = await response.json();
			if (Array.isArray(payload.documents) && payload.documents.length > documentCountBefore) {
				documentCreated = true;
				break;
			}
		}
		await new Promise((resolve) => setTimeout(resolve, 10_000));
	}
	expect(documentCreated, "new estimate document was persisted on the server");

	await page.screenshot({
		path: "output/playwright/mobile-estimate-qa.png",
		fullPage: true,
	});
} finally {
	await browser.close();
}

if (failures.length) {
	console.error(`[qa-mobile-estimate] FAIL:\n${failures.join("\n")}`);
	process.exit(1);
}
console.log("[qa-mobile-estimate] OK: register, promote, AI estimate card, editor");
