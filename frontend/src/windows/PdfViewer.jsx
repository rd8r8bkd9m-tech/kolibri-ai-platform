import { Download, FileWarning } from "lucide-react";
import { API_BASE } from "../runtime/kolibriApi";

const PDF_LOCATOR = /^\/v1\/public\/estimate-artifacts\/[A-Za-z0-9._:-]+\/content$/;

function pdfUrl(locator) {
  return typeof locator === "string" && PDF_LOCATOR.test(locator)
    ? `${API_BASE}${locator}`
    : "";
}

function fileSize(bytes) {
  if (!Number.isSafeInteger(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} Б`;
  return `${(bytes / 1024).toFixed(bytes < 1024 * 100 ? 1 : 0)} КБ`;
}

export function PdfViewer({ artifact }) {
  const url = artifact?.status === "materialized" ? pdfUrl(artifact.locator) : "";
  if (!url) {
    return (
      <div className="system-empty">
        <FileWarning size={28} />
        <h2>PDF недоступен</h2>
        <p>Просмотр открывается только для проверенного same-origin артефакта.</p>
      </div>
    );
  }
  const readinessChecklist = artifact.document_role === "estimate_input_checklist";
  const displayName = artifact.display_name || artifact.name || "Смета.pdf";
  const evidence = [
    `версия ${artifact.estimate_version || 1}`,
    fileSize(artifact.size_bytes),
    readinessChecklist ? "чеклист исходных данных" : "неизменяемый снимок с источниками",
  ].filter(Boolean).join(" · ");
  return (
    <section className="pdf-viewer">
      <header>
        <span>
          <strong>{displayName}</strong>
          <small title={artifact.content_sha256 || ""}>PDF · {evidence}</small>
        </span>
        <a href={`${url}?download=true`} rel="noreferrer">
          <Download size={16} /> Скачать
        </a>
      </header>
      <iframe loading="eager" src={url} title={`Просмотр ${displayName}`} />
    </section>
  );
}
