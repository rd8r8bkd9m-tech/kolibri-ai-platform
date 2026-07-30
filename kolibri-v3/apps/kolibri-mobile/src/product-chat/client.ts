import { API_BASE_URL, MobileApiError } from "@/src/auth/mobile-session";
import {
  isSafeProductId,
  parseMessagePage,
  parseThreadPage,
} from "@/src/product-chat/contracts";

export type AuthorizedFetch = typeof fetch;
export type ThreadAction =
  | "archive"
  | "unarchive"
  | "pin"
  | "unpin"
  | "remove";

const readError = async (response: Response) => {
  try {
    const value = (await response.clone().json()) as {
      code?: unknown;
      message?: unknown;
      detail?: { code?: unknown; message?: unknown };
    };
    const error = value.detail ?? value;
    return new MobileApiError(
      response.status,
      typeof error.code === "string"
        ? error.code
        : `http_${response.status}`,
      typeof error.message === "string"
        ? error.message
        : "Не удалось загрузить данные чата.",
    );
  } catch {
    return new MobileApiError(
      response.status,
      `http_${response.status}`,
      "Не удалось загрузить данные чата.",
    );
  }
};

export class ProductChatClient {
  constructor(private readonly request: AuthorizedFetch) {}

  private async json(path: string) {
    const response = await this.request(`${API_BASE_URL}/v1/chat${path}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw await readError(response);
    return response.json() as Promise<unknown>;
  }

  async listThreads() {
    return parseThreadPage(await this.json("/threads"));
  }

  async listMessages(threadId: string) {
    if (!isSafeProductId(threadId)) throw new Error("Invalid thread ID.");
    return parseMessagePage(
      await this.json(`/threads/${encodeURIComponent(threadId)}/messages`),
      threadId,
    );
  }

  async updateThread(threadId: string, action: ThreadAction) {
    if (!isSafeProductId(threadId)) throw new Error("Invalid thread ID.");
    const response = await this.request(
      `${API_BASE_URL}/v1/chat/threads/${encodeURIComponent(threadId)}`,
      {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ action }),
      },
    );
    if (!response.ok) throw await readError(response);
    if (response.status !== 204) {
      throw new Error("Product Chat returned an invalid mutation response.");
    }
  }

  async cancelRun(runId: string) {
    if (!isSafeProductId(runId)) throw new Error("Invalid run ID.");
    const response = await this.request(
      `${API_BASE_URL}/v1/chat/runs/${encodeURIComponent(runId)}/cancel`,
      {
        method: "POST",
        headers: { Accept: "application/json" },
      },
    );
    if (!response.ok) throw await readError(response);
    if (response.status !== 204) {
      throw new Error("Product Chat returned an invalid cancel response.");
    }
  }
}
