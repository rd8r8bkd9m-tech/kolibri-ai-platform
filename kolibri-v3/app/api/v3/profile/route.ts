import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export function GET(request: Request) {
  return proxyV3JsonRequest(request, "/v1/profile");
}

export function PATCH(request: Request) {
  return proxyV3JsonRequest(request, "/v1/profile", {
    maxRequestBytes: 16 * 1_024,
  });
}
