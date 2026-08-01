import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PAYMENT_INTENT = /^payment_intent_[0-9a-f]{32}$/;

export async function GET(
	request: Request,
	context: { params: Promise<{ intentId: string }> },
) {
	const { intentId } = await context.params;
	if (!SAFE_PAYMENT_INTENT.test(intentId)) {
		return Response.json(
			{ code: "billing_payment_not_found", message: "Платёж не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(
		request,
		`/v1/billing/payment-intents/${encodeURIComponent(intentId)}`,
	);
}
