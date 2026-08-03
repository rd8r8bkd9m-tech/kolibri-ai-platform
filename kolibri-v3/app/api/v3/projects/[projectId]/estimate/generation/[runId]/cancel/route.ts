import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_RUN_ID = /^run_estimate_generation_[0-9a-f]{32}$/;

const notFound = () =>
	Response.json(
		{
			code: "estimate_generation_not_found",
			message: "Запуск формирования сметы не найден.",
		},
		{ status: 404, headers: { "Cache-Control": "no-store" } },
	);

export async function POST(
	request: Request,
	context: { params: Promise<{ projectId: string; runId: string }> },
) {
	const { projectId, runId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId) || !SAFE_RUN_ID.test(runId)) {
		return notFound();
	}
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/generation/${encodeURIComponent(runId)}/cancel`,
		{ method: "POST", maxRequestBytes: 4 * 1_024 },
	);
}
