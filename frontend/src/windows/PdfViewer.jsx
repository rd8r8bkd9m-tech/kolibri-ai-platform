import { Download, FileWarning } from "lucide-react";
import { API_BASE } from "../runtime/kolibriApi";

const PDF_LOCATOR = /^\/v1\/public\/estimate-artifacts\/[A-Za-z0-9._:-]+\/content$/;

function pdfUrl(locator) {
  return typeof locator === "string" && PDF_LOCATOR.test(locator)
    ? `${API_BASE}${locator}`
    : "";
}

export function PdfViewer({ artifact }) {
  const url = pdfUrl(artifact?.locator);
  if (!url) {
    return (
      <div className="system-empty">
        <FileWarning size={28} />
        <h2>PDF недоступен</h2>
        <p>Просмотр открывается только для проверенного same-origin артефакта.</p>
      </div>
    );
  }
  return (
    <section className="pdf-viewer">
      <header>
        <span>
          <strong>{artifact.name || "Смета.pdf"}</strong>
          <small>PDF · версия {artifact.estimate_version || 1} · проверенный файл</small>
        </span>
        <a href={`${url}?download=true`} rel="noreferrer">
          <Download size={16} /> Скачать
        </a>
      </header>
      <iframe src={url} title={`Просмотр ${artifact.name || "сметы PDF"}`} />
    </section>
  );
}
