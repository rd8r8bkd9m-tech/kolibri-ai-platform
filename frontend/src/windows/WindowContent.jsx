import { EstimateWorkspace } from "./EstimateWorkspace";
import { FilesWindow } from "./FilesWindow";
import { ProjectsWindow } from "./ProjectsWindow";
import { ProjectCanvas } from "./ProjectCanvas";
import { ProjectWorkspace } from "./ProjectWorkspace";
import { PdfViewer } from "./PdfViewer";
import { TaskResult } from "./TaskResult";

export function WindowContent({ windowState, project, projectBusy, executionModes, onCalculate, onDetachCanvas, onDetachProject, onExecutionMode, onNewProject, onOpenArtifact, onOpenHistory, onProjectPatch, onSendMessage, onUpdateCanvas }) {
  const payload = windowState.payload;
  if (windowState.kind === "workspace") {
    return <ProjectWorkspace busy={projectBusy} executionModes={executionModes} onCalculate={onCalculate} onDetachCanvas={onDetachCanvas} onDetachProject={onDetachProject} onExecutionMode={onExecutionMode} onOpenArtifact={onOpenArtifact} onProjectPatch={onProjectPatch} onSend={onSendMessage} onUpdateCanvas={onUpdateCanvas} project={project} />;
  }
  if (windowState.kind === "canvas") {
    const canvas = project?.canvases?.find((item) => item.id === payload.canvasId);
    return <ProjectCanvas canvas={canvas} detached onCalculate={(spec) => onCalculate(payload.parentProjectId, payload.canvasId, spec, project?.executionMode || "fast")} onOpenArtifact={(artifact) => onOpenArtifact(payload.parentProjectId, artifact)} onUpdate={(patch) => onUpdateCanvas(payload.parentProjectId, payload.canvasId, patch)} />;
  }
  if (windowState.kind === "estimate") {
    return <EstimateWorkspace onCalculate={(spec) => onCalculate(payload.parentProjectId, payload.canvasId || `estimate:${payload.parentProjectId}`, spec, project?.executionMode || "fast")} payload={payload} />;
  }
  if (windowState.kind === "projects") {
    return <ProjectsWindow items={payload.items || []} onNew={onNewProject} onOpen={onOpenHistory} />;
  }
  if (windowState.kind === "files") {
    return <FilesWindow items={payload.items || []} />;
  }
  if (windowState.kind === "pdf") {
    return <PdfViewer artifact={payload.artifact || payload.artifacts?.[0]} />;
  }
  return <TaskResult payload={payload} />;
}
