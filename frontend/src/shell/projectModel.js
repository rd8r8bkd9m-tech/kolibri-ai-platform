import {
  buildAppTask,
  buildDocumentTask,
  buildEstimateProposalTask,
  buildImageTask,
  buildSiteTask,
} from "../runtime/kolibriApi";
import { makeId } from "../app/utils";
import { estimateArtifactDisplayName, estimateTitleFromPayload } from "../estimate/estimateTitle";

export function buildTaskForIntent(intent, brief) {
  if (intent === "image") {
    return buildImageTask({ brief });
  }
  if (intent === "estimate") {
    return buildEstimateProposalTask({ brief, requestedArtifacts: ["pdf"] });
  }
  if (intent === "document") {
    return buildDocumentTask({ brief, documentType: "custom", format: "docx", content: {} });
  }
  if (intent === "site") {
    return buildSiteTask({
      brief,
      target: "website",
      requirements: {},
      requestedArtifacts: ["source", "site-preview", "test-report"],
    });
  }
  if (intent === "app") {
    return buildAppTask({
      brief,
      target: "web",
      requirements: {},
      requestedArtifacts: ["source", "build", "test-report", "app-preview"],
    });
  }
  return null;
}

export function mergeArtifacts(current, incoming) {
  const byIdentity = new Map();
  [...(current || []), ...(incoming || [])].filter(isMaterializedArtifact).forEach((item, index) => {
    const key = item.reference_sha256 || item.id || `${item.name || item.kind || "artifact"}:${index}`;
    byIdentity.set(key, item);
  });
  return [...byIdentity.values()];
}

export function isMaterializedArtifact(artifact) {
  return Boolean(artifact && artifact.status === "materialized");
}

export function materializedArtifacts(artifacts) {
  return (Array.isArray(artifacts) ? artifacts : []).filter(isMaterializedArtifact);
}

export function projectWindow(project, maximized = false) {
  return {
    id: `workspace:${project.id}`,
    kind: "workspace",
    title: project.title,
    statusLabel: "Проект",
    projectId: project.id,
    maximized,
  };
}

export function estimateWindow(projectId, title = "Смета: строительные работы") {
  return {
    id: `estimate:${projectId}`,
    kind: "estimate",
    title,
    status: "draft",
    statusLabel: "Черновик",
    parentProjectId: projectId,
  };
}

export function projectMessage(role, text, status, fields = {}) {
  return {
    id: makeId("message"),
    role,
    text,
    ...(status ? { status } : {}),
    ...fields,
    createdAt: new Date().toISOString(),
  };
}

export function projectTitle(project, prompt) {
  return project.messages.length ? project.title : prompt.slice(0, 72);
}

export function estimateCanvas(projectId) {
  return {
    id: `estimate:${projectId}`,
    kind: "estimate",
    title: "Смета: строительные работы",
    status: "draft",
    version: 1,
    metadata: { region: "", provenance: "manual" },
    artifacts: [],
    createdAt: new Date().toISOString(),
  };
}

export function taskCanvas({ id, intent, title, status, text, task, artifacts, endpoint, workSummary }) {
  const estimate = intent === "estimate" ? task?.result?.estimate : null;
  const readiness = intent === "estimate" && task?.result?.type === "estimate_readiness"
    ? task.result.readiness
    : null;
  const displayTitle = intent === "estimate" ? estimateTitleFromPayload({ task }) : title;
  const displayArtifacts = intent === "estimate"
    ? (artifacts || []).map((artifact) => ({ ...artifact, display_name: estimateArtifactDisplayName(artifact, displayTitle) }))
    : artifacts;
  return {
    id: `canvas:${id}`,
    kind: intent,
    title: displayTitle,
    status,
    text,
    task,
    artifacts: displayArtifacts,
    endpoint,
    workSummary,
    ...(estimate ? {
      ...estimate,
      metadata: {
        region: estimate.region || "Не указан",
        provenance: estimate.source_summary || "Цены требуют проверки",
      },
      persistence: task?.persistence || null,
    } : {}),
    ...(readiness ? {
      readiness,
      metadata: {
        region: readiness.known_facts?.region || "Требует подтверждения",
        provenance: "Денежный расчёт заблокирован до проверки источников",
      },
    } : {}),
    version: task?.persistence?.version || 1,
    createdAt: new Date().toISOString(),
  };
}

export function upsertCanvas(current, canvas) {
  const canvases = current || [];
  const index = canvases.findIndex((item) => item.id === canvas.id);
  if (index < 0) return [...canvases, canvas];
  return canvases.map((item) => item.id === canvas.id ? { ...item, ...canvas } : item);
}
