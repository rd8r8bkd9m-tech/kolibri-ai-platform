import { execFileSync } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import type { FullConfig } from "@playwright/test";

const statePath = "output/playwright/qa-storage-state.json";
const metadataPath = "output/playwright/qa-tenant.json";

function isLocalBaseUrl(baseURL: string): boolean {
	const hostname = new URL(baseURL).hostname;
	return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1";
}

export default async function globalTeardown(config: FullConfig) {
	if (process.env.KOLIBRI_E2E_QA_STORAGE_STATE) return;
	const baseURL = String(config.projects[0]?.use.baseURL ?? "");
	if (!baseURL || !isLocalBaseUrl(baseURL)) return;

	try {
		const metadata = JSON.parse(await readFile(metadataPath, "utf8")) as {
			tenantId?: string;
		};
		if (!metadata.tenantId) throw new Error("QA teardown metadata omitted tenantId");
		execFileSync(
			"backend/venv/bin/python",
			[
				"-m",
				"app.qa_tenant_archive",
				"--tenant-id",
				metadata.tenantId,
				"--confirm",
				`ARCHIVE QA TENANT ${metadata.tenantId}`,
			],
			{
				cwd: process.cwd(),
				env: {
					...process.env,
					PYTHONPATH: "backend",
					KOLIBRI_V3_DATABASE_URL: "sqlite:///./var/kolibri-v3.db",
				},
				stdio: "pipe",
			},
		);
	} finally {
		await Promise.all([
			rm(statePath, { force: true }),
			rm(metadataPath, { force: true }),
		]);
	}
}
