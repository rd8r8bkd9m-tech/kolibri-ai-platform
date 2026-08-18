import { API_BASE_URL, MobileApiError } from "@/src/auth/mobile-session";
import type { AuthorizedFetch } from "@/src/product-chat/client";
import {
	estimatePatchBody,
	NATIVE_ESTIMATE_PAGE_SIZE,
	parseEstimate,
	parseEstimateCatalog,
	type NativeEstimate,
	type NativeEstimateRow,
} from "@/src/verticals/construction-estimates/contracts";
import {
	estimateExportMediaType,
	isEstimateExportFormat,
	type EstimateExportFormat,
	type EstimateExportResult,
} from "@/src/verticals/construction-estimates/export";

const SAFE_PROJECT_ID = /^project_[A-Za-z0-9._~-]{8,96}$/;

const responseError = async (response: Response) => {
	try {
		const value = (await response.clone().json()) as {
			code?: unknown;
			message?: unknown;
			detail?: { code?: unknown; message?: unknown };
		};
		const detail = value.detail ?? value;
		return new MobileApiError(
			response.status,
			typeof detail.code === "string" ? detail.code : `http_${response.status}`,
			typeof detail.message === "string"
				? detail.message
				: "Не удалось загрузить смету.",
		);
	} catch {
		return new MobileApiError(
			response.status,
			`http_${response.status}`,
			"Не удалось загрузить смету.",
		);
	}
};

export class ConstructionEstimateClient {
	constructor(private readonly request: AuthorizedFetch) {}

	async list() {
		const response = await this.request(`${API_BASE_URL}/v1/documents`, {
			headers: { Accept: "application/json" },
		});
		if (!response.ok) throw await responseError(response);
		return parseEstimateCatalog(await response.json());
	}

	async open(
		projectId: string,
		options: { offset?: number; limit?: number } = {},
	) {
		if (!SAFE_PROJECT_ID.test(projectId)) {
			throw new Error("Invalid estimate project ID.");
		}
		const query = new URLSearchParams({
			offset: String(Math.max(0, Math.trunc(options.offset ?? 0))),
			limit: String(
				Math.min(
					NATIVE_ESTIMATE_PAGE_SIZE,
					Math.max(1, Math.trunc(options.limit ?? NATIVE_ESTIMATE_PAGE_SIZE)),
				),
			),
		});
		const response = await this.request(
			`${API_BASE_URL}/v1/projects/${encodeURIComponent(projectId)}/estimate?${query.toString()}`,
			{ headers: { Accept: "application/json" } },
		);
		if (!response.ok) throw await responseError(response);
		return parseEstimate(await response.json());
	}

	async save(
		estimate: NativeEstimate,
		title: string,
		rows: readonly NativeEstimateRow[],
	) {
		const body = estimatePatchBody(estimate, title, rows);
		if (
			body.title === undefined &&
			body.upsertRows.length === 0 &&
			body.deleteRowIds.length === 0
		) {
			return this.open(estimate.projectId, body.returnPage);
		}
		const response = await this.request(
			`${API_BASE_URL}/v1/projects/${encodeURIComponent(estimate.projectId)}/estimate/rows`,
			{
				method: "PATCH",
				headers: {
					Accept: "application/json",
					"Content-Type": "application/json",
				},
				body: JSON.stringify(body),
			},
		);
		if (!response.ok) throw await responseError(response);
		return parseEstimate(await response.json());
	}

	async export(
		projectId: string,
		format: EstimateExportFormat,
		version?: number,
	): Promise<EstimateExportResult> {
		if (!SAFE_PROJECT_ID.test(projectId)) {
			throw new Error("Invalid estimate project ID.");
		}
		if (!isEstimateExportFormat(format)) {
			throw new Error("Unsupported estimate export format.");
		}
		const query = new URLSearchParams();
		if (version !== undefined && Number.isInteger(version) && version >= 1) {
			query.set("version", String(version));
		}
		const suffix = query.toString() ? `?${query.toString()}` : "";
		const response = await this.request(
			`${API_BASE_URL}/v1/projects/${encodeURIComponent(projectId)}/estimate/export/${format}${suffix}`,
			{ headers: { Accept: estimateExportMediaType(format) } },
		);
		if (!response.ok) throw await responseError(response);
		const blob = await response.blob();
		const disposition = response.headers.get("content-disposition") ?? "";
		const utfName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
		const fallbackName = disposition.match(/filename="([^"]+)"/i)?.[1];
		const filename = decodeURIComponent(
			utfName ?? fallbackName ?? `estimate.${format}`,
		);
		return {
			blob,
			filename,
			mimeType:
				response.headers.get("content-type") ?? estimateExportMediaType(format),
			format,
			version:
				version ??
				Number.parseInt(
					response.headers.get("x-kolibri-estimate-version") ?? "1",
					10,
				),
		};
	}
}
