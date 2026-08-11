import { expect, test, type Page } from "@playwright/test";

function watchConsole(page: Page): string[] {
	const failures: string[] = [];
	page.on("console", (message) => {
		if (message.type() === "error") failures.push(message.text());
	});
	page.on("pageerror", (error) => failures.push(error.message));
	return failures;
}

async function waitForThreadIdle(page: Page) {
	// Chat runs from the previous test can still be streaming when this test
	// starts (the model provider is rate-limited in dev). The quick actions
	// only render on an idle, empty thread, so wait for the run to settle.
	const stop = page.getByRole("button", { name: "Остановить ответ" });
	if (await stop.isVisible().catch(() => false)) {
		await stop.waitFor({ state: "hidden", timeout: 60_000 }).catch(() => undefined);
	}
}

async function expectNoPetOverlap(page: Page) {
	const pet = page.locator('[data-slot="kolibri-pet"]:visible');
	if ((await pet.count()) === 0) return;
	const petBox = await pet.boundingBox();
	if (!petBox) return;
	const controls = page.locator(
		'[data-slot="workspace-sidebar-destination"]:visible, [role="dialog"] button:visible, [data-slot="settings-canvas-surface"] button:visible',
	);
	for (let index = 0; index < (await controls.count()); index += 1) {
		const box = await controls.nth(index).boundingBox();
		if (!box) continue;
		const overlap =
			petBox.x < box.x + box.width &&
			petBox.x + petBox.width > box.x &&
			petBox.y < box.y + box.height &&
			petBox.y + petBox.height > box.y;
		expect(overlap, `pet overlaps control ${index}`).toBe(false);
	}
}

test.beforeEach(async ({ page }) => {
	await page.goto("/app");
	await expect(page.getByRole("navigation", { name: "Основные разделы" })).toBeVisible();
	await page.waitForLoadState("networkidle");
	await expect(page.locator("[data-nextjs-dialog-overlay]")).toHaveCount(0);
});

test("desktop app loads without overlay, supports reload and has a safe pet", async ({ page }, testInfo) => {
	const consoleFailures = watchConsole(page);
	await expect(page.getByLabel("Сообщение для Kolibri")).toBeVisible();
	await expectNoPetOverlap(page);
	await page.reload();
	await expect(page.getByRole("navigation", { name: "Основные разделы" })).toBeVisible();
	await expect(page.getByLabel("Сообщение для Kolibri")).toBeVisible();
	await expectNoPetOverlap(page);
	await page.screenshot({
		path: `output/playwright/${testInfo.project.name}-app.png`,
		fullPage: true,
	});
	expect(consoleFailures).toEqual([]);
});

test("main sections, settings and integrations are keyboard reachable", async ({ page }, testInfo) => {
	const consoleFailures = watchConsole(page);
	for (const label of ["Проекты", "Документы", "Справочники"]) {
		const destination = page.getByRole("button", { name: label, exact: true });
		await destination.focus();
		await expect(destination).toBeFocused();
		await page.keyboard.press("Enter");
		await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
		await expectNoPetOverlap(page);
		await page.keyboard.press("Escape");
	}

	await page.getByRole("button", { name: "Открыть меню личного кабинета" }).click();
	await page.getByRole("menuitem", { name: "Настройки" }).click();
	await expect(page.locator('[data-slot="settings-canvas-surface"]')).toBeVisible();
	await expect(page.locator('[data-slot="kolibri-pet"]:visible')).toHaveCount(0);
	await page.getByRole("button", { name: "Интеграции", exact: true }).click();
	await expect(page.getByText("Интеграции", { exact: true }).first()).toBeVisible();
	await page.screenshot({
		path: `output/playwright/${testInfo.project.name}-integrations.png`,
		fullPage: true,
	});
	await page.keyboard.press("Escape");
	expect(consoleFailures).toEqual([]);
});

test("estimate quick action preserves incomplete and valid inputs without fake zero result", async ({ page }, testInfo) => {
	const consoleFailures = watchConsole(page);
	await waitForThreadIdle(page);
	await page.getByRole("button", { name: "Новая задача", exact: true }).click();
	await page.getByRole("button", { name: "Рассчитать смету по описанию объекта" }).click();
	const composer = page.getByLabel("Сообщение для Kolibri");
	await expect(
		page.locator('[data-slot="aui_user-message-root"]'),
	).toContainText(/предварительную смету/i);
	await expect(composer).toHaveValue("");

	await composer.fill("Рассчитать смету для объекта в Питере");
	await expect(composer).toHaveValue(/Питере/);
	await composer.fill("Рассчитать предварительную смету ремонта квартиры 38 м² в Москве");
	await expect(composer).toHaveValue(/38 м² в Москве/);
	await expect(page.getByText(/^0 ₽$/)).toHaveCount(0);
	await expect(page.getByText(/0 позиц/i)).toHaveCount(0);
	await page.screenshot({
		path: `output/playwright/${testInfo.project.name}-estimate-quick-action.png`,
		fullPage: true,
	});
	expect(consoleFailures).toEqual([]);
});

test("multiple tasks remain navigable after reload", async ({ page }) => {
	const consoleFailures = watchConsole(page);
	await waitForThreadIdle(page);
	const tasks = page.getByRole("button", { name: /Открыть задачу/ });
	const initialTaskCount = await tasks.count();
	await page.getByRole("button", { name: "Новая задача", exact: true }).click();
	const quickEstimate = page.getByRole("button", {
		name: "Рассчитать смету по описанию объекта",
	});
	await quickEstimate.click();
	await expect(page.locator('[data-slot="aui_user-message-root"]')).toHaveCount(1);
	await page.getByRole("button", { name: "Новая задача", exact: true }).click();
	await quickEstimate.click();
	await expect(page.locator('[data-slot="aui_user-message-root"]')).toHaveCount(1);
	await expect.poll(async () => tasks.count()).toBeGreaterThanOrEqual(
		Math.max(2, initialTaskCount + 1),
	);
	await tasks.first().click();
	await expect(page.locator('[data-slot="aui_user-message-root"]')).toHaveCount(1);
	await page.reload();
	await expect(page.locator('[data-slot="aui_user-message-root"]')).toHaveCount(1);
	expect(consoleFailures).toEqual([]);
});

test("200 percent equivalent viewport keeps primary navigation usable", async ({ page }, testInfo) => {
	const configured = testInfo.project.use.viewport;
	if (!configured) throw new Error("desktop project must declare a viewport");

	await page.addInitScript(() => {
		const originalMatchMedia = window.matchMedia;
		window.matchMedia = (query) => {
			if (query === "(max-width: 959px)") {
				return {
					matches: false,
					media: query,
					onchange: null,
					addListener: () => {},
					removeListener: () => {},
					addEventListener: () => {},
					removeEventListener: () => {},
					dispatchEvent: () => false,
				} as any;
			}
			return originalMatchMedia(query);
		};
	});
	
	// We must reload the page so the init script takes effect on the fresh load
	// before mobile-environment.tsx is mounted.
	await page.reload();

	await page.setViewportSize({
		width: Math.floor(configured.width / 2),
		height: Math.floor(configured.height / 2),
	});
	await expect(page.getByLabel("Сообщение для Kolibri")).toBeVisible();
	const horizontallyClipped = await page.evaluate(
		() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
	);
	expect(horizontallyClipped).toBe(false);
	await page.screenshot({
		path: `output/playwright/${testInfo.project.name}-zoom-200.png`,
		fullPage: true,
	});
});
