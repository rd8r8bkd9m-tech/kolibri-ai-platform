import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) {
		return Response.json({ code: "project_not_found", message: "Проект не найден." }, { status: 404 });
	}
	const source = new URL(request.url);
	const scope = source.searchParams.get("scope");
	const suffix = scope ? `?scope=${encodeURIComponent(scope.slice(0, 64))}` : "";
	return proxyV3JsonRequest(request, `/v1/projects/${encodeURIComponent(projectId)}/estimate/consent${suffix}`);
}

export async function POST(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) {
		return Response.json({ code: "project_not_found", message: "Проект не найден." }, { status: 404 });
	}
	return proxyV3JsonRequest(request, `/v1/projects/${encodeURIComponent(projectId)}/estimate/consent`, { maxRequestBytes: 8 * 1_024, method: "POST" });
}
