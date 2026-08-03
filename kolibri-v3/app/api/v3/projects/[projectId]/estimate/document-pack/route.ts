import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

function invalidProject() {
	return Response.json(
		{ code: "project_not_found", message: "Проект не найден." },
		{ status: 404, headers: { "Cache-Control": "no-store" } },
	);
}

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) return invalidProject();
	const source = new URL(request.url);
	const limit = source.searchParams.get("limit");
	const suffix = limit ? `?limit=${encodeURIComponent(limit.slice(0, 3))}` : "";
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/document-pack${suffix}`,
		{ method: "GET" },
	);
}

export async function POST(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) return invalidProject();
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/document-pack`,
		{ method: "POST", maxRequestBytes: 32 * 1_024 },
	);
}
