import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

export async function GET(
  request: Request,
  context: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await context.params;
  if (!SAFE_PROJECT_ID.test(projectId)) {
    return Response.json(
      { code: "estimate_not_found", message: "Смета не найдена." },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    `/v1/projects/${encodeURIComponent(projectId)}/estimate/versions`,
  );
}
