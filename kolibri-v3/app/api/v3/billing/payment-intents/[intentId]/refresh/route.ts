import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * User-owned fallback status check. The backend asks T-Bank GetState for the
 * subject's own intent and applies the verified result, so a blocked return
 * redirect or a missed webhook never leaves the checkout stuck.
 */
export async function POST(
	request: Request,
	context: { params: Promise<{ intentId: string }> },
) {
	const { intentId: rawIntentId } = await context.params;
	const intentId = encodeURIComponent(rawIntentId);
	return proxyV3JsonRequest(
		request,
		`/v1/billing/payment-intents/${intentId}/refresh`,
		{ method: "POST" },
	);
}
