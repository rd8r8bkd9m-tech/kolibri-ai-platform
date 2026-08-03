import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

const notFound = () =>
	Response.json(
		{
			code: "estimate_generation_not_found",
			message: "Запуск формирования сметы не найден.",
		},
		{ status: 404, headers: { "Cache-Control": "no-store" } },
	);

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string }> },
) {
	const { projectId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId)) return notFound();
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/generation`,
		{ method: "GET" },
	);
}
