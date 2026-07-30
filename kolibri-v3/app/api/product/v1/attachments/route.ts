import {
  fetchV3Backend,
  relayV3BackendResponse,
  v3BackendUnavailableResponse,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const R1_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;

export async function POST(request: Request) {
  const declaredLength = Number(request.headers.get("content-length"));
  if (
    Number.isFinite(declaredLength) &&
    declaredLength > R1_ATTACHMENT_MAX_BYTES
  ) {
    return Response.json(
      {
        code: "attachment_too_large",
        message: "R1 принимает вложения размером до 10 МиБ.",
      },
      { status: 413, headers: { "Cache-Control": "no-store" } },
    );
  }
  if (!request.body) {
    return Response.json(
      {
        code: "attachment_empty",
        message: "Нельзя прикрепить пустой файл.",
      },
      { status: 422, headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    const upstream = await fetchV3Backend(request, "/v1/attachments", {
      method: "POST",
      body: request.body,
    });
    return relayV3BackendResponse(upstream);
  } catch {
    return v3BackendUnavailableResponse();
  }
}
