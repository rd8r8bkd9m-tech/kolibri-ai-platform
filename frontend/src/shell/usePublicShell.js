import { useEstimateRuntime } from "./useEstimateRuntime";
import { useExecutionModeSupport } from "./useExecutionModeSupport";
import { useProjectMessaging } from "./useProjectMessaging";
import { useProjectCommands } from "./useProjectCommands";
import { useProjectStore } from "./useProjectStore";
import { useWorkbenchController } from "./useWorkbenchController";
import { useShellNavigation } from "./useShellNavigation";
import { useProductCapabilities } from "./useProductCapabilities";
export function usePublicShell() {
  const {
    activeProjectId,
    addProject,
    beginProjectRequest,
    busyProjects,
    deleteProject,
    dismissDeleteUndo,
    lastDeleted,
    projects,
    endProjectRequest,
    ensureProjectRemote,
    reconcileProjectRemote,
    setActiveProjectId,
    syncProjectMessage,
    undoDeleteProject,
    updateProject,
  } = useProjectStore();
  const {
    activateProject,
    dispatch,
    focusWindow,
    openArtifact,
    openCanvas,
    openProject,
    openSystemApp,
    workbench,
  } = useWorkbenchController({
    projects,
    setActiveProjectId,
  });
  const navigation = useShellNavigation();
  const productCapabilities = useProductCapabilities();
  const executionModes = useExecutionModeSupport();
  const sendProjectMessage = useProjectMessaging({
    beginProjectRequest,
    busyProjects,
    endProjectRequest,
    ensureProjectRemote,
    reconcileProjectRemote,
    projects,
    syncProjectMessage,
    updateProject,
    dispatch,
  });
  const calculateEstimate = useEstimateRuntime({
    beginProjectRequest,
    endProjectRequest,
    ensureProjectRemote,
    syncProjectMessage,
    updateProject,
  });
  const commands = useProjectCommands({
    activeProjectId,
    addProject,
    executionModes,
    openCanvas,
    projects,
    setActiveProjectId,
    updateProject,
  });
  const newProjectFromHistory = () => {
    commands.newProject();
    if (navigation.mobile) dispatch({ type: "DEACTIVATE", id: "projects-window" });
  };
  const deleteProjectFromHistory = (projectId) => {
    const deleted = deleteProject(projectId);
    if (deleted) dispatch({ type: "REMOVE_PROJECT_WINDOWS", projectId });
  };
  const immersive = workbench.windows.some((item) => item.maximized && !item.minimized);
  return {
    activeProjectId,
    availableTools: productCapabilities.tools,
    busyProjects,
    calculateEstimate,
    deleteProject: deleteProjectFromHistory,
    dispatch,
    dismissDeleteUndo,
    detachCanvas: commands.detachCanvas,
    focusWindow,
    executionModes,
    immersive,
    lastDeleted,
    navigation,
    newProject: commands.newProject,
    newProjectFromHistory,
    openArtifact,
    openProject,
    openProjectFromHistory: navigation.mobile ? activateProject : openProject,
    openSystemApp,
    projects,
    selectTool: commands.selectTool,
    sendProjectMessage,
    setExecutionMode: commands.setExecutionMode,
    updateCanvas: commands.updateCanvas,
    updateProject,
    undoDeleteProject,
    workbench,
  };
}
