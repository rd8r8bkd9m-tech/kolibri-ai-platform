import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export function POST(request: Request) {
  return proxyV3JsonRequest(request, "/v1/auth/register", {
    maxRequestBytes: 16 * 1_024,
  });
}
