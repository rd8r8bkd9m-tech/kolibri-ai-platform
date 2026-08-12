import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * User-owned auto-renew toggle. The mutation is authorized by the browser
 * session (CSRF/bearer) and validated by the billing domain against the
 * subject's own subscription row.
 */
export async function POST(
	request: Request,
	context: { params: Promise<{ subscriptionId: string }> },
) {
	const { subscriptionId: rawSubscriptionId } = await context.params;
	const subscriptionId = encodeURIComponent(rawSubscriptionId);
	return proxyV3JsonRequest(
		request,
		`/v1/billing/subscriptions/${subscriptionId}/auto-renew`,
		{ method: "POST" },
	);
}
