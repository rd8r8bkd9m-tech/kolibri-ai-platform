import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function GET(request: Request) {
  const query = new URL(request.url).search;
  return proxyV3JsonRequest(
    request,
    `/v1/platform-admin/trusted-agents/audit${query}`,
    { method: "GET" },
  );
}
