import { API_BASE_URL, MobileApiError } from "@/src/auth/mobile-session";
import type { AuthorizedFetch } from "@/src/product-chat/client";
import {
	parseDocumentCatalog,
	type DocumentSummary,
} from "@/src/backend/documents/contracts";

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
				: "Не удалось загрузить документы.",
		);
	} catch {
		return new MobileApiError(
			response.status,
			`http_${response.status}`,
			"Не удалось загрузить документы.",
		);
	}
};

export class DocumentsClient {
	constructor(private readonly request: AuthorizedFetch) {}

	async list(): Promise<readonly DocumentSummary[]> {
		const response = await this.request(`${API_BASE_URL}/v1/documents`, {
			headers: { Accept: "application/json" },
		});
		if (!response.ok) throw await responseError(response);
		return parseDocumentCatalog(await response.json());
	}
}
