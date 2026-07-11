import { useEstimateRuntime } from "./useEstimateRuntime";
import { useExecutionModeSupport } from "./useExecutionModeSupport";
import { useProjectMessaging } from "./useProjectMessaging";
import { useProjectCommands } from "./useProjectCommands";
import { useProjectStore } from "./useProjectStore";
import { useWorkbenchController } from "./useWorkbenchController";
import { useShellNavigation } from "./useShellNavigation";

export function usePublicShell() {
  const {
    activeProjectId,
    addProject,
    busyProjects,
    projects,
    setActiveProjectId,
    setProjectBusy,
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
  const executionModes = useExecutionModeSupport();

  const sendProjectMessage = useProjectMessaging({
    busyProjects,
    projects,
    setProjectBusy,
    updateProject,
    dispatch,
  });
  const calculateEstimate = useEstimateRuntime({
    setProjectBusy,
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

  const immersive = workbench.windows.some((item) => item.maximized && !item.minimized);

  return {
    activeProjectId,
    busyProjects,
    calculateEstimate,
    dispatch,
    detachCanvas: commands.detachCanvas,
    focusWindow,
    executionModes,
    immersive,
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
    workbench,
  };
}
