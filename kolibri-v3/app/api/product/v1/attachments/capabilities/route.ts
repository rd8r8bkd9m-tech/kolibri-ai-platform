import {
  proxyV3JsonRequest,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_THREAD_ID =
  /^thread_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;

export async function GET(request: Request) {
  const url = new URL(request.url);
  const projectId = url.searchParams.get("projectId") ?? "";
  const threadId = url.searchParams.get("threadId") ?? "";
  if (
    !SAFE_PROJECT_ID.test(projectId) ||
    !SAFE_THREAD_ID.test(threadId)
  ) {
    return Response.json(
      {
        code: "attachment_scope_not_found",
        message: "Вложения недоступны для этой задачи.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  const query = new URLSearchParams({ projectId, threadId });
  return proxyV3JsonRequest(
    request,
    `/v1/attachments/capabilities?${query}`,
  );
}
