import { isSafePlatformAdminId } from "@/lib/server/platform-admin";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
	_request: Request,
	context: { params: Promise<{ modelId: string }> },
) {
	const { modelId } = await context.params;
	if (!isSafePlatformAdminId(modelId)) {
		return Response.json(
			{ code: "platform_model_not_found", message: "Model was not found." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(
		_request,
		`/v1/platform-admin/models/${encodeURIComponent(modelId)}/test`,
		{ method: "POST", maxRequestBytes: 1_024 },
	);
}
