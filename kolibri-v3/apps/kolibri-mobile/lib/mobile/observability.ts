export type ClientErrorEntry = {
	retryId: string;
	message: string;
	createdAt: string;
};

export const createRetryId = () => {
	const random =
		globalThis.crypto?.randomUUID?.().replaceAll("-", "").slice(0, 10) ??
		Math.random().toString(36).slice(2, 10);
	return `mobile_${Date.now().toString(36)}_${random}`;
};

export const toClientError = (
	reason: unknown,
	fallback: string,
): ClientErrorEntry => {
	const message = reason instanceof Error ? reason.message : fallback;
	return {
		retryId: createRetryId(),
		message,
		createdAt: new Date().toISOString(),
	};
};

export const formatClientError = (entry: ClientErrorEntry) =>
	`${entry.message} (retry: ${entry.retryId})`;
