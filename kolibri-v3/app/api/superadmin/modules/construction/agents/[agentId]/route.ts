import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const AGENT_ID = /^[a-z0-9][a-z0-9._-]{2,127}$/;

export async function PATCH(
	request: Request,
	context: { params: Promise<{ agentId: string }> },
) {
	const { agentId } = await context.params;
	if (!AGENT_ID.test(agentId)) {
		return Response.json(
			{
				code: "construction_agent_not_found",
				message: "Construction agent was not found.",
			},
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(
		request,
		`/v1/platform-admin/modules/construction/agents/${agentId}`,
		{ method: "PATCH", maxRequestBytes: 40 * 1_024 },
	);
}
