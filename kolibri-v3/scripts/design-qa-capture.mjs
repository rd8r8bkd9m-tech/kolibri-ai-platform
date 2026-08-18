// One-off design QA capture: local landing vs external reference.
// Usage: node scripts/design-qa-capture.mjs
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const OUT_DIR = "output/design-qa";
const VIEWPORT = { width: 1440, height: 900 };

mkdirSync(OUT_DIR, { recursive: true });

const targets = [
	{ name: "kolibri-landing", url: "http://127.0.0.1:3103/" },
	{ name: "reference-samreshuuu", url: "https://samreshuuu.ru/home" },
];

const browser = await chromium.launch();
for (const target of targets) {
	const page = await browser.newPage({ viewport: VIEWPORT });
	await page.goto(target.url, { waitUntil: "domcontentloaded", timeout: 30_000 });
	await page.waitForTimeout(4_000);
	await page.screenshot({
		path: `${OUT_DIR}/${target.name}-viewport.png`,
	});
	await page.screenshot({
		path: `${OUT_DIR}/${target.name}-full.png`,
		fullPage: true,
	});
	await page.close();
	console.log(`captured ${target.name}`);
}
await browser.close();
