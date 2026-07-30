import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_ROLES = new Set(["client", "contractor"]);

export async function PUT(
  request: Request,
  context: { params: Promise<{ projectId: string; role: string }> },
) {
  const { projectId, role } = await context.params;
  if (!SAFE_PROJECT_ID.test(projectId) || !SAFE_ROLES.has(role)) {
    return Response.json(
      {
        code: "project_party_role_not_found",
        message: "Роль участника не найдена.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/projects/${encodeURIComponent(projectId)}/parties/${role}`,
    { maxRequestBytes: 16 * 1_024, method: "PUT" },
  );
}
