import { isSafeProductChatId } from "@/lib/product-chat/contracts";
import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function PUT(
  request: Request,
  context: {
    params: Promise<{ threadId: string; messageId: string }>;
  },
) {
  const { threadId, messageId } = await context.params;
  if (
    !isSafeProductChatId(threadId) ||
    !isSafeProductChatId(messageId)
  ) {
    return Response.json(
      {
        code: "message_not_found",
        message: "Сообщение не найдено.",
      },
      {
        status: 404,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }

  return proxyV3JsonRequest(
    request,
    `/v1/chat/threads/${encodeURIComponent(threadId)}/messages/${encodeURIComponent(messageId)}/feedback`,
    { maxRequestBytes: 1_024, method: "PUT" },
  );
}
