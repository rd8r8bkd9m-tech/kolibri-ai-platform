import assert from "node:assert/strict";
import { TOOLS } from "../src/app/constants.js";
import { availableTools } from "../src/app/toolAvailability.js";

assert.deepEqual(
  availableTools([]),
  [],
  "catalog presence alone must never expose a composer or Dock action",
);

const serverProjection = [
  {
    id: "estimate",
    object: "product.capability",
    surface: "tool",
    status: "available",
    available: true,
  },
  {
    id: "image",
    object: "product.capability",
    surface: "tool",
    status: "unavailable",
    available: false,
    reason_codes: ["renderer_not_ready"],
  },
  {
    id: "site",
    object: "product.capability",
    surface: "tool",
    status: "available",
    available: false,
  },
  {
    id: "app",
    object: "product.capability",
    surface: "core",
    status: "available",
    available: true,
  },
];

assert.deepEqual(
  availableTools(serverProjection).map((tool) => tool.id),
  ["estimate"],
  "only a server-confirmed available tool surface may be shown",
);

assert.ok(!availableTools(serverProjection).some((tool) => tool.id === "image"), "provider prose cannot promote image generation");

console.log("Kolibri server-derived public tool availability gates passed");
