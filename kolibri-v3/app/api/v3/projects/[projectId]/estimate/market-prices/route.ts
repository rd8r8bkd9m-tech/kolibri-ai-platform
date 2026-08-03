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
	const target = new URLSearchParams();
	for (const key of ["itemKey", "catalogEntryId", "unit", "region", "country", "municipality", "quantityBand", "refresh"]) {
		const value = source.searchParams.get(key);
		if (value) target.set(key, value.slice(0, 160));
	}
	const suffix = target.toString() ? `?${target.toString()}` : "";
	return proxyV3JsonRequest(request, `/v1/projects/${encodeURIComponent(projectId)}/estimate/market-prices${suffix}`);
}
