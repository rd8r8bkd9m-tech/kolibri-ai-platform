import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink, FileText, MessageSquareText, PencilLine } from "lucide-react";
import { materializedArtifacts } from "../shell/projectModel";
import { ProjectCanvas } from "./ProjectCanvas";
import { WorkSummary } from "./shared/WorkSummary";

function Conversation({ canvases, messages, onRetry, renderCanvas }) {
  const viewport = useRef(null);
  useEffect(() => {
    if (viewport.current) viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [messages, canvases]);

  return (
    <div className="project-conversation" ref={viewport}>
      {!messages.length && (
        <div className="project-welcome">
          <span>Новый проект</span>
          <h2>Чем помочь?</h2>
          <p>Один проект хранит весь диалог и результаты. Отдельное окно открывается только по вашей команде.</p>
        </div>
      )}
      {messages.map((message, index) => {
        const canvas = message.canvasId ? canvases.find((item) => item.id === message.canvasId) : null;
        const assistantText = message.text || "";
        const canRetry = message.recoverable && index === messages.length - 1;
        return (
          <div className="project-message-block" key={message.id}>
            <article className={`project-message is-${message.role} ${message.status ? `is-${message.status}` : ""}`}>
              <span>{message.role === "user" ? "Вы" : "Kolibri"}</span>
              <div>
                {message.role === "assistant"
                  ? (assistantText ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{assistantText}</ReactMarkdown> : null)
                  : <p>{message.text}</p>}
              </div>
              {message.role === "assistant" && (
                <WorkSummary
                  completedAt={message.updatedAt}
                  onRetry={canRetry ? () => onRetry(message) : undefined}
                  progressText={message.progressText}
                  recoverable={canRetry}
                  startedAt={message.startedAt || message.createdAt}
                  status={message.status || "completed"}
                  summary={message.workSummary}
                />
              )}
            </article>
            {canvas && renderCanvas(canvas)}
          </div>
        );
      })}
    </div>
  );
}

function ProjectEditor({ canvases, renderCanvas }) {
  if (!canvases.length) {
    return <div className="project-editor-empty"><PencilLine size={24} /><h3>Редактор пока пуст</h3><p>Создайте смету через composer.</p></div>;
  }
  return <div className="project-editor">{canvases.map((canvas) => <div key={canvas.id}>{renderCanvas(canvas)}</div>)}</div>;
}

export function ProjectWorkspace({
  project,
  onCalculate,
  onDetachCanvas,
  onDetachProject,
  onOpenArtifact,
  onProjectPatch,
  onRetryMessage,
  onUpdateCanvas,
}) {
  const viewMode = project.viewMode === "editor" ? "editor" : "dialog";
  const canvases = project.canvases || [];
  const artifacts = materializedArtifacts(project.artifacts);
  const retryMessage = (message) => onRetryMessage?.(
    project.id,
    message.retryPrompt,
    message.retryTool || "",
    message.retryExecutionMode || project.executionMode || "fast",
    { retryMessageId: message.id },
  );
  const renderCanvas = (canvas) => (
    <ProjectCanvas
      canvas={canvas}
      onCalculate={(spec) => onCalculate(project.id, canvas.id, spec, project.executionMode || "fast")}
      onDetach={() => onDetachCanvas(project.id, canvas)}
      onOpenArtifact={(artifact) => onOpenArtifact?.(project.id, artifact)}
      onUpdate={(patch) => onUpdateCanvas(project.id, canvas.id, patch)}
    />
  );

  return (
    <section className="project-workspace">
      <header className="project-view-bar">
        <div role="group" aria-label="Режим проекта">
          <button aria-pressed={viewMode === "dialog"} onClick={() => onProjectPatch(project.id, { viewMode: "dialog" })} type="button"><MessageSquareText size={15} /> Диалог</button>
          <button aria-pressed={viewMode === "editor"} onClick={() => onProjectPatch(project.id, { viewMode: "editor" })} type="button"><PencilLine size={15} /> Редактор</button>
        </div>
        <button aria-label="Открыть проект отдельным окном" onClick={() => onDetachProject(project)} type="button"><ExternalLink size={15} /><span>Открыть окном</span></button>
      </header>
      {viewMode === "dialog"
        ? <Conversation canvases={canvases} messages={project.messages || []} onRetry={retryMessage} renderCanvas={renderCanvas} />
        : <ProjectEditor canvases={canvases} renderCanvas={renderCanvas} />}
      {!!artifacts.length && (
        <div className="project-artifacts" aria-label="Результаты проекта">
          {artifacts.map((artifact, index) => (
            <button key={artifact.reference_sha256 || artifact.id || index} onClick={() => onOpenArtifact?.(project.id, artifact)} type="button">
              <FileText size={16} /><span>{artifact.display_name || artifact.name || artifact.kind || `Результат ${index + 1}`}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
