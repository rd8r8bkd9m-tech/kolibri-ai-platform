import type { ContextPanelMode } from "./context-panel";
import type {
  WorkspaceFile,
  WorkspaceFileCategory,
} from "./workspace-file-manager";

export type CanvasTabPlacement = "right" | "bottom" | "primary";

export type CanvasTabContent =
  | { kind: "desktop" }
  | { kind: "projects" }
  | { kind: "references" }
  | { kind: "files"; category: WorkspaceFileCategory }
  | { kind: "tool"; mode: ContextPanelMode };

export type CanvasTab = {
  content: CanvasTabContent;
  id: string;
  maximized: boolean;
  minimized: boolean;
  placement: CanvasTabPlacement;
  projectId: string | null;
  selectedFile: WorkspaceFile | null;
  title: string;
};

export type CanvasSessionState = {
  activeTabId: string | null;
  tabs: CanvasTab[];
};

export type OpenCanvasTabInput = {
  content: CanvasTabContent;
  id: string;
  maximized?: boolean;
  placement?: CanvasTabPlacement;
  projectId?: string | null;
  selectedFile?: WorkspaceFile | null;
  title: string;
};

export type CanvasTabUpdate = Partial<
  Pick<
    CanvasTab,
    | "content"
    | "maximized"
    | "minimized"
    | "placement"
    | "projectId"
    | "selectedFile"
    | "title"
  >
>;

const DEFAULT_PLACEMENT: CanvasTabPlacement = "primary";

function normalizeId(value: string) {
  return value.trim();
}

function normalizeTitle(value: string) {
  return value.trim() || "Рабочая область";
}

function firstVisibleTabId(tabs: readonly CanvasTab[]) {
  return tabs.find((tab) => !tab.minimized)?.id ?? null;
}

function normalizeActiveTabId(
  tabs: readonly CanvasTab[],
  activeTabId: string | null,
) {
  const requestedTab = tabs.find(
    (tab) => tab.id === activeTabId && !tab.minimized,
  );
  return requestedTab?.id ?? firstVisibleTabId(tabs);
}

/**
 * Creates a deterministic session and collapses duplicate tab ids.
 * The last occurrence wins without changing the first occurrence's position.
 */
export function createCanvasSession(
  tabs: readonly CanvasTab[] = [],
  activeTabId: string | null = null,
): CanvasSessionState {
  const normalizedTabs: CanvasTab[] = [];
  const tabIndexById = new Map<string, number>();

  for (const sourceTab of tabs) {
    const id = normalizeId(sourceTab.id);
    if (!id) continue;

    const tab: CanvasTab = {
      ...sourceTab,
      id,
      maximized: sourceTab.maximized ?? false,
      title: normalizeTitle(sourceTab.title),
    };
    const existingIndex = tabIndexById.get(id);

    if (existingIndex === undefined) {
      tabIndexById.set(id, normalizedTabs.length);
      normalizedTabs.push(tab);
    } else {
      normalizedTabs[existingIndex] = tab;
    }
  }

  return {
    tabs: normalizedTabs,
    activeTabId: normalizeActiveTabId(normalizedTabs, activeTabId),
  };
}

/**
 * Opens a new tab or updates the tab with the same stable id.
 * Upserting always restores and activates the target, so there is one active id.
 */
