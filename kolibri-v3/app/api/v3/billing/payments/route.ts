import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Read-only payment history for the signed-in subject. The backend never
 * includes a hosted payment URL in list views, so this route only forwards
 * the authenticated request to the billing authority.
 */
export function GET(request: Request) {
	const query = new URL(request.url).search;
	return proxyV3JsonRequest(
		request,
		`/v1/billing/payments${query}`,
		{ method: "GET" },
	);
}
