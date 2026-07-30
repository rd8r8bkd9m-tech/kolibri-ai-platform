import { isSafePlatformAdminId } from "@/lib/server/platform-admin";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  context: { params: Promise<{ userId: string }> },
) {
  const { userId } = await context.params;
  if (!isSafePlatformAdminId(userId)) {
    return Response.json(
      { code: "user_not_found", message: "User was not found." },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/platform-admin/users/${encodeURIComponent(userId)}/sessions/revoke`,
    { method: "POST", maxRequestBytes: 1_024 },
  );
}
