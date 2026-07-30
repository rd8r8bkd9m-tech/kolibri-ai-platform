import { useCallback } from "react";
import { buildDeterministicEstimateTask, publicErrorMessage, sendKolibriRequest } from "../runtime/kolibriApi";
import { recordEstimateRevisionFeedback } from "./estimateFeedback";
import { mergeArtifacts, projectMessage } from "./projectModel";
import { estimateArtifactDisplayName, estimateTitleFromPayload } from "../estimate/estimateTitle";
function patchCanvas(canvases, canvasId, patch) {
  return (canvases || []).map((canvas) => canvas.id === canvasId ? { ...canvas, ...patch } : canvas);
}

export function useEstimateRuntime({ beginProjectRequest, endProjectRequest, ensureProjectRemote, syncProjectMessage, updateProject }) {
  return useCallback(async (projectId, canvasId, spec, executionMode = "fast") => {
    const pendingTitle = estimateTitleFromPayload(spec);
    updateProject(projectId, (current) => ({
      ...current,
      canvases: patchCanvas(current.canvases, canvasId, { title: pendingTitle, status: "running", error: "" }),
    }));
    const request = beginProjectRequest(projectId);
    try {
      const remoteProjectId = await ensureProjectRemote(projectId, request.signal);
      const task = buildDeterministicEstimateTask({
        title: spec.title,
        currency: spec.currency,
        minorUnit: spec.minor_unit,
        region: spec.region,
        clientName: spec.client_name,
        objectName: spec.object_name,
        objectAddress: spec.object_address,
        sourceSummary: spec.source_summary,
        assumptions: spec.assumptions,
        questions: spec.questions,
        lines: spec.lines.map((line) => ({ ...line, unitPriceMinor: line.unit_price_minor })),
        overheadRateBps: spec.overhead_rate_bps,
        taxRateBps: spec.tax_rate_bps,
        normativeBasis: spec.normative_basis,
        requestedArtifacts: ["pdf"],
      });
      const response = await sendKolibriRequest({
        text: `Обнови и проверь смету «${spec.title}».`,
        task,
        projectId: remoteProjectId,
        workstreamId: projectId,
        executionMode,
        signal: request.signal,
        metadata: spec.estimate_id ? {
          estimate_id: spec.estimate_id,
          estimate_base_version: spec.estimate_base_version,
        } : {},
      });
      const verifiedText = String(response.text || "").trim();
      if (!verifiedText) throw new Error("Проверенный текст сметы не получен.");
      const status = response.task?.status || "failed";
      const estimate = response.task?.result?.estimate;
      const readiness = response.task?.result?.type === "estimate_readiness" ? response.task.result.readiness : null;
      const displayTitle = estimateTitleFromPayload({ task: response.task, metadata: { region: spec.region }, object_name: spec.object_name });
      const displayArtifacts = (response.artifacts || []).map((artifact) => ({ ...artifact, display_name: estimateArtifactDisplayName(artifact, displayTitle) }));
      await recordEstimateRevisionFeedback(spec, response.task);
      const resultMessage = projectMessage("assistant", verifiedText, status, { canvasId, responseId: response.taskId, updatedAt: new Date().toISOString() });
      updateProject(projectId, (current) => ({
        ...current,
        canvases: (current.canvases || []).map((canvas) => canvas.id === canvasId ? {
          ...canvas,
          ...(readiness ? { readiness } : (estimate || spec)),
          title: displayTitle,
          status,
          task: response.task,
          text: response.text,
          endpoint: response.endpoint,
          artifacts: displayArtifacts,
          persistence: readiness ? null : response.task?.persistence || canvas.persistence || null,
          metadata: {
            region: estimate?.region || readiness?.known_facts?.region || spec.region || "Не указан",
            provenance: estimate?.source_summary || (readiness ? "Денежный расчёт заблокирован до проверки источников" : spec.source_summary) || "Цены требуют проверки",
          },
          version: response.task?.persistence?.version || canvas.version || 1,
        } : canvas),
        messages: [...current.messages, resultMessage],
        artifacts: mergeArtifacts(current.artifacts, displayArtifacts),
      }));
      await syncProjectMessage(projectId, resultMessage, { responseId: response.taskId, signal: request.signal }).catch(() => null);
    } catch (error) {
      updateProject(projectId, (current) => ({
        ...current,
        canvases: patchCanvas(current.canvases, canvasId, { status: "failed", error: publicErrorMessage(error) }),
      }));
    } finally {
      endProjectRequest(projectId, request.token);
    }
  }, [beginProjectRequest, endProjectRequest, ensureProjectRemote, syncProjectMessage, updateProject]);
}
