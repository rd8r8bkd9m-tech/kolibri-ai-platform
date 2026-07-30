import { submitEstimateFeedback } from "../runtime/kolibriApi";

export async function recordEstimateRevisionFeedback(spec, task) {
  if (!spec.estimate_id || !task?.persistence?.version) return;
  try {
    await submitEstimateFeedback({
      estimateId: spec.estimate_id,
      baseVersion: task.persistence.version,
      action: "correct",
      reason: "Владелец сохранил новую редакцию сметы.",
      corrections: {
        previous_version: spec.estimate_base_version,
        current_version: task.persistence.version,
        correction_kind: "owner_editor_revision",
      },
    });
  } catch {
    // FormulaLM feedback is fail-isolated from the saved estimate revision.
  }
}
