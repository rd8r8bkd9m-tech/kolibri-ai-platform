import { History, Layers3, ServerCog, SquarePen } from "lucide-react";
import { Workbench } from "../workbench/Workbench";
import { ProjectWorkspace } from "../windows/ProjectWorkspace";
import { WindowContent } from "../windows/WindowContent";
import { SystemBar } from "./SystemBar";
import { ToolDock } from "./ToolDock";
import { usePublicShell } from "./usePublicShell";

export function PublicShell() {
  const shell = usePublicShell();
  const activeProject = shell.projects.find((project) => project.id === shell.activeProjectId) || shell.projects[0];
  const renderContent = (windowState) => (
    <WindowContent
      onCalculate={shell.calculateEstimate}
      onDetachCanvas={shell.detachCanvas}
      onDetachProject={shell.openProject}
      onExecutionMode={shell.setExecutionMode}
      onNewProject={shell.newProject}
      onOpenArtifact={shell.openArtifact}
      onOpenHistory={shell.openProject}
      onProjectPatch={shell.updateProject}
      onSendMessage={shell.sendProjectMessage}
      onUpdateCanvas={shell.updateCanvas}
      executionModes={shell.executionModes}
      project={shell.projects.find((project) => project.id === (windowState.payload?.projectId || windowState.payload?.parentProjectId))}
      projectBusy={Boolean(shell.busyProjects[windowState.payload?.projectId || windowState.payload?.parentProjectId])}
      windowState={windowState}
    />
  );
  const renderPrimary = () => activeProject ? (
    <ProjectWorkspace
      busy={Boolean(shell.busyProjects[activeProject.id])}
      executionModes={shell.executionModes}
      onCalculate={shell.calculateEstimate}
      onDetachCanvas={shell.detachCanvas}
      onDetachProject={shell.openProject}
      onExecutionMode={shell.setExecutionMode}
      onOpenArtifact={shell.openArtifact}
      onSend={shell.sendProjectMessage}
      onProjectPatch={shell.updateProject}
      onUpdateCanvas={shell.updateCanvas}
      project={activeProject}
    />
  ) : null;

  return (
    <main className={`kolibri-workbench ${shell.immersive ? "is-immersive" : ""}`}>
      <SystemBar subtitle="Kolibri AI OS" title={activeProject?.title || "Рабочее пространство"}>
        <button aria-label="История проектов" onClick={() => shell.openSystemApp("projects")} type="button">
          <History size={18} />
          <span>История</span>
          {shell.projects.length > 0 && <b>{shell.projects.length}</b>}
        </button>
        <button aria-label="Новый проект" onClick={shell.newProject} type="button"><SquarePen size={18} /></button>
        <button
          aria-label="Восстановить окна"
          onClick={() => shell.dispatch({ type: "RESTORE_ALL" })}
          type="button"
        >
          <Layers3 size={18} />
        </button>
        <a aria-label="Control Center" href="/control"><ServerCog size={18} /></a>
      </SystemBar>
      <section className={`workbench-body ${shell.dockExpanded ? "dock-expanded" : ""}`}>
        <ToolDock
          expanded={shell.dockExpanded}
          minimizedWindows={shell.workbench.windows.filter((item) => item.minimized)}
          onExpanded={shell.setDockExpanded}
          onNewProject={shell.newProject}
          onRestoreWindow={(id) => shell.dispatch({ type: "FOCUS", id })}
          onSelect={shell.selectTool}
          onSystem={shell.openSystemApp}
          selected={shell.projects.find((project) => project.id === shell.activeProjectId)?.draftTool || ""}
        />
        <Workbench
          dispatch={shell.dispatch}
          focusedId={shell.workbench.focusedId}
          onFocus={shell.focusWindow}
          renderContent={renderContent}
          renderPrimary={renderPrimary}
          windows={shell.workbench.windows}
        />
      </section>
    </main>
  );
}
