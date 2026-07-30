import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export function POST(request: Request) {
  return proxyV3JsonRequest(
    request,
    "/v1/platform-admin/storage/operations/reconcile",
    { method: "POST", maxRequestBytes: 1 * 1_024 },
  );
}
