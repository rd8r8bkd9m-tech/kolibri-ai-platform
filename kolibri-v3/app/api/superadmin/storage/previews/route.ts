import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function POST(request: Request) {
  return proxyV3JsonRequest(
    request,
    "/v1/platform-admin/storage/previews",
    { method: "POST", maxRequestBytes: 4 * 1_024 },
  );
}
