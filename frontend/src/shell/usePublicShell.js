import { useState } from "react";
import { useEstimateRuntime } from "./useEstimateRuntime";
import { useExecutionModeSupport } from "./useExecutionModeSupport";
import { useProjectMessaging } from "./useProjectMessaging";
import { useProjectCommands } from "./useProjectCommands";
import { useProjectStore } from "./useProjectStore";
import { useWorkbenchController } from "./useWorkbenchController";

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
  const [dockExpanded, setDockExpanded] = useState(false);
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

  const immersive = workbench.windows.some((item) => item.maximized && !item.minimized);

  return {
    activeProjectId,
    busyProjects,
    calculateEstimate,
    dispatch,
    detachCanvas: commands.detachCanvas,
    dockExpanded,
    focusWindow,
    executionModes,
    immersive,
    newProject: commands.newProject,
    openArtifact,
    openProject,
    openSystemApp,
    projects,
    selectTool: commands.selectTool,
    sendProjectMessage,
    setDockExpanded,
    setExecutionMode: commands.setExecutionMode,
    updateCanvas: commands.updateCanvas,
    updateProject,
    workbench,
  };
}
