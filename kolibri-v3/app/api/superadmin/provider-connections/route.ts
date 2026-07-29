import { proxyV3JsonRequest } from "@/lib/server/v3-backend";
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  return proxyV3JsonRequest(request, "/v1/provider-connections", {
    method: "GET",
  });
}
