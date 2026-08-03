import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_CANDIDATE_ID = /^catalog_candidate_[A-Za-z0-9._~-]{8,160}$/;

export async function POST(
	request: Request,
	context: {
		params: Promise<{ projectId: string; candidateId: string }>;
	},
) {
	const { projectId, candidateId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId) || !SAFE_CANDIDATE_ID.test(candidateId)) {
		return Response.json(
			{ code: "catalog_candidate_not_found", message: "Кандидат справочника не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/catalog/candidates/${encodeURIComponent(candidateId)}/review`,
		{ maxRequestBytes: 16 * 1_024, method: "POST" },
	);
}
