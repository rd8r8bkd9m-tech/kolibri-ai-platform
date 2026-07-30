import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: Request) {
  const source = new URL(request.url).searchParams;
  const target = new URLSearchParams();
  const region = source.get("region")?.trim();
  const query = source.get("query")?.trim();
  const limit = source.get("limit")?.trim();
  if (region && region.length <= 160) target.set("region", region);
  if (query && query.length <= 160) target.set("query", query);
  if (limit && /^(?:[1-9]|[1-9]\d|100)$/.test(limit)) {
    target.set("limit", limit);
  }
  const suffix = target.size > 0 ? `?${target.toString()}` : "";
  return proxyV3JsonRequest(request, `/v1/pricing/catalog${suffix}`);
}
