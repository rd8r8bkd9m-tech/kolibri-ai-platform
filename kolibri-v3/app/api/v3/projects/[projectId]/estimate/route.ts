import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

const projectPath = (projectId: string) =>
	`/v1/projects/${encodeURIComponent(projectId)}/estimate`;

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) {
		return Response.json(
			{ code: "estimate_not_found", message: "Смета не найдена." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	const source = new URL(request.url);
	const query = new URLSearchParams();
	for (const key of ["offset", "limit"] as const) {
		const value = source.searchParams.get(key);
		if (value !== null) {
			if (
				!/^\d{1,7}$/.test(value) ||
				(key === "limit" && (Number(value) < 1 || Number(value) > 100))
			) {
				return Response.json(
					{ code: "estimate_page_invalid", message: "Неверное окно строк сметы." },
					{ status: 400, headers: { "Cache-Control": "no-store" } },
				);
			}
			query.set(key, value);
		}
	}
	const suffix = query.size > 0 ? `?${query.toString()}` : "";
	return proxyV3JsonRequest(request, `${projectPath(projectId)}${suffix}`);
}

export async function PATCH(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) {
		return Response.json(
			{ code: "estimate_not_found", message: "Смета не найдена." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	const response = await proxyV3JsonRequest(request, projectPath(projectId), {
		maxRequestBytes: 256 * 1_024,
		method: "PATCH",
	});
	response.headers.set("Deprecation", "true");
	response.headers.set(
		"Link",
		`</api/v3/projects/${encodeURIComponent(projectId)}/estimate/rows>; rel="successor-version"`,
	);
	return response;
}
