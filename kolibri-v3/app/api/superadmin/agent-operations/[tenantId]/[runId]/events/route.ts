import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_OPERATION_ID = /^[A-Za-z0-9][A-Za-z0-9._:~-]{0,191}$/;

export async function GET(
	request: Request,
	context: { params: Promise<{ runId: string; tenantId: string }> },
) {
	const { runId, tenantId } = await context.params;
	if (!SAFE_OPERATION_ID.test(tenantId) || !SAFE_OPERATION_ID.test(runId)) {
		return Response.json(
			{
				code: "agent_operation_not_found",
				message: "Агентная задача не найдена.",
			},
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	const query = new URL(request.url).search;
	return proxyV3JsonRequest(
		request,
		`/v1/platform-admin/agent-operations/${encodeURIComponent(tenantId)}/${encodeURIComponent(runId)}/events${query}`,
		{ method: "GET" },
	);
}
