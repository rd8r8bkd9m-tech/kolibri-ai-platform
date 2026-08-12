"use client";

import { HttpAgent } from "@ag-ui/client";
import {
	AssistantRuntimeProvider,
	WebSpeechDictationAdapter,
	type DictationAdapter,
	type ThreadMessage,
} from "@assistant-ui/react";
import {
	useAgUiRuntime,
	type UseAgUiThreadListAdapter,
} from "@assistant-ui/react-ag-ui";
import {
	useCallback,
	Component,
	useEffect,
	useMemo,
	useRef,
	useState,
	type ReactNode,
} from "react";

import {
	createProductChatFeedbackAdapter,
	createProductChatHistoryAdapter,
	hydrateProductChatMessages,
	toAgUiThreadData,
} from "@/lib/product-chat/adapters";
import {
	createProductChatAttachmentAdapter,
	loadProductAttachmentCapability,
	type ProductAttachmentCapability,
} from "@/lib/product-chat/attachments";
import {
	PRODUCT_AG_UI_BFF_URL,
	ProductChatClient,
	createProductAgUiFetch,
} from "@/lib/product-chat/client";
import type { WorkspaceContextV1 } from "@/lib/workspace-context";
import { WorkspaceContextPublisherProvider } from "@/lib/workspace-context-provider";
import type {
	KolibriAgentProfile,
	ProductChatThread,
} from "@/lib/product-chat/contracts";
import { useIdentity } from "@/lib/identity/provider";
import {
	DeveloperAgentModeContext,
	persistDeveloperAccessMode,
	readDeveloperAccessMode,
	type DeveloperAccessMode,
} from "@/lib/product-chat/developer-agent-mode";
import {
	AcceptedProductChatRunContext,
	type AcceptedProductChatRun,
} from "@/lib/product-chat/accepted-run";
import {
	capabilityIsAvailable,
	fetchProductCapabilityManifest,
	ProductCapabilityManifestProvider,
	type ProductCapabilityManifest,
} from "@/lib/product-chat/capabilities";
import {
	clearPetActivityFeed,
	createPetActivityAgentSubscriber,
	publishPetMessageAccepted,
} from "@/lib/pets/runtime-activity";

type RuntimeProjection = {
	readonly status: "inactive" | "loading" | "ready" | "error";
	readonly threads: readonly ProductChatThread[];
	readonly activeThreadId: string | null;
	readonly draftThreadId: string | null;
};

type BootstrapResult = {
	readonly threads: readonly ProductChatThread[];
	readonly activeThreadId: string;
	readonly persisted: boolean;
};

type AssistantRuntimeRecoveryState = {
	retryKey: number;
	hasError: boolean;
};

/**
 * assistant-ui keeps its message repository outside React state. During a
 * thread/history replacement it can briefly publish a stale head reference;
 * remounting the same runtime once lets the canonical history reattach it.
 */
class AssistantRuntimeRecoveryBoundary extends Component<
	Readonly<{ children: ReactNode }>,
	AssistantRuntimeRecoveryState
> {
	state: AssistantRuntimeRecoveryState = { retryKey: 0, hasError: false };

	static getDerivedStateFromError(): Partial<AssistantRuntimeRecoveryState> {
		return { hasError: true };
	}

	componentDidCatch(error: unknown) {
		if (this.state.retryKey < 1) {
			this.setState((current) => ({
				retryKey: current.retryKey + 1,
				hasError: false,
			}));
			return;
		}
		if (process.env.NODE_ENV === "development") {
			console.error("[Kolibri Product Chat] runtime recovery failed", error);
		}
	}

	render() {
		if (this.state.hasError) {
			return (
				<div
					role="alert"
					className="text-muted-foreground flex h-full items-center justify-center p-6 text-sm"
				>
					Не удалось восстановить чат. Обновите страницу.
				</div>
			);
		}
		return (
			<div key={this.state.retryKey} className="contents">
				{this.props.children}
			</div>
		);
	}
}

const INACTIVE_PROJECTION: RuntimeProjection = {
	status: "inactive",
	threads: [],
	activeThreadId: null,
	draftThreadId: null,
};

const createDraftThreadId = () =>
	`thread_${globalThis.crypto.randomUUID().replaceAll("-", "")}`;

