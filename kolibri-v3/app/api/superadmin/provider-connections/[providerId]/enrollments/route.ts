import { isProviderId } from "@/lib/provider-connections";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type EnrollmentRouteContext = {
  params: Promise<{ providerId: string }>;
};

export async function POST(
  request: NextRequest,
  context: EnrollmentRouteContext,
) {
  const { providerId } = await context.params;
  if (!isProviderId(providerId)) {
    return Response.json(
      { code: "provider_not_found", message: "Provider was not found." },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/provider-connections/${providerId}/enrollment-intents`,
    { method: "POST", maxRequestBytes: 2_048 },
  );
}
