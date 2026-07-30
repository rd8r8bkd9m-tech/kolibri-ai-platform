import {
  fetchV3Backend,
  relayV3BackendResponse,
  v3BackendUnavailableResponse,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_FORMATS = new Set(["pdf", "xlsx", "docx", "csv", "zip"]);

export async function GET(
  request: Request,
  context: { params: Promise<{ projectId: string; format: string }> },
) {
  const { projectId, format } = await context.params;
  if (!SAFE_PROJECT_ID.test(projectId) || !SAFE_FORMATS.has(format)) {
    return Response.json(
      {
        code: "estimate_export_not_found",
        message: "Формат экспорта не поддерживается.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const upstream = await fetchV3Backend(
      request,
      `/v1/projects/${encodeURIComponent(projectId)}/estimate/export/${format}`,
    );
    return relayV3BackendResponse(upstream);
  } catch {
    return v3BackendUnavailableResponse();
  }
}
