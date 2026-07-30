import { isTrustedAgentProfileId } from "@/app/api/superadmin/trusted-agents/identifiers";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  context: { params: Promise<{ profileId: string }> },
) {
  const { profileId } = await context.params;
  if (!isTrustedAgentProfileId(profileId)) {
    return Response.json(
      {
        code: "trusted_agent_profile_not_found",
        message: "Trusted-agent profile was not found.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/platform-admin/trusted-agents/profiles/${profileId}/revoke`,
    { method: "POST", maxRequestBytes: 1_024 },
  );
}