export function openCanvasTab(
  session: CanvasSessionState,
  input: OpenCanvasTabInput,
): CanvasSessionState {
  const id = normalizeId(input.id);
  if (!id) return session;

  const existingIndex = session.tabs.findIndex((tab) => tab.id === id);

  if (existingIndex < 0) {
    const nextTab: CanvasTab = {
      content: input.content,
      id,
      maximized: input.maximized ?? false,
      minimized: false,
      placement: input.placement ?? DEFAULT_PLACEMENT,
      projectId: input.projectId ?? null,
      selectedFile: input.selectedFile ?? null,
      title: normalizeTitle(input.title),
    };

    return {
      tabs: [...session.tabs, nextTab],
      activeTabId: id,
    };
  }

  const existingTab = session.tabs[existingIndex];
  const nextTab: CanvasTab = {
    ...existingTab,
    content: input.content,
    maximized: input.maximized ?? existingTab.maximized,
    minimized: false,
    placement: input.placement ?? existingTab.placement,
    projectId:
      input.projectId === undefined ? existingTab.projectId : input.projectId,
    selectedFile:
      input.selectedFile === undefined
        ? existingTab.selectedFile
        : input.selectedFile,
    title: normalizeTitle(input.title),
  };
  const tabs = session.tabs.map((tab, index) =>
    index === existingIndex ? nextTab : tab,
  );

  return { tabs, activeTabId: id };
}

export function updateCanvasTab(
  session: CanvasSessionState,
  tabId: string,
  update: CanvasTabUpdate,
): CanvasSessionState {
  const id = normalizeId(tabId);
  const existingIndex = session.tabs.findIndex((tab) => tab.id === id);
  if (existingIndex < 0) return session;

  const existingTab = session.tabs[existingIndex];
  const nextTab: CanvasTab = {
    ...existingTab,
    ...update,
    id: existingTab.id,
    title:
      update.title === undefined
        ? existingTab.title
        : normalizeTitle(update.title),
  };
  const tabs = session.tabs.map((tab, index) =>
    index === existingIndex ? nextTab : tab,
  );

  return {
    tabs,
    activeTabId: normalizeActiveTabId(tabs, session.activeTabId),
  };
}

export function activateCanvasTab(
  session: CanvasSessionState,
  tabId: string,
): CanvasSessionState {
  const id = normalizeId(tabId);
  const target = session.tabs.find((tab) => tab.id === id);
  if (!target) return session;

  const tabs = target.minimized
    ? session.tabs.map((tab) =>
        tab.id === id ? { ...tab, minimized: false } : tab,
      )
    : session.tabs;

  return { tabs, activeTabId: id };
}

export function minimizeCanvasTab(
  session: CanvasSessionState,
  tabId: string,
): CanvasSessionState {
  const id = normalizeId(tabId);
  const target = session.tabs.find((tab) => tab.id === id);
  if (!target || target.minimized) return session;

  const tabs = session.tabs.map((tab) =>
    tab.id === id ? { ...tab, minimized: true } : tab,
  );

  return {
    tabs,
    activeTabId:
      session.activeTabId === id
        ? firstVisibleTabId(tabs)
        : normalizeActiveTabId(tabs, session.activeTabId),
  };
}

export function restoreCanvasTab(
  session: CanvasSessionState,
  tabId: string,
): CanvasSessionState {
  return activateCanvasTab(session, tabId);
}

export function closeCanvasTab(
  session: CanvasSessionState,
  tabId: string,
): CanvasSessionState {
  const id = normalizeId(tabId);
  if (!session.tabs.some((tab) => tab.id === id)) return session;

  const tabs = session.tabs.filter((tab) => tab.id !== id);
  const activeTabId =
    session.activeTabId === id
      ? firstVisibleTabId(tabs)
      : normalizeActiveTabId(tabs, session.activeTabId);

  return { tabs, activeTabId };
}

export function setCanvasTabPlacement(
  session: CanvasSessionState,
  tabId: string,
  placement: CanvasTabPlacement,
): CanvasSessionState {
  return updateCanvasTab(session, tabId, { placement });
}

export function setCanvasTabSelectedFile(
  session: CanvasSessionState,
  tabId: string,
  selectedFile: WorkspaceFile | null,
): CanvasSessionState {
  return updateCanvasTab(session, tabId, { selectedFile });
}

export function getActiveCanvasTab(session: CanvasSessionState) {
  return (
    session.tabs.find(
      (tab) => tab.id === session.activeTabId && !tab.minimized,
    ) ?? null
  );
}

export function getMinimizedCanvasTabs(session: CanvasSessionState) {
  return session.tabs.filter((tab) => tab.minimized);
}
