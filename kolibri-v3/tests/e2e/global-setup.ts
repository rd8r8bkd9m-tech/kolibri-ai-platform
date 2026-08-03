import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { request, type FullConfig } from "@playwright/test";

const outputDirectory = "output/playwright";
const statePath = `${outputDirectory}/qa-storage-state.json`;
const metadataPath = `${outputDirectory}/qa-tenant.json`;

function isLocalBaseUrl(baseURL: string): boolean {
	const hostname = new URL(baseURL).hostname;
	return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1";
}

export default async function globalSetup(config: FullConfig) {
	const baseURL = String(config.projects[0]?.use.baseURL ?? "");
	if (!baseURL) throw new Error("KOLIBRI_E2E_BASE_URL is required");
	if (process.env.KOLIBRI_E2E_QA_STORAGE_STATE) return;

	if (!isLocalBaseUrl(baseURL)) {
		throw new Error(
			"Remote E2E requires an externally provisioned QA storage state; automatic production registration is forbidden.",
		);
	}

	await mkdir(outputDirectory, { recursive: true });
	const api = await request.newContext({
		baseURL,
		extraHTTPHeaders: { Origin: new URL(baseURL).origin },
	});
	try {
		const unique = `${Date.now()}-${process.pid}`;
		const response = await api.post("/api/v3/auth/register", {
			data: {
				email: `desktop-acceptance-${unique}+qa@example.com`,
				name: "[QA] Desktop Acceptance",
				password: `qa-only-${unique}-correct-horse`,
			},
		});
		if (response.status() !== 201) {
			throw new Error(`QA tenant registration failed with HTTP ${response.status()}`);
		}
		const body = (await response.json()) as {
			user?: { tenantId?: string; id?: string };
		};
		const tenantId = body.user?.tenantId;
		if (!tenantId) throw new Error("QA tenant registration omitted tenantId");
		execFileSync(
			"backend/venv/bin/python",
			[
				"-m",
				"app.qa_tenant_fixture",
				"--tenant-id",
				tenantId,
				"--confirm",
				`PREPARE QA TENANT ${tenantId}`,
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
		await api.storageState({ path: statePath });
		await writeFile(metadataPath, JSON.stringify({ tenantId }), { mode: 0o600 });
	} finally {
		await api.dispose();
	}
}
