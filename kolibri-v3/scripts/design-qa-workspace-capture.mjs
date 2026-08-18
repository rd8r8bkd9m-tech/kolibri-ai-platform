// Authenticated workspace capture for design QA: registers a disposable QA
// tenant (same flow as tests/e2e), captures the desktop workspace at the
// redesign-spec viewports, then archives the tenant.
// Usage: node scripts/design-qa-workspace-capture.mjs
import { execFileSync } from "node:child_process";
import { mkdir } from "node:fs/promises";
import { chromium, request } from "playwright";

const baseURL = process.env.KOLIBRI_E2E_BASE_URL ?? "http://127.0.0.1:3103";
const outDir = "output/design-qa/workspace";

await mkdir(outDir, { recursive: true });

const api = await request.newContext({
	baseURL,
	extraHTTPHeaders: { Origin: new URL(baseURL).origin },
});
const unique = `${Date.now()}-${process.pid}`;
let tenantId;
try {
	const response = await api.post("/api/v3/auth/register", {
		data: {
			email: `design-qa-${unique}+qa@example.com`,
			name: "[QA] Design Workspace",
			password: `qa-only-${unique}-correct-horse`,
		},
	});
	if (response.status() !== 201) {
		throw new Error(`QA registration failed: HTTP ${response.status()}`);
	}
	tenantId = (await response.json()).user?.tenantId;
	if (!tenantId) throw new Error("registration omitted tenantId");
	execFileSync(
		"backend/venv/bin/python",
		["-m", "app.qa_tenant_fixture", "--tenant-id", tenantId, "--confirm", `PREPARE QA TENANT ${tenantId}`],
		{
			cwd: process.cwd(),
			env: { ...process.env, PYTHONPATH: "backend", KOLIBRI_V3_DATABASE_URL: "sqlite:///./var/kolibri-v3.db" },
			stdio: "pipe",
		},
	);
	const state = await api.storageState();
	const browser = await chromium.launch();
	const page = await browser.newPage({ storageState: state });

	const shots = [
		{ name: "workspace-1440x900", viewport: { width: 1440, height: 900 } },
		{ name: "workspace-1280x720", viewport: { width: 1280, height: 720 } },
		{ name: "workspace-narrow-900x700", viewport: { width: 900, height: 700 } },
	];
	for (const shot of shots) {
		await page.setViewportSize(shot.viewport);
		await page.goto(`${baseURL}/app?client=desktop`, { waitUntil: "domcontentloaded" });
		await page.waitForTimeout(4000);
		await page.screenshot({ path: `${outDir}/${shot.name}.png` });
		console.log(`captured ${shot.name}`);
	}

	// Right-canvas toggle must open Files directly (no launcher page).
	await page.setViewportSize({ width: 1440, height: 900 });
	const contextToggle = page.getByRole("button", { name: "Показать контекст" });
	if (await contextToggle.count() === 1) {
		await contextToggle.click();
		await page.waitForTimeout(1500);
		await page.screenshot({ path: `${outDir}/workspace-aux-files-1440x900.png` });
		console.log("captured workspace-aux-files-1440x900");
	}

	await browser.close();
} finally {
	await api.dispose();
	if (tenantId) {
		execFileSync(
			"backend/venv/bin/python",
			["-m", "app.qa_tenant_archive", "--tenant-id", tenantId, "--confirm", `ARCHIVE QA TENANT ${tenantId}`],
			{
				cwd: process.cwd(),
				env: { ...process.env, PYTHONPATH: "backend", KOLIBRI_V3_DATABASE_URL: "sqlite:///./var/kolibri-v3.db" },
				stdio: "pipe",
			},
		);
		console.log(`archived QA tenant ${tenantId}`);
	}
}
