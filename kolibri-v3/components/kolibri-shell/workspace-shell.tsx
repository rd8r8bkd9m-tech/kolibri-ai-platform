"use client";

import {
  AssistantChatWidget,
  type AssistantChatDock,
} from "@/components/assistant-ui/assistant-chat-widget";
import { Thread } from "@/components/assistant-ui/thread";
import {
  ProfileSettingsSurface,
  type ProfileSettingsSection,
} from "@/components/kolibri-shell/profile-settings-surface";
import { KolibriPetHost } from "@/components/kolibri-shell/kolibri-pet";
import {
  WorkspaceSidebar,
  type WorkspaceProject,
  type ProjectContentSection,
} from "@/components/kolibri-shell/workspace-sidebar";
import { MobileWorkspaceHeader } from "@/components/kolibri-shell/mobile-workspace-header";
import { WorkspaceHeader } from "@/components/kolibri-shell/workspace-header";
import {
  CanvasWorkspace,
  type WorkspaceFile,
} from "@/components/kolibri-workspace";
import {
  CONTEXT_PANEL_TABS,
  type ContextPanelMode,
} from "@/components/kolibri-workspace/context-panel";
import {
  activateCanvasTab,
  createCanvasSession,
  getActiveCanvasTab,
  minimizeCanvasTab,
  openCanvasTab,
  restoreCanvasTab,
  setCanvasTabPlacement,
  setCanvasTabSelectedFile,
  updateCanvasTab,
  type CanvasTabContent,
  type CanvasTabPlacement,
} from "@/components/kolibri-workspace/canvas-session";
import { ProjectsOverview } from "@/components/kolibri-workspace/projects-overview";
import { ReferenceCatalog } from "@/components/kolibri-workspace/reference-catalog";
import { WorkspaceDesktop } from "@/components/kolibri-workspace/workspace-desktop";
import { WorkspaceTaskShelf } from "@/components/kolibri-workspace/workspace-task-shelf";
import {
  useAui,
  useAuiState,
  useAssistantContext,
  useAssistantInstructions,
} from "@assistant-ui/react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { useIdentity } from "@/lib/identity/provider";
import { cn } from "@/lib/utils";
import {
  parseWorkspaceDocuments,
  type WorkspaceCatalogLoadState,
} from "@/lib/workspace-documents";
import {
  KOLIBRI_DOCUMENTS_CHANGED_EVENT,
  KOLIBRI_OPEN_MODEL_SETTINGS_EVENT,
  KOLIBRI_OPEN_ESTIMATE_EVENT,
  isOpenEstimateDetail,
} from "@/lib/workspace-events";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

// Keep the desktop shell stable around browser zoom and small window changes.
// A narrow entry threshold plus a lower exit threshold prevents a 100% → 110%
// zoom from flipping the whole product into a modal/mobile layout.
const DESKTOP_ENTER_WIDTH = 960;
const DESKTOP_EXIT_WIDTH = 860;
const PRIMARY_CANVAS_TAB_ID = "workspace-primary";

type PrimaryView =
  | "chat"
  | "desktop"
  | "projects"
  | "documents"
  | "references";

const PRIMARY_VIEW_TITLES: Record<PrimaryView, string> = {
  chat: "Новая задача",
  desktop: "Рабочий стол",
  projects: "Проекты",
  documents: "Документы",
  references: "Справочники",
};

const FILE_SECTION_TITLES: Record<ProjectContentSection, string> = {
  all: "Все файлы",
  attachments: "Вложения",
  contracts: "Договоры",
  documents: "Документы",
  drawings: "Чертежи",
  estimates: "Сметы",
};

function canvasViewForContent(content: CanvasTabContent): PrimaryView {
  if (content.kind === "desktop") return "desktop";
  if (content.kind === "projects") return "projects";
  if (content.kind === "references") return "references";
  return content.kind === "files" ? "documents" : "desktop";
}

function useDesktopWorkspace() {
  const [isDesktop, setIsDesktop] = useState(false);

  useEffect(() => {
    const update = () => {
      const viewportWidth = window.innerWidth;
      setIsDesktop((current) => {
        if (current) return viewportWidth >= DESKTOP_EXIT_WIDTH;
        return viewportWidth >= DESKTOP_ENTER_WIDTH;
      });
    };

    update();
    window.addEventListener("resize", update, { passive: true });
    return () => window.removeEventListener("resize", update);
  }, []);

  return isDesktop;
}

