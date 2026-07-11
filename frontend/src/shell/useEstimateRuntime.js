import { useCallback } from "react";
import { buildDeterministicEstimateTask, sendKolibriRequest } from "../runtime/kolibriApi";
import { mergeArtifacts, projectMessage } from "./projectModel";

function patchCanvas(canvases, canvasId, patch) {
  return (canvases || []).map((canvas) => canvas.id === canvasId ? { ...canvas, ...patch } : canvas);
}

export function useEstimateRuntime({ setProjectBusy, updateProject }) {
  return useCallback(async (projectId, canvasId, spec, executionMode = "fast") => {
    updateProject(projectId, (current) => ({
      ...current,
      canvases: patchCanvas(current.canvases, canvasId, { title: spec.title, status: "running", error: "" }),
    }));
    setProjectBusy(projectId, true);
    try {
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
        requestedArtifacts: ["pdf"],
      });
      const response = await sendKolibriRequest({
        text: `Обнови и проверь смету «${spec.title}».`,
        task,
        workstreamId: projectId,
        executionMode,
        metadata: spec.estimate_id ? {
          estimate_id: spec.estimate_id,
          estimate_base_version: spec.estimate_base_version,
        } : {},
      });
      const status = response.task?.status || "failed";
      const estimate = response.task?.result?.estimate;
      updateProject(projectId, (current) => ({
        ...current,
        canvases: (current.canvases || []).map((canvas) => canvas.id === canvasId ? {
          ...canvas,
          ...(estimate || spec),
          title: estimate?.title || spec.title,
          status,
          task: response.task,
          text: response.text,
          endpoint: response.endpoint,
          artifacts: response.artifacts,
          persistence: response.task?.persistence || canvas.persistence || null,
          metadata: {
            region: estimate?.region || spec.region || "Не указан",
            provenance: estimate?.source_summary || spec.source_summary || "Цены требуют проверки",
          },
          version: response.task?.persistence?.version || canvas.version || 1,
        } : canvas),
        messages: [...current.messages, projectMessage("assistant", response.text || `Смета «${spec.title}» рассчитана.`, status, { canvasId })],
        artifacts: mergeArtifacts(current.artifacts, response.artifacts),
      }));
    } catch (error) {
      updateProject(projectId, (current) => ({
        ...current,
        canvases: patchCanvas(current.canvases, canvasId, {
          status: "failed",
          error: error?.message || "Не удалось рассчитать смету",
        }),
      }));
    } finally {
      setProjectBusy(projectId, false);
    }
  }, [setProjectBusy, updateProject]);
}
