import { proxyV3JsonRequest } from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_ISSUE_ID = /^estimate_issue_[A-Za-z0-9]{32}$/;

export async function GET(
	request: Request,
	context: { params: Promise<{ projectId: string; issueId: string }> },
) {
	const { projectId, issueId } = await context.params;
	if (!SAFE_PROJECT_ID.test(projectId) || !SAFE_ISSUE_ID.test(issueId)) {
		return Response.json(
			{ code: "document_issue_not_found", message: "Выпуск документа не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	return proxyV3JsonRequest(
		request,
		`/v1/projects/${encodeURIComponent(projectId)}/estimate/document-pack/${encodeURIComponent(issueId)}`,
		{ method: "GET" },
	);
}
