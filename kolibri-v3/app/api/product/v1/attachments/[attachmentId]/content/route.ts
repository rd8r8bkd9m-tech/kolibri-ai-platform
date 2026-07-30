import {
  fetchV3Backend,
  relayV3BackendResponse,
  v3BackendUnavailableResponse,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_ATTACHMENT_ID =
  /^attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;

export async function GET(
  request: Request,
  context: { params: Promise<{ attachmentId: string }> },
) {
  const { attachmentId } = await context.params;
  if (!SAFE_ATTACHMENT_ID.test(attachmentId)) {
    return Response.json(
      {
        code: "attachment_not_found",
        message: "Вложение не найдено.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const upstream = await fetchV3Backend(
      request,
      `/v1/attachments/${encodeURIComponent(attachmentId)}/content`,
    );
    return relayV3BackendResponse(upstream);
  } catch {
    return v3BackendUnavailableResponse();
  }
}
