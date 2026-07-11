export const RENDERER_REGISTRY = Object.freeze([
  { id: "web-preview", label: "Web preview", kind: "website", icon: "globe", accepts: ["text/html", "application/x-kolibri-preview"], sandbox: "iframe", modes: ["view", "responsive", "inspect"] },
  { id: "pdf", label: "PDF / PDF-X", kind: "pdf", icon: "file", accepts: ["application/pdf", "application/pdf-x"], sandbox: "worker", modes: ["view", "compare", "present"] },
  { id: "xlsx", label: "XLSX", kind: "spreadsheet", icon: "table", accepts: ["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"], sandbox: "worker", modes: ["view", "sheet", "formula"] },
  { id: "docx", label: "DOCX", kind: "document", icon: "file", accepts: ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"], sandbox: "worker", modes: ["view", "outline", "compare"] },
  { id: "image", label: "Image", kind: "image", icon: "image", accepts: ["image/*"], sandbox: "native", modes: ["view", "compare"] },
  { id: "audio", label: "Audio", kind: "audio", icon: "audio", accepts: ["audio/*"], sandbox: "native", modes: ["play", "waveform", "transcript"] },
  { id: "video", label: "Video", kind: "video", icon: "video", accepts: ["video/*"], sandbox: "native", modes: ["play", "timeline"] },
  { id: "code-diff", label: "Code / Diff / PR", kind: "code", icon: "code", accepts: ["text/x-diff", "application/x-kolibri-code"], sandbox: "worker", modes: ["tree", "diff", "review"] },
  { id: "terminal", label: "Terminal / Logs", kind: "terminal", icon: "terminal", accepts: ["text/x-log", "application/x-ndjson"], sandbox: "worker", modes: ["tail", "search", "evidence"] },
  { id: "plan", label: "Task / Plan", kind: "plan", icon: "plan", accepts: ["application/x-kolibri-plan"], sandbox: "native", modes: ["graph", "list", "critical-path"] },
  { id: "estimate", label: "Estimate", kind: "estimate", icon: "estimate", accepts: ["application/x-kolibri-estimate"], sandbox: "native", modes: ["table", "audit", "export"] },
  { id: "automation", label: "Automation", kind: "automation", icon: "automation", accepts: ["application/x-kolibri-automation"], sandbox: "native", modes: ["builder", "history", "replay"] },
]);

export const FALLBACK_RENDERER = Object.freeze({
  id: "download",
  label: "Безопасное скачивание",
  kind: "file",
  icon: "file",
  sandbox: "native",
  modes: ["metadata", "download"],
});

export function rendererForArtifact(artifact = {}) {
  const mime = String(artifact.mime_type || artifact.mimeType || "");
  const kind = String(artifact.kind || artifact.type || "");
  return RENDERER_REGISTRY.find((renderer) => (
    renderer.kind === kind || renderer.accepts.some((accepted) => accepted.endsWith("/*") ? mime.startsWith(accepted.slice(0, -1)) : accepted === mime)
  )) || FALLBACK_RENDERER;
}