const isPersistedThread = (
	threads: readonly ProductChatThread[],
	threadId: string,
) => threads.some((thread) => thread.id === threadId);

function ProductChatRuntimeScope({
	authenticated,
	children,
	preferredAgentProfile,
	developerAgentAvailable,
	capabilityManifest,
	getWorkspaceContext,
}: Readonly<{
	authenticated: boolean;
	children: ReactNode;
	preferredAgentProfile: KolibriAgentProfile;
	developerAgentAvailable: boolean;
	capabilityManifest: ProductCapabilityManifest | null;
	getWorkspaceContext: () => WorkspaceContextV1 | null;
}>) {
	const client = useMemo(() => new ProductChatClient(), []);
	const profileRef = useRef(preferredAgentProfile);
	profileRef.current = preferredAgentProfile;
	// Developer mode defaults to full, unlimited access for the owner and
	// persists the choice so a reload does not silently downgrade it.
	const [developerAccessMode, setDeveloperAccessMode] =
		useState<DeveloperAccessMode>(readDeveloperAccessMode);
	const [acceptedRun, setAcceptedRun] = useState<AcceptedProductChatRun | null>(
		null,
	);
	const [dictation, setDictation] = useState<DictationAdapter | undefined>();
	const developerAccessModeRef = useRef(developerAccessMode);
	developerAccessModeRef.current = developerAccessMode;
	const persistMode = useCallback(
		(next: DeveloperAccessMode) => {
			developerAccessModeRef.current = next;
			persistDeveloperAccessMode(next);
		},
		[],
	);
	const setDeveloperAccessModePersisted = useCallback(
		(next: DeveloperAccessMode | ((current: DeveloperAccessMode) => DeveloperAccessMode)) => {
			setDeveloperAccessMode((current) => {
				const resolved =
					typeof next === "function" ? next(current) : next;
				persistMode(resolved);
				return resolved;
			});
		},
		[persistMode],
	);

	useEffect(() => {
		if (!WebSpeechDictationAdapter.isSupported()) return;
		setDictation(
			new WebSpeechDictationAdapter({
				language: "ru-RU",
				continuous: true,
				interimResults: true,
			}),
		);
	}, []);

	useEffect(() => {
		if (!developerAgentAvailable) setDeveloperAccessMode("standard");
	}, [developerAgentAvailable]);

	const initialProjection = authenticated
		? { ...INACTIVE_PROJECTION, status: "loading" as const }
		: INACTIVE_PROJECTION;
	const [projection, setProjection] =
		useState<RuntimeProjection>(initialProjection);
	const projectionRef = useRef(projection);
	const mountedRef = useRef(false);
	const pendingProjectionRef = useRef<RuntimeProjection | null>(null);
	const refreshThreadsRef = useRef<() => Promise<void>>(async () => undefined);
	const activeRunIdRef = useRef<string | null>(null);
	const bootstrapRef = useRef<Promise<BootstrapResult> | null>(null);

	const agent = useMemo(
		() =>
			new HttpAgent({
				url: PRODUCT_AG_UI_BFF_URL,
				headers: { Accept: "text/event-stream" },
				fetch: createProductAgUiFetch({
					getAgentProfile: () => profileRef.current,
					getExecutionMode: () =>
						developerAccessModeRef.current === "standard"
							? "standard"
							: "developer",
					getAccessMode: () => developerAccessModeRef.current,
					getActiveThreadId: () => projectionRef.current.activeThreadId,
					getWorkspaceContext,
					onAccepted: (runId) => {
						activeRunIdRef.current = runId;
						const threadId = projectionRef.current.activeThreadId;
						if (threadId) {
							setAcceptedRun({ acceptedAt: Date.now(), runId, threadId });
							publishPetMessageAccepted(threadId, runId);
						}
						return refreshThreadsRef.current();
					},
				}),
			}),
		[],
	);

	useEffect(() => {
		clearPetActivityFeed();
		const subscription = agent.subscribe(createPetActivityAgentSubscriber());
		return () => {
			subscription.unsubscribe();
			clearPetActivityFeed();
		};
	}, [agent]);

	const commitProjection = useCallback((next: RuntimeProjection) => {
		projectionRef.current = next;
		if (mountedRef.current) {
			setProjection(next);
			return;
		}
		pendingProjectionRef.current = next;
	}, []);

	useEffect(() => {
		mountedRef.current = true;
		const pending = pendingProjectionRef.current;
		if (pending) {
			pendingProjectionRef.current = null;
			setProjection(pending);
		}
		return () => {
			mountedRef.current = false;
		};
	}, []);

	const applyCanonicalThreads = useCallback(
		(threads: readonly ProductChatThread[]): BootstrapResult => {
			const current = projectionRef.current;
			let draftThreadId = current.draftThreadId;
			if (draftThreadId && isPersistedThread(threads, draftThreadId)) {
				draftThreadId = null;
			}

			let activeThreadId = current.activeThreadId;
			const activeStillAvailable =
				activeThreadId !== null &&
				(isPersistedThread(threads, activeThreadId) ||
					activeThreadId === draftThreadId);
			if (!activeStillAvailable) {
				activeThreadId =
					threads.find((thread) => thread.status === "regular")?.id ??
					createDraftThreadId();
				draftThreadId = isPersistedThread(threads, activeThreadId)
					? null
					: activeThreadId;
			}

			const selectedThreadId = activeThreadId ?? createDraftThreadId();
			if (activeThreadId === null) {
				activeThreadId = selectedThreadId;
				draftThreadId = selectedThreadId;
			}
			agent.threadId = selectedThreadId;
			const next: RuntimeProjection = {
				status: "ready",
				threads,
				activeThreadId: selectedThreadId,
				draftThreadId,
			};
			commitProjection(next);
			return {
				threads,
				activeThreadId: selectedThreadId,
				persisted: isPersistedThread(threads, selectedThreadId),
			};
		},
		[agent, commitProjection],
	);

	const loadCanonicalThreads = useCallback(async () => {
		if (!authenticated) {
			// assistant-ui asks the history adapter for an initial thread even when
			// the composer is disabled. Keep that guest projection local and empty;
			// no protected request should be attempted before authentication.
			return applyCanonicalThreads([]);
		}
		return applyCanonicalThreads(await client.listThreads());
	}, [applyCanonicalThreads, authenticated, client]);

	refreshThreadsRef.current = async () => {
		await loadCanonicalThreads();
	};

	const ensureBootstrap = useCallback(() => {
		if (!bootstrapRef.current) {
			const bootstrap = loadCanonicalThreads()
				.catch((error: unknown) => {
					commitProjection({
						...projectionRef.current,
						status: "error",
					});
					throw error;
				})
				.finally(() => {
					if (
						bootstrapRef.current === bootstrap &&
						projectionRef.current.status === "error"
					) {
						bootstrapRef.current = null;
					}
				});
			bootstrapRef.current = bootstrap;
		}
		return bootstrapRef.current;
	}, [commitProjection, loadCanonicalThreads]);

	const history = useMemo(
		() =>
			createProductChatHistoryAdapter({
				client,
				resolveInitialThread: async () => {
					const bootstrap = await ensureBootstrap();
					return {
						threadId: bootstrap.activeThreadId,
						persisted: bootstrap.persisted,
					};
				},
			}),
		[client, ensureBootstrap],
	);

	useEffect(() => {
		if (!authenticated) return;
		void ensureBootstrap().catch(() => {
			// The runtime remains disabled and exposes no demo/fallback history.
		});
	}, [authenticated, ensureBootstrap]);

	const switchToNewThread = useCallback(() => {
		const threadId = createDraftThreadId();
		agent.threadId = threadId;
		commitProjection({
			...projectionRef.current,
			status: "ready",
			activeThreadId: threadId,
			draftThreadId: threadId,
		});
	}, [agent, commitProjection]);

	const switchToThread = useCallback(
		async (
			threadId: string,
		): Promise<{
			messages: readonly ThreadMessage[];
		}> => {
			const selected = projectionRef.current.threads.find(
				(thread) => thread.id === threadId,
			);
			if (!selected) {
				throw new Error("Product Chat thread is not available.");
			}

			// Hydrate the target before publishing the selection. Publishing the
			// projection first makes assistant-ui render the target id with the
			// previous thread's messages for one frame (the visible "flash" when
			// switching conversations). A failed history read must also leave the
			// current conversation selected.
			const hydration = hydrateProductChatMessages(
				await client.listMessages(threadId),
			);
			agent.threadId = threadId;
			commitProjection({
				...projectionRef.current,
				status: "ready",
				activeThreadId: threadId,
				draftThreadId: null,
			});

			return { messages: hydration.messages };
		},
		[agent, client, commitProjection],
	);

	const mutateThread = useCallback(
		async (
			threadId: string,
			action: "archive" | "unarchive" | "pin" | "unpin" | "remove",
		) => {
			await client.updateThread(threadId, action);
			await loadCanonicalThreads();
		},
		[client, loadCanonicalThreads],
	);

	const threadListAdapter = useMemo<UseAgUiThreadListAdapter>(() => {
		const regularThreads = projection.threads
			.filter((thread) => thread.status === "regular")
			.map((thread) => ({
				...toAgUiThreadData(thread),
				status: "regular" as const,
			}));
		const archivedThreads = projection.threads
			.filter((thread) => thread.status === "archived")
			.map((thread) => ({
				...toAgUiThreadData(thread),
				status: "archived" as const,
			}));
		const draftThread =
			projection.draftThreadId === null
				? []
				: [
						{
							id: projection.draftThreadId,
							status: "regular" as const,
							title: "Новая задача",
							custom: { draft: true },
						},
					];

		return {
			threadId: projection.activeThreadId ?? undefined,
			isLoading: projection.status === "loading",
			threads: [...draftThread, ...regularThreads],
			archivedThreads,
			onSwitchToNewThread: switchToNewThread,
			onSwitchToThread: switchToThread,
			onUpdateCustom: async (threadId, custom) => {
				const current = projection.threads.find(
					(thread) => thread.id === threadId,
				);
				if (!current) return;
				const pinned = custom?.pinned === true;
				if (pinned === current.pinned) return;
				await mutateThread(threadId, pinned ? "pin" : "unpin");
			},
			onArchive: (threadId) => mutateThread(threadId, "archive"),
			onUnarchive: (threadId) => mutateThread(threadId, "unarchive"),
			// Removing a dialog is user-scoped and soft-hides only its thread-list
			// entry. The project, messages, documents, and audit lineage remain.
			onDelete: (threadId) => mutateThread(threadId, "remove"),
		};
	}, [mutateThread, projection, switchToNewThread, switchToThread]);

	const activeThread = projection.threads.find(
		(thread) => thread.id === projection.activeThreadId,
	);
	const [attachmentCapability, setAttachmentCapability] =
		useState<ProductAttachmentCapability | null>(null);
	useEffect(() => {
		if (
			!authenticated ||
			projection.status !== "ready" ||
			!activeThread ||
			activeThread.status !== "regular"
		) {
			setAttachmentCapability(null);
			return;
		}
		let current = true;
		setAttachmentCapability(null);
		void loadProductAttachmentCapability({
			projectId: activeThread.projectId,
			threadId: activeThread.id,
		})
			.then((capability) => {
				if (current) setAttachmentCapability(capability);
			})
			.catch(() => {
				if (current) setAttachmentCapability(null);
			});
		return () => {
			current = false;
		};
	}, [activeThread, authenticated, projection.status]);
	const attachments = useMemo(
		() =>
			attachmentCapability
				? createProductChatAttachmentAdapter({
						capability: attachmentCapability,
					})
				: undefined,
		[attachmentCapability],
	);
	const feedback = useMemo(
		() =>
			createProductChatFeedbackAdapter({
				client,
				resolveActiveThreadId: () => projectionRef.current.activeThreadId,
				onError: (error) => {
					if (process.env.NODE_ENV === "development") {
						console.error(
							"[Kolibri Product Chat] failed to save feedback",
							error,
						);
					}
				},
			}),
		[client],
	);
	const runtime = useAgUiRuntime({
		agent,
		onCancel: () => {
			// assistant-ui and HttpAgent own separate abort controllers. Stop both
			// locally, then terminalize and fence the canonical server run.
			agent.abortRun();
			const runId = activeRunIdRef.current;
			activeRunIdRef.current = null;
			if (!runId) return;
			void client
				.cancelRun(runId)
				.then(() => refreshThreadsRef.current())
				.catch((error: unknown) => {
					if (process.env.NODE_ENV === "development") {
						console.error("[Kolibri Product Chat] failed to cancel run", error);
					}
				});
		},
		// Keep reasoning lifecycle parts so the UI can show a safe, collapsible
		// progress summary. Raw chain-of-thought text is never rendered.
		showThinking: true,
		isDisabled:
			!authenticated ||
			projection.status !== "ready" ||
			activeThread?.status === "archived",
		adapters: {
			attachments,
			dictation,
			feedback: authenticated ? feedback : undefined,
			history,
			threadList: threadListAdapter,
		},
		logger: {
			error: (...details: unknown[]) => {
				if (process.env.NODE_ENV === "development") {
					console.error("[Kolibri Product Chat]", ...details);
				}
			},
		},
	});

	return (
		<ProductCapabilityManifestProvider manifest={capabilityManifest}>
			<DeveloperAgentModeContext.Provider
				value={{
					available: developerAgentAvailable,
					mode: developerAccessMode,
					setMode: setDeveloperAccessModePersisted,
					enabled: developerAccessMode !== "standard",
					setEnabled: (next) =>
						setDeveloperAccessModePersisted((current) => {
							const enabled = current !== "standard";
							const resolved =
								typeof next === "function" ? next(enabled) : next;
							return resolved ? "auto" : "standard";
						}),
				}}
			>
				<AcceptedProductChatRunContext.Provider value={acceptedRun}>
					<AssistantRuntimeRecoveryBoundary>
						<AssistantRuntimeProvider runtime={runtime}>
							{children}
						</AssistantRuntimeProvider>
					</AssistantRuntimeRecoveryBoundary>
				</AcceptedProductChatRunContext.Provider>
			</DeveloperAgentModeContext.Provider>
		</ProductCapabilityManifestProvider>
	);
}

