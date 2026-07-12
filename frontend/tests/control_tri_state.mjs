import assert from "node:assert/strict";

import { buildControlView } from "../src/control/controlViewModel.js";

const loading = buildControlView(null, "loading");
assert.equal(loading.state, "loading");
assert.ok(loading.metrics.every((metric) => metric.value === "…" && metric.state === "loading"));

const unavailable = buildControlView(null, "unavailable");
assert.equal(unavailable.state, "unavailable");
assert.ok(unavailable.metrics.every((metric) => metric.value === "Нет данных"));
assert.ok(unavailable.metrics.every((metric) => metric.value !== 0));

const liveZero = buildControlView({
  status: {
    available: true,
    value: { online_nodes: 0, total_nodes: 0, queue_size: 0, control_plane: { status: "ok" } },
  },
  tasks: { available: true, value: [] },
  nodes: { available: true, value: [] },
}, "ready");
assert.deepEqual(liveZero.metrics.map((metric) => metric.value), [0, 0, 0, "Home"]);
assert.ok(liveZero.metrics.every((metric) => metric.state === "live"));
assert.equal(liveZero.tasksMessage, "Подтверждённых задач в списке нет.");

const partial = buildControlView({
  status: { available: false, value: null },
  tasks: {
    available: true,
    value: [
      { state: "queued" },
      { state: "running" },
      { state: "completed" },
    ],
  },
  nodes: {
    available: true,
    value: [{ status: "online" }, { status: "offline" }, { status: "stale" }],
  },
}, "ready");
assert.equal(partial.metrics.find((metric) => metric.label === "Узлы online").value, 1);
assert.equal(partial.metrics.find((metric) => metric.label === "В очереди").value, 1);
assert.equal(partial.metrics.find((metric) => metric.label === "В работе").value, 1);
assert.equal(partial.metrics.find((metric) => metric.label === "Control Plane").value, "Нет данных");

const noNodeEvidence = buildControlView({
  nodes: { available: true, value: [{ id: "node-without-status" }] },
}, "ready");
assert.equal(noNodeEvidence.metrics[0].state, "unavailable");
assert.equal(noNodeEvidence.metrics[0].value, "Нет данных");

const unknownStates = buildControlView({
  status: { available: true, value: { control_plane: { status: "mystery" } } },
  tasks: { available: true, value: [{ state: "mystery" }] },
}, "ready");
assert.equal(unknownStates.metrics.find((metric) => metric.label === "В очереди").value, "Нет данных");
assert.equal(unknownStates.metrics.find((metric) => metric.label === "В работе").value, "Нет данных");
assert.equal(unknownStates.metrics.find((metric) => metric.label === "Control Plane").value, "Нет данных");

const explicitDegraded = buildControlView({
  status: { available: true, value: { control_plane: { status: "degraded" } } },
}, "ready");
assert.equal(explicitDegraded.metrics.find((metric) => metric.label === "Control Plane").value, "Degraded");

console.log("Kolibri Control loading, live, partial, zero, and unavailable metric contracts passed");
