import {
  API_BASE_URL,
  MobileApiError,
} from "@/src/auth/mobile-session";
import type { AuthorizedFetch } from "@/src/product-chat/client";
import {
  estimatePatchBody,
  parseEstimate,
  parseEstimateCatalog,
  type NativeEstimate,
  type NativeEstimateRow,
} from "@/src/verticals/construction-estimates/contracts";

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
      typeof detail.code === "string"
        ? detail.code
        : `http_${response.status}`,
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

  async open(projectId: string) {
    if (!SAFE_PROJECT_ID.test(projectId)) {
      throw new Error("Invalid estimate project ID.");
    }
    const response = await this.request(
      `${API_BASE_URL}/v1/projects/${encodeURIComponent(projectId)}/estimate`,
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
    const response = await this.request(
      `${API_BASE_URL}/v1/projects/${encodeURIComponent(estimate.projectId)}/estimate`,
      {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(estimatePatchBody(estimate, title, rows)),
      },
    );
    if (!response.ok) throw await responseError(response);
    return parseEstimate(await response.json());
  }
}
