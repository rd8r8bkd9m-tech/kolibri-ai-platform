import { isWorkspaceBindingId } from "@/app/api/superadmin/trusted-agents/identifiers";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(
  request: Request,
  context: { params: Promise<{ bindingId: string }> },
) {
  const { bindingId } = await context.params;
  if (!isWorkspaceBindingId(bindingId)) {
    return Response.json(
      {
        code: "trusted_agent_binding_not_found",
        message: "Workspace binding was not found.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/platform-admin/trusted-agents/workspace-bindings/${bindingId}/revoke`,
    { method: "POST", maxRequestBytes: 1_024 },
  );
}
