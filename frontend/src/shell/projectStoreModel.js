import { recoverInterruptedProject, recoverInterruptedProjects } from "./projectMessageRecovery.js";

function removeBusyProject(busyProjects, projectId) {
  const next = { ...(busyProjects || {}) };
  delete next[projectId];
  return next;
}

export function sameProjectSnapshot(left, right) {
  if (!left || !right || left.id !== right.id) return false;
  const leftSnapshot = { ...left };
  const rightSnapshot = { ...right };
  delete leftSnapshot.remoteId;
  delete rightSnapshot.remoteId;
  return JSON.stringify(leftSnapshot) === JSON.stringify(rightSnapshot);
}

function interruptedProject(project) {
  return {
    ...project,
    messages: (project.messages || []).map((message) => message.status === "running"
      ? {
          ...message,
          status: "cancelled",
          progressText: "",
          text: message.text || "Запрос остановлен при удалении проекта.",
          updatedAt: new Date().toISOString(),
        }
      : message),
    canvases: (project.canvases || []).map((canvas) => canvas.status === "running"
      ? { ...canvas, status: "cancelled", error: "Выполнение остановлено при удалении проекта." }
      : canvas),
  };
}

function mergeHydratedProject(current, hydrated, preserveActive = false) {
  const hydratedMessages = new Map((hydrated.messages || []).map((message) => [message.id, message]));
  const messages = (current.messages || []).map((message) => {
    const remote = hydratedMessages.get(message.id);
    hydratedMessages.delete(message.id);
    return remote ? {
      ...remote,
      ...message,
      remoteId: remote.remoteId || message.remoteId,
      responseId: message.responseId || remote.responseId,
    } : message;
  });
  const merged = {
    ...hydrated,
    ...current,
    remoteId: hydrated.remoteId || current.remoteId,
    messages: [...messages, ...hydratedMessages.values()],
  };
  return preserveActive ? merged : recoverInterruptedProject(merged);
}

export function createProjectStoreState(projects, savedActiveProjectId = "") {
  const list = recoverInterruptedProjects(projects);
  const activeProjectId = list.some((project) => project.id === savedActiveProjectId)
    ? savedActiveProjectId
    : list[0]?.id || "";
  return {
    projects: list,
    activeProjectId,
    busyProjects: {},
    lastDeleted: null,
  };
}

export function deleteProjectState(state, projectId, replacementProject = null, operationId = "") {
  if (state.busyProjects?.[projectId]) return state;
  const index = state.projects.findIndex((project) => project.id === projectId);
  if (index < 0) return state;
  const project = interruptedProject(state.projects[index]);
  const remaining = state.projects.filter((item) => item.id !== projectId);
  const generatedReplacement = remaining.length === 0 ? replacementProject : null;
  if (generatedReplacement) remaining.push(generatedReplacement);
  const wasActive = state.activeProjectId === projectId;
  const fallbackIndex = Math.min(index, Math.max(remaining.length - 1, 0));
  const activeStillExists = remaining.some((item) => item.id === state.activeProjectId);
  const activeProjectId = wasActive || !activeStillExists
    ? remaining[fallbackIndex]?.id || remaining[0]?.id || ""
    : state.activeProjectId;

  return {
    ...state,
    projects: remaining,
    activeProjectId,
    busyProjects: removeBusyProject(state.busyProjects, projectId),
    lastDeleted: {
      project,
      index,
      wasActive,
      previousActiveProjectId: state.activeProjectId,
      replacementProject: generatedReplacement,
      activeChanged: false,
      operationId,
    },
  };
}

