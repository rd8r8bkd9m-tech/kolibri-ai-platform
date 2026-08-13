import { HttpAgent } from "@ag-ui/client";
import {
	AssistantRuntimeProvider,
	ExportedMessageRepository,
	type ThreadHistoryAdapter,
	type ThreadMessage,
} from "@assistant-ui/react-native";
import {
	fromAgUiMessages,
	useAgUiRuntime,
	type UseAgUiThreadListAdapter,
} from "@assistant-ui/react-ag-ui";
import {
	useCallback,
	createContext,
	useEffect,
	useMemo,
	useRef,
	useState,
	useContext,
	type PropsWithChildren,
} from "react";

import { API_BASE_URL, useMobileSession } from "@/src/auth/mobile-session";
import { ProductChatClient } from "@/src/product-chat/client";
import { MobileAttachmentClient } from "@/src/product-chat/attachments";
import {
	isSafeProductId,
	type ProductMessage,
	type ProductThread,
} from "@/src/product-chat/contracts";
import {
	clearPetActivityFeed,
	createPetActivityAgentSubscriber,
	publishPetMessageAccepted,
} from "@/src/pets/runtime-activity";

const AG_UI_URL = `${API_BASE_URL}/v1/chat/ag-ui`;
const SAFE_SHORT_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,123}$/;
const ATTACHMENT_CONTENT_PATH =
	/^\/api\/product\/v1\/attachments\/attachment_[A-Za-z0-9][A-Za-z0-9._~-]{5,127}\/content$/;
