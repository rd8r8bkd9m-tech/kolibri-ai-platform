import type { NextRequest } from "next/server";

import {
	fetchV3Backend,
	relayV3BackendResponse,
	v3BackendUnavailableResponse,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PAYMENT_INTENT = /^payment_intent_[0-9a-f]{32}$/;
const SAFE_NONCE = /^[0-9a-f]{64}$/;

export async function GET(
	request: NextRequest,
	context: { params: Promise<{ intentId: string }> },
) {
	const { intentId } = await context.params;
	const source = request.nextUrl.searchParams;
	const nonce = source.get("nonce") ?? "";
	const providerResult = source.get("providerResult") ?? "";
	const returnSurface = source.get("returnSurface") ?? "web";
	if (
		!SAFE_PAYMENT_INTENT.test(intentId) ||
		!SAFE_NONCE.test(nonce) ||
		(providerResult !== "success" && providerResult !== "fail") ||
		(returnSurface !== "web" && returnSurface !== "pwa")
	) {
		return Response.json(
			{ code: "billing_return_not_found", message: "Платёж не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	const query = new URLSearchParams({ nonce, providerResult });
	try {
		const upstream = await fetchV3Backend(
			request,
			`/v1/billing/tbank/return/${encodeURIComponent(intentId)}?${query.toString()}`,
		);
		if (upstream.status !== 200 && upstream.status !== 202) {
			return relayV3BackendResponse(upstream);
		}

		await upstream.body?.cancel();
		const destination =
			returnSurface === "pwa"
				? new URLSearchParams({
						client: "mobile",
						paymentIntent: intentId,
					})
				: new URLSearchParams({
						account: "billing",
						paymentIntent: intentId,
					});
		const destinationPath = returnSurface === "pwa" ? "/account" : "/app";
		return new Response(null, {
			status: 303,
			headers: {
				"Cache-Control": "no-store",
				Location: `${destinationPath}?${destination.toString()}`,
				"Referrer-Policy": "no-referrer",
			},
		});
	} catch {
		return v3BackendUnavailableResponse();
	}
}
