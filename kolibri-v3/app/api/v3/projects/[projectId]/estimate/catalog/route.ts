import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

function path(projectId: string, request: Request) {
	const source = new URL(request.url);
	const target = new URLSearchParams();
	for (const key of ["query", "kind", "categoryId", "region", "source", "limit"]) {
		const value = source.searchParams.get(key);
		if (value) target.set(key, value.slice(0, 160));
	}
	const suffix = target.toString() ? `?${target.toString()}` : "";
	return `/v1/projects/${encodeURIComponent(projectId)}/estimate/catalog${suffix}`;
}

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) {
		return Response.json(
			{ code: "project_not_found", message: "Проект не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(request, path(projectId, request));
}

export async function POST(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) {
		return Response.json(
			{ code: "project_not_found", message: "Проект не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/catalog/candidates`,
		{ maxRequestBytes: 32 * 1_024, method: "POST" },
	);
}
