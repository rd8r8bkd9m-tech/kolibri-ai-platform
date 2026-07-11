// @refresh reset
import { Workbench } from "../workbench/Workbench";
import { ProjectWorkspace } from "../windows/ProjectWorkspace";
import { WindowContent } from "../windows/WindowContent";
import { ShellHeader } from "./ShellHeader";
import { ShellNavigation } from "./ShellNavigation";
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
      <ShellHeader
        navigation={shell.navigation}
        onNewProject={shell.newProject}
        onOpenProjects={() => shell.openSystemApp("projects")}
        onRestoreWindows={() => shell.dispatch({ type: "RESTORE_ALL" })}
        projectCount={shell.projects.length}
        title={activeProject?.title || "Рабочее пространство"}
      />
      <section className={`workbench-body ${shell.navigation.layoutPinned ? "dock-pinned" : ""}`}>
        <ShellNavigation
          minimizedWindows={shell.workbench.windows.filter((item) => item.minimized)}
          navigation={shell.navigation}
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
