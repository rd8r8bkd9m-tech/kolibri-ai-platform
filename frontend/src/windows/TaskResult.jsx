import { FileText } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { StatusBadge } from "./shared/StatusBadge";

export function TaskResult({ payload }) {
  const task = payload.task;
  const status = payload.status || task?.status || (payload.error ? "failed" : "running");
  const taskText = task?.result?.type === "verified_provider_response" ? task.result.text : payload.text;
  const artifacts = task?.artifacts || payload.artifacts || [];
  const missing = task?.artifact_delivery?.missing || [];

  if (status === "running") {
    return (
      <div className="task-running">
        <span className="activity-ring" />
        <h2>Kolibri выполняет задачу</h2>
        <p>Планирует, подключает инструменты и проверяет результат.</p>
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="task-error">
        <StatusBadge status="failed" />
        <h2>Задача не завершена</h2>
        <p>{payload.error || "Исполнительный контур временно недоступен."}</p>
      </div>
    );
  }

  return (
    <div className="task-result">
      <header>
        <StatusBadge status={status} />
        {payload.endpoint && <small>{payload.endpoint}</small>}
      </header>
      {taskText ? (
        <article className="markdown-result">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{taskText}</ReactMarkdown>
        </article>
      ) : <p className="empty-result">Текстовый результат не получен.</p>}
      {!!missing.length && (
        <aside className="truth-note">
          <strong>Ещё не материализовано</strong>
          <span>{missing.join(", ")}</span>
        </aside>
      )}
      {!!artifacts.length && (
        <div className="artifact-list">
          {artifacts.map((artifact, index) => (
            <article key={artifact.reference_sha256 || artifact.id || index}>
              <FileText size={18} />
              <span>
                <strong>{artifact.name || artifact.kind || `Артефакт ${index + 1}`}</strong>
                <small>{artifact.status || "verified"}</small>
              </span>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
