import { ExternalLink, FileText, Image as ImageIcon } from "lucide-react";
import { materializedArtifacts } from "../shell/projectModel";
import { EstimateWorkspace } from "./EstimateWorkspace";
import { estimateArtifactDisplayName, estimateTitleFromPayload } from "../estimate/estimateTitle";
import { StatusBadge } from "./shared/StatusBadge";
import { WorkSummary } from "./shared/WorkSummary";
import { imageArtifactUrl } from "../runtime/artifactLocators";

const EXPORT_KINDS = ["pdf", "xlsx", "docx"];

function CanvasArtifacts({ artifacts, estimateTitle, onOpen }) {
  return (
    <div className="canvas-artifacts">
      {artifacts.map((artifact, index) => (
        <button key={artifact.reference_sha256 || artifact.id || index} onClick={() => onOpen?.(estimateTitle ? { ...artifact, display_name: estimateArtifactDisplayName(artifact, estimateTitle) } : artifact)} type="button">
          {artifact.kind === "image" || String(artifact.media_type || "").startsWith("image/") ? <ImageIcon size={15} /> : <FileText size={15} />} {estimateTitle ? estimateArtifactDisplayName(artifact, estimateTitle) : artifact.name || artifact.deliverable_type || artifact.kind || `Файл ${index + 1}`}
        </button>
      ))}
    </div>
  );
}

export function ProjectCanvas({ canvas, detached = false, onCalculate, onDetach, onOpenArtifact, onUpdate }) {
  if (!canvas) return null;
  const artifacts = materializedArtifacts(canvas.artifacts || canvas.task?.artifacts);
  const text = canvas.draftText ?? canvas.text ?? canvas.task?.result?.text ?? "";
  const metadata = canvas.metadata || {};
  const readiness = canvas.readiness || (canvas.task?.result?.type === "estimate_readiness" ? canvas.task.result.readiness : null);
  const displayTitle = canvas.kind === "estimate" ? estimateTitleFromPayload(canvas) : canvas.title;
  const imagePreview = canvas.kind === "image" ? imageArtifactUrl(artifacts[0]) : "";

  return (
    <section className={`project-canvas ${detached ? "is-detached" : ""}`} data-canvas-kind={canvas.kind}>
      <header className="canvas-header">
        <div>
          <StatusBadge status={canvas.status || "draft"} />
          <strong>{displayTitle}</strong>
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
            {!!artifacts.some((item) => EXPORT_KINDS.includes(item.deliverable_type || item.kind)) && (
              <div className="estimate-export-actions" aria-label="Материализованные файлы сметы">
                {artifacts.filter((item) => EXPORT_KINDS.includes(item.deliverable_type || item.kind)).map((artifact) => {
                  const kind = artifact.deliverable_type || artifact.kind;
                  return <button key={artifact.reference_sha256 || artifact.id} onClick={() => onOpenArtifact?.({ ...artifact, display_name: estimateArtifactDisplayName(artifact, displayTitle) })} type="button">{kind.toUpperCase()}</button>;
                })}
              </div>
            )}
          </div>
          <EstimateWorkspace onCalculate={onCalculate} onOpenArtifact={onOpenArtifact} onUpdate={onUpdate} payload={canvas} />
        </>
      ) : (
        <>
          {imagePreview && (
            <button className="canvas-image-preview" onClick={() => onOpenArtifact?.(artifacts[0])} type="button">
              <img alt={artifacts[0].name || "Изображение Kolibri"} src={imagePreview} />
              <span>Открыть изображение</span>
            </button>
          )}
          <textarea
            aria-label="Редактор результата"
            className="canvas-manual-editor"
            onChange={(event) => onUpdate({ draftText: event.target.value })}
            placeholder={canvas.status === "running" ? "Kolibri выполняет задачу…" : "Проверенный текст результата появится здесь"}
            readOnly={canvas.status === "running"}
            value={text}
          />
          {!!canvas.task?.artifact_delivery?.missing?.length && <p className="canvas-missing">Не материализовано: {canvas.task.artifact_delivery.missing.join(", ")}</p>}
          {!!artifacts.length && <CanvasArtifacts artifacts={artifacts} estimateTitle={canvas.kind === "estimate" ? displayTitle : ""} onOpen={onOpenArtifact} />}
        </>
      )}
      <WorkSummary summary={canvas.workSummary} />
      {canvas.error && <div className="inline-error">{canvas.error}</div>}
    </section>
  );
}