/**
 * Auth/session authority stays in the IdentityProvider and HttpOnly cookie.
 * Changing the authenticated subject remounts the runtime so one account's
 * in-memory projection cannot survive into another account.
 */
export function MyRuntimeProvider({
	children,
}: Readonly<{ children: ReactNode }>) {
	const identity = useIdentity();
	const authenticated =
		identity.status === "authenticated" && identity.user !== null;
	const scopeKey = identity.user
		? `account:${identity.user.id}`
		: `identity:${identity.status}`;
	const preferredAgentProfile = identity.user?.preferredAgentProfile ?? "auto";
	const [capabilityManifest, setCapabilityManifest] =
		useState<ProductCapabilityManifest | null>(null);
	useEffect(() => {
		if (!authenticated) {
			setCapabilityManifest(null);
			return;
		}
		let active = true;
		void fetchProductCapabilityManifest()
			.then((manifest) => {
				if (active) setCapabilityManifest(manifest);
			})
			.catch(() => {
				if (active) setCapabilityManifest(null);
			});
		return () => {
			active = false;
		};
	}, [authenticated]);
	const developerAgentAvailable =
		identity.user?.role === "owner" &&
		capabilityIsAvailable(capabilityManifest, "developer.runtime.execute");
	const workspaceContextRef = useRef<WorkspaceContextV1 | null>(null);
	const publishWorkspaceContext = useCallback(
		(context: WorkspaceContextV1 | null) => {
			workspaceContextRef.current = context;
			if (typeof document !== "undefined") {
				if (context) {
					document.documentElement.setAttribute(
						"data-kolibri-runtime-surface",
						context.surface,
					);
				} else {
					document.documentElement.removeAttribute(
						"data-kolibri-runtime-surface",
					);
				}
			}
		},
		[],
	);
	const getWorkspaceContext = useCallback(() => {
		const context = workspaceContextRef.current;
		if (typeof document !== "undefined") {
			document.documentElement.setAttribute(
				"data-kolibri-runtime-context-read",
				context?.surface ?? "none",
			);
		}
		return context;
	}, []);

	return (
		<WorkspaceContextPublisherProvider publish={publishWorkspaceContext}>
			<ProductChatRuntimeScope
				key={scopeKey}
				authenticated={authenticated}
				preferredAgentProfile={preferredAgentProfile}
				developerAgentAvailable={developerAgentAvailable}
				capabilityManifest={capabilityManifest}
				getWorkspaceContext={getWorkspaceContext}
			>
				{children}
			</ProductChatRuntimeScope>
		</WorkspaceContextPublisherProvider>
	);
}
