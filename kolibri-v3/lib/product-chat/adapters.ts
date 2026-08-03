import {
	ExportedMessageRepository,
	type FeedbackAdapter,
	type ExportedMessageRepository as ExportedMessageRepositoryValue,
	type ThreadHistoryAdapter,
	type ThreadMessage,
	type ThreadMessageLike,
} from "@assistant-ui/react";
import { fromAgUiMessages } from "@assistant-ui/react-ag-ui";
import type { ProductChatClient } from "./client";
import type { ProductChatMessagePage, ProductChatThread } from "./contracts";

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

	const branchableMessages: Array<{
		message: ThreadMessageLike;
		parentId: string | null;
	}> = [];
	const importedIds = new Set<string>();
	let parentId: string | null = null;
	for (const [index, message] of converted.entries()) {
		const historical = page.messages[index]!;
		const hydratedId = historical.id;
		const hydrated: ThreadMessageLike = {
			...message,
			id: hydratedId,
			createdAt: new Date(historical.createdAt),
			...(historical.submittedFeedback && message.role === "assistant"
				? {
						metadata: {
							...message.metadata,
							submittedFeedback: {
								type: historical.submittedFeedback,
							},
						},
					}
				: null),
		};
		// The server contract normally guarantees unique message IDs. Keep the
		// client repository branch-safe if a legacy page violates that contract.
		if (importedIds.has(hydratedId)) continue;
		importedIds.add(hydratedId);
		branchableMessages.push({ message: hydrated, parentId });
		parentId = hydratedId;
	}

	const repository = ExportedMessageRepository.fromBranchableArray(
		branchableMessages,
		{ headId: parentId },
	);

	return {
		repository,
		messages: repository.messages.map(({ message }) => message),
	};
};

export const toAgUiThreadData = (thread: ProductChatThread) => ({
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
