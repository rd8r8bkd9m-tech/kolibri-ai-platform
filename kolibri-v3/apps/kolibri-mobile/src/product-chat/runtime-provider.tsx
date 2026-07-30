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
  useEffect,
  useMemo,
  useRef,
  useState,
  type PropsWithChildren,
} from "react";

import {
  API_BASE_URL,
  useMobileSession,
} from "@/src/auth/mobile-session";
import { ProductChatClient } from "@/src/product-chat/client";
import {
  isSafeProductId,
  type ProductMessage,
  type ProductThread,
} from "@/src/product-chat/contracts";

const AG_UI_URL = `${API_BASE_URL}/v1/chat/ag-ui`;
const SAFE_SHORT_ID = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,123}$/;

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
    if (typeof message.content === "string" && message.content.trim()) {
      return [{ id, role: "user" as const, content: message.content }];
    }
    if (!Array.isArray(message.content)) return null;
    const content = message.content.flatMap((part: unknown) =>
      typeof part === "object" &&
      part !== null &&
      "type" in part &&
      part.type === "text" &&
      "text" in part &&
      typeof part.text === "string" &&
      part.text.trim()
        ? [{ type: "text" as const, text: part.text }]
        : [],
    );
    return content.length ? [{ id, role: "user" as const, content }] : null;
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
    { showThinking: false },
  );
  if (converted.length !== messages.length) {
    throw new Error("Product Chat history could not be reconstructed.");
  }
  return ExportedMessageRepository.fromArray(
    converted.map((message, index) => ({
      ...message,
      id: messages[index]!.id,
      createdAt: new Date(messages[index]!.createdAt),
    })),
  );
};

const createProductAgent = ({
  request,
  threadId,
  agentProfile,
  onAccepted,
}: {
  request: typeof fetch;
  threadId: string;
  agentProfile: string;
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
      const response = await request(input, {
        ...init,
        headers: {
          ...Object.fromEntries(new Headers(init.headers).entries()),
          Accept: "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          threadId,
          runId,
          state: null,
          messages,
          tools: [],
          context: [],
          forwardedProps: {
            agentProfile,
            executionMode: "standard",
            accessMode: "standard",
          },
        }),
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
  const activeAgentProfile =
    session.user?.preferredAgentProfile ?? "auto";
  const agent = useMemo(
    () =>
      // HttpAgent stores this callback and invokes it only after a network
      // response; it does not read React refs during construction.
      // eslint-disable-next-line react-hooks/refs
      createProductAgent({
        request: session.authorizedFetch,
        threadId: activeAgentThreadId,
        agentProfile: activeAgentProfile,
        onAccepted: (runId) => {
          activeRunIdRef.current = runId;
          void loadThreads();
        },
      }),
    [
      activeAgentProfile,
      activeAgentThreadId,
      loadThreads,
      session.authorizedFetch,
    ],
  );

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
    async (threadId: string): Promise<{ messages: readonly ThreadMessage[] }> => {
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
          .map((thread) => ({ ...mapThread(thread), status: "regular" as const })),
      ],
      archivedThreads: projection.threads
        .filter(({ status }) => status === "archived")
        .map((thread) => ({ ...mapThread(thread), status: "archived" as const })),
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
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
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
