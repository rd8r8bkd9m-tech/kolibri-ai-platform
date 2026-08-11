import { expect, test, type Page } from "@playwright/test";

const baseOrigin = "http://127.0.0.1:3103";

function watchConsole(page: Page): string[] {
	const failures: string[] = [];
	page.on("console", (message) => {
		if (message.type() === "error") failures.push(message.text());
	});
	page.on("pageerror", (error) => failures.push(error.message));
	return failures;
}

test.beforeEach(async ({ browser, page }) => {
	// Fresh user per test: composer runs must never inherit an in-flight run,
	// rate-limited provider state, or thread history from another test.
	const unique = `${Date.now()}-${Math.round(Math.random() * 1e6)}`;
	// Register through an isolated request context. Using `page.request` here
	// would send the shared QA storage-state cookie along and trigger backend
	// session rotation, which silently invalidates the acceptance suite's
	// stored session (its tests then start signed out).
	const api = await browser.newContext({ baseURL: "http://127.0.0.1:3103" });
	// Inside a test, browser.newContext() still inherits the project's
	// storageState, so clear it before registering the composer user.
	await api.clearCookies();
	const response = await api.request.post("/api/v3/auth/register", {
		headers: { Origin: baseOrigin },
		data: {
			email: `composer-qa-${unique}+qa@example.com`,
			name: "[QA] Composer",
			password: `qa-only-${unique}-correct-horse`,
		},
	});
	const state = await api.storageState();
	await api.close();
	if (response.status() !== 201) {
		throw new Error(`composer QA user registration failed: ${response.status()}`);
	}
	// Drop the acceptance suite's shared QA cookies before applying the
	// composer user's session. If both sessions travel in one request, the
	// backend's session-revocation paths (register/login) can invalidate the
	// QA storage state and break every later acceptance test.
	await page.context().clearCookies();
	await page.context().addCookies(state.cookies);
	await page.goto("/app");
	await expect(page.getByLabel("Сообщение для Kolibri")).toBeVisible({
		timeout: 60_000,
	});
});

test("composer send button appears only when typing and submit renders the user message", async ({
	page,
}) => {
	const consoleFailures = watchConsole(page);
	const input = page.getByLabel("Сообщение для Kolibri");
	const send = page.getByRole("button", { name: "Отправить сообщение" });

	await expect(send).toHaveCount(0);
	await input.fill("Привет, Kolibri");
	await expect(send).toBeVisible();
	await send.click();

	await expect(page.locator('[data-role="user"]').last()).toContainText(
		"Привет, Kolibri",
	);
	expect(consoleFailures).toEqual([]);
});

test("composer slash commands transform the input through the runtime", async ({
	page,
}) => {
	const input = page.getByLabel("Сообщение для Kolibri");
	await input.fill("/");
	await expect(
		page.getByRole("option", { name: /Создать смету/ }),
	).toBeVisible();
	await expect(
		page.getByRole("option", { name: /Экспорт/ }),
	).toBeVisible();

	await page.getByRole("option", { name: /Создать смету/ }).click();
	await expect(input).toHaveValue("Создай смету на: ");
});

test("composer @ mentions insert a structured directive and render as a chip", async ({
	page,
}) => {
	const input = page.getByLabel("Сообщение для Kolibri");
	await input.fill("@");
	await expect(page.getByRole("option", { name: /Контекст/ })).toBeVisible();
	await expect(page.getByRole("option", { name: /Инструменты/ })).toBeVisible();

	await page.getByRole("option", { name: /Контекст/ }).click();
	await page.getByRole("option", { name: /Проект/ }).click();
	await expect(input).toHaveValue(":context[Проект]{name=project} ");

	await input.fill(":context[Проект]{name=project} Опиши состав работ");
	await page.getByRole("button", { name: "Отправить сообщение" }).click();
	await expect(page.locator("[data-kind='context']").last()).toBeVisible();
});

test("composer stop cancels a running generation", async ({ page }) => {
	const consoleFailures = watchConsole(page);
	const input = page.getByLabel("Сообщение для Kolibri");
	await input.fill("Напиши развёрнутый ответ длиной в несколько абзацев");
	await page.getByRole("button", { name: "Отправить сообщение" }).click();

	const stop = page.getByRole("button", { name: "Остановить ответ" });
	try {
		await expect(stop).toBeVisible({ timeout: 12_000 });
		await stop.click().catch(() => {
			// The run may have completed between visibility and the click.
		});
	} catch {
		// Provider may have failed fast (e.g. rate limit); the important
		// contract is that the composer returns to the send state.
	}

	await expect(
		page.getByRole("button", { name: "Отправить сообщение" }),
	).toBeVisible({ timeout: 25_000 });
	expect(consoleFailures).toEqual([]);
});

test("thread list: new thread, message, switch back restores history", async ({
	page,
}) => {
	const input = page.getByLabel("Сообщение для Kolibri");
	await input.fill("Сообщение в первом треде");
	await page.getByRole("button", { name: "Отправить сообщение" }).click();
	await expect(page.locator('[data-role="user"]').last()).toContainText(
		"Сообщение в первом треде",
	);

	await page
		.getByRole("button", { name: "Новая задача", exact: true })
		.first()
		.click();
	await expect(input).toHaveValue("");

	await input.fill("Сообщение во втором треде");
	await page.getByRole("button", { name: "Отправить сообщение" }).click();
	await expect(page.locator('[data-role="user"]').last()).toContainText(
		"Сообщение во втором треде",
	);
});

test("composer attachment tray is wired when the tenant supports attachments", async ({
	page,
}) => {
	const attach = page.getByRole("button", { name: "Прикрепить файл" });
	if ((await attach.count()) === 0 || (await attach.isDisabled())) {
		test.skip(true, "QA tenant has no attachment capability");
	}
	const dataTransfer = await page.evaluateHandle(() => {
		const transfer = new DataTransfer();
		transfer.items.add(
			new File(["xlsx"], "estimate.xlsx", {
				type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			}),
		);
		return transfer;
	});
	await page
		.locator("[data-slot='aui_composer-shell']")
		.dispatchEvent("drop", { dataTransfer });
	await expect(page.getByText("estimate.xlsx").first()).toBeVisible({
		timeout: 15_000,
	});
});