export function WorkspaceShell() {
  const aui = useAui();
  const isDesktop = useDesktopWorkspace();
  const identity = useIdentity();
  const previousDesktopState = useRef(false);
  const [activeProject, setActiveProject] =
    useState<WorkspaceProject | null>(null);
  const [navigationPinned, setNavigationPinned] = useState(false);
  const [navigationPreviewOpen, setNavigationPreviewOpen] = useState(false);
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const previewCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [canvasSession, setCanvasSession] = useState(() =>
    createCanvasSession(),
  );
  const [canvasVisible, setCanvasVisible] = useState(false);
  const [canvasMaximized, setCanvasMaximized] = useState(false);
  const [canvasPlacement, setCanvasPlacement] =
    useState<CanvasTabPlacement>("primary");
  const [assistantWidgetOpen, setAssistantWidgetOpen] = useState(false);
  const [assistantWidgetPinned, setAssistantWidgetPinned] = useState(false);
  const [assistantWidgetDock, setAssistantWidgetDock] =
    useState<AssistantChatDock>("right");
  const [accountSurfaceOpen, setAccountSurfaceOpen] = useState(false);
  const [accountSection, setAccountSection] =
    useState<ProfileSettingsSection>("general");
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([]);
  const [workspaceCatalogState, setWorkspaceCatalogState] =
    useState<WorkspaceCatalogLoadState>("loading");
  const activeThreadItem = useAuiState((state) =>
    state.threads.threadItems.find(
      (thread) => thread.id === state.threads.mainThreadId,
    ),
  );
  const workspaceProjects = useMemo(() => {
    const projects = new Map<string, WorkspaceProject>();
    for (const file of workspaceFiles) {
      if (!file.projectId || !file.projectName) continue;
      projects.set(file.projectId, {
        id: file.projectId,
        name: file.projectName,
        updatedAt: file.modifiedAt,
      });
    }
    return [...projects.values()];
  }, [workspaceFiles]);
  const canvasReturnFocusLauncherRef = useRef("composer");
  const activeCanvasTab = getActiveCanvasTab(canvasSession);
  const canvasOpen = canvasVisible && activeCanvasTab !== null;
  const canvasTool: ContextPanelMode | null =
    activeCanvasTab?.content.kind === "files"
      ? "files"
      : activeCanvasTab?.content.kind === "tool"
        ? activeCanvasTab.content.mode
        : null;
  const canvasFileCategory =
    activeCanvasTab?.content.kind === "files"
      ? activeCanvasTab.content.category
      : "all";
  const canvasFile = activeCanvasTab?.selectedFile ?? null;
  const primaryView: PrimaryView =
    !canvasOpen || canvasPlacement !== "primary"
      ? "chat"
      : canvasViewForContent(activeCanvasTab.content);
  const workspaceDestination: PrimaryView =
    !canvasOpen
      ? "chat"
      : canvasViewForContent(activeCanvasTab.content);

  useEffect(() => {
    const projectId = activeThreadItem?.custom?.projectId;
    if (typeof projectId !== "string" || projectId.trim() === "") {
      setActiveProject(null);
      return;
    }

    const knownProject = workspaceProjects.find(
      (project) => project.id === projectId,
    );
    const nextProject: WorkspaceProject = knownProject ?? {
      id: projectId,
      name: activeThreadItem?.title?.trim() || "Проект",
    };
    setActiveProject((current) =>
      current?.id === nextProject.id &&
      current.name === nextProject.name &&
      current.updatedAt === nextProject.updatedAt
        ? current
        : nextProject,
    );
  }, [
    activeThreadItem?.custom?.projectId,
    activeThreadItem?.title,
    workspaceProjects,
  ]);

  useAssistantInstructions(
    `You are Kolibri, an AI assistant inside a commercial project workspace.
Use the current project, Canvas view, selected artifact, calculation, reference catalog, and browser source as working context.
Treat drafts, marketplace offers, prices, contracts, and calculations as unapproved until their visible status says otherwise.
Preserve source, marketplace, capture date, project version, and user approval boundaries.
Never claim that a payment, legal signature, publication, purchase, or external mutation occurred without an explicit typed action and confirmed result.`,
  );
  useAssistantContext({
    getContext: () =>
      [
        activeProject
          ? `Active project: ${activeProject.name} (${activeProject.id}).`
          : "Active project: none.",
        `Canvas: ${canvasOpen ? "open" : "closed"}; placement: ${canvasPlacement}; maximized: ${canvasMaximized}.`,
        `Active workspace tool: ${canvasTool ?? "launcher"}.`,
        `Primary surface: ${primaryView}.`,
        `Assistant widget: ${
          primaryView === "chat"
            ? "full conversation surface"
            : assistantWidgetPinned
              ? "pinned beside the primary surface"
              : assistantWidgetOpen
                ? "floating and open"
                : "floating and collapsed"
        }.`,
        `File category: ${canvasFileCategory}.`,
        canvasFile
          ? `Selected artifact: ${canvasFile.name}; kind: ${canvasFile.kind}; status: ${canvasFile.status}; editable: ${canvasFile.editable}.`
          : "Selected artifact: none.",
      ].join("\n"),
  });

  useEffect(() => {
    if (isDesktop === previousDesktopState.current) return;

    previousDesktopState.current = isDesktop;
    setNavigationPinned(isDesktop);
    setNavigationPreviewOpen(false);
    setMobileNavigationOpen(false);
    if (!isDesktop) {
      setCanvasMaximized(false);
      setCanvasSession((current) => {
        if (!current.tabs.some((tab) => tab.maximized)) return current;
        return {
          ...current,
          tabs: current.tabs.map((tab) =>
            tab.maximized ? { ...tab, maximized: false } : tab,
          ),
        };
      });
    }
  }, [isDesktop]);

  const refreshWorkspaceDocuments = useCallback(async () => {
    if (identity.status !== "authenticated") {
      setWorkspaceFiles([]);
      setWorkspaceCatalogState("ready");
      return;
    }
    setWorkspaceCatalogState("loading");
    try {
      const response = await fetch("/api/v3/documents", {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`Document catalog returned HTTP ${response.status}.`);
      }
      setWorkspaceFiles(parseWorkspaceDocuments(await response.json()));
      setWorkspaceCatalogState("ready");
    } catch {
      setWorkspaceCatalogState("error");
    }
  }, [identity.status]);

  useEffect(() => {
    void refreshWorkspaceDocuments();
  }, [refreshWorkspaceDocuments]);

  useEffect(() => {
    const refresh = () => void refreshWorkspaceDocuments();
    window.addEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, refresh);
    return () =>
      window.removeEventListener(KOLIBRI_DOCUMENTS_CHANGED_EVENT, refresh);
  }, [refreshWorkspaceDocuments]);

  useEffect(() => {
    const openEstimate = (event: Event) => {
      const detail =
        event instanceof CustomEvent ? (event as CustomEvent).detail : null;
      if (!isOpenEstimateDetail(detail)) return;
      const knownFile = workspaceFiles.find(
        (candidate) => candidate.documentId === detail.documentId,
      );
      const file: WorkspaceFile =
        knownFile ?? {
          category: "estimates",
          documentId: detail.documentId,
          editable: true,
          id: detail.documentId,
          kind: "estimate",
          modifiedAt: "сейчас",
          name: detail.title,
          projectId: detail.projectId,
          projectName: detail.projectName,
          size: "Смета",
          status: "Черновик",
          version: detail.version,
        };
      setActiveProject({
        id: detail.projectId,
        name: detail.projectName || knownFile?.projectName || "Проект",
      });
      setCanvasSession((current) =>
        openCanvasTab(current, {
          content: { kind: "files", category: "estimates" },
          id: `estimate:${detail.documentId}`,
          placement: "primary",
          projectId: detail.projectId,
          selectedFile: file,
          title: detail.title,
        }),
      );
      setCanvasPlacement("primary");
      setCanvasVisible(true);
      setCanvasMaximized(false);
      setAccountSurfaceOpen(false);
      setNavigationPreviewOpen(false);
      setMobileNavigationOpen(false);
    };
    window.addEventListener(KOLIBRI_OPEN_ESTIMATE_EVENT, openEstimate);
    return () =>
      window.removeEventListener(KOLIBRI_OPEN_ESTIMATE_EVENT, openEstimate);
  }, [workspaceFiles]);

  const openWorkspaceTab = ({
    content,
    id,
    placement,
    project,
    selectedFile,
    title,
    maximized,
  }: {
    content: CanvasTabContent;
    id: string;
    placement: CanvasTabPlacement;
    project?: WorkspaceProject;
    selectedFile?: WorkspaceFile | null;
    title: string;
    maximized?: boolean;
  }) => {
    const activeElement =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const launcherId = activeElement
      ?.closest<HTMLElement>("[data-canvas-launcher]")
      ?.getAttribute("data-canvas-launcher");
    if (launcherId && launcherId !== "canvas") {
      canvasReturnFocusLauncherRef.current = launcherId;
    }

    const keepImmersiveWorkspace =
      isDesktop && canvasMaximized && placement === "primary";
    const nextMaximized = maximized ?? keepImmersiveWorkspace;
    if (project) setActiveProject(project);
    setCanvasSession((current) =>
      openCanvasTab(current, {
        content,
        id,
        maximized: nextMaximized,
        placement,
        projectId: project?.id ?? activeProject?.id ?? null,
        selectedFile: selectedFile ?? null,
        title,
      }),
    );
    setCanvasPlacement(placement);
    setCanvasVisible(true);
    setCanvasMaximized(nextMaximized);
    setNavigationPreviewOpen(false);
    setMobileNavigationOpen(false);
    setAccountSurfaceOpen(false);
    if (placement !== "primary") {
      setAssistantWidgetPinned(false);
      setAssistantWidgetOpen(false);
    }
  };

  const openProjectSection = (
    project: WorkspaceProject,
    section: ProjectContentSection,
  ) => {
    openWorkspaceTab({
      content: { kind: "files", category: section },
      id: PRIMARY_CANVAS_TAB_ID,
      placement: canvasOpen ? canvasPlacement : "primary",
      project,
      title: `${FILE_SECTION_TITLES[section]} · ${project.name}`,
    });
  };

  const openCurrentFileSection = (
    section: ProjectContentSection,
    placement: CanvasTabPlacement = canvasOpen
      ? canvasPlacement
      : "primary",
    tabId = PRIMARY_CANVAS_TAB_ID,
  ) => {
    if (activeProject) {
      openWorkspaceTab({
        content: { kind: "files", category: section },
        id: tabId,
        placement,
        project: activeProject,
        title: `${FILE_SECTION_TITLES[section]} · ${activeProject.name}`,
      });
      return;
    }

    openWorkspaceTab({
      content: { kind: "files", category: section },
      id: tabId,
      placement,
      title: FILE_SECTION_TITLES[section],
    });
  };

  const openPrimaryDestination = (view: PrimaryView) => {
    setNavigationPreviewOpen(false);
    setMobileNavigationOpen(false);
    setAccountSurfaceOpen(false);

    if (view === "chat") {
      setCanvasVisible(false);
      setCanvasMaximized(false);
      setAssistantWidgetOpen(false);
      return;
    }

    const destinationPlacement =
      activeCanvasTab?.placement ?? canvasPlacement;
    const storedPrimaryTab = canvasSession.tabs.find(
      (tab) => tab.id === PRIMARY_CANVAS_TAB_ID,
    );

    if (view === "desktop") {
      openWorkspaceTab({
        content: { kind: "desktop" },
        id: PRIMARY_CANVAS_TAB_ID,
        maximized:
          isDesktop &&
          (canvasOpen
            ? canvasMaximized
            : storedPrimaryTab?.content.kind === "desktop"
              ? storedPrimaryTab.maximized
              : true),
        placement: destinationPlacement,
        title: "Рабочий стол",
      });
    } else if (view === "projects") {
      openWorkspaceTab({
        content: { kind: "projects" },
        id: PRIMARY_CANVAS_TAB_ID,
        placement: destinationPlacement,
        title: "Проекты",
      });
    } else if (view === "documents") {
      openCurrentFileSection(
        "all",
        destinationPlacement,
        PRIMARY_CANVAS_TAB_ID,
      );
    } else {
      openWorkspaceTab({
        content: { kind: "references" },
        id: PRIMARY_CANVAS_TAB_ID,
        placement: destinationPlacement,
        title: "Справочники",
      });
    }
  };

  const toggleWorkspaceVisibility = () => {
    setNavigationPreviewOpen(false);
    setMobileNavigationOpen(false);
    setAccountSurfaceOpen(false);
    setAssistantWidgetOpen(false);

    if (canvasOpen) {
      setCanvasVisible(false);
      return;
    }
    if (activeCanvasTab) {
      setCanvasVisible(true);
      return;
    }
    openPrimaryDestination("desktop");
  };

  const activateOrToggleDesktop = () => {
    if (canvasOpen && activeCanvasTab?.content.kind === "desktop") {
      toggleWorkspaceVisibility();
      return;
    }
    openPrimaryDestination("desktop");
  };

  const switchToProjectThread = (projectId: string) => {
    const threadState = aui.threads().getState();
    const linkedThread = threadState.threadItems.find(
      (thread) => thread.custom?.projectId === projectId,
    );
    if (linkedThread && linkedThread.id !== threadState.mainThreadId) {
      aui.threads().switchToThread(linkedThread.id);
    }
  };

  const openProjectInPrimary = (project: WorkspaceProject) => {
    switchToProjectThread(project.id);
    openProjectSection(project, "all");
  };

  const openWorkspaceFile = (file: WorkspaceFile) => {
    const project = file.projectId
      ? workspaceProjects.find((candidate) => candidate.id === file.projectId)
      : undefined;
    if (file.projectId) switchToProjectThread(file.projectId);
    openWorkspaceTab({
      content: { kind: "files", category: file.category },
      id: `artifact:${file.id}`,
      placement: activeCanvasTab?.placement ?? canvasPlacement,
      project,
      selectedFile: file,
      title: file.name,
    });
  };

  const openToolTab = (
    mode: ContextPanelMode,
    placement: CanvasTabPlacement = canvasOpen
      ? canvasPlacement
      : "right",
  ) => {
    if (mode === "files") {
      openCurrentFileSection(
        "all",
        placement,
        activeProject
          ? `project:${activeProject.id}:files`
          : "workspace:files",
      );
      return;
    }

    const title =
      CONTEXT_PANEL_TABS.find((tab) => tab.id === mode)?.label ??
      "Рабочая область";
    openWorkspaceTab({
      content: { kind: "tool", mode },
      id: activeProject
        ? `project:${activeProject.id}:tool:${mode}`
        : `workspace:tool:${mode}`,
      placement,
      project: activeProject ?? undefined,
      title,
    });
  };

  const toggleNavigation = () => {
    if (isDesktop) {
      setNavigationPinned((pinned) => !pinned);
      setNavigationPreviewOpen(false);
    } else {
      setMobileNavigationOpen((open) => !open);
    }
  };

  const closeCanvas = () => {
    setCanvasSession(createCanvasSession());
    setCanvasVisible(false);
    setCanvasMaximized(false);
    setCanvasPlacement("primary");
    setAssistantWidgetOpen(false);
    setAssistantWidgetPinned(false);
    const preferredLauncher = canvasReturnFocusLauncherRef.current;
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        for (const launcherId of [
          preferredLauncher,
          "composer",
          "header",
          "sidebar",
        ]) {
          const launcher = document.querySelector<HTMLElement>(
            `[data-canvas-launcher="${launcherId}"]`,
          );
          if (!launcher) continue;
          launcher.focus();
          return;
        }
      });
    });
  };

  const minimizeCanvas = () => {
    if (!activeCanvasTab) return;
    const minimizedTabId = activeCanvasTab.id;
    const nextSession = minimizeCanvasTab(canvasSession, activeCanvasTab.id);
    const nextTab = getActiveCanvasTab(nextSession);
    setCanvasSession(nextSession);
    setCanvasVisible(nextTab !== null);
    if (nextTab) {
      setCanvasPlacement(nextTab.placement);
      setCanvasMaximized(nextTab.maximized);
    }
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (nextTab) {
          document
            .querySelector<HTMLElement>(
              '[role="tab"][aria-selected="true"]',
            )
            ?.focus();
          return;
        }
        document
          .querySelector<HTMLElement>(
            `[data-canvas-restore-tab="${minimizedTabId}"]`,
          )
          ?.focus();
      });
    });
  };

  const activateWorkspaceTab = (tabId: string) => {
    const nextSession = activateCanvasTab(canvasSession, tabId);
    const nextTab = getActiveCanvasTab(nextSession);
    setCanvasSession(nextSession);
    setCanvasVisible(nextTab !== null);
    if (nextTab) {
      setCanvasPlacement(nextTab.placement);
      setCanvasMaximized(nextTab.maximized);
    }
    if (nextTab?.projectId) {
      const project = workspaceProjects.find(
        (candidate) => candidate.id === nextTab.projectId,
      );
      if (project) setActiveProject(project);
    }
  };

  const restoreWorkspaceTab = (tabId: string) => {
    const nextSession = restoreCanvasTab(canvasSession, tabId);
    const nextTab = getActiveCanvasTab(nextSession);
    setCanvasSession(nextSession);
    setCanvasVisible(true);
    if (nextTab) {
      setCanvasPlacement(nextTab.placement);
      setCanvasMaximized(nextTab.maximized);
    }
  };

  const moveCanvas = (placement: CanvasTabPlacement) => {
    if (!activeCanvasTab) return;
    setCanvasPlacement(placement);
    setCanvasSession((current) =>
      updateCanvasTab(
        setCanvasTabPlacement(current, activeCanvasTab.id, placement),
        activeCanvasTab.id,
        { maximized: false },
      ),
    );
    setCanvasVisible(true);
    setCanvasMaximized(false);
  };

  const toggleCanvasMaximize = () => {
    const next = !canvasMaximized;
    setCanvasMaximized(next);
    if (activeCanvasTab) {
      setCanvasSession((session) =>
        updateCanvasTab(session, activeCanvasTab.id, { maximized: next }),
      );
    }
    if (next) {
      setNavigationPreviewOpen(false);
      setMobileNavigationOpen(false);
    }
  };

  useEffect(() => {
    if (!canvasOpen || !canvasMaximized || !activeCanvasTab) return;

    let innerFrame = 0;
    const outerFrame = window.requestAnimationFrame(() => {
      innerFrame = window.requestAnimationFrame(() => {
        document
          .querySelector<HTMLElement>(
            '#workspace-canvas [role="tab"][aria-selected="true"]',
          )
          ?.focus();
      });
    });

    return () => {
      window.cancelAnimationFrame(outerFrame);
      if (innerFrame) window.cancelAnimationFrame(innerFrame);
    };
  }, [activeCanvasTab?.id, canvasMaximized, canvasOpen]);

  useEffect(() => {
    if (!canvasOpen || !canvasMaximized) return;

    const minimizeImmersiveWorkspace = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      const target = event.target;
      if (
        event.defaultPrevented ||
        (target instanceof HTMLElement &&
          (target.isContentEditable ||
            target.closest('[role="dialog"]') !== null ||
            target.matches("input, textarea, select, [role='textbox']")))
      ) {
        return;
      }
      event.preventDefault();
      minimizeCanvas();
    };

    window.addEventListener("keydown", minimizeImmersiveWorkspace);
    return () =>
      window.removeEventListener("keydown", minimizeImmersiveWorkspace);
  }, [canvasMaximized, canvasOpen, canvasSession]);

  useEffect(() => {
    const handleWorkspaceShortcut = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        (target.isContentEditable ||
          target.matches("input, textarea, select, [role='textbox']"))
      ) {
        return;
      }

      const key = event.key.toLocaleLowerCase("en-US");
      const commandKey = event.metaKey || event.ctrlKey;

      if (commandKey && !event.altKey && !event.shiftKey && key === "b") {
        event.preventDefault();
        if (isDesktop) {
          setNavigationPinned((pinned) => !pinned);
          setNavigationPreviewOpen(false);
        } else {
          setMobileNavigationOpen((open) => !open);
        }
        return;
      }

      if (
        commandKey &&
        !event.altKey &&
        !event.shiftKey &&
        key === "j" &&
        primaryView !== "chat"
      ) {
        event.preventDefault();
        setAssistantWidgetOpen((open) => !open);
        return;
      }

      let nextTool: ContextPanelMode | null = null;
      if (event.ctrlKey && event.shiftKey && key === "g") {
        nextTool = "review";
      } else if (commandKey && !event.altKey && key === "t") {
        nextTool = "browser";
      } else if (commandKey && !event.altKey && key === "p") {
        nextTool = "files";
      } else if (event.altKey && commandKey && key === "s") {
        nextTool = "subtask";
      }

      if (nextTool) {
        event.preventDefault();
        openToolTab(nextTool);
      }
    };

    window.addEventListener("keydown", handleWorkspaceShortcut);
    return () => window.removeEventListener("keydown", handleWorkspaceShortcut);
  }, [activeProject, canvasOpen, canvasSession, isDesktop, primaryView]);

  const navigationDocked = isDesktop && navigationPinned;

  const cancelPreviewClose = () => {
    if (previewCloseTimer.current) {
      clearTimeout(previewCloseTimer.current);
      previewCloseTimer.current = null;
    }
  };

  const openNavigationPreview = () => {
    if (!isDesktop || navigationPinned || canvasMaximized) return;
    cancelPreviewClose();
    setNavigationPreviewOpen(true);
  };

  const scheduleNavigationPreviewClose = () => {
    if (!isDesktop || navigationPinned) return;
    cancelPreviewClose();
    previewCloseTimer.current = setTimeout(() => {
      setNavigationPreviewOpen(false);
      previewCloseTimer.current = null;
    }, 140);
  };

  useEffect(
    () => () => {
      if (previewCloseTimer.current) clearTimeout(previewCloseTimer.current);
    },
    [],
  );

  useEffect(() => {
    const overlayOpen =
      (isDesktop && navigationPreviewOpen && !navigationPinned) ||
      (!isDesktop && mobileNavigationOpen);
    if (!overlayOpen) return;

    const closeOverlayOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setNavigationPreviewOpen(false);
      setMobileNavigationOpen(false);
    };

    window.addEventListener("keydown", closeOverlayOnEscape);
    return () => window.removeEventListener("keydown", closeOverlayOnEscape);
  }, [
    isDesktop,
    mobileNavigationOpen,
    navigationPinned,
    navigationPreviewOpen,
  ]);

  const openAccountSettings = useCallback(
    (section: ProfileSettingsSection = accountSection) => {
      setAccountSection(section);
      setNavigationPreviewOpen(false);
      setMobileNavigationOpen(false);
      setAssistantWidgetOpen(false);
      setAccountSurfaceOpen(true);
    },
    [accountSection],
  );

  useEffect(() => {
    const openModels = () => openAccountSettings("ai-models");
    window.addEventListener(
      KOLIBRI_OPEN_MODEL_SETTINGS_EVENT,
      openModels,
    );
    return () =>
      window.removeEventListener(
        KOLIBRI_OPEN_MODEL_SETTINGS_EVENT,
        openModels,
      );
  }, [openAccountSettings]);

  const currentSurfaceTitle = accountSurfaceOpen
    ? identity.status === "authenticated"
      ? "Личный кабинет"
      : "Вход"
    : canvasOpen
      ? canvasFile?.name ?? activeCanvasTab?.title ?? "Рабочая область"
      : activeThreadItem?.title?.trim() || PRIMARY_VIEW_TITLES[primaryView];
  const mobileSurfaceTitle =
    canvasOpen && canvasFile
      ? canvasFile.name
      : canvasOpen && activeCanvasTab?.content.kind === "files"
        ? "Библиотека"
        : currentSurfaceTitle;

  const header = isDesktop ? (
    <WorkspaceHeader
      activeProjectId={activeProject?.id}
      projectName={activeProject?.name}
      projects={workspaceProjects}
      threadTitle={currentSurfaceTitle}
      navigationOpen={navigationDocked}
      canvasOpen={canvasOpen}
      onOpenDesktop={toggleWorkspaceVisibility}
      onProjectSelect={openProjectInPrimary}
      onToggleNavigation={toggleNavigation}
      onNavigationPreviewEnter={openNavigationPreview}
      onNavigationPreviewLeave={scheduleNavigationPreviewClose}
    />
  ) : (
    <MobileWorkspaceHeader
      navigationOpen={mobileNavigationOpen}
      onBack={
        canvasOpen ? () => openPrimaryDestination("chat") : undefined
      }
      onOpenChat={() => openPrimaryDestination("chat")}
      onOpenDestination={openPrimaryDestination}
      onToggleNavigation={toggleNavigation}
      title={canvasOpen ? mobileSurfaceTitle : "Chat"}
    />
  );

  const sidebarNavigationProps = {
    activeDestination: accountSurfaceOpen ? "chat" : workspaceDestination,
    onOpenChat: () => openPrimaryDestination("chat"),
    onOpenDocuments: () => openPrimaryDestination("documents"),
    onOpenDesktop: activateOrToggleDesktop,
    onOpenFile: openWorkspaceFile,
    onOpenAiModels: () => openAccountSettings("ai-models"),
    onOpenProfileSettings: () => openAccountSettings(),
    onOpenProject: openProjectInPrimary,
    onOpenProjects: () => openPrimaryDestination("projects"),
    onOpenReferenceCatalog: () => openPrimaryDestination("references"),
    projects: workspaceProjects,
    workspaceFiles,
  } as const;

  const visibleCanvasTabs = canvasSession.tabs.filter(
    (tab) => !tab.minimized,
  );
  const activeSurfaceContent =
    activeCanvasTab?.content.kind === "desktop" ? (
      <WorkspaceDesktop
        recentFiles={
          activeProject
            ? workspaceFiles.filter(
                (file) => file.projectId === activeProject.id,
              )
            : workspaceFiles
        }
        onOpenBrowser={() => openToolTab("browser")}
        onOpenDocuments={() => openCurrentFileSection("all")}
        onOpenFile={openWorkspaceFile}
        onOpenProjects={() => openPrimaryDestination("projects")}
        onOpenReferences={() => openPrimaryDestination("references")}
      />
    ) : activeCanvasTab?.content.kind === "projects" ? (
      <ProjectsOverview
        activeProjectId={activeProject?.id}
        catalogState={workspaceCatalogState}
        onOpenProject={openProjectInPrimary}
        onRetry={() => void refreshWorkspaceDocuments()}
        projects={workspaceProjects}
      />
    ) : activeCanvasTab?.content.kind === "references" ? (
      <ReferenceCatalog
        onBack={() => openPrimaryDestination("desktop")}
      />
    ) : undefined;

  const updateActiveTool = (nextTool: ContextPanelMode | null) => {
    if (!activeCanvasTab) return;
    if (nextTool === null) {
      openPrimaryDestination("desktop");
      return;
    }

    const nextContent: CanvasTabContent =
      nextTool === "files"
          ? { kind: "files", category: canvasFileCategory }
          : { kind: "tool", mode: nextTool };
    const nextTitle =
      CONTEXT_PANEL_TABS.find((tab) => tab.id === nextTool)?.label ??
          "Рабочая область";

    setCanvasSession((current) =>
      updateCanvasTab(current, activeCanvasTab.id, {
        content: nextContent,
        selectedFile: null,
        title: nextTitle,
      }),
    );
  };

  const canvasSurface = activeCanvasTab ? (
    <div
      id="workspace-canvas"
      data-canvas-surface="singleton"
      data-canvas-layout={
        canvasMaximized ? "fullscreen" : canvasPlacement
      }
      className={
        canvasMaximized
          ? "fixed inset-0 z-50 h-dvh w-dvw overflow-hidden bg-background"
          : "h-full min-h-0 min-w-0"
      }
    >
      <CanvasAssistantPane
        assistantDock={assistantWidgetDock}
        assistantOpen={assistantWidgetOpen}
        assistantPinned={assistantWidgetPinned}
        isDesktop={isDesktop}
        onAssistantDockChange={setAssistantWidgetDock}
        onAssistantOpenChange={setAssistantWidgetOpen}
        onAssistantPinnedChange={setAssistantWidgetPinned}
        onOpenAccount={() => openAccountSettings()}
        onOpenDesktop={toggleWorkspaceVisibility}
        showAssistantWidget={
          canvasMaximized || canvasPlacement === "primary"
        }
      >
        <CanvasWorkspace
          activeSessionTabId={activeCanvasTab.id}
          compactChrome={!isDesktop && canvasPlacement === "primary"}
          fileCategory={canvasFileCategory}
          maximized={canvasMaximized}
          projectName={activeProject?.name}
          placement={canvasPlacement}
          selectedFile={canvasFile}
          sessionTabs={visibleCanvasTabs}
          surfaceContent={activeSurfaceContent}
          surfaceMode={activeCanvasTab.content.kind}
          toolMode={canvasTool}
          workspaceFiles={
            activeProject
              ? workspaceFiles.filter(
                  (file) => file.projectId === activeProject.id,
                )
              : workspaceFiles
          }
          workspaceCatalogState={workspaceCatalogState}
          onRetryWorkspaceCatalog={() => void refreshWorkspaceDocuments()}
          onClose={closeCanvas}
          onFilesBack={() => openPrimaryDestination("desktop")}
          onMinimize={minimizeCanvas}
          onOpenDesktop={activateOrToggleDesktop}
          onOpenSettings={() => openAccountSettings("profile")}
          onPlacementChange={isDesktop ? moveCanvas : undefined}
          onSelectedFileChange={(file) => {
            if (file?.projectId) {
              switchToProjectThread(file.projectId);
              setActiveProject({
                id: file.projectId,
                name: file.projectName || "Проект",
              });
            }
            setCanvasSession((current) =>
              setCanvasTabSelectedFile(
                current,
                activeCanvasTab.id,
                file,
              ),
            );
          }}
          onSessionTabSelect={activateWorkspaceTab}
          onToolModeChange={updateActiveTool}
          onToggleMaximize={toggleCanvasMaximize}
        />
      </CanvasAssistantPane>
    </div>
  ) : null;

  const accountSurface = (
    <section
      aria-label="Аккаунт Kolibri"
      data-slot="mobile-account-sheet"
      className="fixed inset-x-0 top-[env(safe-area-inset-top)] bottom-0 z-[60] min-h-0 min-w-0 overflow-hidden rounded-t-[2.5rem] bg-background min-[960px]:inset-0 min-[960px]:h-dvh min-[960px]:rounded-none"
    >
      <ProfileSettingsSurface
        activeSection={accountSection}
        onClose={() => setAccountSurfaceOpen(false)}
        onSectionChange={setAccountSection}
      />
    </section>
  );
  const threadSurface = (
    <section
      aria-label="Диалог с Kolibri"
      className="h-full min-h-0 min-w-0 overflow-hidden"
    >
      <Thread
        compact={!isDesktop}
        onOpenAccount={() => openAccountSettings()}
        onOpenDesktop={toggleWorkspaceVisibility}
        workspaceOpen={canvasOpen}
      />
    </section>
  );
  const mobilePrimarySurfaceOpen =
    canvasOpen && canvasPlacement === "primary";
  const mobilePrimaryCanvasMounted =
    activeCanvasTab !== null && canvasPlacement === "primary";
  const mobilePrimaryWorkspaceHidden =
    !mobilePrimarySurfaceOpen || accountSurfaceOpen;
  const primaryContent = !isDesktop ? (
    <div className="relative h-full min-h-0 min-w-0 overflow-hidden">
      <div
        data-slot="mobile-thread-preserver"
        aria-hidden={
          mobilePrimarySurfaceOpen || accountSurfaceOpen ? true : undefined
        }
        inert={
          mobilePrimarySurfaceOpen || accountSurfaceOpen ? true : undefined
        }
        className={cn(
          "absolute inset-0 min-h-0 min-w-0",
          (mobilePrimarySurfaceOpen || accountSurfaceOpen) &&
            "invisible pointer-events-none",
        )}
      >
        {threadSurface}
      </div>
      {mobilePrimaryCanvasMounted ? (
        <div
          data-slot="mobile-primary-workspace"
          aria-hidden={mobilePrimaryWorkspaceHidden ? true : undefined}
          inert={mobilePrimaryWorkspaceHidden ? true : undefined}
          className={cn(
            "absolute inset-0 min-h-0 min-w-0 overflow-hidden",
            mobilePrimaryWorkspaceHidden &&
              "invisible pointer-events-none",
          )}
        >
          {canvasSurface}
        </div>
      ) : null}
      {accountSurfaceOpen ? accountSurface : null}
    </div>
  ) : accountSurfaceOpen ? (
    accountSurface
  ) : canvasOpen && canvasPlacement === "primary" ? (
    canvasSurface
  ) : (
    threadSurface
  );

  const primaryPane = (
    <PrimaryPane
      header={header}
    >
      {primaryContent}
    </PrimaryPane>
  );

  if (canvasOpen && canvasMaximized) {
    return (
      <main
        data-slot="kolibri-workspace-shell"
        data-workspace-mode="immersive"
        aria-label="Полноэкранный рабочий стол Kolibri"
        className="bg-background text-foreground h-dvh max-h-dvh w-dvw max-w-full overflow-hidden"
      >
        {canvasSurface}
        <KolibriPetHost />
        <WorkspaceTaskShelf
          className="fixed bottom-2 left-1/2 z-[70] w-max max-w-[calc(100vw-1rem)] -translate-x-1/2 rounded-xl border bg-background p-1 shadow-lg"
          tabs={canvasSession.tabs}
          onRestoreTab={restoreWorkspaceTab}
        />
      </main>
    );
  }

  if (isDesktop) {
    return (
      <div
        data-slot="kolibri-workspace-shell"
        data-workspace-mode="desktop"
        className="bg-background text-foreground relative flex h-dvh max-h-dvh w-full max-w-full min-w-0 flex-col overflow-hidden"
      >
        <ResizablePanelGroup
          orientation="horizontal"
          className="min-h-0 min-w-0 flex-1"
        >
          {navigationDocked ? (
            <>
              <ResizablePanel
                id="project-navigation"
                defaultSize={389}
                minSize={300}
                maxSize={440}
                groupResizeBehavior="preserve-pixel-size"
                className="min-h-0 min-w-0 overflow-hidden"
              >
                <div id="workspace-project-navigation" className="h-full">
                  <WorkspaceSidebar
                    {...sidebarNavigationProps}
                    onRequestClose={() => setNavigationPinned(false)}
                  />
                </div>
              </ResizablePanel>
              <ResizableHandle aria-label="Изменить ширину навигации" />
            </>
          ) : null}

          <ResizablePanel
            id="primary-workspace"
            minSize={560}
            className="min-h-0 min-w-0 overflow-hidden"
          >
            <main className="h-full min-h-0 min-w-0 overflow-hidden">
              {canvasOpen && canvasPlacement === "right" ? (
                <ResizablePanelGroup
                  orientation="horizontal"
                  className="min-h-0 min-w-0"
                >
                  <ResizablePanel
                    id="assistant-thread"
                    defaultSize="46%"
                    minSize={300}
                    className="min-h-0 min-w-0 overflow-hidden"
                  >
                    {primaryPane}
                  </ResizablePanel>
                  <ResizableHandle
                    withHandle
                    aria-label="Изменить ширину рабочей области"
                  />
                  <ResizablePanel
                    id="project-canvas"
                    defaultSize="54%"
                    minSize={300}
                    className="min-h-0 min-w-0 overflow-hidden"
                  >
                    {canvasSurface}
                  </ResizablePanel>
                </ResizablePanelGroup>
              ) : canvasOpen && canvasPlacement === "bottom" ? (
                <ResizablePanelGroup
                  orientation="vertical"
                  className="min-h-0 min-w-0"
                >
                  <ResizablePanel
                    id="assistant-thread"
                    defaultSize="58%"
                    minSize={260}
                    className="min-h-0 min-w-0 overflow-hidden"
                  >
                    {primaryPane}
                  </ResizablePanel>
                  <ResizableHandle aria-label="Изменить высоту рабочей области" />
                  <ResizablePanel
                    id="project-canvas"
                    defaultSize="42%"
                    minSize={220}
                    className="min-h-0 min-w-0 overflow-hidden"
                  >
                    {canvasSurface}
                  </ResizablePanel>
                </ResizablePanelGroup>
              ) : (
                primaryPane
              )}
            </main>
          </ResizablePanel>
        </ResizablePanelGroup>

        <WorkspaceTaskShelf
          tabs={canvasSession.tabs}
          onRestoreTab={restoreWorkspaceTab}
        />

        {navigationPreviewOpen && !navigationPinned && !canvasMaximized ? (
          <div
            id="workspace-project-navigation"
            className="absolute inset-y-0 left-0 z-50 w-[min(389px,calc(100vw-24px))] overflow-hidden rounded-r-xl border-r border-[#dadadb] bg-background shadow-[8px_0_28px_-18px_rgba(0,0,0,0.3)]"
            onMouseEnter={cancelPreviewClose}
            onMouseLeave={scheduleNavigationPreviewClose}
          >
            <WorkspaceSidebar
              {...sidebarNavigationProps}
              isOverlay
              onRequestClose={() => {
                cancelPreviewClose();
                setNavigationPreviewOpen(false);
                setNavigationPinned(true);
              }}
            />
          </div>
        ) : null}

        <KolibriPetHost />
      </div>
    );
  }

  return (
    <div
      data-slot="kolibri-workspace-shell"
      data-workspace-mode="compact"
      className="bg-background text-foreground flex h-dvh max-h-dvh w-full max-w-full min-w-0 flex-col overflow-hidden"
    >
      <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
        {primaryPane}
      </main>

      <WorkspaceDialog
        open={mobileNavigationOpen}
        onOpenChange={setMobileNavigationOpen}
        label="Навигация по проектам"
        side="left"
        widthClassName="w-[min(78vw,24rem)]"
      >
        <div id="workspace-project-navigation" className="h-full">
          <WorkspaceSidebar
            {...sidebarNavigationProps}
            isOverlay
            onRequestClose={() => setMobileNavigationOpen(false)}
          />
        </div>
      </WorkspaceDialog>

      <WorkspaceDialog
        open={canvasOpen && canvasPlacement !== "primary"}
        onOpenChange={(open) => {
          setCanvasVisible(open);
          if (!open) setCanvasMaximized(false);
        }}
        label="Рабочая область проекта"
        side="right"
        widthClassName={
          canvasMaximized ? "w-dvw border-x-0" : "w-[min(96vw,48rem)]"
        }
      >
        {canvasSurface}
      </WorkspaceDialog>

      <WorkspaceTaskShelf
        tabs={canvasSession.tabs}
        onRestoreTab={restoreWorkspaceTab}
      />

      <KolibriPetHost />
    </div>
  );
}

