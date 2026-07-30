export const dynamic = "force-dynamic";
export const revalidate = 0;

const RESPONSE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
  "Content-Type": "application/json; charset=utf-8",
  Pragma: "no-cache",
  "X-Content-Type-Options": "nosniff",
};

function livenessResponse(head: boolean) {
  return new Response(
    head
      ? null
      : JSON.stringify({
          status: "ok",
          service: "kolibri-v3",
          component: "frontend",
        }),
    {
      status: 200,
      headers: RESPONSE_HEADERS,
    },
  );
}

export function GET() {
  return livenessResponse(false);
}

export function HEAD() {
  return livenessResponse(true);
}