const MIME_TYPE =
	/^[a-z0-9][a-z0-9!#$&^_.+-]{0,126}\/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$/;

export type MobileDeveloperMode = "standard" | "auto" | "full";

export const MOBILE_DEV_MODE_CYCLE: readonly MobileDeveloperMode[] = [
	"standard",
	"auto",
	"full",
];

export const MOBILE_DEV_MODE_LABELS: Record<MobileDeveloperMode, string> = {
	standard: "Dev",
	auto: "Dev · Авто",
	full: "Dev · Полный",
};

const MOBILE_DEVELOPER_MODE_KEY = "kolibri.ui.mobile-developer-access-mode";

const readMobileDeveloperMode = (): MobileDeveloperMode => {
	if (typeof globalThis.localStorage === "undefined") return "full";
	const saved = globalThis.localStorage.getItem(MOBILE_DEVELOPER_MODE_KEY);
	return saved === "standard" || saved === "auto" || saved === "full"
		? saved
		: "full";
};

const persistMobileDeveloperMode = (next: MobileDeveloperMode) => {
	try {
		globalThis.localStorage?.setItem(MOBILE_DEVELOPER_MODE_KEY, next);
	} catch {
		// Storage can be blocked; the in-memory choice still applies.
	}
};

export const MobileDeveloperModeContext =
	createContext<{
		mode: MobileDeveloperMode;
		setMode: (next: MobileDeveloperMode) => void;
	}>({
		mode: "full",
		setMode: () => undefined,
	});

export const useMobileDeveloperMode = () =>
	useContext(MobileDeveloperModeContext);

type NormalizedContentPart =
	| { type: "text"; text: string }
	| {
			type: "image" | "document";
			source: { type: "url"; value: string; mimeType: string };
			metadata: { filename: string };
	  };

type Projection = {
	status: "inactive" | "loading" | "ready" | "error";
	threads: readonly ProductThread[];
	activeThreadId: string | null;
	draftThreadId: string | null;
};

type Bootstrap = {
	threadId: string;
	persisted: boolean;
};

type ProductChatContextValue = {
	readonly activeThreadId: string | null;
	readonly activeProjectId: string | null;
	readonly attachmentClient: MobileAttachmentClient;
};

const ProductChatContext = createContext<ProductChatContextValue | null>(null);

export function useProductChatContext() {
	const value = useContext(ProductChatContext);
	if (!value) throw new Error("useProductChatContext must be used in ProductRuntimeProvider.");
	return value;
}

const createDraftId = () => {
	const random =
		globalThis.crypto?.randomUUID?.().replaceAll("-", "") ??
		`${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
	return `thread_${random}`;
};

const normalizeId = (value: unknown, prefix: "run_" | "msg_") => {
	if (typeof value !== "string" || !SAFE_SHORT_ID.test(value)) return null;
	return value.length >= 8 ? value : `${prefix}${value}`;
};

const normalizeAgentProfile = (value: unknown) =>
	typeof value === "string" && /^[a-z0-9][a-z0-9._-]{1,95}$/.test(value)
		? value
		: "auto";

const normalizeAttachmentPart = (
	part: unknown,
): NormalizedContentPart | null => {
	if (typeof part !== "object" || part === null) return null;
	const value = part as Record<string, unknown>;
	if (value.type === "text" && typeof value.text === "string" && value.text.trim()) {
		return { type: "text", text: value.text };
	}

	let type: "image" | "document" | null = null;
	let rawValue: string | null = null;
	let mimeType: string | null = null;
	let filename: string | null = null;
	if (
		(value.type === "file" || value.type === "image") &&
		typeof (value.type === "file" ? value.data : value.image) === "string"
	) {
		rawValue = (value.type === "file" ? value.data : value.image) as string;
		mimeType =
			typeof value.mimeType === "string" ? value.mimeType : null;
		filename = typeof value.filename === "string" ? value.filename : null;
		type = mimeType?.startsWith("image/") || value.type === "image" ? "image" : "document";
	} else if (
		(value.type === "image" || value.type === "document") &&
		typeof value.source === "object" &&
		value.source !== null
	) {
		const source = value.source as Record<string, unknown>;
		rawValue = typeof source.value === "string" ? source.value : null;
		mimeType = typeof source.mimeType === "string" ? source.mimeType : null;
		const metadata = value.metadata;
		filename =
			typeof metadata === "object" && metadata !== null &&
			typeof (metadata as Record<string, unknown>).filename === "string"
				? ((metadata as Record<string, unknown>).filename as string)
				: null;
		type = value.type;
	}
	if (!type || !rawValue || !mimeType || !MIME_TYPE.test(mimeType) || !filename) {
		return null;
	}
	let contentPath: string;
	try {
		const parsed = new URL(rawValue, API_BASE_URL);
		if (parsed.origin !== new URL(API_BASE_URL).origin || parsed.search || parsed.hash) {
			return null;
		}
		contentPath = parsed.pathname;
	} catch {
		return null;
	}
	if (
		!ATTACHMENT_CONTENT_PATH.test(contentPath) ||
		filename.length > 240 ||
		/[/\\\0\r\n]/.test(filename)
	) {
		return null;
	}
	return {
		type,
		source: { type: "url", value: contentPath, mimeType },
		metadata: { filename },
	};
};

const normalizeMessages = (value: unknown) => {
	if (!Array.isArray(value)) return null;
	for (let index = value.length - 1; index >= 0; index -= 1) {
		const message = value[index];
		if (
			typeof message !== "object" ||
			message === null ||
			!("role" in message) ||
			message.role !== "user" ||
			!("id" in message)
		) {
			continue;
		}
		const id = normalizeId(message.id, "msg_");
		if (!id || !("content" in message)) return null;
		const rawParts = Array.isArray(message.content)
			? message.content
			: typeof message.content === "string"
				? [{ type: "text", text: message.content }]
				: [];
		const attachments =
			"attachments" in message && Array.isArray(message.attachments)
				? message.attachments.flatMap((attachment: unknown) =>
						typeof attachment === "object" &&
						attachment !== null &&
						"content" in attachment &&
						Array.isArray(attachment.content)
							? attachment.content
							: [],
					)
				: [];
		const content = [...rawParts, ...attachments]
			.flatMap((part: unknown) => {
				const normalized = normalizeAttachmentPart(part);
				return normalized ? [normalized] : [];
			});
		const textParts = content.filter(
			(part): part is { type: "text"; text: string } => part.type === "text",
		);
		const attachmentParts = content.filter((part) => part.type !== "text");
		if (textParts.length === 0 || attachmentParts.length > 10) return null;
		if (attachmentParts.length === 0 && typeof message.content === "string") {
			return [{ id, role: "user" as const, content: textParts[0]!.text }];
		}
		return [{ id, role: "user" as const, content }];
	}
	return null;
};

const hydrate = (messages: readonly ProductMessage[]) => {
	const converted = fromAgUiMessages(
		messages.map((message) => ({
			id: message.id,
			role: message.role,
			content: message.content,
		})),
		{ showThinking: true },
	);
	if (converted.length !== messages.length) {
		throw new Error("Product Chat history could not be reconstructed.");
	}
	// The server persists reasoning as a content part of the assistant
	// message. assistant-ui's snapshot converter keeps only text parts, so
	// re-inject the reasoning part to render one bubble: collapsed
	// «Рассуждение» plus the always-visible answer.
	const pairs = converted.map((message, index) => ({
		message,
		historical: messages[index]!,
	}));
	const mergedPairs = pairs.map(({ message, historical }) => {
		if (message.role !== "assistant") return { message, historical };
		const reasoningPart = historical.content.find(
			(part) =>
				part.type === "reasoning" &&
				typeof (part as { text?: unknown }).text === "string",
		);
		if (!reasoningPart) return { message, historical };
		return {
			message: {
				...message,
				content: [
					reasoningPart,
					...(Array.isArray(message.content)
						? message.content
						: []),
				],
			},
			historical,
		};
	});
	return ExportedMessageRepository.fromArray(
		mergedPairs.map(({ message, historical }) => ({
			...message,
			id: historical.id,
			createdAt: new Date(historical.createdAt),
		})),
	);
};

const createProductAgent = ({
	request,
	threadId,
	agentProfile,
	developerMode,
	onAccepted,
}: {
	request: typeof fetch;
	threadId: string;
	agentProfile: string;
	developerMode: MobileDeveloperMode;
	onAccepted: (runId: string) => void;
	}) =>
	new HttpAgent({
		url: AG_UI_URL,
		threadId,
		headers: { Accept: "text/event-stream" },
		fetch: async (input, init) => {
			if (typeof input !== "string" || input !== AG_UI_URL) {
				throw new Error("AG-UI attempted an unexpected endpoint.");
			}
			if (typeof init?.body !== "string") {
				throw new Error("AG-UI request must be JSON text.");
			}
			const raw = JSON.parse(init.body) as Record<string, unknown>;
			const runId = normalizeId(raw.runId, "run_");
			const messages = normalizeMessages(raw.messages);
			if (!runId || !messages) {
				throw new Error("AG-UI request has an incompatible shape.");
			}
			const payload = buildMobileAgUiPayload({
				threadId,
				runId,
				messages,
				agentProfile,
				developerMode,
			});
			const headers = new Headers(init.headers);
			headers.set("Accept", "text/event-stream");
			headers.set("Content-Type", "application/json");
			const response = await request(input, {
				...init,
				headers,
				body: JSON.stringify(payload),
			});
			if (response.ok) {
				const acceptedRunId = response.headers.get("x-kolibri-run-id");
				if (!isSafeProductId(acceptedRunId)) {
					await response.body?.cancel().catch(() => undefined);
					throw new Error("AG-UI did not identify the accepted run.");
				}
				onAccepted(acceptedRunId);
			}
			return response;
		},
	});

export const buildMobileAgUiPayload = ({
	threadId,
	runId,
	messages,
	agentProfile,
	developerMode,
}: {
	threadId: string;
	runId: string;
	messages: readonly unknown[];
	agentProfile: unknown;
	developerMode: MobileDeveloperMode;
}) => ({
	threadId,
	runId,
	state: null,
	messages,
	tools: [],
	context: [],
	// Developer mode is an explicit owner hint: the backend independently
	// verifies the session role, policy and workspace before executing.
	forwardedProps: {
		agentProfile: normalizeAgentProfile(agentProfile),
		executionMode:
			developerMode === "standard"
				? ("standard" as const)
				: ("developer" as const),
		...(developerMode === "standard"
			? {}
			: { accessMode: developerMode }),
	},
});

function ProductRuntimeScope({
	children,
	scopeKey,
}: PropsWithChildren<{ scopeKey: string }>) {
	const session = useMobileSession();
	const authenticated = session.status === "authenticated";
	const client = useMemo(
		() => new ProductChatClient(session.authorizedFetch),
		[session.authorizedFetch],
	);
	const attachmentClient = useMemo(
		() => new MobileAttachmentClient(session.authorizedFetch),
		[session.authorizedFetch],
	);
	const [projection, setProjection] = useState<Projection>({
		status: authenticated ? "loading" : "inactive",
		threads: [],
		activeThreadId: null,
		draftThreadId: null,
	});
	const projectionRef = useRef(projection);
	const activeRunIdRef = useRef<string | null>(null);
	const bootstrapRef = useRef<Promise<Bootstrap> | null>(null);
	const [initialDraftId] = useState(createDraftId);
	const [developerMode, setDeveloperMode] =
		useState<MobileDeveloperMode>(readMobileDeveloperMode);
	const setDeveloperModePersisted = useCallback(
		(next: MobileDeveloperMode) => {
			setDeveloperMode(next);
			persistMobileDeveloperMode(next);
		},
		[],
	);

	const commit = useCallback((next: Projection) => {
		projectionRef.current = next;
		setProjection(next);
	}, []);

	const applyThreads = useCallback(
		(threads: readonly ProductThread[]) => {
			const previous = projectionRef.current;
			let activeThreadId = previous.activeThreadId;
			let draftThreadId = previous.draftThreadId;

			if (draftThreadId && threads.some(({ id }) => id === draftThreadId)) {
				draftThreadId = null;
			}
			if (
				!activeThreadId ||
				(!threads.some(({ id }) => id === activeThreadId) &&
					activeThreadId !== draftThreadId)
			) {
				activeThreadId =
					threads.find(({ status }) => status === "regular")?.id ??
					createDraftId();
				draftThreadId = threads.some(({ id }) => id === activeThreadId)
					? null
					: activeThreadId;
			}

			const next: Projection = {
				status: "ready",
				threads,
				activeThreadId,
				draftThreadId,
			};
			commit(next);
			return {
				threadId: activeThreadId,
				persisted: threads.some(({ id }) => id === activeThreadId),
			};
		},
		[commit],
	);

	const loadThreads = useCallback(async () => {
		if (!authenticated) {
			const draft = projectionRef.current.draftThreadId ?? createDraftId();
			commit({
				status: "inactive",
				threads: [],
				activeThreadId: draft,
				draftThreadId: draft,
			});
			return { threadId: draft, persisted: false };
		}
		return applyThreads(await client.listThreads());
	}, [applyThreads, authenticated, client, commit]);

	const ensureBootstrap = useCallback(() => {
		if (!bootstrapRef.current) {
			bootstrapRef.current = loadThreads().catch((reason) => {
				commit({ ...projectionRef.current, status: "error" });
				bootstrapRef.current = null;
				throw reason;
			});
		}
		return bootstrapRef.current;
	}, [commit, loadThreads]);

	useEffect(() => {
		bootstrapRef.current = null;
		void ensureBootstrap().catch(() => {
			// The projection exposes the failed state; avoid an unhandled rejection.
		});
	}, [ensureBootstrap, scopeKey]);

	const activeAgentThreadId =
		projection.activeThreadId ?? projection.draftThreadId ?? initialDraftId;
	const activeAgentProfile = session.user?.preferredAgentProfile ?? "auto";
	const agent = useMemo(
		() =>
			// HttpAgent stores this callback and invokes it only after a network
			// response; it does not read React refs during construction.
			// eslint-disable-next-line react-hooks/refs
			createProductAgent({
				request: session.authorizedFetch,
				threadId: activeAgentThreadId,
				agentProfile: activeAgentProfile,
				developerMode,
				onAccepted: (runId) => {
					activeRunIdRef.current = runId;
					publishPetMessageAccepted(activeAgentThreadId, runId);
					void loadThreads();
				},
			}),
		[
			activeAgentProfile,
			activeAgentThreadId,
			developerMode,
			loadThreads,
			session.authorizedFetch,
		],
	);

	useEffect(() => {
		clearPetActivityFeed();
		const subscription = agent.subscribe(createPetActivityAgentSubscriber());
		return () => {
			subscription.unsubscribe();
			clearPetActivityFeed();
		};
	}, [agent]);

	const history = useMemo<ThreadHistoryAdapter>(
		() => ({
			async load() {
				const initial = await ensureBootstrap();
				if (!initial.persisted) return { messages: [] };
				return hydrate(await client.listMessages(initial.threadId));
			},
			async append() {
				// Product/Data persists the user message and run atomically.
			},
		}),
		[client, ensureBootstrap],
	);

	const switchToNewThread = useCallback(() => {
		const draft = createDraftId();
		commit({
			...projectionRef.current,
			status: authenticated ? "ready" : "inactive",
			activeThreadId: draft,
			draftThreadId: draft,
		});
	}, [authenticated, commit]);

	const switchToThread = useCallback(
		async (
			threadId: string,
		): Promise<{ messages: readonly ThreadMessage[] }> => {
			const selected = projectionRef.current.threads.find(
				(thread) => thread.id === threadId,
			);
			if (!selected) throw new Error("Thread is not available.");
			const repository = hydrate(await client.listMessages(threadId));
			commit({
				...projectionRef.current,
				activeThreadId: threadId,
				draftThreadId: null,
			});
			return {
				messages: repository.messages.map(({ message }) => message),
			};
		},
		[client, commit],
	);

	const mutate = useCallback(
		async (
			threadId: string,
			action: "archive" | "unarchive" | "pin" | "unpin" | "remove",
		) => {
			await client.updateThread(threadId, action);
			await loadThreads();
		},
		[client, loadThreads],
	);

	const threadList = useMemo<UseAgUiThreadListAdapter>(() => {
		const mapThread = (thread: ProductThread) => ({
			id: thread.id,
			remoteId: thread.id,
			title: thread.title,
			lastMessageAt: thread.lastMessageAt
				? new Date(thread.lastMessageAt)
				: undefined,
			custom: {
				projectId: thread.projectId,
				pinned: thread.pinned,
				updatedAt: thread.updatedAt,
			},
		});
		const draft = projection.draftThreadId
			? [
					{
						id: projection.draftThreadId,
						status: "regular" as const,
						title: "Новая задача",
						custom: { draft: true },
					},
				]
			: [];
		return {
			threadId: projection.activeThreadId ?? undefined,
			isLoading: projection.status === "loading",
			threads: [
				...draft,
				...projection.threads
					.filter(({ status }) => status === "regular")
					.map((thread) => ({
						...mapThread(thread),
						status: "regular" as const,
					})),
			],
			archivedThreads: projection.threads
				.filter(({ status }) => status === "archived")
				.map((thread) => ({
					...mapThread(thread),
					status: "archived" as const,
				})),
			onSwitchToNewThread: switchToNewThread,
			onSwitchToThread: switchToThread,
			onUpdateCustom: async (threadId, custom) => {
				const current = projection.threads.find(({ id }) => id === threadId);
				if (!current || current.pinned === (custom?.pinned === true)) return;
				await mutate(threadId, current.pinned ? "unpin" : "pin");
			},
			onArchive: (threadId) => mutate(threadId, "archive"),
			onUnarchive: (threadId) => mutate(threadId, "unarchive"),
			onDelete: (threadId) => mutate(threadId, "remove"),
		};
	}, [mutate, projection, switchToNewThread, switchToThread]);

	const active = projection.threads.find(
		({ id }) => id === projection.activeThreadId,
	);
	const productChatContext = useMemo<ProductChatContextValue>(
		() => ({
			activeThreadId: projection.activeThreadId,
			activeProjectId: active?.projectId ?? null,
			attachmentClient,
		}),
		[active?.projectId, attachmentClient, projection.activeThreadId],
	);
	const runtime = useAgUiRuntime({
		agent,
		onCancel: () => {
			agent.abortRun();
			const runId = activeRunIdRef.current;
			activeRunIdRef.current = null;
			if (!runId) return;
			void client
				.cancelRun(runId)
				.then(loadThreads)
				.catch((reason: unknown) => {
					if (__DEV__) {
						console.error("[Kolibri Mobile] failed to cancel run", reason);
					}
				});
		},
		showThinking: true,
		isDisabled:
			!authenticated ||
			projection.status !== "ready" ||
			active?.status === "archived",
		adapters: { history, threadList },
	});

	return (
		<MobileDeveloperModeContext.Provider
			value={{ mode: developerMode, setMode: setDeveloperModePersisted }}
		>
			<ProductChatContext.Provider value={productChatContext}>
				<AssistantRuntimeProvider runtime={runtime}>
					{children}
				</AssistantRuntimeProvider>
			</ProductChatContext.Provider>
		</MobileDeveloperModeContext.Provider>
	);
}

export function ProductRuntimeProvider({ children }: PropsWithChildren) {
	const session = useMobileSession();
	const scopeKey = session.user
		? `user:${session.user.id}`
		: `session:${session.status}`;
	return (
		<ProductRuntimeScope key={scopeKey} scopeKey={scopeKey}>
			{children}
		</ProductRuntimeScope>
	);
}
