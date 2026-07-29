import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export function PUT(request: Request) {
  return proxyV3JsonRequest(request, "/v1/profile/agent-profile", {
    maxRequestBytes: 2_048,
  });
}
