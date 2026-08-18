#!/usr/bin/env node

// Real mobile QA: registers a fresh user through the mobile UI, opens a chat,
// sends enough long messages to overflow the viewport, then verifies the
// message list actually scrolls (wheel up/down) and auto-scrolls to the
// newest message. This is a behavioral regression test, not a static check.
// Requires the dev stack (`npm run dev:persistent`) to be running.

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

function expect(condition, message) {
	if (!condition) {
		failures.push(message);
	}
}

try {
	await page.goto(target, { waitUntil: "domcontentloaded", timeout: 30_000 });

	// Register a brand-new account through the real mobile UI.
	// In login mode both the submit button and the mode toggle are labeled
	// "Создать аккаунт"; the toggle is the second (enabled) match.
	const toggle = page.getByText("Создать аккаунт").last();
	await toggle.click({ timeout: 20_000 });
	const unique = `${Date.now()}-${process.pid}`;
	await page.getByLabel("Имя").fill(`QA Mobile ${unique}`);
	await page
		.getByLabel("Электронная почта")
		.fill(`qa-mobile-${unique}+qa@example.com`);
	await page.getByLabel("Пароль").fill(`qa-only-${unique}-correct-horse`);
	await page.getByText("Создать аккаунт").click({ timeout: 20_000 });
	await page.getByLabel("Сообщение", { exact: true }).waitFor({ timeout: 30_000 });
	expect(true, "mobile registration and chat shell booted");

	// Six short messages fit inside a 390x844 viewport, so the old test never
	// overflowed and produced a false negative. Force overflow deterministically:
	// 12 messages with multi-line text guarantee scrollHeight > clientHeight.
	const longText =
		"Это достаточно длинное сообщение для проверки скролла на мобильном устройстве. ".repeat(
			3,
		);
	for (let index = 0; index < 12; index += 1) {
		const input = page.getByLabel("Сообщение", { exact: true });
		await input.fill(`Проверка скролла сообщение номер ${index + 1}. ${longText}`);
		// Pressing Enter submits through the composer form and avoids the
		// element-detach race when the send button re-renders mid-stream.
		await input.press("Enter");
		await page.waitForTimeout(1_000);
	}
	await page.waitForTimeout(2_000);

	// Locate the actual scrollable message list (RN Web renders FlatList).
	const scroll = await page.evaluate(() => {
		const candidates = Array.from(
			document.querySelectorAll("div"),
		).filter((element) => {
			const style = window.getComputedStyle(element);
			return (
				style.overflowY === "auto" &&
				element.scrollHeight > element.clientHeight + 10
			);
		});
		const targetElement = [...candidates].sort(
			(left, right) => right.scrollHeight - left.scrollHeight,
		)[0];
		if (!targetElement) return null;
		return {
			scrollHeight: targetElement.scrollHeight,
			clientHeight: targetElement.clientHeight,
			overflowY: window.getComputedStyle(targetElement).overflowY,
			scrollTop: targetElement.scrollTop,
		};
	});

	expect(
		scroll !== null,
		"message list has an overflowing scroll container (12 long messages sent)",
	);
	if (scroll) {
		expect(
			scroll.scrollHeight > scroll.clientHeight,
			`message list overflows (${scroll.scrollHeight} > ${scroll.clientHeight})`,
		);
		const before = scroll.scrollTop;
		// Wheel up: history must be reachable.
		await page.mouse.move(195, 300);
		await page.mouse.wheel(0, -3000);
		await page.waitForTimeout(800);
		const afterUp = await page.evaluate(() => {
			const element = Array.from(
				document.querySelectorAll("div"),
			)
				.filter(
					(entry) =>
						window.getComputedStyle(entry).overflowY === "auto" &&
						entry.scrollHeight > entry.clientHeight + 10,
				)
				.sort((left, right) => right.scrollHeight - left.scrollHeight)[0];
			return element?.scrollTop ?? 0;
		});
		expect(
			afterUp < before,
			`wheel scroll up moved the message list (${before} -> ${afterUp})`,
		);
		// Wheel down: back to the bottom.
		await page.mouse.wheel(0, 600);
		await page.waitForTimeout(800);
		const after = await page.evaluate(() => {
			const element = Array.from(
				document.querySelectorAll("div"),
			)
				.filter(
					(entry) =>
						window.getComputedStyle(entry).overflowY === "auto" &&
						entry.scrollHeight > entry.clientHeight + 10,
				)
				.sort((left, right) => right.scrollHeight - left.scrollHeight)[0];
			return element?.scrollTop ?? 0;
		});
		expect(
			after > afterUp,
			`wheel scroll down returned to the bottom (${afterUp} -> ${after})`,
		);

		// Auto-scroll: a new message while at/near the bottom must bring the
		// newest message into view (scrollTop grows by the added height).
		await page.evaluate(() => {
			const element = Array.from(document.querySelectorAll("div"))
				.filter(
					(entry) =>
						window.getComputedStyle(entry).overflowY === "auto" &&
						entry.scrollHeight > entry.clientHeight + 10,
				)
				.sort((left, right) => right.scrollHeight - left.scrollHeight)[0];
			if (element) element.scrollTop = element.scrollHeight;
		});
		// Emulate a real wheel movement so React receives the scroll event and
		// updates its at-bottom state before the next message is appended.
		await page.mouse.move(195, 300);
		await page.mouse.wheel(0, 3_000);
		await page.waitForTimeout(800);
		const beforeNew = await page.evaluate(() => {
			const element = Array.from(document.querySelectorAll("div"))
				.filter(
					(entry) =>
						window.getComputedStyle(entry).overflowY === "auto" &&
						entry.scrollHeight > entry.clientHeight + 10,
				)
				.sort((left, right) => right.scrollHeight - left.scrollHeight)[0];
			return element?.scrollTop ?? 0;
		});
		await page.getByLabel("Сообщение", { exact: true }).fill(`Финальное сообщение ${Date.now()}`);
		await page.getByLabel("Сообщение", { exact: true }).press("Enter");
		await page.waitForTimeout(3_000);
		const afterNew = await page.evaluate(() => {
			const element = Array.from(
				document.querySelectorAll("div"),
			)
				.filter(
					(entry) =>
						window.getComputedStyle(entry).overflowY === "auto" &&
						entry.scrollHeight > entry.clientHeight + 10,
				)
				.sort((left, right) => right.scrollHeight - left.scrollHeight)[0];
			return element?.scrollTop ?? 0;
		});
		expect(
			afterNew > beforeNew,
			`auto-scroll pinned the newest message (${beforeNew} -> ${afterNew})`,
		);
	}

	await page.screenshot({
		path: "output/playwright/mobile-chat-qa.png",
		fullPage: true,
	});
} finally {
	await browser.close();
}

if (failures.length) {
	console.error(`[qa-mobile-chat] FAIL:\n${failures.join("\n")}`);
	process.exit(1);
}
console.log("[qa-mobile-chat] OK: mobile register, chat send and scroll verified");
