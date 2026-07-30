import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_ARTIFACT_ID =
  /^artifact_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}$/;
const SAFE_ARTIFACT_VERSION = /^[1-9][0-9]{0,9}$/;

export async function GET(
  request: Request,
  context: {
    params: Promise<{
      artifactId: string;
      artifactVersion: string;
    }>;
  },
) {
  const { artifactId, artifactVersion } = await context.params;
  if (
    !SAFE_ARTIFACT_ID.test(artifactId) ||
    !SAFE_ARTIFACT_VERSION.test(artifactVersion) ||
    Number(artifactVersion) > 2_147_483_647
  ) {
    return Response.json(
      {
        code: "artifact_not_found",
        message: "Артефакт не найден.",
      },
      { status: 404, headers: { "Cache-Control": "no-store" } },
    );
  }
  return proxyV3JsonRequest(
    request,
    (
      `/v1/artifacts/${encodeURIComponent(artifactId)}/versions/` +
      encodeURIComponent(artifactVersion)
    ),
    { method: "GET" },
  );
}
