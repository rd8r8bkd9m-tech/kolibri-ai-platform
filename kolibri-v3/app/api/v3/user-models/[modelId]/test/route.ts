import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
	_request: Request,
	context: { params: Promise<{ modelId: string }> },
) {
	const { modelId } = await context.params;
	return proxyV3JsonRequest(
		_request,
		`/v1/user-models/${encodeURIComponent(modelId)}/test`,
		{ method: "POST", maxRequestBytes: 1_024 },
	);
}
