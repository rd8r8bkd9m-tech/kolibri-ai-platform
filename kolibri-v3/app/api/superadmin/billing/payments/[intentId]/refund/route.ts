import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Owner-only full refund. The financial mutation is guarded server-side by
 * owner role + CSRF; this route only forwards the request and response.
 */
export async function POST(
	request: Request,
	context: { params: Promise<{ intentId: string }> },
) {
	const { intentId: rawIntentId } = await context.params;
	const intentId = encodeURIComponent(rawIntentId);
	return proxyV3JsonRequest(
		request,
		`/v1/platform-admin/billing/payments/${intentId}/refund`,
		{ method: "POST" },
	);
}
