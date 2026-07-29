import { isSafeProductChatId } from "@/lib/product-chat/contracts";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function PATCH(
  request: Request,
  context: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await context.params;
  if (!isSafeProductChatId(threadId)) {
    return Response.json(
      {
        code: "thread_not_found",
        message: "Диалог не найден.",
      },
      {
        status: 404,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  return proxyV3JsonRequest(
    request,
    `/v1/chat/threads/${encodeURIComponent(threadId)}`,
    { maxRequestBytes: 1_024, method: "PATCH" },
  );
}