type PrimaryPaneProps = {
  children: ReactNode;
  header: ReactNode;
};

function PrimaryPane({
  children,
  header,
}: PrimaryPaneProps) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
      {header}
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
        {children}
      </div>
    </div>
  );
}

type CanvasAssistantPaneProps = {
  assistantDock: AssistantChatDock;
  assistantOpen: boolean;
  assistantPinned: boolean;
  children: ReactNode;
  isDesktop: boolean;
  onAssistantDockChange: (dock: AssistantChatDock) => void;
  onAssistantOpenChange: (open: boolean) => void;
  onAssistantPinnedChange: (pinned: boolean) => void;
  onOpenAccount: () => void;
  onOpenDesktop: () => void;
  showAssistantWidget: boolean;
};

function CanvasAssistantPane({
  assistantDock,
  assistantOpen,
  assistantPinned,
  children,
  isDesktop,
  onAssistantDockChange,
  onAssistantOpenChange,
  onAssistantPinnedChange,
  onOpenAccount,
  onOpenDesktop,
  showAssistantWidget,
}: CanvasAssistantPaneProps) {
  if (!showAssistantWidget) return children;

  const effectiveDock =
    isDesktop && assistantDock === "right" ? "right" : "bottom";
  const assistant = (
    <AssistantChatWidget
      dock={effectiveDock}
      pinned={assistantPinned}
      open={assistantOpen}
      onDockChange={isDesktop ? onAssistantDockChange : undefined}
      onOpenAccount={onOpenAccount}
      onOpenDesktop={onOpenDesktop}
      onOpenChange={onAssistantOpenChange}
      onPinnedChange={onAssistantPinnedChange}
      className={
        assistantPinned && effectiveDock === "bottom"
          ? "border-t border-l-0"
          : undefined
      }
    />
  );

  if (!assistantPinned) {
    return (
      <div className="relative flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
        {children}
        {assistant}
      </div>
    );
  }

  const dockedRight = effectiveDock === "right";
  return (
    <ResizablePanelGroup
      orientation={dockedRight ? "horizontal" : "vertical"}
      className="min-h-0 min-w-0"
    >
      <ResizablePanel
        id="canvas-primary-content"
        defaultSize={dockedRight ? "68%" : "54%"}
        minSize={dockedRight ? 360 : 260}
        className="min-h-0 min-w-0 overflow-hidden"
      >
        <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
          {children}
        </div>
      </ResizablePanel>
      <ResizableHandle
        withHandle
        aria-label={
          dockedRight
            ? "Изменить ширину закреплённого чата"
            : "Изменить высоту закреплённого чата"
        }
      />
      <ResizablePanel
        id="canvas-assistant-chat"
        defaultSize={dockedRight ? "32%" : "46%"}
        minSize={dockedRight ? 280 : 320}
        maxSize={dockedRight ? 520 : undefined}
        className="min-h-0 min-w-0 overflow-hidden"
      >
        {assistant}
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}

type WorkspaceDialogProps = {
  children: ReactNode;
  label: string;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  side: "left" | "right";
  widthClassName: string;
};

function WorkspaceDialog({
  children,
  label,
  onOpenChange,
  open,
  side,
  widthClassName,
}: WorkspaceDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        data-side={side}
        className={[
          "top-0 bottom-0 h-dvh max-w-none translate-x-0 translate-y-0 gap-0 overflow-hidden border-y-0 p-0 shadow-2xl sm:max-w-none",
          "data-[state=closed]:zoom-out-100 data-[state=open]:zoom-in-100",
          side === "left"
            ? "left-0 rounded-l-none rounded-r-[2.5rem] border-l-0 data-[state=closed]:slide-out-to-left-full data-[state=open]:slide-in-from-left-full"
            : "right-0 left-auto rounded-none border-r-0 data-[state=closed]:slide-out-to-right-full data-[state=open]:slide-in-from-right-full",
          widthClassName,
        ].join(" ")}
      >
        <DialogTitle className="sr-only">{label}</DialogTitle>
        <DialogDescription className="sr-only">
          Панель рабочего пространства Kolibri
        </DialogDescription>
        <div className="min-h-0 min-w-0 overflow-hidden">{children}</div>
      </DialogContent>
    </Dialog>
  );
}
