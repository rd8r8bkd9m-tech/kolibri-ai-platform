import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";

const storageState = process.env.KOLIBRI_E2E_QA_STORAGE_STATE;
if (!storageState) {
	throw new Error(
		"KOLIBRI_E2E_QA_STORAGE_STATE must point to an authenticated, entitled QA account with a live GPT or MiMo connection.",
	);
}
if (!existsSync(storageState)) {
	throw new Error(`QA storage state does not exist: ${storageState}`);
}

const executable = process.platform === "win32" ? "npx.cmd" : "npx";
const result = spawnSync(
	executable,
	[
		"playwright",
		"test",
		"--config",
		"playwright.config.ts",
			"tests/e2e/full-estimate-live.spec.ts",
			"--project=desktop-1363x936",
			"--workers=1",
			"--reporter=line",
	],
	{
		stdio: "inherit",
		env: {
			...process.env,
			KOLIBRI_E2E_LIVE_ESTIMATE: "1",
		},
	},
);
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
