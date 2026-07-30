import { isSafeProductChatId } from "@/lib/product-chat/contracts";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(
  request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const { runId } = await context.params;
  if (!isSafeProductChatId(runId)) {
    return Response.json(
      {
        code: "run_not_found",
        message: "Задача не найдена.",
      },
      {
        status: 404,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  return proxyV3JsonRequest(
    request,
    `/v1/chat/runs/${encodeURIComponent(runId)}/events`,
    { method: "GET" },
  );
}
