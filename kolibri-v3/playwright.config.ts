import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.KOLIBRI_E2E_BASE_URL ?? "http://127.0.0.1:3103";
const localQaState = "output/playwright/qa-storage-state.json";

export default defineConfig({
	testDir: "./tests/e2e",
	outputDir: "./output/playwright/results",
	globalSetup: "./tests/e2e/global-setup.ts",
	globalTeardown: "./tests/e2e/global-teardown.ts",
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 45_000,
	expect: { timeout: 10_000 },
	reporter: [
		["list"],
		["html", { outputFolder: "output/playwright/report", open: "never" }],
	],
	use: {
		...devices["Desktop Chrome"],
		baseURL,
		storageState:
			process.env.KOLIBRI_E2E_QA_STORAGE_STATE ?? localQaState,
		actionTimeout: 10_000,
		navigationTimeout: 20_000,
		screenshot: "only-on-failure",
		trace: "retain-on-failure",
		video: "off",
	},
	projects: [
		{
			name: "desktop-1363x936",
			use: { viewport: { width: 1363, height: 936 } },
		},
		{
			name: "desktop-1440x900",
			use: { viewport: { width: 1440, height: 900 } },
		},
	],
});
