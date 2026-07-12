import { eventFromWire, responseFromWire, sessionFromWire } from "@services/safeWire";
import { describe, expect, it } from "vitest";

describe("public Edge wire normalization", () => {
  it("accepts the real PublicSession bootstrap shape", () => {
    expect(sessionFromWire({
      id: "session_123",
      object: "public.session",
      active: true,
      model: "kolibri",
      current_project_id: "project_123",
    })).toEqual({ id: "session_123", currentProjectId: "project_123" });
  });

  it("accepts the real public response and named SSE payload", () => {
    expect(responseFromWire({
      id: "resp_123",
      object: "response",
      model: "kolibri",
      status: "running",
      last_sequence: 3,
    })).toMatchObject({ id: "resp_123", status: "running", lastSequence: 3 });
    expect(eventFromWire("response.output_text.delta", {
      type: "response.output_text.delta",
      sequence: 4,
      delta: "Готово",
    })).toEqual({ kind: "text.delta", sequence: 4, delta: "Готово" });
  });

  it("rejects event-name/payload mismatches", () => {
    expect(() => eventFromWire("response.completed", {
      type: "response.safe_stage",
      sequence: 1,
    })).toThrow(/Mismatched/);
  });
});
