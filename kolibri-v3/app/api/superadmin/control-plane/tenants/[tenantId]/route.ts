import { isSafePlatformAdminId } from "@/lib/server/platform-admin";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ tenantId: string }> },
) {
  const { tenantId } = await context.params;
  if (!isSafePlatformAdminId(tenantId)) {
    return Response.json(
      { code: "tenant_not_found", message: "Tenant was not found." },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/platform-admin/tenants/${encodeURIComponent(tenantId)}`,
    { method: "PATCH", maxRequestBytes: 64 * 1024 },
  );
}
