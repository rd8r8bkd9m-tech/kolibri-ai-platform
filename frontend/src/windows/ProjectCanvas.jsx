import { ExternalLink, FileText } from "lucide-react";
import { EstimateWorkspace } from "./EstimateWorkspace";
import { StatusBadge } from "./shared/StatusBadge";
import { WorkSummary } from "./shared/WorkSummary";

const EXPORT_KINDS = ["pdf", "xlsx", "docx"];

function CanvasArtifacts({ artifacts, onOpen }) {
  return (
    <div className="canvas-artifacts">
      {artifacts.map((artifact, index) => (
        <button key={artifact.reference_sha256 || artifact.id || index} onClick={() => onOpen?.(artifact)} type="button">
          <FileText size={15} /> {artifact.name || artifact.deliverable_type || artifact.kind || `Файл ${index + 1}`}
        </button>
      ))}
    </div>
  );
}

export function ProjectCanvas({ canvas, detached = false, onCalculate, onDetach, onOpenArtifact, onUpdate }) {
  if (!canvas) return null;
  const artifacts = canvas.artifacts || canvas.task?.artifacts || [];
  const text = canvas.draftText ?? canvas.text ?? canvas.task?.result?.text ?? "";
  const metadata = canvas.metadata || {};
  const readiness = canvas.readiness || (canvas.task?.result?.type === "estimate_readiness" ? canvas.task.result.readiness : null);

  return (
    <section className={`project-canvas ${detached ? "is-detached" : ""}`} data-canvas-kind={canvas.kind}>
      <header className="canvas-header">
        <div>
          <StatusBadge status={canvas.status || "draft"} />
          <strong>{canvas.title}</strong>
          <small>Версия {canvas.version || 1}</small>
        </div>
        {!detached && <button onClick={onDetach} type="button"><ExternalLink size={15} /> Открыть отдельно</button>}
      </header>
      {canvas.kind === "estimate" ? (
        <>
          <div className={`estimate-metadata ${readiness ? "is-readiness" : ""}`}>
            {readiness ? (
              <>
                <div><small>Регион</small><strong>{readiness.known_facts?.region || "Требует подтверждения"}</strong></div>
                <div><small>Денежный итог</small><strong>Не рассчитан</strong></div>
              </>
            ) : (
              <>
                <label>Регион<input onChange={(event) => onUpdate({ metadata: { ...metadata, region: event.target.value } })} placeholder="Например, Москва" value={metadata.region || ""} /></label>
                <label>Источник цен<input onChange={(event) => onUpdate({ metadata: { ...metadata, provenance: event.target.value } })} placeholder="норматив / каталог / договор" value={metadata.provenance || "manual"} /></label>
              </>
            )}
            <div className="estimate-export-placeholders" aria-label="Экспорт сметы">
              {EXPORT_KINDS.map((kind) => {
                const artifact = artifacts.find((item) => item.deliverable_type === kind || item.kind === kind);
                return <button disabled={!artifact} key={kind} onClick={() => artifact && onOpenArtifact?.(artifact)} type="button">{kind.toUpperCase()}</button>;
              })}
            </div>
          </div>
          <EstimateWorkspace onCalculate={onCalculate} onOpenArtifact={onOpenArtifact} onUpdate={onUpdate} payload={canvas} />
        </>
      ) : (
        <>
          <textarea
            aria-label="Редактор результата"
            className="canvas-manual-editor"
            onChange={(event) => onUpdate({ draftText: event.target.value })}
            placeholder={canvas.status === "running" ? "Kolibri выполняет задачу…" : "Проверенный текст результата появится здесь"}
            readOnly={canvas.status === "running"}
            value={text}
          />
          {!!canvas.task?.artifact_delivery?.missing?.length && <p className="canvas-missing">Не материализовано: {canvas.task.artifact_delivery.missing.join(", ")}</p>}
          {!!artifacts.length && <CanvasArtifacts artifacts={artifacts} onOpen={onOpenArtifact} />}
        </>
      )}
      <WorkSummary summary={canvas.workSummary} />
      {canvas.error && <div className="inline-error">{canvas.error}</div>}
    </section>
  );
}
