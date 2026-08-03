import { fetchV3Backend, relayV3BackendResponse } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string; runId: string }> },
) {
	const { projectId, runId } = await context.params;
	if (!/^project_[A-Za-z0-9._~-]{8,96}$/.test(projectId) || !/^run_estimate_generation_[0-9a-f]{32}$/.test(runId)) {
		return Response.json({ code: "estimate_generation_not_found", message: "Запуск не найден." }, { status: 404 });
	}
	try {
		const upstream = await fetchV3Backend(
			request,
			`/v1/projects/${encodeURIComponent(projectId)}/estimate/generation/${encodeURIComponent(runId)}/events`,
			{ method: "GET" },
		);
		return relayV3BackendResponse(upstream);
	} catch {
		return Response.json({ code: "v3_backend_unavailable", message: "Backend недоступен." }, { status: 503 });
	}
}
