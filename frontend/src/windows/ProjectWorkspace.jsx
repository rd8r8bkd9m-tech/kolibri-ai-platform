import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink, FileText, MessageSquareText, PencilLine } from "lucide-react";
import { Composer } from "../shell/Composer";
import { ProjectCanvas } from "./ProjectCanvas";
import { WorkSummary } from "./shared/WorkSummary";

function Conversation({ canvases, messages, renderCanvas }) {
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
      {messages.map((message) => {
        const canvas = message.canvasId ? canvases.find((item) => item.id === message.canvasId) : null;
        const assistantText = message.text || message.progressText || "";
        return (
          <div className="project-message-block" key={message.id}>
            <article className={`project-message is-${message.role} ${message.status ? `is-${message.status}` : ""}`}>
              <span>{message.role === "user" ? "Вы" : "Kolibri"}</span>
              <div>
                {message.role === "assistant"
                  ? (assistantText ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{assistantText}</ReactMarkdown> : null)
                  : <p>{message.text}</p>}
              </div>
              {message.role === "assistant" && <WorkSummary summary={message.workSummary} />}
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
    return <div className="project-editor-empty"><PencilLine size={24} /><h3>Редактор пока пуст</h3><p>Создайте смету, документ, сайт или приложение через composer.</p></div>;
  }
  return <div className="project-editor">{canvases.map((canvas) => <div key={canvas.id}>{renderCanvas(canvas)}</div>)}</div>;
}

export function ProjectWorkspace({
  project,
  busy,
  executionModes,
  onCalculate,
  onDetachCanvas,
  onDetachProject,
  onExecutionMode,
  onOpenArtifact,
  onProjectPatch,
  onSend,
  onUpdateCanvas,
}) {
  const [value, setValue] = useState("");
  const [selectedTool, setSelectedTool] = useState("");
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const supportedModes = executionModes?.length ? executionModes : ["fast"];
  const effectiveMode = supportedModes.includes(project.executionMode) ? project.executionMode : "fast";
  const [executionMode, setExecutionMode] = useState(effectiveMode);
  const viewMode = project.viewMode === "editor" ? "editor" : "dialog";
  const canvases = project.canvases || [];

  useEffect(() => {
    if (project.draftTool) setSelectedTool(project.draftTool);
  }, [project.draftTool]);
  useEffect(() => setExecutionMode(effectiveMode), [effectiveMode]);

  const submit = (text) => {
    const clean = text.trim();
    if (!clean || busy) return;
    onSend(project.id, clean, selectedTool, executionMode);
    setValue("");
    setSelectedTool("");
  };
  const renderCanvas = (canvas) => (
    <ProjectCanvas
      canvas={canvas}
      onCalculate={(spec) => onCalculate(project.id, canvas.id, spec, executionMode)}
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
        ? <Conversation canvases={canvases} messages={project.messages || []} renderCanvas={renderCanvas} />
        : <ProjectEditor canvases={canvases} renderCanvas={renderCanvas} />}
      {!!project.artifacts?.length && (
        <div className="project-artifacts" aria-label="Результаты проекта">
          {project.artifacts.map((artifact, index) => (
            <button key={artifact.reference_sha256 || artifact.id || index} onClick={() => onOpenArtifact?.(project.id, artifact)} type="button">
              <FileText size={16} /><span>{artifact.name || artifact.kind || `Результат ${index + 1}`}</span>
            </button>
          ))}
        </div>
      )}
      <Composer
        busy={busy}
        embedded
        executionMode={executionMode}
        executionModes={supportedModes}
        onChange={setValue}
        onExecutionMode={(mode) => { setExecutionMode(mode); onExecutionMode?.(project.id, mode); }}
        onSubmit={submit}
        onTool={setSelectedTool}
        selectedTool={selectedTool}
        setToolMenuOpen={setToolMenuOpen}
        toolMenuOpen={toolMenuOpen}
        value={value}
      />
    </section>
  );
}
