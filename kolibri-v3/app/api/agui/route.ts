import {
  fetchV3Backend,
  readBoundedRequestBody,
  relayV3BackendResponse,
  v3BackendUnavailableResponse,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const MAX_AG_UI_REQUEST_BYTES = 2 * 1_024 * 1_024;

export async function POST(request: Request) {
  try {
    const body = await readBoundedRequestBody(
      request,
      MAX_AG_UI_REQUEST_BYTES,
    );
    const upstream = await fetchV3Backend(request, "/v1/chat/ag-ui", {
      method: "POST",
      body,
    });

    if (upstream.ok) {
      const contentType =
        upstream.headers.get("content-type")?.toLowerCase() ?? "";
      if (
        !upstream.body ||
        !contentType.startsWith("text/event-stream")
      ) {
        await upstream.body?.cancel().catch(() => undefined);
        return Response.json(
          {
            code: "invalid_ag_ui_response",
            message: "Backend вернул некорректный поток ответа.",
          },
          {
            status: 502,
            headers: { "Cache-Control": "no-store" },
          },
        );
      }
    }

    return relayV3BackendResponse(upstream);
  } catch (error) {
    if (error instanceof RangeError) {
      return Response.json(
        {
          code: "request_too_large",
          message: "Запрос превышает допустимый размер.",
        },
        {
          status: 413,
          headers: { "Cache-Control": "no-store" },
        },
      );
    }
    return v3BackendUnavailableResponse();
  }
}
