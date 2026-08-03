import {
	fetchV3Backend,
	relayV3BackendResponse,
	v3BackendUnavailableResponse,
} from "@/lib/server/v3-backend";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;
const SAFE_ISSUE_ID = /^estimate_issue_[A-Za-z0-9]{32}$/;
const SAFE_ARTIFACT_ID = /^estimate_artifact_[A-Za-z0-9]{32}$/;

export async function GET(
	request: Request,
	context: {
		params: Promise<{ projectId: string; issueId: string; artifactId: string }>;
	},
) {
	const { projectId, issueId, artifactId } = await context.params;
	if (
		!SAFE_PROJECT_ID.test(projectId) ||
		!SAFE_ISSUE_ID.test(issueId) ||
		!SAFE_ARTIFACT_ID.test(artifactId)
	) {
		return Response.json(
			{ code: "document_artifact_not_found", message: "Файл документа не найден." },
			{ status: 404, headers: { "Cache-Control": "no-store" } },
		);
	}
	try {
		const upstream = await fetchV3Backend(
			request,
			`/v1/projects/${encodeURIComponent(projectId)}/estimate/document-pack/${encodeURIComponent(issueId)}/artifacts/${encodeURIComponent(artifactId)}`,
		);
		return relayV3BackendResponse(upstream);
	} catch {
		return v3BackendUnavailableResponse();
	}
}
