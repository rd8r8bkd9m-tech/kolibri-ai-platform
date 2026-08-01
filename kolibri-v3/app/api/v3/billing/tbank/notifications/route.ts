import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Public bank-to-server callback. Authentication is the T-Bank Token verified
 * by the backend against its server-only password; browser CSRF is neither
 * required nor synthesized here. The bounded proxy preserves the exact JSON
 * bytes and content type so signature canonicalization happens once, in the
 * billing authority.
 */
export function POST(request: Request) {
	return proxyV3JsonRequest(
		request,
		"/v1/billing/tbank/notifications",
		{ maxRequestBytes: 64 * 1_024 },
	);
}