export function restoreProjectState(state, { preserveCurrentActive = false } = {}) {
  const deletion = state.lastDeleted;
  if (!deletion?.project) return state;
  if (state.projects.some((project) => project.id === deletion.project.id)) {
    return { ...state, lastDeleted: null };
  }

  let projects = [...state.projects];
  if (deletion.replacementProject) {
    projects = projects.filter((project) => !sameProjectSnapshot(project, deletion.replacementProject));
  }
  const index = Math.min(Math.max(deletion.index, 0), projects.length);
  projects.splice(index, 0, deletion.project);
  const activeProjectId = deletion.wasActive && !deletion.activeChanged && !preserveCurrentActive
    ? deletion.project.id
    : projects.some((project) => project.id === state.activeProjectId)
      ? state.activeProjectId
      : projects.some((project) => project.id === deletion.previousActiveProjectId)
        ? deletion.previousActiveProjectId
        : projects[0]?.id || "";

  return { ...state, projects, activeProjectId, lastDeleted: null };
}

export function projectStoreReducer(state, action) {
  switch (action.type) {
    case "UPDATE_PROJECT":
      return {
        ...state,
        projects: state.projects.map((project) => {
          if (project.id !== action.projectId) return project;
          const next = typeof action.updater === "function"
            ? action.updater(project)
            : { ...project, ...action.updater };
          return { ...next, updatedAt: action.updatedAt };
        }),
      };
    case "ADD_PROJECT":
      return {
        ...state,
        projects: [action.project, ...state.projects],
        activeProjectId: action.activate ? action.project.id : state.activeProjectId,
      };
    case "SET_ACTIVE_PROJECT":
      return state.projects.some((project) => project.id === action.projectId)
        ? {
            ...state,
            activeProjectId: action.projectId,
            lastDeleted: state.lastDeleted && action.projectId !== state.activeProjectId
              ? { ...state.lastDeleted, activeChanged: true }
              : state.lastDeleted,
          }
        : state;
    case "SET_PROJECT_BUSY":
      return action.busy
        ? { ...state, busyProjects: { ...state.busyProjects, [action.projectId]: true } }
        : { ...state, busyProjects: removeBusyProject(state.busyProjects, action.projectId) };
    case "DELETE_PROJECT":
      return deleteProjectState(state, action.projectId, action.replacementProject, action.operationId);
    case "RESTORE_PROJECT":
      return restoreProjectState(state, { preserveCurrentActive: action.preserveCurrentActive });
    case "RECONCILE_PROJECTS": {
      const baseIds = new Set(action.baseProjectIds || []);
      const currentById = new Map(state.projects.map((project) => [project.id, project]));
      const reconciled = recoverInterruptedProjects(action.projects).flatMap((hydrated) => {
        const current = currentById.get(hydrated.id);
        currentById.delete(hydrated.id);
        if (!current && baseIds.has(hydrated.id)) return [];
        if (!current) return [hydrated];
        return [Date.parse(current.updatedAt || "") > action.startedAt
          ? mergeHydratedProject(current, hydrated, Boolean(state.busyProjects?.[hydrated.id]))
          : hydrated];
      });
      reconciled.push(...currentById.values());
      const activeProjectId = reconciled.some((project) => project.id === state.activeProjectId)
        ? state.activeProjectId
        : reconciled[0]?.id || "";
      return { ...state, projects: reconciled, activeProjectId };
    }
    case "BIND_REMOTE_PROJECT":
      return {
        ...state,
        projects: state.projects.map((project) => project.id === action.projectId
          ? { ...project, remoteId: action.remoteId }
          : project),
      };
    case "BIND_REMOTE_MESSAGE":
      return {
        ...state,
        projects: state.projects.map((project) => project.id === action.projectId
          ? {
              ...project,
              messages: (project.messages || []).map((message) => message.id === action.messageId
                ? { ...message, ...action.patch }
                : message),
            }
          : project),
      };
    case "ROLLBACK_PROJECT_DELETE": {
      if (!action.deletion?.project || state.projects.some((project) => project.id === action.deletion.project.id)) return state;
      const currentDeletion = state.lastDeleted;
      const restored = restoreProjectState(
        { ...state, lastDeleted: action.deletion },
        { preserveCurrentActive: true },
      );
      return {
        ...restored,
        lastDeleted: currentDeletion?.operationId === action.deletion.operationId
          ? null
          : currentDeletion,
      };
    }
    case "DISMISS_DELETION":
      return { ...state, lastDeleted: null };
    default:
      return state;
  }
}
