import { EstimateWorkspace } from "./EstimateWorkspace";
import { FilesWindow } from "./FilesWindow";
import { ProjectsWindow } from "./ProjectsWindow";
import { ProjectCanvas } from "./ProjectCanvas";
import { ProjectWorkspace } from "./ProjectWorkspace";
import { PdfViewer } from "./PdfViewer";
import { TaskResult } from "./TaskResult";
import { ImageViewer } from "./ImageViewer";

export function WindowContent({ windowState, project, busyProjects, onCalculate, onDeleteProject, onDetachCanvas, onDetachProject, onNewProject, onOpenArtifact, onOpenHistory, onProjectPatch, onRetryMessage, onUpdateCanvas }) {
  const payload = windowState.payload;
  if (windowState.kind === "workspace") {
    return <ProjectWorkspace onCalculate={onCalculate} onDetachCanvas={onDetachCanvas} onDetachProject={onDetachProject} onOpenArtifact={onOpenArtifact} onProjectPatch={onProjectPatch} onRetryMessage={onRetryMessage} onUpdateCanvas={onUpdateCanvas} project={project} />;
  }
  if (windowState.kind === "canvas") {
    const canvas = project?.canvases?.find((item) => item.id === payload.canvasId);
    return <ProjectCanvas canvas={canvas} detached onCalculate={(spec) => onCalculate(payload.parentProjectId, payload.canvasId, spec, project?.executionMode || "fast")} onOpenArtifact={(artifact) => onOpenArtifact(payload.parentProjectId, artifact)} onUpdate={(patch) => onUpdateCanvas(payload.parentProjectId, payload.canvasId, patch)} />;
  }
  if (windowState.kind === "estimate") {
    return <EstimateWorkspace onCalculate={(spec) => onCalculate(payload.parentProjectId, payload.canvasId || `estimate:${payload.parentProjectId}`, spec, project?.executionMode || "fast")} onOpenArtifact={(artifact) => onOpenArtifact(payload.parentProjectId, artifact)} onUpdate={(patch) => onUpdateCanvas(payload.parentProjectId, payload.canvasId || `estimate:${payload.parentProjectId}`, patch)} payload={payload} />;
  }
  if (windowState.kind === "projects") {
    return <ProjectsWindow busyProjects={busyProjects} items={payload.items || []} onDelete={onDeleteProject} onNew={onNewProject} onOpen={onOpenHistory} />;
  }
  if (windowState.kind === "files") {
    return <FilesWindow items={payload.items || []} />;
  }
  if (windowState.kind === "pdf") {
    return <PdfViewer artifact={payload.artifact || payload.artifacts?.[0]} />;
  }
  if (windowState.kind === "image") {
    return <ImageViewer artifact={payload.artifact || payload.artifacts?.[0]} />;
  }
  return <TaskResult payload={payload} />;
}
