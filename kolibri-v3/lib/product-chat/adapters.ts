import {
  ExportedMessageRepository,
  type FeedbackAdapter,
  type ExportedMessageRepository as ExportedMessageRepositoryValue,
  type ThreadHistoryAdapter,
  type ThreadMessage,
} from "@assistant-ui/react";
import { fromAgUiMessages } from "@assistant-ui/react-ag-ui";
import type {
  ProductChatClient,
} from "./client";
import type {
  ProductChatMessagePage,
  ProductChatThread,
} from "./contracts";

export type ProductChatHydration = {
  readonly repository: ExportedMessageRepositoryValue;
  readonly messages: readonly ThreadMessage[];
};

export const hydrateProductChatMessages = (
  page: ProductChatMessagePage,
): ProductChatHydration => {
  const converted = fromAgUiMessages(
    page.messages.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
    })),
    { showThinking: false },
  );

  if (converted.length !== page.messages.length) {
    throw new Error("Product Chat history could not be reconstructed.");
  }

  const repository = ExportedMessageRepository.fromArray(
    converted.map((message, index) => ({
      ...message,
      id: page.messages[index]!.id,
      createdAt: new Date(page.messages[index]!.createdAt),
      ...(page.messages[index]!.submittedFeedback &&
      message.role === "assistant"
        ? {
            metadata: {
              ...message.metadata,
              submittedFeedback: {
                type: page.messages[index]!.submittedFeedback,
              },
            },
          }
        : null),
    })),
  );

  return {
    repository,
    messages: repository.messages.map(({ message }) => message),
  };
};

export const toAgUiThreadData = (
  thread: ProductChatThread,
) => ({
  id: thread.id,
  remoteId: thread.id,
  status: thread.status,
  title: thread.title,
  lastMessageAt: thread.lastMessageAt
    ? new Date(thread.lastMessageAt)
    : undefined,
  custom: {
    projectId: thread.projectId,
    createdAt: thread.createdAt,
    updatedAt: thread.updatedAt,
    pinned: thread.pinned,
  },
});

export type ProductChatHistoryAdapterOptions = {
  readonly client: ProductChatClient;
  readonly resolveInitialThread: () => Promise<{
    readonly threadId: string;
    readonly persisted: boolean;
  } | null>;
};

/**
 * Product/Data persists both sides of the conversation in the AG-UI
 * transaction. The adapter only reloads that ledger; append deliberately
 * does not create a browser-owned second history.
 */
export const createProductChatHistoryAdapter = ({
  client,
  resolveInitialThread,
}: ProductChatHistoryAdapterOptions): ThreadHistoryAdapter => ({
  async load() {
    const selected = await resolveInitialThread();
    if (!selected || !selected.persisted) {
      return { messages: [] };
    }
    return hydrateProductChatMessages(
      await client.listMessages(selected.threadId),
    ).repository;
  },

  async append() {
    // The backend atomically persists the AG-UI user message and run.
  },
});

export const createProductChatFeedbackAdapter = ({
  client,
  resolveActiveThreadId,
  onError,
}: {
  readonly client: ProductChatClient;
  readonly resolveActiveThreadId: () => string | null;
  readonly onError?: (error: unknown) => void;
}): FeedbackAdapter => ({
  submit({ message, type }) {
    const threadId = resolveActiveThreadId();
    if (!threadId) return;
    void client
      .submitMessageFeedback(threadId, message.id, type)
      .catch((error: unknown) => onError?.(error));
  },
});
