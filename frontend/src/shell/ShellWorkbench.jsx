import { Workbench } from "../workbench/Workbench";
import { ProjectWorkspace } from "../windows/ProjectWorkspace";
import { WindowContent } from "../windows/WindowContent";
import { ShellNavigation } from "./ShellNavigation";

export function ShellWorkbench({ activeProject, shell }) {
  const renderContent = (windowState) => (
    <WindowContent
      busyProjects={shell.busyProjects}
      onCalculate={shell.calculateEstimate}
      onDetachCanvas={shell.detachCanvas}
      onDetachProject={shell.openProject}
      onDeleteProject={shell.deleteProject}
      onNewProject={shell.newProjectFromHistory}
      onOpenArtifact={shell.openArtifact}
      onOpenHistory={shell.openProjectFromHistory}
      onProjectPatch={shell.updateProject}
      onRetryMessage={shell.sendProjectMessage}
      onUpdateCanvas={shell.updateCanvas}
      project={shell.projects.find((project) => project.id === (windowState.payload?.projectId || windowState.payload?.parentProjectId))}
      windowState={windowState}
    />
  );
  const renderPrimary = () => activeProject ? (
    <ProjectWorkspace
      onCalculate={shell.calculateEstimate}
      onDetachCanvas={shell.detachCanvas}
      onDetachProject={shell.openProject}
      onOpenArtifact={shell.openArtifact}
      onProjectPatch={shell.updateProject}
      onRetryMessage={shell.sendProjectMessage}
      onUpdateCanvas={shell.updateCanvas}
      project={activeProject}
    />
  ) : null;

  return (
    <section className={`workbench-body ${shell.navigation.layoutPinned ? "dock-pinned" : ""}`}>
      <ShellNavigation
        availableTools={shell.availableTools}
        minimizedWindows={shell.workbench.windows.filter((item) => item.minimized)}
        navigation={shell.navigation}
        onNewProject={shell.newProject}
        onRestoreWindow={(id) => shell.dispatch({ type: "FOCUS", id })}
        onSelect={shell.selectTool}
        onSystem={shell.openSystemApp}
        selected={activeProject?.draftTool || ""}
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
  );
}
