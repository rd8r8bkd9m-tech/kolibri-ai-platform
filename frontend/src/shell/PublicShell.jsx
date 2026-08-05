// @refresh reset
import { useRef } from "react";
import { ProjectDeletionNotice } from "./ProjectDeletionNotice";
import { ShellComposer } from "./ShellComposer";
import { ShellHeader } from "./ShellHeader";
import { ShellWorkbench } from "./ShellWorkbench";
import { usePublicShell } from "./usePublicShell";
import { useShellViewport } from "./useShellViewport";

export function PublicShell() {
  const shell = usePublicShell();
  const root = useRef(null);
  useShellViewport(root);
  const activeProject = shell.projects.find((project) => project.id === shell.activeProjectId) || shell.projects[0];

  return (
    <main className={`kolibri-workbench ${shell.immersive ? "is-immersive" : ""}`} data-app-version="v4" ref={root}>
      <ShellHeader
        navigation={shell.navigation}
        onNewProject={shell.newProject}
        onOpenProjects={() => shell.openSystemApp("projects")}
        onRestoreWindows={() => shell.dispatch({ type: "RESTORE_ALL" })}
        projectCount={shell.projects.length}
        title={activeProject?.title || "Рабочее пространство"}
      />
      <ShellWorkbench activeProject={activeProject} shell={shell} />
      <ShellComposer
        availableTools={shell.availableTools}
        busy={Boolean(shell.busyProjects[activeProject?.id])}
        executionModes={shell.executionModes}
        key={activeProject?.id || "no-project"}
        onExecutionMode={shell.setExecutionMode}
        onProjectPatch={shell.updateProject}
        onSend={shell.sendProjectMessage}
        project={activeProject}
      />
      <ProjectDeletionNotice deletion={shell.lastDeleted} onDismiss={shell.dismissDeleteUndo} onUndo={shell.undoDeleteProject} />
    </main>
  );
}
