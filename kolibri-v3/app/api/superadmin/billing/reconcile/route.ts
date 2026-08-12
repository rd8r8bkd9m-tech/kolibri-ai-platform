import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Owner-only GetState reconciliation for missed webhooks. Runs bounded,
 * idempotent provider checks and returns a summary of scanned/reconciled/
 * failed intents.
 */
export function POST(request: Request) {
	return proxyV3JsonRequest(
		request,
		"/v1/platform-admin/billing/reconcile",
		{ method: "POST" },
	);
}
